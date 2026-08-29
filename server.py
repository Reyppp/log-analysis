from __future__ import annotations

import json
import logging
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
from plotly.offline import get_plotlyjs

from analyzer import AnalysisError, analyze_folder, csv_bytes, detect_anomalies, load_layer_detail, source_fingerprint
from version import APP_NAME, APP_VERSION, BUILD_CHANNEL


SOURCE_ROOT = Path(__file__).resolve().parent
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))
LEGACY_LAST_FOLDER = SOURCE_ROOT / ".last_folder.txt"
STATE: dict[str, object] = {
    "path": "",
    "result": None,
    "fingerprint": None,
    "progress": {"status": "idle", "phase": "", "current": 0, "total": 0, "elapsed": 0.0},
}
FOLDER_DIALOG_LOCK = threading.Lock()
ANALYSIS_LOCK = threading.Lock()
LOGGER = logging.getLogger(__name__)


class FolderDialogError(RuntimeError):
    pass


def frame_records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def monitor_summary(result) -> pd.DataFrame:
    frame = result.layer_summary.copy()
    for suffix in ("mean", "std", "min", "max", "range"):
        reference = f"monitor_motor_{suffix}"
        if reference in frame:
            frame[f"motor_{suffix}"] = frame[reference]
    if "motor_source" in frame:
        frame["motor_source"] = "监控log参考值"
    return frame


def export_frame(result, kind: str, threshold: float = 3.5) -> tuple[pd.DataFrame, str]:
    monitor = monitor_summary(result)
    if kind in {"summary", "monitor_summary"}:
        return monitor, "layer_summary.csv"
    if kind in {"anomalies", "monitor_anomalies"}:
        return detect_anomalies(monitor, threshold), "anomalies.csv"
    raise AnalysisError(f"不支持的导出类型：{kind}")


