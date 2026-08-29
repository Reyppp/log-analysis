from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd


DATE_CSV_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.csv$", re.IGNORECASE)
AUXILIARY_CSV_RE = re.compile(r"(?:^Extrm\.csv$|_BaseLine\.csv$)", re.IGNORECASE)
MACHINE_CORE_COLUMNS = {
    "Time", "H Power", "H Current", "H Voltage", "L Power", "L Current", "L Voltage", "Motor Speed",
}
MACHINE_NUMERIC_COLUMNS = [
    "H Power", "H Current", "H Voltage", "L Power", "L Current", "L Voltage",
    "Water-In", "Water-Out", "Chammber Vacuum", "Pipe Vacuum", "Chammber Low Vacuum",
    "Gas-O2(1)", "Gas-Ar(2)", "Gas-Ar(3)", "Gas-O2(4)", "Left DP Temperture",
    "Right DP Temperature", "Motor Speed", "Chammber Temperture", "H1 Target Water In",
    "H2 Target Water In", "L1 Target Water In", "L2 Target Water In",
]
MONITOR_DEVICE_RENAME = {
    "#HPower": "H Power", "#HCurrent": "H Current", "#HVoltage": "H Voltage",
    "#LPower": "L Power", "#LCurrent": "L Current", "#LVoltage": "L Voltage",
    "MotorSpeed": "Motor Speed", "ChammberVacuum": "Chammber Vacuum",
    "ChammberTemperature": "Chammber Temperture", "Water-InTemperature": "Water-In",
    "Water-OutTemperature": "Water-Out", "(1)O2Gas": "Gas-O2(1)",
    "(2)ArGas": "Gas-Ar(2)", "(3)ArGas": "Gas-Ar(3)", "(4)O2Gas": "Gas-O2(4)",
}
COOLING_STATUS_COLUMNS = [
    "ChammberCoolingWaterStatus", "LMP1CoolingWaterStatus", "LMP2CoolingWaterStatus",
    "RMP1CoolingWaterStatus", "RMP2CoolingWaterStatus", "SubstrateMotorCoolingWaterStatus",
    "MachanicalPumpCoolingWaterStatus", "H1TargetCooingWaterStatus", "H2TargetCooingWaterStatus",
    "L1TargetCooingWaterStatus", "L2TargetCooingWaterStatus", "HTargetPowerCoolingWaterStatus",
    "LTargetPowerCoolingWaterStatus",
]
MACHINE_EVENT_COLUMNS = [
    "source", "category", "time", "end_time", "segment_id", "material", "metric", "value", "baseline", "robust_z", "level", "reason",
]
MACHINE_SESSION_COLUMNS = [
    "session_id", "start", "end", "elapsed_seconds", "target_seconds", "segment_count", "h_segments", "l_segments", "is_default",
]
MACHINE_SEGMENT_COLUMNS = [
    "segment_id", "session_id", "material", "start", "end", "target_seconds", "rows",
    *[f"{prefix}_{suffix}" for prefix in ("power", "current", "voltage", "vacuum", "chamber_temp", "water_in", "water_out", "motor", "o2", "ar") for suffix in ("mean", "std", "min", "max", "range")],
    "layer",
]
CROSS_SOURCE_COLUMNS = ["source", "layer", "material", "metric", "value", "level", "reason"]
NUMBERED_PATTERNS = {
    "meas": re.compile(r"^MeasPower_(\d+)\.csv$", re.IGNORECASE),
    "machine": re.compile(r"^MachineStatus_(\d+)\.csv$", re.IGNORECASE),
    "calc": re.compile(r"CalcPower_\s*(\d+)\.csv$", re.IGNORECASE),
    "image": re.compile(r"^(\d+)\.jpg$", re.IGNORECASE),
}
QUALITY_COLUMNS = ["severity", "scope", "layer", "issue", "detail"]
ANOMALY_COLUMNS = [
    "layer",
    "material",
    "method",
    "metric",
    "value",
    "change",
    "group",
    "baseline",
    "mad",
    "robust_z",
    "level",
    "reason",
]

OPTICAL_METRICS = [
    "time_delta",
    "rate_delta",
    "fit_end_residual",
    "recipe_end_offset",
    "fit_mae",
    "fit_rmse",
    "fit_p95_abs",
    "fit_max_abs",
    "signal_cv",
]
DEVICE_METRICS = [
    "power_mean",
    "power_std",
    "current_mean",
    "current_std",
    "voltage_mean",
    "voltage_std",
    "vacuum_mean",
    "vacuum_std",
    "chamber_temp_mean",
    "chamber_temp_std",
    "water_in_mean",
    "water_out_mean",
    "motor_mean",
    "motor_std",
    "o2_mean",
    "ar_mean",
]

SUMMARY_COLUMNS = [
    "layer", "material", "method", "phy_thick", "recipe_rate", "planned_time", "start_t", "end_t",
    "recipe_extreme", "final_meas", "final_calc", "fit_end_residual", "recipe_end_offset", "fit_mae",
    "fit_rmse", "fit_p95_abs", "fit_max_abs", "actual_time", "time_delta", "actual_rate", "rate_delta",
    "actual_extreme", "signal_median", "signal_std", "signal_cv", "optical_rows",
    *[f"{prefix}_{suffix}" for prefix in ("power", "current", "voltage", "vacuum", "chamber_temp", "water_in", "water_out", "motor", "o2", "ar") for suffix in ("mean", "std", "min", "max", "range")],
    "substrate_shutter_mismatch", "material_shutter_mismatch", "shutter_mismatch",
    "layer_start", "layer_end", "machine_span", "machine_rows",
    *[f"monitor_motor_{suffix}" for suffix in ("mean", "std", "min", "max", "range")],
    "motor_source", "target_power_seconds", "target_time_delta", "machine_segment_id",
]


class AnalysisError(ValueError):
    pass


@dataclass
class AnalysisResult:
    batch_summary: dict[str, Any]
    layer_summary: pd.DataFrame
    anomalies: pd.DataFrame
    data_quality: pd.DataFrame
    constant_fields: pd.DataFrame
    file_index: pd.DataFrame
    events: dict[str, Any]
    sources: dict[str, bool] = field(default_factory=dict)
    machine_summary: dict[str, Any] = field(default_factory=dict)
    machine_sessions: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=MACHINE_SESSION_COLUMNS))
    machine_segments: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=MACHINE_SEGMENT_COLUMNS))
    machine_events: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=MACHINE_EVENT_COLUMNS))
    machine_quality: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=QUALITY_COLUMNS))
    alignment: dict[str, Any] = field(default_factory=dict)
    cross_source_review: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=CROSS_SOURCE_COLUMNS))
    monitor_device_data: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)
    machine_data: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)


def parse_mixed_datetime(value: str) -> datetime:
    """Parse the logger's mixed 12/24-hour timestamps, including '13:00 PM'."""
    parts = str(value).split()
    if len(parts) < 2:
        raise ValueError(f"无法解析时间：{value!r}")
    year, month, day = map(int, parts[0].split("-"))
    hour, minute, second = map(int, parts[1].split(":"))
    am_pm = parts[2].upper() if len(parts) >= 3 else ""
    if hour <= 12:
        if am_pm == "PM" and hour < 12:
            hour += 12
        elif am_pm == "AM" and hour == 12:
            hour = 0
    return datetime(year, month, day, hour, minute, second)


def source_fingerprint(folder: str | Path) -> tuple[tuple[str, int, int], ...]:
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        return ()
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.parent == root and AUXILIARY_CSV_RE.search(path.name):
            continue
        stat = path.stat()
        files.append((path.relative_to(root).as_posix(), stat.st_size, stat.st_mtime_ns))
    return tuple(sorted(files))


def _quality(rows: list[dict[str, Any]], severity: str, scope: str, issue: str, detail: str, layer: int | None = None) -> None:
    rows.append(
        {
            "severity": severity,
            "scope": scope,
            "layer": layer,
            "issue": issue,
            "detail": detail,
        }
    )


