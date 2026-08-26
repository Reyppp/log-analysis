from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


DATE_CSV_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.csv$", re.IGNORECASE)
AUXILIARY_CSV_RE = re.compile(r"(?:^Extrm\.csv$|_BaseLine\.csv$)", re.IGNORECASE)
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
        if path.parent == root and (DATE_CSV_RE.match(path.name) or AUXILIARY_CSV_RE.search(path.name)):
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


def _convert_numeric(frame: pd.DataFrame, columns: list[str], scope: str, layer: int, quality: list[dict[str, Any]]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        raw = result[column]
        converted = pd.to_numeric(raw, errors="coerce")
        invalid = raw.notna() & raw.astype(str).str.strip().ne("") & converted.isna()
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
    values = pd.to_numeric(series, errors="coerce").dropna()
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


def _find_recipe(root: Path) -> tuple[Path, pd.DataFrame]:
    candidates: list[tuple[Path, pd.DataFrame]] = []
    for path in root.iterdir():
        if not path.is_file() or path.suffix.lower() != ".csv" or DATE_CSV_RE.match(path.name) or AUXILIARY_CSV_RE.search(path.name):
            continue
        try:
            header = pd.read_csv(path, encoding="utf-8-sig", nrows=1)
        except Exception:
            continue
        if {"Layer#", "Material", "Method"}.issubset(header.columns):
            candidates.append((path, pd.read_csv(path, encoding="utf-8-sig", low_memory=False)))
    if len(candidates) != 1:
        raise AnalysisError(f"应找到 1 个理论 CSV，实际找到 {len(candidates)} 个")
    return candidates[0]


def _track_fields(profile: dict[str, set[str]], source: str, frame: pd.DataFrame) -> None:
    for column in frame.columns:
        key = f"{source}.{column}"
        values = profile.setdefault(key, set())
        if len(values) >= 2:
            continue
        for value in pd.unique(frame[column].dropna().astype(str)):
            values.add(value)
            if len(values) >= 2:
                break


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


def analyze_folder(folder: str | Path) -> AnalysisResult:
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise AnalysisError(f"文件夹不存在：{root}")

    quality: list[dict[str, Any]] = []
    profile: dict[str, set[str]] = {}
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

    for recipe_row in recipe.to_dict("records"):
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

        summaries.append(row)

    layer_summary = pd.DataFrame(summaries).sort_values("layer").reset_index(drop=True)
    for column in SUMMARY_COLUMNS:
        if column not in layer_summary:
            layer_summary[column] = math.nan
    layer_summary = layer_summary[SUMMARY_COLUMNS]
    log_paths = sorted((root / "CoatingLog").glob("*.log")) if (root / "CoatingLog").is_dir() else []
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
    anomalies = detect_anomalies(layer_summary, 3.5)
    return AnalysisResult(batch_summary, layer_summary, anomalies, data_quality, constant_fields, file_index, events)


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