def _local_log_timestamp(value: str) -> pd.Timestamp:
    timestamp = pd.to_datetime(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(datetime.now().astimezone().tzinfo).tz_localize(None)
    return timestamp


def machine_series(result, metrics: list[str], session: str = "", start: str = "", end: str = "", max_points: int = 2500) -> dict:
    frame = result.machine_data
    if frame.empty:
        raise AnalysisError("当前分析结果不包含工控log")
    available = set(result.machine_summary.get("available_metrics", []))
    metrics = [metric for metric in metrics if metric in available]
    if not metrics:
        raise AnalysisError("请选择有效的工控指标")
    selected = frame
    if start:
        selected = selected[selected["_time"].ge(_local_log_timestamp(start))]
    if end:
        selected = selected[selected["_time"].le(_local_log_timestamp(end))]
    if not start and not end and session != "all":
        session_id = int(session or result.machine_summary.get("default_session_id") or 0)
        sessions = result.machine_sessions[result.machine_sessions["session_id"].eq(session_id)]
        if not sessions.empty:
            current = sessions.iloc[0]
            selected = selected[selected["_time"].between(current["start"], current["end"])]
    selected = selected.reset_index(drop=True)
    original_rows = len(selected)
    max_points = max(200, min(int(max_points), 8000))
    if len(selected) > max_points:
        bucket_count = max(1, max_points // max(4, len(metrics) * 2 + 2))
        buckets = pd.Series((pd.RangeIndex(len(selected)) * bucket_count // len(selected)).astype(int), index=selected.index)
        keep = {0, len(selected) - 1}
        grouped = selected.groupby(buckets)
        keep.update(grouped.head(1).index.tolist())
        keep.update(grouped.tail(1).index.tolist())
        for metric in metrics:
            numeric = pd.to_numeric(selected[metric], errors="coerce")
            keep.update(numeric.groupby(buckets).idxmin().dropna().astype(int).tolist())
            keep.update(numeric.groupby(buckets).idxmax().dropna().astype(int).tolist())
        selected = selected.iloc[sorted(keep)]
    return {
        "time": selected["_time"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist(),
        "series": {
            metric: pd.to_numeric(selected[metric], errors="coerce").astype(object).where(lambda values: values.notna(), None).tolist()
            for metric in metrics
        },
        "rows": original_rows,
        "returned": len(selected),
    }


DEVICE_TIME_METRICS = {
    "power_mean": ("active", "Power"),
    "current_mean": ("active", "Current"),
    "voltage_mean": ("active", "Voltage"),
    "vacuum_mean": ("columns", ["Chammber Vacuum"]),
    "pipe_vacuum": ("columns", ["Pipe Vacuum"]),
    "chamber_temp_mean": ("columns", ["Chammber Temperture"]),
    "water_in_mean": ("columns", ["Water-In"]),
    "water_out_mean": ("columns", ["Water-Out"]),
    "motor_mean": ("columns", ["Motor Speed"]),
    "o2_mean": ("columns", ["Gas-O2(1)", "Gas-O2(4)"]),
    "ar_mean": ("columns", ["Gas-Ar(2)", "Gas-Ar(3)"]),
    "gas": ("columns", ["Gas-O2(1)", "Gas-O2(4)", "Gas-Ar(2)", "Gas-Ar(3)"]),
}
DEVICE_TIME_ALIASES = {
    "power": "power_mean", "current": "current_mean", "voltage": "voltage_mean",
    "Chammber Vacuum": "vacuum_mean", "Pipe Vacuum": "pipe_vacuum",
    "Chammber Temperture": "chamber_temp_mean", "Water-In": "water_in_mean",
    "Water-Out": "water_out_mean", "Motor Speed": "motor_mean",
}


def _device_values(frame: pd.DataFrame, metric: str, materials: list[str] | None = None) -> dict[str, pd.Series]:
    metric = DEVICE_TIME_ALIASES.get(metric, metric)
    kind, specification = DEVICE_TIME_METRICS.get(metric, (None, None))
    if kind == "active":
        h_column, l_column = f"H {specification}", f"L {specification}"
        if h_column not in frame or l_column not in frame:
            return {}
        material = frame["material"]
        selected = set(materials or [])
        if "H" in selected and "L" not in selected:
            values = frame[h_column]
        elif "L" in selected and "H" not in selected:
            values = frame[l_column]
        else:
            values = frame[h_column].where(material.eq("H"), frame[l_column].where(material.eq("L")))
            combined = frame[h_column].fillna(0) + frame[l_column].fillna(0)
            values = values.where(~(material.eq("H+L") | material.isna()), combined)
        return {metric: pd.to_numeric(values, errors="coerce")}
    if kind == "columns":
        return {
            column: pd.to_numeric(frame[column], errors="coerce")
            for column in specification if column in frame
        }
    raise AnalysisError("请选择有效的设备指标")


def _device_keep(frame: pd.DataFrame, values: dict[str, pd.Series], max_points: int) -> list[int]:
    if len(frame) <= max_points:
        return list(range(len(frame)))
    layers = frame["layer"].fillna(-1)
    layer_changes = layers.ne(layers.shift(fill_value=-1))
    block_changes = frame["_block"].ne(frame["_block"].shift())
    boundary_positions = set(frame.index[layer_changes | block_changes].tolist())
    boundary_positions.update(max(0, index - 1) for index in list(boundary_positions))
    bucket_width = max(2, len(values) * 2 + 2)
    bucket_count = max(1, (max_points - len(boundary_positions)) // bucket_width)
    buckets = pd.Series((pd.RangeIndex(len(frame)) * bucket_count // len(frame)).astype(int), index=frame.index)
    keep = {0, len(frame) - 1, *boundary_positions}
    grouped = frame.groupby(buckets)
    keep.update(grouped.head(1).index.tolist())
    keep.update(grouped.tail(1).index.tolist())
    for series in values.values():
        keep.update(series.groupby(buckets).idxmin().dropna().astype(int).tolist())
        keep.update(series.groupby(buckets).idxmax().dropna().astype(int).tolist())
    ordered = sorted(keep)
    if len(ordered) < min(max_points, len(frame)):
        candidates = [position for position in range(len(frame)) if position not in keep]
        budget = min(max_points - len(ordered), len(candidates))
        if budget == 1:
            keep.add(candidates[len(candidates) // 2])
        elif budget > 1:
            keep.update(candidates[round(index * (len(candidates) - 1) / (budget - 1))] for index in range(budget))
        ordered = sorted(keep)
    if len(ordered) <= max_points:
        return ordered
    essential = {0, len(frame) - 1}
    for series in values.values():
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().any():
            essential.update([int(numeric.idxmin()), int(numeric.idxmax())])
    candidates = [position for position in ordered if position not in essential]
    budget = max(0, max_points - len(essential))
    if budget and candidates:
        if budget == 1:
            essential.add(candidates[len(candidates) // 2])
        else:
            essential.update(candidates[round(index * (len(candidates) - 1) / (budget - 1))] for index in range(budget))
    return sorted(essential)


def _device_marker_count(
    frame: pd.DataFrame, values: dict[str, pd.Series], split_by_material: bool, materials: list[str],
) -> int:
    if not split_by_material:
        return sum(int(pd.to_numeric(value, errors="coerce").notna().sum()) for value in values.values())
    selected = set(materials)
    material = frame["material"].fillna("").astype(str)
    multiplier = material.map(
        lambda value: sum(item in selected for item in ("H", "L"))
        if value == "H+L" else int(value in selected)
    )
    return sum(int((pd.to_numeric(value, errors="coerce").notna().astype(int) * multiplier).sum()) for value in values.values())


def _device_trace(frame: pd.DataFrame, values: pd.Series, source: str, channel: str) -> dict:
    changes = frame["_block"].ne(frame["_block"].shift()).tolist()

    def separated(items: list) -> list:
        output = []
        for position, item in enumerate(items):
            if position and changes[position]:
                output.append(None)
            output.append(item)
        return output

    numeric = pd.to_numeric(values, errors="coerce")
    display_start = frame["_display_start"] if "_display_start" in frame else frame["_display_time"]
    display_end = frame["_display_end"] if "_display_end" in frame else frame["_display_time"]
    result = {
        "time": separated(frame["_display_time"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()),
        "start_time": separated(display_start.dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()),
        "end_time": separated(display_end.dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()),
        "source_time": separated(frame["_source_time"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()),
        "value": separated([None if pd.isna(value) else float(value) for value in numeric]),
        "layer": separated([None if pd.isna(value) else int(value) for value in frame["layer"]]),
        "material": separated([None if pd.isna(value) else str(value) for value in frame["material"]]),
        "method": separated([None if pd.isna(value) else str(value) for value in frame["method"]]),
    }
    return {"source": source, "channel": channel, **result}


def _device_mean_points(
    frame: pd.DataFrame, values: dict[str, pd.Series],
) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    selected = frame[frame["layer"].notna()].copy()
    if selected.empty:
        return selected, {channel: pd.Series(dtype=float) for channel in values}
    rows: list[dict] = []
    means = {channel: [] for channel in values}
    for _, group in selected.groupby("layer", sort=True):
        display_start, display_end = group["_display_time"].min(), group["_display_time"].max()
        source_start, source_end = group["_source_time"].min(), group["_source_time"].max()
        rows.append(
            {
                "_display_time": display_start + (display_end - display_start) / 2,
                "_display_start": display_start,
                "_display_end": display_end,
                "_source_time": source_start + (source_end - source_start) / 2,
                "layer": group["layer"].iloc[0],
                "material": group["material"].dropna().iloc[0] if group["material"].notna().any() else pd.NA,
                "method": group["method"].dropna().iloc[0] if group["method"].notna().any() else pd.NA,
                "_block": len(rows),
            }
        )
        for channel, series in values.items():
            means[channel].append(pd.to_numeric(series.loc[group.index], errors="coerce").mean())
    return pd.DataFrame(rows), {channel: pd.Series(channel_means, dtype=float) for channel, channel_means in means.items()}


def _machine_activity(frame: pd.DataFrame) -> pd.Series:
    h_power = frame["H Power"] if "H Power" in frame else pd.Series(0, index=frame.index)
    l_power = frame["L Power"] if "L Power" in frame else pd.Series(0, index=frame.index)
    h_active = pd.to_numeric(h_power, errors="coerce").fillna(0).gt(0.1)
    l_active = pd.to_numeric(l_power, errors="coerce").fillna(0).gt(0.1)
    state = pd.Series("idle", index=frame.index, dtype=object)
    state.loc[h_active & ~l_active] = "H"
    state.loc[l_active & ~h_active] = "L"
    state.loc[h_active & l_active] = "H+L"
    return state


def _machine_material_mask(state: pd.Series, materials: list[str]) -> pd.Series:
    selected = set(materials)
    if {"H", "L"}.issubset(selected):
        return pd.Series(True, index=state.index)
    if selected == {"H+L"}:
        return state.eq("H+L")
    if "H" in selected and "L" not in selected:
        return state.isin(["H", "H+L"])
    if "L" in selected and "H" not in selected:
        return state.isin(["L", "H+L"])
    return state.isin(selected)


def _machine_hidden_mask(state: pd.Series, materials: list[str]) -> pd.Series:
    selected = set(materials)
    if {"H", "L"}.issubset(selected):
        return pd.Series(False, index=state.index)
    if selected == {"H+L"}:
        return state.ne("H+L")
    if "H" in selected and "L" not in selected:
        return ~state.isin(["H", "H+L"])
    if "L" in selected and "H" not in selected:
        return ~state.isin(["L", "H+L"])
    return pd.Series(False, index=state.index)


def _device_iso(value: pd.Timestamp | None) -> str | None:
    return None if value is None or pd.isna(value) else value.strftime("%Y-%m-%dT%H:%M:%S")


def _machine_time_breaks(frame: pd.DataFrame, materials: list[str], cadence: float) -> list[dict[str, str]]:
    if frame.empty:
        return []
    ordered = frame.sort_values("_time").copy()
    state = _machine_activity(ordered)
    hidden = _machine_hidden_mask(state, materials)
    times = ordered["_time"]
    if cadence <= 0:
        deltas = times.diff().dt.total_seconds().dropna()
        cadence = float(deltas[deltas.gt(0)].median()) if not deltas.empty else 1.0
    cadence = max(cadence, 0.001)
    threshold = cadence * 1.5
    gap_before = times.diff().dt.total_seconds().gt(threshold)
    gap_after = times.shift(-1).sub(times).dt.total_seconds().gt(threshold)
    starts = hidden & (~hidden.shift(fill_value=False) | gap_before)
    ends = hidden & (~hidden.shift(-1, fill_value=False) | gap_after)
    next_times = times.shift(-1)
    fallback_ends = times + pd.to_timedelta(cadence, unit="s")
    interval_ends = next_times.where(next_times.notna() & ~gap_after, fallback_ends)
    intervals = list(zip(times[starts].tolist(), interval_ends[ends].tolist()))
    merged: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return [{"start": _device_iso(start), "end": _device_iso(end)} for start, end in merged]


def device_time_series(
    result, metric: str, sources: list[str], layer_min: int | None = None, layer_max: int | None = None,
    materials: list[str] | None = None, methods: list[str] | None = None, session: str = "",
    max_points: int = 2500, start: str = "", end: str = "", detail: str = "overview",
) -> dict:
    sources = [source for source in sources if source in {"machine", "monitor"}]
    if not sources:
        raise AnalysisError("请选择有效的数据源")
    if "monitor" in sources and result.alignment.get("status") != "matched":
        raise AnalysisError("双日志未成功关联，无法按时间对照原始数据")
    materials = materials or ["H", "L"]
    methods = methods or []
    detail = str(detail or "overview").lower()
    if detail not in {"overview", "mean", "full"}:
        raise AnalysisError("detail 只能是 overview、mean 或 full")
    start_time = _local_log_timestamp(start) if start else None
    end_time = _local_log_timestamp(end) if end else None
    max_points = max(200, min(int(max_points), 8000))
    limit_per_source = max_points
    limit_total = max_points
    traces: list[dict] = []
    counts: dict[str, int] = {}
    coverage: dict[str, dict[str, str | int | None]] = {}
    boundary_rows: list[pd.DataFrame] = []
    prepared: list[tuple[str, pd.DataFrame, dict[str, pd.Series]]] = []
    aligned_to_monitor = "monitor" in sources and result.alignment.get("status") == "matched"
    time_offset = float(result.alignment.get("time_offset_seconds") or 0)
    split_by_material = metric not in {"o2_mean", "ar_mean", "gas"}
    machine_raw = result.machine_data
    machine_scope = machine_raw.copy()
    if not machine_scope.empty:
        if session != "all":
            session_id = int(session or (getattr(result, "machine_summary", {}) or {}).get("default_session_id") or 0)
            sessions = getattr(result, "machine_sessions", pd.DataFrame())
            sessions = sessions[sessions["session_id"].eq(session_id)] if not sessions.empty else sessions
            if not sessions.empty:
                current = sessions.iloc[0]
                machine_scope = machine_scope[machine_scope["_time"].between(current["start"], current["end"])]
        assignment_filter = pd.Series(True, index=machine_scope.index)
        if layer_min is not None and "layer" in machine_scope:
            assignment_filter &= machine_scope["layer"].ge(layer_min)
        if layer_max is not None and "layer" in machine_scope:
            assignment_filter &= machine_scope["layer"].le(layer_max)
        if methods and "method" in machine_scope:
            assignment_filter &= machine_scope["method"].isin(methods)
        if layer_min is not None or layer_max is not None or methods:
            assigned = machine_scope[assignment_filter]
            if assigned.empty:
                machine_scope = machine_scope.iloc[0:0]
            else:
                machine_scope = machine_scope[machine_scope["_time"].between(assigned["_time"].min(), assigned["_time"].max())]
    machine_summary = getattr(result, "machine_summary", {}) or {}
    cadence = float(machine_summary.get("cadence_seconds") or 0)
    time_breaks = _machine_time_breaks(machine_scope, materials, cadence)
    if aligned_to_monitor and time_offset:
        delta = pd.to_timedelta(-time_offset, unit="s")
        time_breaks = [
            {
                "start": _device_iso(pd.Timestamp(item["start"]) + delta),
                "end": _device_iso(pd.Timestamp(item["end"]) + delta),
            }
            for item in time_breaks
        ]
    for source in sources:
        raw = machine_scope if source == "machine" else result.monitor_device_data
        counts[source] = 0
        coverage[source] = {"start": None, "end": None, "rows": 0}
        if raw.empty:
            continue
        selected = raw.copy()
        selected["_source_time"] = pd.to_datetime(selected.get("_source_time", selected["_time"]))
        offset = -time_offset if aligned_to_monitor and source == "machine" else 0.0
        selected["_display_time"] = selected["_source_time"] + pd.to_timedelta(offset, unit="s")
        if start_time:
            selected = selected[selected["_display_time"].ge(start_time)]
        if end_time:
            selected = selected[selected["_display_time"].le(end_time)]
        if source == "machine":
            state = _machine_activity(selected)
            assignment_filter = pd.Series(True, index=selected.index)
            if layer_min is not None and "layer" in selected:
                assignment_filter &= selected["layer"].ge(layer_min)
            if layer_max is not None and "layer" in selected:
                assignment_filter &= selected["layer"].le(layer_max)
            if methods and "method" in selected:
                assignment_filter &= selected["method"].isin(methods)
            material_mask = _machine_material_mask(state, materials)
            if {"H", "L"}.issubset(set(materials)):
                selected = selected[material_mask & (assignment_filter | state.eq("idle"))].copy()
            else:
                selected = selected[material_mask & assignment_filter].copy()
            selected["material"] = state.loc[selected.index].replace("idle", pd.NA)
        else:
            selected = selected[selected["material"].isin(materials)]
            if layer_min is not None and "layer" in selected:
                selected = selected[selected["layer"].ge(layer_min)]
            if layer_max is not None and "layer" in selected:
                selected = selected[selected["layer"].le(layer_max)]
            if methods and "method" in selected:
                selected = selected[selected["method"].isin(methods)]
        if split_by_material:
            selected = selected[selected["material"].notna()]
        selected = selected.sort_values("_source_time")
        if selected.empty:
            continue
        counts[source] = len(selected)
        coverage[source] = {
            "start": _device_iso(selected["_display_time"].iloc[0]),
            "end": _device_iso(selected["_display_time"].iloc[-1]),
            "rows": len(selected),
        }
        source_cadence = cadence
        if source_cadence <= 0:
            deltas = selected["_source_time"].diff().dt.total_seconds().dropna()
            source_cadence = float(deltas[deltas.gt(0)].median()) if not deltas.empty else 1.0
        gap_limit = max(source_cadence * 1.5, 1.0)
        display_times = selected["_display_time"]
        break_changes = display_times.diff().dt.total_seconds().gt(gap_limit)
        material_values = selected["material"].fillna("__idle__")
        selected["_block"] = (
            selected.index.to_series().diff().ne(1)
            | selected["layer"].fillna(-1).ne(selected["layer"].fillna(-1).shift(fill_value=-1))
            | material_values.ne(material_values.shift())
            | break_changes
        ).cumsum().to_numpy()
        values = _device_values(selected, metric, materials)
        if not values:
            continue
        prepared.append((source, selected, values))
    raw_points = {source: _device_marker_count(frame, values, split_by_material, materials) for source, frame, values in prepared}
    total_points = sum(raw_points.values())
    total_within_limit = total_points <= limit_total
    source_full_available = {
        source: raw_points.get(source, 0) <= limit_per_source and total_within_limit for source in sources
    }
    full_available = all(source_full_available.values())
    full_unavailable_reason = None
    if detail == "full" and not full_available:
        full_unavailable_reason = f"当前范围共 {total_points:,} 个数据点，超过 {limit_total:,} 点上限。"
    for source in sources:
        coverage[source]["coverage"] = (
            "mean" if detail == "mean" else "full" if detail == "full" and full_available else "overview"
        )
        coverage[source]["full_available"] = source_full_available[source]
    marker_budgets: dict[str, int] = {}
    if total_points > max_points:
        remaining_sources = raw_points.copy()
        remaining_budget = max_points
        while remaining_sources:
            fair_share = remaining_budget / len(remaining_sources)
            small_sources = [source for source, count in remaining_sources.items() if count <= fair_share]
            if not small_sources:
                break
            for source in small_sources:
                marker_budgets[source] = remaining_sources.pop(source)
                remaining_budget -= marker_budgets[source]
        if remaining_sources:
            share, extra = divmod(remaining_budget, len(remaining_sources))
            for index, source in enumerate(remaining_sources):
                marker_budgets[source] = share + int(index < extra)
    else:
        marker_budgets = raw_points.copy()
    returned: dict[str, int] = {source: 0 for source in sources}
    for source, selected, values in prepared:
        selected = selected.reset_index(drop=True)
        values = {key: value.reset_index(drop=True) for key, value in values.items()}
        boundary_rows.append(selected.dropna(subset=["layer"]).groupby("layer", as_index=False).first())
        if detail == "mean":
            reduced, reduced_values = _device_mean_points(selected, values)
        else:
            use_full = detail == "full" and full_available
            density = raw_points.get(source, 0) / max(1, len(selected))
            row_budget = max(2, int(marker_budgets.get(source, max_points) / max(density, 1)))
            keep = list(range(len(selected))) if use_full else _device_keep(selected, values, row_budget)
            reduced = selected.iloc[keep]
            reduced_values = {channel: value.iloc[keep] for channel, value in values.items()}
            actual_points = _device_marker_count(reduced, reduced_values, split_by_material, materials)
            while not use_full and actual_points > marker_budgets.get(source, max_points) and row_budget > 2:
                next_budget = max(2, int(row_budget * marker_budgets.get(source, max_points) / actual_points))
                row_budget = min(row_budget - 1, next_budget)
                keep = _device_keep(selected, values, row_budget)
                reduced = selected.iloc[keep]
                reduced_values = {channel: value.iloc[keep] for channel, value in values.items()}
                actual_points = _device_marker_count(reduced, reduced_values, split_by_material, materials)
        returned[source] = _device_marker_count(reduced, reduced_values, split_by_material, materials)
        for channel, value in reduced_values.items():
            traces.append(_device_trace(reduced, value, source, channel))
    boundaries: dict[int, dict] = {}
    for frame in boundary_rows:
        for _, row in frame.iterrows():
            boundaries[int(row["layer"])] = {
                "layer": int(row["layer"]), "time": row["_display_time"].strftime("%Y-%m-%dT%H:%M:%S"),
                "material": row["material"], "method": row["method"],
            }
    coverage_name = "mean" if detail == "mean" else "full" if detail == "full" and full_available else "overview"
    loaded_starts = [item["start"] for item in coverage.values() if item.get("start")]
    loaded_ends = [item["end"] for item in coverage.values() if item.get("end")]
    return {
        "traces": traces, "boundaries": sorted(boundaries.values(), key=lambda row: row["time"]),
        "coverage": coverage_name,
        "source_coverage": coverage,
        "full_available": full_available,
        "full_unavailable_reason": full_unavailable_reason,
        "limit_per_source": limit_per_source,
        "limit_total": limit_total,
        "time_breaks": time_breaks,
        "rows": counts, "raw_points": raw_points, "returned": returned, "point_counts": returned,
        "loaded_range": {
            "start": min(loaded_starts) if loaded_starts else None,
            "end": max(loaded_ends) if loaded_ends else None,
        },
        "exact": coverage_name == "full",
    }


def settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return base / APP_NAME / "settings.json"


def read_settings() -> dict:
    try:
        value = json.loads(settings_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def saved_path() -> str:
    path = str(read_settings().get("last_folder") or "").strip()
    if path:
        return path
    try:
        return LEGACY_LAST_FOLDER.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_path(path: str) -> None:
    target = settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps({"last_folder": path}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)


def apply_folder_selection(selected: str) -> tuple[str, bool, bool]:
    if not selected:
        return str(STATE.get("path") or saved_path()), True, False
    path = str(Path(selected).resolve())
    changed = path != str(STATE.get("path") or saved_path())
    save_path(path)
    STATE["path"] = path
    if changed:
        STATE.update(
            result=None,
            fingerprint=None,
            progress={"status": "idle", "phase": "", "current": 0, "total": 0, "elapsed": 0.0},
        )
    return path, False, changed


def choose_folder() -> tuple[str, bool, bool]:
    """Open a Windows STA folder dialog without blocking the HTTP worker GUI thread."""
    previous = saved_path()
    if not FOLDER_DIALOG_LOCK.acquire(blocking=False):
        raise FolderDialogError("文件夹选择窗口已经打开，请先完成或取消当前选择。")
    try:
        env = os.environ.copy()
        env["LOG_ANALYSIS_INITIAL_FOLDER"] = previous if Path(previous).is_dir() else ""
        script = r"""
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Windows.Forms
$dialog = [System.Windows.Forms.FolderBrowserDialog]::new()
$dialog.Description = '选择炉次日志文件夹'
$dialog.ShowNewFolderButton = $false
if ($env:LOG_ANALYSIS_INITIAL_FOLDER -and (Test-Path -LiteralPath $env:LOG_ANALYSIS_INITIAL_FOLDER)) {
    $dialog.SelectedPath = $env:LOG_ANALYSIS_INITIAL_FOLDER
}
$owner = [System.Windows.Forms.Form]::new()
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
try {
    if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::Write($dialog.SelectedPath)
    }
} finally {
    $dialog.Dispose()
    $owner.Dispose()
}
"""
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    finally:
        FOLDER_DIALOG_LOCK.release()
    if completed.returncode:
        detail = completed.stderr.strip() or "Windows 文件夹选择器未能启动"
        raise FolderDialogError(detail)
    return apply_folder_selection(completed.stdout.strip().lstrip("\ufeff"))


def set_progress(status: str, phase: str, current: int, total: int, started: float) -> None:
    STATE["progress"] = {
        "status": status,
        "phase": phase,
        "current": current,
        "total": total,
        "elapsed": round(max(0.0, time.monotonic() - started), 1),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(RESOURCE_ROOT), **kwargs)

    def log_message(self, *_: object) -> None:
        pass

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body: bytes, content_type: str, name: str | None = None) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if name:
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.end_headers()
        self.wfile.write(body)

    def body_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def authorized(self, parsed) -> bool:
        expected = str(getattr(self.server, "api_token", ""))
        if not expected:
            return True
        supplied = self.headers.get("X-Log-Analysis-Token", "") or parse_qs(parsed.query).get("token", [""])[0]
        return bool(supplied) and secrets.compare_digest(supplied, expected)

    def reject_unauthorized(self) -> None:
        self.send_json(
            {"error": "本地分析会话无效，请重新启动 Log Analysis。", "code": "unauthorized", "recovery": "关闭当前窗口后重新打开应用。"},
            HTTPStatus.FORBIDDEN,
        )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self.authorized(parsed):
            self.reject_unauthorized()
            return
        try:
            if parsed.path == "/api/choose-folder":
                try:
                    path, cancelled, changed = choose_folder()
                    self.send_json({"path": path, "cancelled": cancelled, "changed": changed})
                except FolderDialogError as exc:
                    self.send_json(
                        {
                            "error": f"无法打开文件夹选择窗口：{exc}",
                            "code": "folder_picker_failed",
                            "recovery": "请关闭残留的选择窗口后重试；如仍失败，请重新启动分析工具。",
                        },
                        HTTPStatus.CONFLICT,
                    )
                return
            if parsed.path == "/api/analyze":
                request = self.body_json()
                requested = request.get("path", "")
                threshold = float(request.get("threshold", 3.5))
                path = str(requested or STATE.get("path") or saved_path())
                if not ANALYSIS_LOCK.acquire(blocking=False):
                    self.send_json(
                        {
                            "error": "已有分析任务正在运行。",
                            "code": "analysis_busy",
                            "recovery": "请等待当前进度完成后再试。",
                        },
                        HTTPStatus.CONFLICT,
                    )
                    return
                started = time.monotonic()
                set_progress("running", "索引文件", 0, 0, started)
                try:
                    fingerprint = source_fingerprint(path)
                    cached = (
                        STATE.get("result") is not None
                        and path == STATE.get("path")
                        and fingerprint == STATE.get("fingerprint")
                    )
                    if cached:
                        result = STATE["result"]
                        set_progress("running", "缓存复用", len(result.layer_summary), len(result.layer_summary), started)
                    else:
                        result = analyze_folder(
                            path,
                            lambda phase, current, total: set_progress("running", phase, current, total, started),
                        )
                        STATE.update(path=path, result=result, fingerprint=fingerprint)
                    save_path(path)
                    monitor = monitor_summary(result)
                    anomalies = result.anomalies if threshold == 3.5 else detect_anomalies(monitor, threshold)
                    response = {
                        "batch": result.batch_summary,
                        "summary": frame_records(result.layer_summary),
                        "monitor_summary": frame_records(monitor),
                        "anomalies": frame_records(anomalies),
                        "quality": frame_records(result.data_quality),
                        "constants": frame_records(result.constant_fields),
                        "events": result.events,
                        "sources": result.sources,
                        "machine_summary": result.machine_summary,
                        "machine_sessions": frame_records(result.machine_sessions),
                        "machine_segments": frame_records(result.machine_segments),
                        "machine_quality": frame_records(result.machine_quality),
                        "alignment": result.alignment,
                    }
                    set_progress("completed", "完成", len(result.layer_summary), len(result.layer_summary), started)
                    self.send_json(response)
                    LOGGER.info("analysis completed cached=%s layers=%s elapsed=%.3fs", cached, len(result.layer_summary), time.monotonic() - started)
                except Exception:
                    current = dict(STATE.get("progress") or {})
                    set_progress("failed", str(current.get("phase") or "分析"), int(current.get("current") or 0), int(current.get("total") or 0), started)
                    raise
                finally:
                    ANALYSIS_LOCK.release()
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except (AnalysisError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            LOGGER.exception("request failed")
            self.send_json(
                {
                    "error": f"分析失败：{exc}",
                    "code": "analysis_failed",
                    "recovery": "请确认炉次文件完整后重试；若仍失败，请查看运行日志。",
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "service": "coating-analyzer",
                    "app_name": APP_NAME,
                    "app_version": APP_VERSION,
                    "build_channel": BUILD_CHANNEL,
                }
            )
            return
        if parsed.path == "/plotly.min.js":
            self.send_bytes(get_plotlyjs().encode("utf-8"), "text/javascript; charset=utf-8")
            return
        if parsed.path.startswith("/api/") and not self.authorized(parsed):
            self.reject_unauthorized()
            return
        if parsed.path == "/api/state":
            self.send_json({"path": str(STATE.get("path") or saved_path())})
            return
        try:
            result = STATE.get("result")
            params = parse_qs(parsed.query)
            if parsed.path == "/api/progress":
                self.send_json(dict(STATE.get("progress") or {}))
                return
            if parsed.path == "/api/anomalies":
                if result is None:
                    raise AnalysisError("请先完成炉次分析")
                threshold = float(params.get("threshold", ["3.5"])[0])
                monitor = monitor_summary(result)
                anomalies = result.anomalies if threshold == 3.5 else detect_anomalies(monitor, threshold)
                self.send_json({"anomalies": frame_records(anomalies)})
                return
            if parsed.path == "/api/device-series":
                if result is None:
                    raise AnalysisError("请先完成日志分析")
                list_param = lambda name: [item for value in params.get(name, []) for item in value.split(",") if item]
                self.send_json(
                    device_time_series(
                        result,
                        params.get("metric", [""])[0],
                        list_param("sources") or ["machine"],
                        int(params["layer_min"][0]) if params.get("layer_min") else None,
                        int(params["layer_max"][0]) if params.get("layer_max") else None,
                        list_param("materials"),
                        list_param("methods"),
                        params.get("session", [""])[0],
                        int(params.get("max_points", ["2500"])[0]),
                        params.get("start", [""])[0],
                        params.get("end", [""])[0],
                        params.get("detail", ["overview"])[0],
                    )
                )
                return
            if parsed.path == "/api/machine-series":
                if result is None:
                    raise AnalysisError("请先完成日志分析")
                metrics = [item for value in params.get("metrics", []) for item in value.split(",") if item]
                self.send_json(
                    machine_series(
                        result, metrics, params.get("session", [""])[0], params.get("start", [""])[0],
                        params.get("end", [""])[0], int(params.get("max_points", ["2500"])[0]),
                    )
                )
                return
            if parsed.path == "/api/layer":
                if result is None:
                    raise AnalysisError("请先完成炉次分析")
                detail = load_layer_detail(str(STATE["path"]), int(params["layer"][0]))
                self.send_json({"meas": frame_records(detail["meas"]), "calc": frame_records(detail["calc"]), "has_image": bool(detail["image_path"])})
                return
            if parsed.path == "/api/image":
                if result is None:
                    raise AnalysisError("请先完成炉次分析")
                detail = load_layer_detail(str(STATE["path"]), int(params["layer"][0]))
                image = detail["image_path"]
                if not image:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                image_path = Path(image)
                self.send_bytes(image_path.read_bytes(), mimetypes.guess_type(image_path.name)[0] or "image/jpeg")
                return
            if parsed.path == "/api/export":
                if result is None:
                    raise AnalysisError("请先完成炉次分析")
                threshold = float(params.get("threshold", ["3.5"])[0])
                frame, name = export_frame(result, params.get("kind", ["summary"])[0], threshold)
                self.send_bytes(csv_bytes(frame), "text/csv; charset=utf-8", name)
                return
        except (AnalysisError, KeyError, TypeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        super().do_GET()


def create_server(port: int = 0, token: str = "") -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.api_token = token
    httpd.daemon_threads = True
    httpd.block_on_close = False
    return httpd


def main() -> None:
    STATE["path"] = saved_path()
    port = int(os.environ.get("LOG_ANALYSIS_PORT", "8502"))
    httpd = create_server(port)
    threading.Timer(0.4, lambda: webbrowser.open(f"http://127.0.0.1:{httpd.server_port}")).start()
    print(f"{APP_NAME}： http://127.0.0.1:{httpd.server_port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