def _read_csv(path: Path, required: set[str], scope: str, layer: int | None, quality: list[dict[str, Any]]) -> pd.DataFrame | None:
    try:
        frame = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except Exception as exc:
        _quality(quality, "错误", scope, "CSV读取失败", f"{path.name}: {exc}", layer)
        return None
    missing = sorted(required - set(frame.columns))
    if missing:
        _quality(quality, "错误", scope, "表头缺失", f"{path.name}: {', '.join(missing)}", layer)
        return None
    if frame.empty:
        _quality(quality, "错误", scope, "文件无数据", path.name, layer)
        return None
    return frame


def _convert_numeric(frame: pd.DataFrame, columns: list[str], scope: str, layer: int | None, quality: list[dict[str, Any]]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        raw = result[column]
        if pd.api.types.is_numeric_dtype(raw.dtype):
            continue
        converted = pd.to_numeric(raw, errors="coerce")
        invalid = raw.notna() & converted.isna()
        if invalid.any():
            candidates = raw.loc[invalid].astype(str).str.strip()
            invalid.loc[candidates.index[candidates.eq("")]] = False
        if invalid.any():
            _quality(
                quality,
                "错误",
                scope,
                "非法数值",
                f"{column}: {int(invalid.sum())} 行无法解析",
                layer,
            )
        result[column] = converted
    return result


def _stats(series: pd.Series, prefix: str) -> dict[str, float]:
    values = series.dropna() if pd.api.types.is_numeric_dtype(series.dtype) else pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return {f"{prefix}_{suffix}": math.nan for suffix in ("mean", "std", "min", "max", "range")}
    return {
        f"{prefix}_mean": float(values.mean()),
        f"{prefix}_std": float(values.std(ddof=0)),
        f"{prefix}_min": float(values.min()),
        f"{prefix}_max": float(values.max()),
        f"{prefix}_range": float(values.max() - values.min()),
    }


def _discover_numbered(folder: Path, pattern: re.Pattern[str], family: str, quality: list[dict[str, Any]]) -> tuple[dict[int, Path], list[Path]]:
    result: dict[int, Path] = {}
    duplicates: list[Path] = []
    if not folder.is_dir():
        _quality(quality, "错误", family, "目录缺失", str(folder))
        return result, duplicates
    for path in folder.iterdir():
        if not path.is_file():
            continue
        match = pattern.search(path.name)
        if not match:
            continue
        number = int(match.group(1))
        if number in result:
            duplicates.extend([result[number], path])
            _quality(quality, "错误", family, "重复层号", f"第 {number} 层存在多个文件", number)
            continue
        result[number] = path
    return result, duplicates


def _recipe_paths(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in root.iterdir():
        if not path.is_file() or path.suffix.lower() != ".csv" or DATE_CSV_RE.match(path.name) or AUXILIARY_CSV_RE.search(path.name):
            continue
        try:
            header = pd.read_csv(path, encoding="utf-8-sig", nrows=1)
        except Exception:
            continue
        if {"Layer#", "Material", "Method"}.issubset(header.columns):
            candidates.append(path)
    return candidates


def _find_recipe(root: Path) -> tuple[Path, pd.DataFrame]:
    candidates = _recipe_paths(root)
    if len(candidates) != 1:
        raise AnalysisError(f"应找到 1 个理论 CSV，实际找到 {len(candidates)} 个")
    path = candidates[0]
    return path, pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


def _track_fields(profile: dict[str, set[Any]], source: str, frame: pd.DataFrame) -> None:
    for column in frame.columns:
        key = f"{source}.{column}"
        values = profile.setdefault(key, set())
        if len(values) >= 2:
            continue
        current = frame[column].dropna()
        if current.empty:
            continue
        if not values:
            values.add(current.iloc[0])
        known = next(iter(values))
        if not current.eq(known).all():
            values.add("__varied__")


def _file_rows(root: Path, family: str, mapping: dict[int, Path]) -> list[dict[str, Any]]:
    rows = []
    for layer, path in mapping.items():
        stat = path.stat()
        rows.append(
            {
                "family": family,
                "layer": layer,
                "relative_path": path.relative_to(root).as_posix(),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return rows


def _parse_events(log_paths: list[Path], recipe_materials: list[str], quality: list[dict[str, Any]]) -> dict[str, Any]:
    messages: list[str] = []
    error_lines: list[str] = []
    for path in sorted(log_paths):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as exc:
            _quality(quality, "警告", "CoatingLog", "日志读取失败", f"{path.name}: {exc}")
            continue
        for line in text.splitlines():
            match = re.match(r"^\[[^]]+\]\s+\[[^]]+\]\s+(.*)$", line)
            if match:
                message = match.group(1).strip()
                messages.append(message)
                if re.search(r"error|alarm|fail|fault|abort|emergency|warning|exception|interlock|trip|timeout|abnormal", message, re.I):
                    error_lines.append(message)

    sequence = ["H" if "#H" in message else "L" for message in messages if re.fullmatch(r"#[HL] Coating command completed", message)]
    mismatches = [index + 1 for index, pair in enumerate(zip(sequence, recipe_materials)) if pair[0] != pair[1]]
    finished = sum(message == "Coating Finished!" for message in messages)
    if len(sequence) != len(recipe_materials):
        _quality(quality, "警告", "CoatingLog", "执行层数不一致", f"日志 {len(sequence)} 层，理论表 {len(recipe_materials)} 层")
    if mismatches:
        _quality(quality, "错误", "CoatingLog", "材料执行顺序不一致", f"异常层: {mismatches[:20]}")
    if finished != 1:
        _quality(quality, "警告", "CoatingLog", "完成标志异常", f"Coating Finished! 出现 {finished} 次")
    if error_lines:
        _quality(quality, "警告", "CoatingLog", "发现错误关键词", f"共 {len(error_lines)} 条")
    return {
        "message_count": len(messages),
        "coating_sequence_count": len(sequence),
        "sequence_mismatches": mismatches,
        "finished_count": finished,
        "set_sens_count": sum(message.startswith("Set Sens:") for message in messages),
        "end_layer_test_count": sum(message == "End layer test command completed" for message in messages),
        "error_like_count": len(error_lines),
        "error_like_samples": error_lines[:20],
    }


def _analyze_monitor_folder(
    folder: str | Path,
    progress: Callable[[str, int, int], None] | None = None,
) -> AnalysisResult:
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise AnalysisError(f"文件夹不存在：{root}")

    if progress:
        progress("索引文件", 0, 0)

    quality: list[dict[str, Any]] = []
    profile: dict[str, set[Any]] = {}
    recipe_path, recipe = _find_recipe(root)
    required_recipe = {"Layer#", "Material", "PhyThick", "Rate", "Time", "Start T", "End T", "Extreme#", "Method"}
    missing_recipe = sorted(required_recipe - set(recipe.columns))
    if missing_recipe:
        raise AnalysisError(f"理论表缺少字段：{', '.join(missing_recipe)}")

    recipe = _convert_numeric(
        recipe,
        ["Layer#", "PhyThick", "Rate", "Time", "Start T", "End T", "Extreme#"],
        "recipe",
        0,
        quality,
    )
    if recipe["Layer#"].isna().any():
        raise AnalysisError("理论表层号包含非法值")
    recipe["layer"] = recipe["Layer#"].astype(int)
    if recipe["layer"].duplicated().any():
        duplicated = recipe.loc[recipe["layer"].duplicated(keep=False), "layer"].tolist()
        raise AnalysisError(f"理论表存在重复层号：{duplicated}")
    recipe = recipe.sort_values("layer").reset_index(drop=True)
    expected = list(range(1, int(recipe["layer"].max()) + 1))
    if recipe["layer"].tolist() != expected:
        raise AnalysisError("理论表层号必须从 1 开始连续")

    mappings: dict[str, dict[int, Path]] = {}
    family_folders = {
        "meas": root / "CoatingPower",
        "machine": root / "CoatingPower",
        "calc": root / "CoatingCalc",
        "image": root / "CoatingImage",
    }
    for family, pattern in NUMBERED_PATTERNS.items():
        mappings[family], _ = _discover_numbered(family_folders[family], pattern, family, quality)
        missing = sorted(set(expected) - set(mappings[family]))
        extras = sorted(set(mappings[family]) - set(expected))
        for layer in missing:
            severity = "警告" if family == "image" else "错误"
            _quality(quality, severity, family, "缺少层文件", f"第 {layer} 层", layer)
        if extras:
            _quality(quality, "警告", family, "超出理论层号", str(extras[:20]))

    ignored_date_csvs = sorted(path.name for path in root.iterdir() if path.is_file() and DATE_CSV_RE.match(path.name))
    file_rows = []
    for family, mapping in mappings.items():
        file_rows.extend(_file_rows(root, family, mapping))
    recipe_stat = recipe_path.stat()
    file_rows.append(
        {
            "family": "recipe",
            "layer": math.nan,
            "relative_path": recipe_path.relative_to(root).as_posix(),
            "size": recipe_stat.st_size,
            "mtime_ns": recipe_stat.st_mtime_ns,
        }
    )

    summaries: list[dict[str, Any]] = []
    monitor_device_frames: list[pd.DataFrame] = []
    meas_required = {
        "LayNum",
        "Material",
        "SamTime",
        "ExtremeNum",
        "MeasVal(1)",
        "CalcVal(1)",
        "S_ignals(1)",
        "Rates",
    }
    machine_required = {
        "LayNum",
        "Timer",
        "MotorSpeed",
        "SubstrateShutter",
        "#HCurrent",
        "#HVoltage",
        "#HPower",
        "#LCurrent",
        "#LVoltage",
        "#LPower",
        "#H1Shutter",
        "#H2Shutter",
        "#L1Shutter",
        "#L2Shutter",
        "(1)O2Gas",
        "(2)ArGas",
        "(3)ArGas",
        "(4)O2Gas",
        "ChammberVacuum",
        "ChammberTemperature",
        "Water-InTemperature",
        "Water-OutTemperature",
    }
    machine_numeric = sorted(machine_required - {"LayNum", "Timer"})

    total_layers = len(expected)
    for layer_index, recipe_row in enumerate(recipe.to_dict("records"), start=1):
        layer = int(recipe_row["layer"])
        material = str(recipe_row["Material"]).strip()
        method = str(recipe_row["Method"]).strip()
        row: dict[str, Any] = {
            "layer": layer,
            "material": material,
            "method": method,
            "phy_thick": float(recipe_row["PhyThick"]),
            "recipe_rate": float(recipe_row["Rate"]),
            "planned_time": float(recipe_row["Time"]),
            "start_t": float(recipe_row["Start T"]),
            "end_t": float(recipe_row["End T"]),
            "recipe_extreme": float(recipe_row["Extreme#"]),
        }

        meas_path = mappings["meas"].get(layer)
        if meas_path:
            meas = _read_csv(meas_path, meas_required, "MeasPower", layer, quality)
            if meas is not None:
                _track_fields(profile, "MeasPower", meas)
                meas = _convert_numeric(
                    meas,
                    ["LayNum", "SamTime", "ExtremeNum", "MeasVal(1)", "CalcVal(1)", "S_ignals(1)", "Rates"],
                    "MeasPower",
                    layer,
                    quality,
                )
                bad_layers = meas["LayNum"].dropna().astype(int).ne(layer)
                if bad_layers.any():
                    _quality(quality, "错误", "MeasPower", "层号不匹配", f"{int(bad_layers.sum())} 行", layer)
                materials = set(meas["Material"].dropna().astype(str).str.strip())
                if materials != {material}:
                    _quality(quality, "错误", "MeasPower", "材料不匹配", f"理论 {material}，文件 {sorted(materials)}", layer)
                sample_times = meas["SamTime"].dropna()
                if not sample_times.is_monotonic_increasing:
                    _quality(quality, "错误", "MeasPower", "采样时间非单调", meas_path.name, layer)
                endpoint = meas.dropna(subset=["MeasVal(1)", "CalcVal(1)"])
                residual = endpoint["MeasVal(1)"] - endpoint["CalcVal(1)"]
                signal = meas["S_ignals(1)"].dropna()
                actual_time = float(sample_times.iloc[-1]) if not sample_times.empty else math.nan
                actual_rate = float(meas["Rates"].dropna().median()) if meas["Rates"].notna().any() else math.nan
                if not endpoint.empty:
                    final_meas = float(endpoint["MeasVal(1)"].iloc[-1])
                    final_calc = float(endpoint["CalcVal(1)"].iloc[-1])
                    abs_residual = residual.abs()
                    row.update(
                        {
                            "final_meas": final_meas,
                            "final_calc": final_calc,
                            "fit_end_residual": final_meas - final_calc,
                            "recipe_end_offset": final_meas - row["end_t"],
                            "fit_mae": float(abs_residual.mean()),
                            "fit_rmse": float(math.sqrt((residual.pow(2)).mean())),
                            "fit_p95_abs": float(abs_residual.quantile(0.95)),
                            "fit_max_abs": float(abs_residual.max()),
                        }
                    )
                signal_mean = float(signal.mean()) if not signal.empty else math.nan
                signal_std = float(signal.std(ddof=0)) if not signal.empty else math.nan
                row.update(
                    {
                        "actual_time": actual_time,
                        "time_delta": actual_time - row["planned_time"],
                        "actual_rate": actual_rate,
                        "rate_delta": actual_rate - row["recipe_rate"],
                        "actual_extreme": float(meas["ExtremeNum"].dropna().iloc[-1]) if meas["ExtremeNum"].notna().any() else math.nan,
                        "signal_median": float(signal.median()) if not signal.empty else math.nan,
                        "signal_std": signal_std,
                        "signal_cv": signal_std / abs(signal_mean) if signal_mean else math.nan,
                        "optical_rows": len(meas),
                    }
                )

        machine_path = mappings["machine"].get(layer)
        if machine_path:
            machine = _read_csv(machine_path, machine_required, "MachineStatus", layer, quality)
            if machine is not None:
                _track_fields(profile, "MachineStatus", machine)
                machine = _convert_numeric(machine, machine_numeric, "MachineStatus", layer, quality)
                file_layers = pd.to_numeric(machine["LayNum"].astype(str).str.extract(r"(\d+)", expand=False), errors="coerce")
                if file_layers.isna().any() or file_layers.dropna().astype(int).ne(layer).any():
                    _quality(quality, "错误", "MachineStatus", "层号不匹配", machine_path.name, layer)
                parsed_times = []
                invalid_time_count = 0
                for value in machine["Timer"]:
                    try:
                        parsed_times.append(parse_mixed_datetime(value))
                    except Exception:
                        parsed_times.append(pd.NaT)
                        invalid_time_count += 1
                time_series = pd.Series(parsed_times).dropna()
                if invalid_time_count:
                    _quality(quality, "错误", "MachineStatus", "时间无法解析", f"{invalid_time_count} 行", layer)
                if not time_series.is_monotonic_increasing:
                    _quality(quality, "错误", "MachineStatus", "时间非单调", machine_path.name, layer)

                channel = "#H" if material == "H" else "#L"
                row.update(_stats(machine[f"{channel}Power"], "power"))
                row.update(_stats(machine[f"{channel}Current"], "current"))
                row.update(_stats(machine[f"{channel}Voltage"], "voltage"))
                for source, prefix in [
                    ("ChammberVacuum", "vacuum"),
                    ("ChammberTemperature", "chamber_temp"),
                    ("Water-InTemperature", "water_in"),
                    ("Water-OutTemperature", "water_out"),
                    ("MotorSpeed", "motor"),
                ]:
                    row.update(_stats(machine[source], prefix))
                o2 = pd.concat([machine["(1)O2Gas"], machine["(4)O2Gas"]], ignore_index=True)
                ar = pd.concat([machine["(2)ArGas"], machine["(3)ArGas"]], ignore_index=True)
                row.update(_stats(o2, "o2"))
                row.update(_stats(ar, "ar"))

                expected_shutters = (1, 1, 0, 0) if material == "H" else (0, 0, 1, 1)
                shutter_columns = ["#H1Shutter", "#H2Shutter", "#L1Shutter", "#L2Shutter"]
                material_bad = pd.Series(False, index=machine.index)
                for column, expected_value in zip(shutter_columns, expected_shutters):
                    material_bad |= machine[column].ne(expected_value)
                substrate_bad = machine["SubstrateShutter"].ne(1)
                row["substrate_shutter_mismatch"] = int(substrate_bad.sum())
                row["material_shutter_mismatch"] = int(material_bad.sum())
                row["shutter_mismatch"] = int(substrate_bad.sum() + material_bad.sum())
                if substrate_bad.any() or material_bad.any():
                    _quality(
                        quality,
                        "错误",
                        "MachineStatus",
                        "挡板状态不一致",
                        f"基片 {int(substrate_bad.sum())} 行，材料 {int(material_bad.sum())} 行",
                        layer,
                    )
                if not time_series.empty:
                    row["layer_start"] = time_series.iloc[0]
                    row["layer_end"] = time_series.iloc[-1]
                    row["machine_span"] = float((time_series.iloc[-1] - time_series.iloc[0]).total_seconds())
                row["machine_rows"] = len(machine)
                device = machine[list(MONITOR_DEVICE_RENAME)].rename(columns=MONITOR_DEVICE_RENAME).copy()
                device["_source_time"] = pd.to_datetime(parsed_times)
                device["_time"] = device["_source_time"]
                device["layer"] = layer
                device["material"] = material
                device["method"] = method
                monitor_device_frames.append(device.dropna(subset=["_time"]))

        summaries.append(row)
        if progress:
            progress("逐层读取", layer_index, total_layers)

    layer_summary = pd.DataFrame(summaries).sort_values("layer").reset_index(drop=True)
    for column in SUMMARY_COLUMNS:
        if column not in layer_summary:
            layer_summary[column] = math.nan
    layer_summary = layer_summary[SUMMARY_COLUMNS]
    log_paths = sorted((root / "CoatingLog").glob("*.log")) if (root / "CoatingLog").is_dir() else []
    if progress:
        progress("事件汇总", total_layers, total_layers)
    if not log_paths:
        _quality(quality, "警告", "CoatingLog", "日志缺失", "未找到 .log 文件")
    for path in log_paths:
        stat = path.stat()
        file_rows.append(
            {
                "family": "coating_log",
                "layer": math.nan,
                "relative_path": path.relative_to(root).as_posix(),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    events = _parse_events(log_paths, recipe["Material"].astype(str).str.strip().tolist(), quality)

    constant_rows = []
    for field, values in sorted(profile.items()):
        if len(values) == 1:
            source, column = field.split(".", 1)
            constant_rows.append({"source": source, "field": column, "value": next(iter(values)), "reason": "全炉恒定，默认不绘图"})
    constant_fields = pd.DataFrame(constant_rows, columns=["source", "field", "value", "reason"])

    hidden_summary_metrics = [
        column
        for column in OPTICAL_METRICS + DEVICE_METRICS
        if column in layer_summary and layer_summary[column].dropna().nunique() <= 1
    ]
    for metric in hidden_summary_metrics:
        constant_rows.append({"source": "LayerSummary", "field": metric, "value": "constant", "reason": "逐层无变化，默认不绘图"})
    if hidden_summary_metrics:
        constant_fields = pd.DataFrame(constant_rows, columns=["source", "field", "value", "reason"])

    data_quality = pd.DataFrame(quality, columns=QUALITY_COLUMNS)
    file_index = pd.DataFrame(file_rows).sort_values(["family", "layer"], na_position="last").reset_index(drop=True)
    starts = pd.to_datetime(layer_summary.get("layer_start"), errors="coerce").dropna()
    ends = pd.to_datetime(layer_summary.get("layer_end"), errors="coerce").dropna()
    batch_summary = {
        "lot_id": root.name.removesuffix("log"),
        "folder": str(root),
        "layer_count": len(layer_summary),
        "h_layers": int((layer_summary["material"] == "H").sum()),
        "l_layers": int((layer_summary["material"] == "L").sum()),
        "oms_layers": int((layer_summary["method"] == "OMS").sum()),
        "timer_layers": int((layer_summary["method"] == "Timer").sum()),
        "planned_seconds": float(layer_summary["planned_time"].sum()),
        "actual_seconds": float(layer_summary["actual_time"].sum(min_count=1)),
        "machine_elapsed_seconds": float((ends.max() - starts.min()).total_seconds()) if not starts.empty and not ends.empty else math.nan,
        "finished": events["finished_count"] == 1,
        "quality_errors": int((data_quality["severity"] == "错误").sum()) if not data_quality.empty else 0,
        "quality_warnings": int((data_quality["severity"] == "警告").sum()) if not data_quality.empty else 0,
        "ignored_date_csvs": ignored_date_csvs,
        "hidden_summary_metrics": hidden_summary_metrics,
    }
    if progress:
        progress("统计计算", total_layers, total_layers)
    anomalies = detect_anomalies(layer_summary, 3.5)
    if progress:
        progress("完成", total_layers, total_layers)
    result = AnalysisResult(batch_summary, layer_summary, anomalies, data_quality, constant_fields, file_index, events)
    if monitor_device_frames:
        result.monitor_device_data = pd.concat(monitor_device_frames, ignore_index=True)
    return result


def _discover_machine_files(root: Path, quality: list[dict[str, Any]]) -> list[Path]:
    valid: list[Path] = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or not DATE_CSV_RE.match(path.name):
            continue
        try:
            columns = set(pd.read_csv(path, encoding="utf-8-sig", nrows=0).columns)
        except Exception as exc:
            _quality(quality, "错误", "工控log", "CSV读取失败", f"{path.name}: {exc}")
            continue
        missing = sorted(MACHINE_CORE_COLUMNS - columns)
        if missing:
            _quality(quality, "错误", "工控log", "表头不符合工控log", f"{path.name}: 缺少 {', '.join(missing)}")
            continue
        valid.append(path)
    return valid


def _machine_event(
    rows: list[dict[str, Any]], category: str, reason: str, *, time: Any = None, end_time: Any = None,
    segment_id: Any = None, material: Any = None, metric: str = "", value: Any = None,
    baseline: Any = None, robust_z: Any = None, level: str = "关注",
) -> None:
    rows.append(
        {
            "source": "工控log", "category": category, "time": time, "end_time": end_time,
            "segment_id": segment_id, "material": material, "metric": metric, "value": value,
            "baseline": baseline, "robust_z": robust_z, "level": level, "reason": reason,
        }
    )


def _series_stats(frame: pd.DataFrame, columns: list[str], prefix: str) -> dict[str, float]:
    available = [column for column in columns if column in frame]
    if not available:
        return _stats(pd.Series(dtype=float), prefix)
    if len(available) == 1:
        return _stats(frame[available[0]], prefix)
    values = frame[available].mean(axis=1)
    return _stats(values, prefix)


def _build_machine_segments(frame: pd.DataFrame, cadence: float) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    if frame.empty:
        return (
            pd.DataFrame(columns=MACHINE_SEGMENT_COLUMNS),
            pd.DataFrame(columns=MACHINE_SESSION_COLUMNS),
            [],
        )
    h_active = frame["H Power"].fillna(0).gt(0.1)
    l_active = frame["L Power"].fillna(0).gt(0.1)
    state = pd.Series("", index=frame.index, dtype=object)
    state.loc[h_active & ~l_active] = "H"
    state.loc[l_active & ~h_active] = "L"
    state.loc[h_active & l_active] = "H+L"
    gaps = frame["_time"].diff().dt.total_seconds()
    block = (state.ne(state.shift(fill_value="")) | gaps.ge(300)).cumsum()
    segment_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    for segment_id, (_, group) in enumerate(frame.loc[state.ne("")].groupby(block[state.ne("")]), start=1):
        material = str(state.loc[group.index[0]])
        start = group["_time"].iloc[0]
        end = group["_time"].iloc[-1]
        row: dict[str, Any] = {
            "segment_id": segment_id,
            "session_id": 0,
            "material": material,
            "start": start,
            "end": end,
            "target_seconds": float((end - start).total_seconds() + cadence),
            "rows": len(group),
            "layer": math.nan,
        }
        if material == "H":
            row.update(_stats(group["H Power"], "power"))
            row.update(_stats(group["H Current"], "current"))
            row.update(_stats(group["H Voltage"], "voltage"))
        elif material == "L":
            row.update(_stats(group["L Power"], "power"))
            row.update(_stats(group["L Current"], "current"))
            row.update(_stats(group["L Voltage"], "voltage"))
        else:
            row.update(_stats(group["H Power"].fillna(0) + group["L Power"].fillna(0), "power"))
            row.update(_stats(group["H Current"].fillna(0) + group["L Current"].fillna(0), "current"))
            row.update(_series_stats(group, ["H Voltage", "L Voltage"], "voltage"))
            _machine_event(
                event_rows, "设备逻辑", "H/L 功率同时大于 0.1", time=start, end_time=end,
                segment_id=segment_id, material=material, metric="simultaneous_power",
                value=row["target_seconds"], level="重点复核",
            )
        row.update(_series_stats(group, ["Chammber Vacuum"], "vacuum"))
        row.update(_series_stats(group, ["Chammber Temperture"], "chamber_temp"))
        row.update(_series_stats(group, ["Water-In"], "water_in"))
        row.update(_series_stats(group, ["Water-Out"], "water_out"))
        row.update(_series_stats(group, ["Motor Speed"], "motor"))
        row.update(_series_stats(group, ["Gas-O2(1)", "Gas-O2(4)"], "o2"))
        row.update(_series_stats(group, ["Gas-Ar(2)", "Gas-Ar(3)"], "ar"))
        segment_rows.append(row)

    segments = pd.DataFrame(segment_rows)
    if segments.empty:
        return pd.DataFrame(columns=MACHINE_SEGMENT_COLUMNS), pd.DataFrame(columns=MACHINE_SESSION_COLUMNS), event_rows
    session_id = 1
    session_ids = []
    previous_end = None
    for row in segments.itertuples():
        if previous_end is not None and (row.start - previous_end).total_seconds() >= 300:
            session_id += 1
        session_ids.append(session_id)
        previous_end = row.end
    segments["session_id"] = session_ids
    sessions = []
    for current_id, group in segments.groupby("session_id", sort=True):
        start, end = group["start"].min(), group["end"].max()
        sessions.append(
            {
                "session_id": int(current_id), "start": start, "end": end,
                "elapsed_seconds": float((end - start).total_seconds() + cadence),
                "target_seconds": float(group["target_seconds"].sum()), "segment_count": len(group),
                "h_segments": int(group["material"].eq("H").sum()), "l_segments": int(group["material"].eq("L").sum()),
                "is_default": False,
            }
        )
    session_frame = pd.DataFrame(sessions, columns=MACHINE_SESSION_COLUMNS)
    if not session_frame.empty:
        default_index = session_frame["elapsed_seconds"].idxmax()
        session_frame.loc[default_index, "is_default"] = True
    for column in MACHINE_SEGMENT_COLUMNS:
        if column not in segments:
            segments[column] = math.nan
    return segments[MACHINE_SEGMENT_COLUMNS], session_frame, event_rows


def _segment_review_events(segments: pd.DataFrame, threshold: float = 3.5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    resolutions = {
        "power_mean": 0.01, "current_mean": 0.1, "voltage_mean": 1.0,
        "vacuum_mean": 0.000001, "chamber_temp_mean": 1.0, "water_in_mean": 0.01,
        "water_out_mean": 0.01, "motor_mean": 0.1, "o2_mean": 0.01, "ar_mean": 0.01,
    }
    normal = segments[segments["material"].isin(["H", "L"])]
    for (session_id, material), group in normal.groupby(["session_id", "material"]):
        for metric, resolution in resolutions.items():
            values = pd.to_numeric(group[metric], errors="coerce")
            valid = values.dropna()
            if len(valid) < 5 or valid.nunique() <= 1:
                continue
            median = float(valid.median())
            mad = float((valid - median).abs().median())
            scale = max(mad, resolution * 2)
            minimum_change = max(resolution * 3, abs(median) * 0.005)
            robust_z = 0.6745 * (values - median) / scale
            flagged = robust_z.abs().ge(threshold) & values.sub(median).abs().ge(minimum_change)
            for index in robust_z.index[flagged.fillna(False)]:
                segment = group.loc[index]
                z_value = float(robust_z.loc[index])
                _machine_event(
                    rows, "同材料工作时段统计", f"同一镀膜区段、同材料工作时段偏离中位数，|robust z| ≥ {threshold:.1f}",
                    time=segment["start"], end_time=segment["end"], segment_id=int(segment["segment_id"]),
                    material=material, metric=metric, value=float(values.loc[index]), baseline=median,
                    robust_z=z_value, level="重点复核" if abs(z_value) >= 5 else "关注",
                )
    return rows


def _analyze_machine_logs(
    files: list[Path], quality: list[dict[str, Any]],
    progress: Callable[[str, int, int], None] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    for index, path in enumerate(files, start=1):
        frame = _read_csv(path, MACHINE_CORE_COLUMNS, "工控log", None, quality)
        if frame is not None:
            frame["_source_file"] = path.name
            frames.append(frame)
        if progress:
            progress("工控log读取", index, len(files))
    if not frames:
        return {}, pd.DataFrame(columns=MACHINE_SESSION_COLUMNS), pd.DataFrame(columns=MACHINE_SEGMENT_COLUMNS), pd.DataFrame(columns=MACHINE_EVENT_COLUMNS), pd.DataFrame()
    frame = pd.concat(frames, ignore_index=True)
    numeric = [column for column in MACHINE_NUMERIC_COLUMNS + COOLING_STATUS_COLUMNS if column in frame]
    frame = _convert_numeric(frame, numeric, "工控log", None, quality)
    parsed_times = []
    invalid_times = 0
    for value in frame["Time"]:
        try:
            parsed_times.append(parse_mixed_datetime(value))
        except Exception:
            parsed_times.append(pd.NaT)
            invalid_times += 1
    frame["_time"] = pd.to_datetime(parsed_times)
    if invalid_times:
        _quality(quality, "错误", "工控log", "时间无法解析", f"{invalid_times} 行")
    valid_time = frame["_time"].dropna()
    if not valid_time.is_monotonic_increasing:
        _quality(quality, "错误", "工控log", "时间非单调", "合并后的日期文件时间顺序异常")
    duplicate_count = int(valid_time.duplicated().sum())
    if duplicate_count:
        _quality(quality, "错误", "工控log", "重复时间", f"{duplicate_count} 行")
    frame = frame.dropna(subset=["_time"]).sort_values("_time").drop_duplicates("_time", keep="first").reset_index(drop=True)
    gaps = frame["_time"].diff().dt.total_seconds()
    positive_gaps = gaps[gaps.gt(0)]
    cadence = float(positive_gaps.median()) if not positive_gaps.empty else 0.0
    event_rows: list[dict[str, Any]] = []
    gap_threshold = max(30.0, cadence * 3)
    for index in gaps.index[gaps.gt(gap_threshold).fillna(False)]:
        seconds = float(gaps.loc[index])
        _quality(quality, "警告", "工控log", "采样时间缺口", f"{frame.loc[index, '_time']}: {seconds:.0f} s")
        _machine_event(
            event_rows, "时间质量", f"连续记录间隔 {seconds:.0f} s", time=frame.loc[index - 1, "_time"],
            end_time=frame.loc[index, "_time"], metric="sample_gap", value=seconds,
            level="重点复核" if seconds >= 300 else "关注",
        )
    for column in COOLING_STATUS_COLUMNS:
        if column not in frame:
            continue
        bad = frame[column].notna() & frame[column].ne(1)
        if bad.any():
            first, last = frame.loc[bad, "_time"].iloc[[0, -1]]
            _machine_event(
                event_rows, "设备逻辑", f"{column} 非正常状态共 {int(bad.sum())} 行",
                time=first, end_time=last, metric=column, value=int(bad.sum()), level="重点复核",
            )
    segments, sessions, segment_events = _build_machine_segments(frame, cadence or 4.0)
    event_rows.extend(segment_events)
    event_rows.extend(_segment_review_events(segments))
    events = pd.DataFrame(event_rows, columns=MACHINE_EVENT_COLUMNS)
    if not events.empty:
        events["_level"] = events["level"].map({"重点复核": 0, "关注": 1}).fillna(2)
        events = events.sort_values(["_level", "time"], na_position="last").drop(columns="_level").reset_index(drop=True)
    starts, ends = frame["_time"], frame["_time"]
    default_session = sessions.loc[sessions["is_default"]].iloc[0] if not sessions.empty else None
    summary = {
        "files": [path.name for path in files], "file_count": len(files), "rows": len(frame),
        "start": starts.iloc[0] if not starts.empty else None, "end": ends.iloc[-1] if not ends.empty else None,
        "elapsed_seconds": float((ends.iloc[-1] - starts.iloc[0]).total_seconds()) if len(frame) > 1 else 0.0,
        "cadence_seconds": cadence, "max_gap_seconds": float(gaps.max()) if gaps.notna().any() else 0.0,
        "session_count": len(sessions), "segment_count": len(segments),
        "default_session_id": int(default_session["session_id"]) if default_session is not None else None,
        "target_seconds": float(segments["target_seconds"].sum()) if not segments.empty else 0.0,
        "available_metrics": [column for column in MACHINE_NUMERIC_COLUMNS if column in frame],
        "quality_errors": sum(row["severity"] == "错误" for row in quality),
        "quality_warnings": sum(row["severity"] == "警告" for row in quality),
    }
    return summary, sessions, segments, events, frame


def _align_sources(layer_summary: pd.DataFrame, segments: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    summary = layer_summary.copy()
    for suffix in ("mean", "std", "min", "max", "range"):
        summary[f"monitor_motor_{suffix}"] = summary.get(f"motor_{suffix}")
    summary["motor_source"] = "监控log参考值"
    summary["target_power_seconds"] = math.nan
    summary["target_time_delta"] = math.nan
    summary["machine_segment_id"] = math.nan
    reviews: list[dict[str, Any]] = []
    failed = {
        "status": "failed", "confidence": "关联失败", "matched_segments": 0, "candidate_count": 0,
        "duration_correlation": None, "time_offset_seconds": None, "offset_std_seconds": None,
        "reason": "未找到与监控log材料顺序一致的连续工控工作时段。",
    }
    if summary.empty or segments.empty or summary["layer_start"].isna().any():
        failed["reason"] = "镀膜层时间或工控工作时段不足，无法自动关联。"
        reviews.append({"source": "跨源关联", "layer": None, "material": None, "metric": "alignment", "value": None, "level": "重点复核", "reason": failed["reason"]})
        return failed, summary, pd.DataFrame(reviews, columns=CROSS_SOURCE_COLUMNS)
    eligible = segments[segments["material"].isin(["H", "L"])].sort_values("start").reset_index(drop=True)
    target = summary["material"].astype(str).str.strip().tolist()

    def candidate_metrics(monitor: pd.DataFrame, candidate: pd.DataFrame) -> tuple[float, float, float, float]:
        monitor_duration = pd.to_numeric(monitor["actual_time"], errors="coerce").reset_index(drop=True)
        segment_duration = pd.to_numeric(candidate["target_seconds"], errors="coerce").reset_index(drop=True)
        correlation = float(segment_duration.corr(monitor_duration)) if monitor_duration.nunique() > 1 else math.nan
        monitor_start = pd.to_datetime(monitor["layer_start"], errors="coerce").reset_index(drop=True)
        machine_start = pd.to_datetime(candidate["start"], errors="coerce").reset_index(drop=True)
        offsets = (machine_start - monitor_start).dt.total_seconds()
        offset_std = float(offsets.std(ddof=0))
        score = (-1 if not math.isfinite(correlation) else correlation) - offset_std / 1000
        return score, correlation, offset_std, float(offsets.median())

    candidates = []
    for start in range(len(eligible) - len(target) + 1):
        candidate = eligible.iloc[start:start + len(target)]
        if candidate["material"].tolist() != target:
            continue
        candidates.append((*candidate_metrics(summary, candidate), candidate))

    if not candidates and "layer_end" in summary:
        gap_seconds = pd.to_datetime(summary["layer_start"], errors="coerce").sub(
            pd.to_datetime(summary["layer_end"], errors="coerce").shift()
        ).dt.total_seconds()
        monitor_runs = [group.reset_index(drop=True) for _, group in summary.groupby(gap_seconds.ge(300).cumsum())]
        if len(monitor_runs) > 1:
            run_options: list[list[tuple[int, int, pd.DataFrame]]] = []
            for monitor_run in monitor_runs:
                run_target = monitor_run["material"].astype(str).str.strip().tolist()
                options = []
                for start in range(len(eligible) - len(run_target) + 1):
                    candidate = eligible.iloc[start:start + len(run_target)]
                    if candidate["material"].tolist() != run_target:
                        continue
                    if "session_id" in candidate and candidate["session_id"].nunique(dropna=True) > 1:
                        continue
                    options.append((start, start + len(run_target) - 1, candidate))
                if not options:
                    run_options = []
                    break
                run_options.append(options)

            if run_options:
                paths = [([option], option[1], candidate_metrics(monitor_runs[0], option[2])) for option in run_options[0]]
                for run_index in range(1, len(run_options)):
                    monitor_so_far = pd.concat(monitor_runs[:run_index + 1], ignore_index=True)
                    next_paths = []
                    for option in run_options[run_index]:
                        best = None
                        for path, previous_end, _ in paths:
                            if previous_end >= option[0]:
                                continue
                            next_path = path + [option]
                            matched = pd.concat([item[2] for item in next_path], ignore_index=True)
                            metrics = candidate_metrics(monitor_so_far, matched)
                            if best is None or metrics[0] > best[2][0]:
                                best = (next_path, option[1], metrics)
                        if best is not None:
                            next_paths.append(best)
                    paths = next_paths
                    if not paths:
                        break
                candidates.extend(
                    (*metrics, pd.concat([item[2] for item in path], ignore_index=True))
                    for path, _, metrics in paths
                )
    failed["candidate_count"] = len(candidates)
    if not candidates:
        reviews.append({"source": "跨源关联", "layer": None, "material": None, "metric": "alignment", "value": None, "level": "重点复核", "reason": failed["reason"]})
        return failed, summary, pd.DataFrame(reviews, columns=CROSS_SOURCE_COLUMNS)
    _, correlation, offset_std, offset, matched = max(candidates, key=lambda item: item[0])
    if math.isfinite(correlation) and correlation >= 0.98 and offset_std <= 5:
        confidence = "高可信"
    elif math.isfinite(correlation) and correlation >= 0.90 and offset_std <= 15:
        confidence = "中可信"
    else:
        failed.update(
            candidate_count=len(candidates), duration_correlation=correlation,
            time_offset_seconds=offset, offset_std_seconds=offset_std,
            reason="材料顺序匹配，但持续时间相关性或时钟偏移稳定性不足。",
        )
        reviews.append({"source": "跨源关联", "layer": None, "material": None, "metric": "alignment", "value": correlation, "level": "重点复核", "reason": failed["reason"]})
        return failed, summary, pd.DataFrame(reviews, columns=CROSS_SOURCE_COLUMNS)
    matched = matched.copy().reset_index(drop=True)
    matched["layer"] = summary["layer"].astype(int).tolist()
    matched_by_layer = matched.set_index("layer")
    layer_index = summary["layer"]
    for suffix in ("mean", "std", "min", "max", "range"):
        summary[f"motor_{suffix}"] = layer_index.map(matched_by_layer[f"motor_{suffix}"])
    summary["motor_source"] = "工控log"
    summary["target_power_seconds"] = layer_index.map(matched_by_layer["target_seconds"])
    summary["target_time_delta"] = summary["target_power_seconds"] - summary["actual_time"]
    summary["machine_segment_id"] = layer_index.map(matched_by_layer["segment_id"])
    segment_layers = matched.set_index("segment_id")["layer"]
    segments["layer"] = segments["segment_id"].map(segment_layers)
    if confidence == "中可信":
        reviews.append({"source": "跨源关联", "layer": None, "material": None, "metric": "alignment", "value": correlation, "level": "关注", "reason": "关联为中可信，建议核对时间范围。"})
    for metric, minimum_change in (("target_time_delta", 8.0),):
        for material, group in summary.groupby("material"):
            values = pd.to_numeric(group[metric], errors="coerce")
            valid = values.dropna()
            if len(valid) < 5 or valid.nunique() <= 1:
                continue
            median = float(valid.median())
            mad = float((valid - median).abs().median())
            if mad == 0:
                continue
            z = 0.6745 * (values - median) / max(mad, 4.0)
            flagged = z.abs().ge(3.5) & values.sub(median).abs().ge(minimum_change)
            for index in z.index[flagged.fillna(False)]:
                record = group.loc[index]
                reviews.append(
                    {
                        "source": "跨源关联", "layer": int(record["layer"]), "material": material,
                        "metric": metric, "value": float(record[metric]),
                        "level": "重点复核" if abs(float(z.loc[index])) >= 5 else "关注",
                        "reason": "工控靶材工作时间与监控实际镀膜时间之差偏离同材料层。",
                    }
                )
    alignment = {
        "status": "matched", "confidence": confidence, "matched_segments": len(matched),
        "candidate_count": len(candidates), "duration_correlation": correlation,
        "time_offset_seconds": offset, "offset_std_seconds": offset_std,
        "machine_start": matched["start"].min(), "machine_end": matched["end"].max(),
        "reason": "材料顺序、持续时间和时钟偏移满足自动关联条件。",
    }
    return alignment, summary, pd.DataFrame(reviews, columns=CROSS_SOURCE_COLUMNS)


def _annotate_machine_device_data(
    frame: pd.DataFrame, segments: pd.DataFrame, layer_summary: pd.DataFrame,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    data = frame.copy()
    h_active = data["H Power"].fillna(0).gt(0.1)
    l_active = data["L Power"].fillna(0).gt(0.1)
    material = pd.Series(pd.NA, index=data.index, dtype=object)
    material.loc[h_active & ~l_active] = "H"
    material.loc[l_active & ~h_active] = "L"
    material.loc[h_active & l_active] = "H+L"
    data["_source_time"] = data["_time"]
    data["layer"] = pd.Series(pd.NA, index=data.index, dtype="Int64")
    data["material"] = material
    data["method"] = pd.Series(pd.NA, index=data.index, dtype=object)
    linked = segments.dropna(subset=["layer"]).sort_values("start")
    if linked.empty:
        return data
    methods = layer_summary.set_index("layer")["method"].to_dict()
    for segment in linked.itertuples():
        left = int(data["_time"].searchsorted(segment.start, side="left"))
        right = int(data["_time"].searchsorted(segment.end, side="right"))
        if right <= left:
            continue
        indexes = data.index[left:right]
        layer = int(segment.layer)
        data.loc[indexes, "layer"] = layer
        data.loc[indexes, "material"] = segment.material
        data.loc[indexes, "method"] = methods.get(layer)
    return data


def _empty_monitor_result(root: Path) -> AnalysisResult:
    return AnalysisResult(
        {
            "lot_id": root.name.removesuffix("log"), "folder": str(root), "layer_count": 0,
            "h_layers": 0, "l_layers": 0, "oms_layers": 0, "timer_layers": 0,
            "planned_seconds": 0.0, "actual_seconds": 0.0, "machine_elapsed_seconds": None,
            "finished": False, "quality_errors": 0, "quality_warnings": 0,
            "ignored_date_csvs": [], "hidden_summary_metrics": [],
        },
        pd.DataFrame(columns=SUMMARY_COLUMNS), pd.DataFrame(columns=ANOMALY_COLUMNS),
        pd.DataFrame(columns=QUALITY_COLUMNS), pd.DataFrame(columns=["source", "field", "value", "reason"]),
        pd.DataFrame(columns=["family", "layer", "relative_path", "size", "mtime_ns"]), {},
    )


def analyze_folder(
    folder: str | Path,
    progress: Callable[[str, int, int], None] | None = None,
) -> AnalysisResult:
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise AnalysisError(f"文件夹不存在：{root}")
    if progress:
        progress("数据源识别", 0, 0)
    recipes = _recipe_paths(root)
    if len(recipes) > 1:
        raise AnalysisError(f"应找到至多 1 个理论 CSV，实际找到 {len(recipes)} 个")
    machine_quality_rows: list[dict[str, Any]] = []
    machine_files = _discover_machine_files(root, machine_quality_rows)
    monitor_available = len(recipes) == 1
    machine_available = bool(machine_files)
    if not monitor_available and not machine_available:
        invalid_dates = [row for row in machine_quality_rows if row["issue"] == "表头不符合工控log"]
        detail = invalid_dates[0]["detail"] if invalid_dates else "未找到理论 CSV 或有效的 YYYY-MM-DD.csv"
        raise AnalysisError(f"未识别到监控log或工控log：{detail}")

    monitor_progress = progress
    if progress and machine_available:
        monitor_progress = lambda phase, current, total: progress(f"监控log：{phase}", current, total) if phase != "完成" else None
    result = _analyze_monitor_folder(root, monitor_progress) if monitor_available else _empty_monitor_result(root)
    machine_summary: dict[str, Any] = {}
    machine_sessions = pd.DataFrame(columns=MACHINE_SESSION_COLUMNS)
    machine_segments = pd.DataFrame(columns=MACHINE_SEGMENT_COLUMNS)
    machine_events = pd.DataFrame(columns=MACHINE_EVENT_COLUMNS)
    machine_data = pd.DataFrame()
    if machine_available:
        machine_summary, machine_sessions, machine_segments, machine_events, machine_data = _analyze_machine_logs(
            machine_files, machine_quality_rows, progress,
        )
    alignment: dict[str, Any] = {}
    cross_source = pd.DataFrame(columns=CROSS_SOURCE_COLUMNS)
    if monitor_available:
        for suffix in ("mean", "std", "min", "max", "range"):
            result.layer_summary[f"monitor_motor_{suffix}"] = result.layer_summary[f"motor_{suffix}"]
        result.layer_summary["motor_source"] = "监控log参考值"
    if monitor_available and machine_available:
        if progress:
            progress("双源关联", len(result.layer_summary), len(result.layer_summary))
        alignment, result.layer_summary, cross_source = _align_sources(result.layer_summary, machine_segments)
    if machine_available:
        machine_data = _annotate_machine_device_data(machine_data, machine_segments, result.layer_summary)

    machine_quality = pd.DataFrame(machine_quality_rows, columns=QUALITY_COLUMNS)
    if machine_available:
        machine_file_rows = []
        for path in machine_files:
            stat = path.stat()
            machine_file_rows.append(
                {"family": "machine_log", "layer": math.nan, "relative_path": path.name, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            )
        result.file_index = pd.concat([result.file_index, pd.DataFrame(machine_file_rows)], ignore_index=True)
        result.file_index = result.file_index.sort_values(["family", "layer"], na_position="last").reset_index(drop=True)
    result.sources = {"monitor": monitor_available, "machine": machine_available, "combined": monitor_available and machine_available}
    result.machine_summary = machine_summary
    result.machine_sessions = machine_sessions
    result.machine_segments = machine_segments
    result.machine_events = machine_events
    result.machine_quality = machine_quality
    result.alignment = alignment
    result.cross_source_review = cross_source
    result.machine_data = machine_data
    result.batch_summary["sources"] = result.sources
    result.batch_summary["machine_log_files"] = machine_summary.get("files", [])
    result.batch_summary["ignored_date_csvs"] = []
    result.batch_summary["machine_quality_errors"] = int((machine_quality["severity"] == "错误").sum()) if not machine_quality.empty else 0
    result.batch_summary["machine_quality_warnings"] = int((machine_quality["severity"] == "警告").sum()) if not machine_quality.empty else 0
    if progress:
        total = len(result.layer_summary) if monitor_available else len(machine_files)
        progress("完成", total, total)
    return result


def _group_label(keys: Any, columns: list[str]) -> str:
    if not isinstance(keys, tuple):
        keys = (keys,)
    return ", ".join(f"{column}={value}" for column, value in zip(columns, keys))


def detect_anomalies(layer_summary: pd.DataFrame, threshold: float = 3.5) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    metric_groups = [(OPTICAL_METRICS, ["material", "method"]), (DEVICE_METRICS, ["material"])]
    for metrics, group_columns in metric_groups:
        for metric in metrics:
            if metric not in layer_summary:
                continue
            for keys, group in layer_summary.groupby(group_columns, dropna=False):
                values = pd.to_numeric(group[metric], errors="coerce")
                valid = values.dropna()
                if len(valid) < 5:
                    continue
                median = float(valid.median())
                mad = float((valid - median).abs().median())
                if not math.isfinite(mad) or mad == 0:
                    continue
                robust_z = 0.6745 * (values - median) / mad
                for index in robust_z.index[robust_z.abs().ge(threshold).fillna(False)]:
                    record = group.loc[index]
                    z_value = float(robust_z.loc[index])
                    rows.append(
                        {
                            "layer": int(record["layer"]),
                            "material": record["material"],
                            "method": record["method"],
                            "metric": metric,
                            "value": float(record[metric]),
                            "change": math.nan,
                            "group": _group_label(keys, group_columns),
                            "baseline": median,
                            "mad": mad,
                            "robust_z": z_value,
                            "level": "重点复核" if abs(z_value) >= 5 else "关注",
                            "reason": f"组内偏离中位数，|robust z| ≥ {threshold:.1f}",
                        }
                    )

                ordered = group.sort_values("layer")
                changes = pd.to_numeric(ordered[metric], errors="coerce").diff()
                valid_changes = changes.dropna()
                if len(valid_changes) < 5:
                    continue
                change_median = float(valid_changes.median())
                change_mad = float((valid_changes - change_median).abs().median())
                if not math.isfinite(change_mad) or change_mad == 0:
                    continue
                change_z = 0.6745 * (changes - change_median) / change_mad
                for index in change_z.index[change_z.abs().ge(threshold).fillna(False)]:
                    record = ordered.loc[index]
                    z_value = float(change_z.loc[index])
                    rows.append(
                        {
                            "layer": int(record["layer"]),
                            "material": record["material"],
                            "method": record["method"],
                            "metric": metric,
                            "value": float(record[metric]),
                            "change": float(changes.loc[index]),
                            "group": _group_label(keys, group_columns),
                            "baseline": change_median,
                            "mad": change_mad,
                            "robust_z": z_value,
                            "level": "重点复核" if abs(z_value) >= 5 else "关注",
                            "reason": f"同组相邻层突变，|robust z| ≥ {threshold:.1f}",
                        }
                    )
    if not rows:
        return pd.DataFrame(columns=ANOMALY_COLUMNS)
    result = pd.DataFrame(rows, columns=ANOMALY_COLUMNS)
    result["_level"] = result["level"].map({"重点复核": 0, "关注": 1})
    return result.sort_values(["_level", "robust_z"], ascending=[True, False], key=lambda column: column.abs() if column.name == "robust_z" else column).drop(columns="_level").reset_index(drop=True)


def compute_correlations(layer_summary: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    targets = [metric for metric in ["fit_end_residual", "recipe_end_offset", "fit_mae", "fit_p95_abs", "signal_cv"] if metric in layer_summary]
    drivers = [
        metric
        for metric in [
            "phy_thick",
            "recipe_rate",
            "actual_rate",
            "rate_delta",
            "planned_time",
            "actual_time",
            "power_mean",
            "power_std",
            "current_mean",
            "voltage_mean",
            "vacuum_mean",
            "vacuum_std",
            "chamber_temp_mean",
            "water_in_mean",
            "water_out_mean",
            "motor_mean",
            "o2_mean",
        ]
        if metric in layer_summary
    ]
    rows = []
    for material, group in layer_summary.groupby("material"):
        for target in targets:
            for driver in drivers:
                pair = group[[target, driver]].apply(pd.to_numeric, errors="coerce").dropna()
                if len(pair) < 20 or pair[target].nunique() <= 1 or pair[driver].nunique() <= 1:
                    continue
                ranked = pair.rank(method="average")
                correlation = ranked[target].corr(ranked[driver])
                if pd.notna(correlation):
                    rows.append(
                        {
                            "material": material,
                            "target": target,
                            "driver": driver,
                            "spearman": float(correlation),
                            "abs_spearman": abs(float(correlation)),
                            "samples": len(pair),
                        }
                    )
    if not rows:
        return pd.DataFrame(columns=["material", "target", "driver", "spearman", "abs_spearman", "samples"])
    return pd.DataFrame(rows).sort_values("abs_spearman", ascending=False).head(limit).reset_index(drop=True)


def load_layer_detail(folder: str | Path, layer: int) -> dict[str, Any]:
    root = Path(folder).expanduser().resolve()
    power = root / "CoatingPower"
    meas_map, _ = _discover_numbered(power, NUMBERED_PATTERNS["meas"], "meas", [])
    machine_map, _ = _discover_numbered(power, NUMBERED_PATTERNS["machine"], "machine", [])
    calc_map, _ = _discover_numbered(root / "CoatingCalc", NUMBERED_PATTERNS["calc"], "calc", [])
    image_map, _ = _discover_numbered(root / "CoatingImage", NUMBERED_PATTERNS["image"], "image", [])
    if layer not in meas_map:
        raise AnalysisError(f"缺少第 {layer} 层 MeasPower 文件")
    meas = pd.read_csv(meas_map[layer], encoding="utf-8-sig", low_memory=False)
    for column in ["SamTime", "MeasVal(1)", "CalcVal(1)", "S_ignals(1)", "ToZero(1)"]:
        if column in meas:
            meas[column] = pd.to_numeric(meas[column], errors="coerce")
    calc = pd.DataFrame(columns=["thickness", "calculated_t"])
    if layer in calc_map:
        calc = pd.read_csv(calc_map[layer], header=None, names=["thickness", "calculated_t"], encoding="utf-8-sig")
        calc = calc.apply(pd.to_numeric, errors="coerce")
    machine = pd.DataFrame()
    if layer in machine_map:
        machine = pd.read_csv(machine_map[layer], encoding="utf-8-sig", low_memory=False)
    return {
        "meas": meas,
        "calc": calc,
        "machine": machine,
        "image_path": str(image_map[layer]) if layer in image_map else None,
    }


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")
