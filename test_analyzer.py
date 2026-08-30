import os
import tempfile
import threading
import unittest
import json
import urllib.request
from urllib.error import HTTPError
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from analyzer import (
    AnalysisError,
    SUMMARY_COLUMNS,
    _align_sources,
    analyze_folder,
    compute_correlations,
    csv_bytes,
    detect_anomalies,
    parse_mixed_datetime,
    source_fingerprint,
)
import server
import desktop


GOLDEN_PATH = os.environ.get("LOG_ANALYSIS_GOLDEN_FOLDER")
GOLDEN_FOLDER = Path(GOLDEN_PATH) if GOLDEN_PATH else None


class AnalyzerTests(unittest.TestCase):
    def test_mixed_clock(self):
        self.assertEqual(parse_mixed_datetime("2026-08-20  13:00:00 PM"), datetime(2026, 8, 20, 13, 0, 0))
        self.assertEqual(parse_mixed_datetime("2026-08-20  01:00:00 PM"), datetime(2026, 8, 20, 13, 0, 0))
        self.assertEqual(parse_mixed_datetime("2026-08-20  12:00:00 AM"), datetime(2026, 8, 20, 0, 0, 0))

    def test_date_csv_is_included_in_fingerprint(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "2026-08-20.csv").write_text("ignored", encoding="utf-8")
            (root / "Extrm.csv").write_text("ignored", encoding="utf-8")
            (root / "test_BaseLine.csv").write_text("ignored", encoding="utf-8")
            (root / "recipe.csv").write_text("kept", encoding="utf-8")
            files = [item[0] for item in source_fingerprint(root)]
            self.assertEqual(files, ["2026-08-20.csv", "recipe.csv"])

    def test_machine_log_can_be_analyzed_without_monitor_log(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rows = []
            for time, h_power, l_power in [
                ("2026-08-20  00:00:00 AM", 3.2, 0),
                ("2026-08-20  00:00:04 AM", 3.2, 0),
                ("2026-08-20  00:00:08 AM", 0, 0),
                ("2026-08-20  00:06:00 AM", 0, 3.1),
                ("2026-08-20  00:06:04 AM", 0, 3.1),
            ]:
                rows.append(
                    {
                        "Time": time, "H Power": h_power, "H Current": h_power, "H Voltage": 900,
                        "L Power": l_power, "L Current": l_power, "L Voltage": 900, "Motor Speed": 280,
                    }
                )
            pd.DataFrame(rows).to_csv(root / "2026-08-20.csv", index=False)
            result = analyze_folder(root)
            self.assertEqual(result.sources, {"monitor": False, "machine": True, "combined": False})
            self.assertTrue(result.layer_summary.empty)
            self.assertEqual(len(result.machine_segments), 2)
            self.assertEqual(len(result.machine_sessions), 2)
            self.assertEqual(result.machine_summary["default_session_id"], 1)

    def test_machine_series_accepts_browser_utc_time_range(self):
        local_zone = datetime.now().astimezone().tzinfo
        times = pd.date_range("2026-08-20 19:30:00", periods=3, freq="4s")
        start = times[0].tz_localize(local_zone).tz_convert("UTC").isoformat()
        end = times[-1].tz_localize(local_zone).tz_convert("UTC").isoformat()
        result = SimpleNamespace(
            machine_data=pd.DataFrame({"_time": times, "H Power": [3.1, 3.2, 3.3]}),
            machine_summary={"available_metrics": ["H Power"], "default_session_id": None},
            machine_sessions=pd.DataFrame(),
        )

        series = server.machine_series(result, ["H Power"], start=start, end=end)

        self.assertEqual(series["rows"], 3)
        self.assertEqual(series["returned"], 3)

    def test_device_time_series_uses_real_points_on_monitor_timeline(self):
        monitor_start = pd.Timestamp("2026-08-20 12:00:00")
        machine_start = monitor_start + pd.Timedelta(seconds=200)
        machine = pd.DataFrame(
            {
                "_time": [machine_start, machine_start + pd.Timedelta(seconds=4), machine_start + pd.Timedelta(seconds=8)],
                "_source_time": [machine_start, machine_start + pd.Timedelta(seconds=4), machine_start + pd.Timedelta(seconds=8)],
                "layer": pd.Series([1, 1, 1], dtype="Int64"),
                "material": ["H", "H", "H"], "method": ["OMS", "OMS", "OMS"],
                "H Power": [3.1, 3.3, 3.5], "L Power": [0.0, 0.0, 0.0],
            }
        )
        monitor = pd.DataFrame(
            {
                "_time": [monitor_start + pd.Timedelta(seconds=index * 2) for index in range(5)],
                "_source_time": [monitor_start + pd.Timedelta(seconds=index * 2) for index in range(5)],
                "layer": pd.Series([1] * 5, dtype="Int64"), "material": ["H"] * 5,
                "method": ["OMS"] * 5, "H Power": [2.9, 3.0, 3.1, 3.2, 3.3], "L Power": [0.0] * 5,
            }
        )
        result = SimpleNamespace(
            machine_data=machine, monitor_device_data=monitor,
            machine_sessions=pd.DataFrame(),
            alignment={"status": "matched", "time_offset_seconds": 200.0},
        )

        series = server.device_time_series(
            result, "power_mean", ["machine", "monitor"], 1, 1, ["H"], ["OMS"], "all", 2500,
            detail="full",
        )

        machine_trace = next(item for item in series["traces"] if item["source"] == "machine")
        monitor_trace = next(item for item in series["traces"] if item["source"] == "monitor")
        self.assertEqual(machine_trace["value"], [3.1, 3.3, 3.5])
        self.assertEqual(monitor_trace["value"], [2.9, 3.0, 3.1, 3.2, 3.3])
        self.assertEqual(machine_trace["source_time"][0], "2026-08-20T12:03:20")
        self.assertEqual(monitor_trace["source_time"][0], "2026-08-20T12:00:00")
        self.assertEqual(machine_trace["time"][0], "2026-08-20T12:00:00")
        self.assertEqual(monitor_trace["time"][0], "2026-08-20T12:00:00")
        self.assertEqual(series["coverage"], "full")
        self.assertEqual(series["rows"], {"machine": 3, "monitor": 5})
        self.assertEqual(series["returned"], {"machine": 3, "monitor": 5})
        self.assertEqual(series["boundaries"][0]["layer"], 1)

    def test_device_time_series_mean_returns_one_point_per_layer_and_source(self):
        monitor_start = pd.Timestamp("2026-08-20 12:00:00")
        machine_start = monitor_start + pd.Timedelta(seconds=200)
        machine_times = [machine_start + pd.Timedelta(seconds=value) for value in (0, 4, 8, 12)]
        monitor_times = [monitor_start + pd.Timedelta(seconds=value) for value in (0, 2, 4, 6)]
        machine = pd.DataFrame(
            {
                "_time": machine_times, "_source_time": machine_times,
                "layer": pd.Series([1, 1, 2, 2], dtype="Int64"),
                "material": ["H", "H", "L", "L"], "method": ["OMS", "OMS", "Timer", "Timer"],
                "H Power": [3.0, 4.0, 0.0, 0.0], "L Power": [0.0, 0.0, 5.0, 7.0],
            }
        )
        monitor = pd.DataFrame(
            {
                "_time": monitor_times, "_source_time": monitor_times,
                "layer": pd.Series([1, 1, 2, 2], dtype="Int64"),
                "material": ["H", "H", "L", "L"], "method": ["OMS", "OMS", "Timer", "Timer"],
                "H Power": [2.0, 4.0, 0.0, 0.0], "L Power": [0.0, 0.0, 6.0, 8.0],
            }
        )
        result = SimpleNamespace(
            machine_data=machine, monitor_device_data=monitor,
            machine_summary={"cadence_seconds": 4}, machine_sessions=pd.DataFrame(),
            alignment={"status": "matched", "time_offset_seconds": 200.0},
        )

        series = server.device_time_series(
            result, "power_mean", ["machine", "monitor"], 1, 2, ["H", "L"], ["OMS", "Timer"], "all",
            detail="mean",
        )

        self.assertEqual(series["coverage"], "mean")
        self.assertFalse(series["exact"])
        machine_trace = next(item for item in series["traces"] if item["source"] == "machine")
        monitor_trace = next(item for item in series["traces"] if item["source"] == "monitor")
        self.assertEqual(machine_trace["value"], [3.5, None, 6.0])
        self.assertEqual(monitor_trace["value"], [3.0, None, 7.0])
        self.assertEqual(machine_trace["time"], ["2026-08-20T12:00:02", None, "2026-08-20T12:00:10"])
        self.assertEqual(machine_trace["start_time"][0], "2026-08-20T12:00:00")
        self.assertEqual(machine_trace["end_time"][0], "2026-08-20T12:00:04")
        self.assertEqual(series["returned"], {"machine": 2, "monitor": 2})

    def test_device_time_series_single_material_hides_all_inactive_rows(self):
        start = pd.Timestamp("2026-08-20 12:00:00")
        times = [start + pd.Timedelta(seconds=index * 4) for index in range(7)]
        machine = pd.DataFrame(
            {
                "_time": times, "_source_time": times,
                "layer": pd.Series([1, pd.NA, 2, 2, pd.NA, 3, 3], dtype="Int64"),
                "material": ["H", pd.NA, "L", "L", pd.NA, "H+L", "H"],
                "method": ["OMS", pd.NA, "OMS", "OMS", pd.NA, "OMS", "OMS"],
                "H Power": [3.0, 0.0, 0.0, 0.0, 0.0, 2.0, 3.0],
                "L Power": [0.0, 0.0, 3.0, 3.0, 0.0, 2.5, 0.0],
            }
        )
        result = SimpleNamespace(
            machine_data=machine, monitor_device_data=pd.DataFrame(),
            machine_summary={"cadence_seconds": 4}, machine_sessions=pd.DataFrame(),
            alignment={"status": "failed", "time_offset_seconds": None},
        )

        filters = {"layer_min": 1, "layer_max": 3, "methods": ["OMS"], "detail": "full"}
        h_series = server.device_time_series(result, "power_mean", ["machine"], materials=["H"], **filters)
        l_series = server.device_time_series(result, "power_mean", ["machine"], materials=["L"], **filters)
        both_series = server.device_time_series(result, "power_mean", ["machine"], materials=["H", "L"], **filters)

        self.assertEqual(h_series["time_breaks"], [{"start": "2026-08-20T12:00:04", "end": "2026-08-20T12:00:20"}])
        self.assertEqual(l_series["time_breaks"], [
            {"start": "2026-08-20T12:00:00", "end": "2026-08-20T12:00:08"},
            {"start": "2026-08-20T12:00:16", "end": "2026-08-20T12:00:20"},
            {"start": "2026-08-20T12:00:24", "end": "2026-08-20T12:00:28"},
        ])
        self.assertEqual(both_series["time_breaks"], [])
        self.assertEqual(h_series["rows"]["machine"], 3)
        self.assertEqual(l_series["rows"]["machine"], 3)
        self.assertEqual(both_series["rows"]["machine"], 5)
        self.assertEqual(h_series["returned"]["machine"], 3)
        self.assertEqual(l_series["returned"]["machine"], 3)
        self.assertEqual(both_series["returned"]["machine"], 6)
        h_trace = h_series["traces"][0]
        self.assertNotIn("2026-08-20T12:00:04", h_trace["source_time"])
        self.assertNotIn("2026-08-20T12:00:16", h_trace["source_time"])
        self.assertIn("H+L", h_trace["material"])
        self.assertEqual([value for value in h_trace["value"] if value is not None], [3.0, 2.0, 3.0])

    def test_device_time_series_full_range_and_large_range_fallback(self):
        start = pd.Timestamp("2026-08-20 12:00:00")
        short_times = pd.date_range(start, periods=4, freq="4s")
        short_result = SimpleNamespace(
            machine_data=pd.DataFrame(
                {
                    "_time": short_times, "_source_time": short_times,
                    "layer": pd.Series([1, 1, 1, 1], dtype="Int64"),
                    "material": ["H"] * 4, "method": ["OMS"] * 4,
                    "H Power": [3.0, 3.1, 3.2, 3.3], "L Power": [0.0] * 4,
                }
            ),
            monitor_device_data=pd.DataFrame(), machine_summary={"cadence_seconds": 4},
            machine_sessions=pd.DataFrame(), alignment={"status": "failed", "time_offset_seconds": None},
        )
        full = server.device_time_series(
            short_result, "power_mean", ["machine"], materials=["H"], detail="full",
            start="2026-08-20T12:00:04", end="2026-08-20T12:00:12",
        )
        self.assertEqual(full["coverage"], "full")
        self.assertTrue(full["full_available"])
        self.assertEqual(full["rows"]["machine"], 3)
        self.assertEqual(full["returned"]["machine"], 3)
        self.assertEqual(full["traces"][0]["value"], [3.1, 3.2, 3.3])

        long_times = pd.date_range(start, periods=10001, freq="4s")
        long_result = SimpleNamespace(
            machine_data=pd.DataFrame(
                {
                    "_time": long_times, "_source_time": long_times,
                    "layer": pd.Series([1] * 10001, dtype="Int64"),
                    "material": ["H"] * 10001, "method": ["OMS"] * 10001,
                    "H Power": [3.0] * 10001, "L Power": [0.0] * 10001,
                }
            ),
            monitor_device_data=pd.DataFrame(), machine_summary={"cadence_seconds": 4},
            machine_sessions=pd.DataFrame(), alignment={"status": "failed", "time_offset_seconds": None},
        )
        fallback = server.device_time_series(
            long_result, "power_mean", ["machine"], materials=["H"], detail="full", max_points=2500,
        )
        self.assertEqual(fallback["coverage"], "overview")
        self.assertFalse(fallback["full_available"])
        self.assertEqual(fallback["limit_per_source"], 2500)
        self.assertEqual(fallback["rows"]["machine"], 10001)
        self.assertLess(fallback["returned"]["machine"], 10001)

        capped = server.device_time_series(
            long_result, "power_mean", ["machine"], materials=["H"], detail="overview", max_points=20000,
        )
        self.assertGreater(capped["returned"]["machine"], fallback["returned"]["machine"])
        self.assertLessEqual(capped["returned"]["machine"], 8000)

        monitor_times = pd.date_range(start, periods=3, freq="2s")
        long_result.monitor_device_data = pd.DataFrame(
            {
                "_time": monitor_times, "_source_time": monitor_times,
                "layer": pd.Series([1, 1, 1], dtype="Int64"),
                "material": ["H"] * 3, "method": ["OMS"] * 3,
                "H Power": [2.9, 3.0, 3.1], "L Power": [0.0] * 3,
            }
        )
        long_result.alignment = {"status": "matched", "time_offset_seconds": 0.0}
        mixed = server.device_time_series(
            long_result, "power_mean", ["machine", "monitor"], materials=["H"], detail="full", max_points=2500,
        )
        self.assertEqual(mixed["coverage"], "overview")
        self.assertEqual(mixed["source_coverage"]["machine"]["coverage"], "overview")
        self.assertEqual(mixed["source_coverage"]["monitor"]["coverage"], "overview")
        self.assertIn("10,004", mixed["full_unavailable_reason"])
        self.assertLess(mixed["returned"]["machine"], 10001)
        self.assertEqual(mixed["returned"]["monitor"], 3)

        balanced_machine_times = pd.date_range(start, periods=6001, freq="4s")
        balanced_monitor_times = pd.date_range(start, periods=6001, freq="2s")
        balanced = SimpleNamespace(
            machine_data=pd.DataFrame(
                {
                    "_time": balanced_machine_times, "_source_time": balanced_machine_times,
                    "layer": pd.Series([1] * 6001, dtype="Int64"), "material": ["H"] * 6001,
                    "method": ["OMS"] * 6001, "H Power": [3.0] * 6001, "L Power": [0.0] * 6001,
                }
            ),
            monitor_device_data=pd.DataFrame(
                {
                    "_time": balanced_monitor_times, "_source_time": balanced_monitor_times,
                    "layer": pd.Series([1] * 6001, dtype="Int64"), "material": ["H"] * 6001,
                    "method": ["OMS"] * 6001, "H Power": [3.0] * 6001, "L Power": [0.0] * 6001,
                }
            ),
            machine_summary={"cadence_seconds": 4}, machine_sessions=pd.DataFrame(),
            alignment={"status": "matched", "time_offset_seconds": 0.0},
        )
        total_limited = server.device_time_series(
            balanced, "power_mean", ["machine", "monitor"], materials=["H"], detail="full",
        )
        self.assertFalse(total_limited["full_available"])
        self.assertEqual(total_limited["limit_total"], 2500)
        self.assertIn("2,500", total_limited["full_unavailable_reason"])

        fragmented_times = pd.date_range(start, periods=600, freq="4s")
        fragmented = SimpleNamespace(
            machine_data=pd.DataFrame(
                {
                    "_time": fragmented_times, "_source_time": fragmented_times,
                    "layer": pd.Series(range(1, 601), dtype="Int64"),
                    "material": ["H"] * 600, "method": ["OMS"] * 600,
                    "H Power": [3.0 + (index % 5) / 10 for index in range(600)], "L Power": [0.0] * 600,
                }
            ),
            monitor_device_data=pd.DataFrame(), machine_summary={"cadence_seconds": 4},
            machine_sessions=pd.DataFrame(), alignment={"status": "failed", "time_offset_seconds": None},
        )
        bounded = server.device_time_series(
            fragmented, "power_mean", ["machine"], materials=["H", "L"], detail="overview", max_points=200,
        )
        self.assertLessEqual(bounded["returned"]["machine"], 200)

    def test_device_time_series_caps_all_visible_markers_at_8000(self):
        start = pd.Timestamp("2026-08-20 12:00:00")
        rows = 3000
        machine_times = pd.date_range(start + pd.Timedelta(seconds=200), periods=rows, freq="4s")
        monitor_times = pd.date_range(start, periods=rows, freq="2s")

        def frame(times, base):
            return pd.DataFrame(
                {
                    "_time": times, "_source_time": times,
                    "layer": pd.Series([1] * rows, dtype="Int64"), "material": ["H"] * rows,
                    "method": ["OMS"] * rows, "H Power": [3.0] * rows, "L Power": [0.0] * rows,
                    "Gas-O2(1)": [base + index / 1000 for index in range(rows)],
                    "Gas-O2(4)": [base + 10 + index / 1000 for index in range(rows)],
                }
            )

        result = SimpleNamespace(
            machine_data=frame(machine_times, 1), monitor_device_data=frame(monitor_times, 2),
            machine_summary={"cadence_seconds": 4}, machine_sessions=pd.DataFrame(),
            alignment={"status": "matched", "time_offset_seconds": 200.0},
        )
        series = server.device_time_series(
            result, "o2_mean", ["machine", "monitor"], materials=["H"], detail="overview", max_points=8000,
        )

        self.assertLessEqual(sum(series["returned"].values()), 8000)
        self.assertGreater(sum(series["returned"].values()), 7000)
        self.assertLessEqual(abs(series["returned"]["machine"] - series["returned"]["monitor"]), 1)
        self.assertEqual(series["limit_total"], 8000)
        for trace in series["traces"]:
            source_frame = result.machine_data if trace["source"] == "machine" else result.monitor_device_data
            originals = set(source_frame[trace["channel"]].astype(float))
            self.assertTrue(all(value is None or value in originals for value in trace["value"]))

        result.machine_data["material"] = "H+L"
        result.machine_data["H Power"] = 3.0
        result.machine_data["L Power"] = 2.0
        material_series = server.device_time_series(
            result, "power_mean", ["machine", "monitor"], materials=["H", "L"], detail="overview", max_points=8000,
        )
        self.assertLessEqual(sum(material_series["returned"].values()), 8000)

    def test_combined_alignment_overrides_motor_and_keeps_reference(self):
        start = pd.Timestamp("2026-08-20 12:00:00")
        materials = ["H", "L", "H", "L", "H", "L"]
        monitor = pd.DataFrame(
            {
                "layer": range(1, 7), "material": materials,
                "layer_start": [start + pd.Timedelta(seconds=index * 120) for index in range(6)],
                "actual_time": [80, 90, 100, 110, 120, 130],
                **{f"motor_{suffix}": [1280.0] * 6 for suffix in ("mean", "std", "min", "max", "range")},
            }
        )
        segments = pd.DataFrame(
            [
                {"segment_id": 1, "material": "L", "start": start, "end": start, "target_seconds": 20, **{f"motor_{suffix}": 280.0 for suffix in ("mean", "std", "min", "max", "range")}},
                *[
                    {
                        "segment_id": index + 2, "material": material,
                        "start": start + pd.Timedelta(seconds=index * 120 + 205),
                        "end": start + pd.Timedelta(seconds=index * 120 + 205 + duration + 23),
                        "target_seconds": duration + 23,
                        **{f"motor_{suffix}": 280.0 for suffix in ("mean", "std", "min", "max", "range")},
                    }
                    for index, (material, duration) in enumerate(zip(materials, [80, 90, 100, 110, 120, 130]))
                ],
            ]
        )
        alignment, combined, _ = _align_sources(monitor, segments)
        self.assertEqual(alignment["confidence"], "高可信")
        self.assertEqual(alignment["matched_segments"], 6)
        self.assertEqual(set(combined["motor_source"]), {"工控log"})
        self.assertEqual(set(combined["motor_mean"]), {280.0})
        self.assertEqual(set(combined["monitor_motor_mean"]), {1280.0})

    def test_combined_alignment_skips_non_coating_segments_between_monitor_runs(self):
        start = pd.Timestamp("2026-06-15 21:00:00")
        groups = [
            (["L", "H", "L", "H"], [80, 90, 100, 110], 0),
            (["L", "H"], [120, 130], 3600),
            (["L", "H", "L"], [140, 150, 160], 7200),
        ]
        monitor_rows = []
        segment_rows = []
        segment_id = 1
        layer = 1
        for session_id, (materials, durations, group_offset) in enumerate(groups, start=1):
            cursor = start + pd.Timedelta(seconds=group_offset)
            if session_id > 1:
                for extra_index, material in enumerate(["H", "L", "L", "H", "L", "L"]):
                    extra_start = cursor + pd.Timedelta(seconds=30 + extra_index * 24)
                    segment_rows.append(
                        {
                            "segment_id": segment_id, "session_id": session_id, "material": material,
                            "start": extra_start, "end": extra_start + pd.Timedelta(seconds=16),
                            "target_seconds": 20,
                            **{f"motor_{suffix}": 999.0 for suffix in ("mean", "std", "min", "max", "range")},
                        }
                    )
                    segment_id += 1
            for material, duration in zip(materials, durations):
                monitor_rows.append(
                    {
                        "layer": layer, "material": material, "layer_start": cursor,
                        "layer_end": cursor + pd.Timedelta(seconds=duration), "actual_time": duration,
                        **{f"motor_{suffix}": 1280.0 for suffix in ("mean", "std", "min", "max", "range")},
                    }
                )
                machine_start = cursor + pd.Timedelta(seconds=210)
                segment_rows.append(
                    {
                        "segment_id": segment_id, "session_id": session_id, "material": material,
                        "start": machine_start, "end": machine_start + pd.Timedelta(seconds=duration - 4),
                        "target_seconds": duration,
                        **{f"motor_{suffix}": 280.0 for suffix in ("mean", "std", "min", "max", "range")},
                    }
                )
                segment_id += 1
                layer += 1
                cursor += pd.Timedelta(seconds=duration + 20)

        alignment, combined, _ = _align_sources(
            pd.DataFrame(monitor_rows), pd.DataFrame(segment_rows).sort_values("start").reset_index(drop=True)
        )

        self.assertEqual(alignment["confidence"], "高可信")
        self.assertEqual(alignment["matched_segments"], 9)
        self.assertAlmostEqual(alignment["time_offset_seconds"], 210.0)
        self.assertEqual(set(combined["motor_mean"]), {280.0})
        self.assertNotIn(999.0, combined["motor_mean"].tolist())

    def test_robust_anomaly_and_constant_skip(self):
        frame = pd.DataFrame(
            {
                "layer": range(1, 13),
                "material": ["H"] * 6 + ["L"] * 6,
                "method": ["OMS"] * 12,
                "fit_mae": [1, 2, 3, 4, 5, 100, 7, 7, 7, 7, 7, 7],
                "power_mean": [2.7] * 6 + [3.2] * 6,
            }
        )
        anomalies = detect_anomalies(frame, 3.5)
        self.assertEqual({6}, set(anomalies.loc[anomalies["metric"] == "fit_mae", "layer"]))
        self.assertNotIn("power_mean", anomalies["metric"].tolist())

    def test_incomplete_folder_returns_quality_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pd.DataFrame(
                [{"Layer#": 1, "Material": "H", "PhyThick": 10, "Rate": 0.2, "Time": 50,
                  "Start T": 0.1, "End T": 0.2, "Extreme#": 1, "Method": "OMS"}]
            ).to_csv(root / "recipe.csv", index=False)
            result = analyze_folder(root)
            self.assertEqual(len(result.layer_summary), 1)
            self.assertGreater(result.batch_summary["quality_errors"], 0)
            self.assertIn("final_meas", result.layer_summary.columns)

    def test_csv_download_has_utf8_bom(self):
        self.assertTrue(csv_bytes(pd.DataFrame({"材料": ["高折"]})).startswith(b"\xef\xbb\xbf"))

    def test_removed_exports_are_rejected(self):
        result = SimpleNamespace(layer_summary=pd.DataFrame())
        for kind in ("machine_events", "combined_summary", "cross_source"):
            with self.assertRaises(AnalysisError):
                server.export_frame(result, kind)

    def test_html_has_folder_picker_layer_navigation_and_smooth_device_curve(self):
        html = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
        self.assertIn("选择日志文件夹", html)
        self.assertIn('id="prev">前一层', html)
        self.assertIn('id="next">后一层', html)
        self.assertIn("shape:smooth?'spline':'linear'", html)
        self.assertIn('id="anomaly-metric"', html)
        self.assertNotIn('id="correlation-target"', html)
        self.assertNotIn("Spearman", html)
        self.assertIn('id="image-prev">前一层', html)
        self.assertIn('id="image-next">后一层', html)
        self.assertIn("监控方式", html)
        self.assertNotIn("终止方式", html)
        self.assertIn("location.protocol==='file:'", html)
        self.assertNotIn("Failed to fetch", html)
        self.assertIn("工控log", html)
        self.assertNotIn("机台Log", html)
        self.assertIn("监控log", html)
        self.assertIn("combined-overview", html)
        self.assertIn("['combined-device','设备']", html)
        self.assertIn("s.combined?['combined','monitor','machine']", html)
        self.assertNotIn("pageHeader('设备对照'", html)
        self.assertIn("整炉工控log结构与时间质量", html)
        self.assertIn("检查完成：未发现文件、表头、数值或时间连续性问题。", html)
        self.assertIn("machine-trend", html)
        self.assertIn("/api/device-series", html)
        self.assertIn('name="combined-device-axis"', html)
        self.assertIn("<span>层数</span>", html)
        self.assertIn("<span>时间</span>", html)
        self.assertIn("{markersOnly:true}", html)
        self.assertIn("'machine-trend-chart',spec.api,['machine'],spec.label,spec.unit,{markersOnly:true}", html)
        self.assertIn("mode:markersOnly?'markers':'lines+markers'", html)
        self.assertIn("${channelName} %{y:.6g} ${unit} · ${sourceName}", html)
        self.assertNotIn("hovertemplate:`时间 %{x", html)
        self.assertNotIn("采样时间 %{x} s<br>", html)
        self.assertNotIn("层开始 %{customdata", html)
        self.assertNotIn("<br>数据源", html)
        self.assertNotIn("实际时间在数据详情中显示", html)
        self.assertIn("new AbortController()", html)
        self.assertNotIn("deviceSeriesTimer", html)
        self.assertNotIn("setTimeout(()=>load", html)
        self.assertIn("modebar:{uirevision", html)
        self.assertNotIn('data-series-detail="full"', html)
        self.assertIn("max_points:'8000'", html)
        self.assertIn("viewState.scope==='machine'?(viewState.machineSession||'all'):'all'", html)
        self.assertNotIn("高密度真实采样", html)
        self.assertNotIn("高密度采样", html)
        self.assertNotIn('class="layer-axis-band"', html)
        self.assertNotIn("coverage-status", html)
        self.assertIn("overlaying:'x'", html)
        self.assertIn("matches:'x'", html)
        self.assertIn("side:'top'", html)
        self.assertIn("title:{text:''}", html)
        self.assertIn("automargin:false", html)
        self.assertIn("xaxis:'x2'", html)
        self.assertIn(".chart,.chart.tall{height:430px}", html)
        self.assertIn(".device-layout{grid-template-columns:210px minmax(0,1fr);align-items:stretch}", html)
        self.assertIn(".device-layout>.metric-rail,.device-layout>.device-main{min-height:620px}", html)
        self.assertIn(".device-layout>.device-main>.chart-panel:not(.focused)>.chart{height:calc(100% - 47px)}", html)
        self.assertIn('class="panel device-table-panel"', html)
        self.assertIn("y:.95,yref:'container',yanchor:'top'", html)
        self.assertIn("y:.89,yref:'container',yanchor:'top'", html)
        self.assertIn("bgcolor:'rgba(255,255,255,0)',borderwidth:0", html)
        self.assertIn("tickangle:0", html)
        self.assertIn("xaxis=null,minGap=68", html)
        self.assertIn("maxLabels,xaxis,68", html)
        self.assertIn("margin:{t:148}", html)
        self.assertIn("Promise.resolve(Plotly.Plots.resize(chart)).then", html)
        self.assertIn("const sortMaterials=", html)
        self.assertIn("'xaxis2.tickvals':tickvals", html)
        self.assertIn("${item.layer}层", html)
        self.assertIn("镀膜层：%{customdata[0]}", html)
        self.assertNotIn("第 ${item.layer} 层", html)
        self.assertIn("镀膜区段", html)
        self.assertIn("管道真空", html)
        self.assertIn("转速", html)
        self.assertIn("['machine-trend','设备']", html)
        self.assertIn("o2:{label:'O₂'", html)
        self.assertIn("ar:{label:'Ar'", html)
        self.assertNotIn('data-machine-gas=', html)
        self.assertIn("function materialColor(material)", html)
        self.assertIn("if(material==='H')return COLORS[0]", html)
        self.assertIn("if(material==='L')return COLORS[1]", html)
        self.assertIn("splitByMaterial=!['o2_mean','ar_mean'].includes(metric)", html)
        self.assertIn("alignment.confidence==='中可信'?'已关联（待复核）':'已关联'", html)
        self.assertNotIn("原始时间 %{", html)
        self.assertNotIn("实际时间 %{", html)
        self.assertNotIn("#62afd2", html)
        self.assertNotIn("#b95f19", html)
        self.assertIn("hovermode:'x unified'", html)
        self.assertIn("<extra>%{fullData.name}</extra>", html)
        self.assertIn('class="optical-detail-grid"', html)
        self.assertNotIn("['combined-time','时间关联']", html)
        self.assertNotIn("['machine-segments','功率分段']", html)
        self.assertNotIn("['combined-anomaly','异常关联']", html)
        self.assertNotIn("['machine-events','异常事件']", html)
        self.assertNotIn("下载联合逐层", html)
        self.assertNotIn("下载跨源复核", html)
        self.assertNotIn("下载异常事件", html)
        self.assertNotIn("下载功率分段", html)
        self.assertNotIn("compute_correlations", Path(__file__).with_name("server.py").read_text(encoding="utf-8"))
        self.assertIn("当前筛选无数据", html)
        self.assertIn("filteredMachineSegments", html)
        self.assertIn("完成状态（整炉）", html)
        self.assertIn("整炉关联诊断", html)

    def test_html_uses_workbench_focus_and_field_metadata(self):
        html = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
        self.assertIn('class="module-nav"', html)
        self.assertIn("const FIELD_META=", html)
        self.assertIn("const viewState=", html)
        self.assertIn("function renderActivePage()", html)
        self.assertIn("function toggleChartFocus(button)", html)
        self.assertIn("role','dialog'", html)
        self.assertIn("aria-modal','true'", html)
        self.assertIn("Plotly.Plots.resize", html)
        self.assertNotIn("requestFullscreen", html)
        self.assertIn(".chart-panel>.chart-toolbar{position:static", html)
        self.assertIn("height:calc(100dvh - 70px)!important", html)
        generated_device_prefixes = (
            "power_", "current_", "voltage_", "vacuum_", "chamber_temp_",
            "water_in_", "water_out_", "motor_", "o2_", "ar_",
            "monitor_motor_",
        )
        for field in SUMMARY_COLUMNS:
            if field.startswith(generated_device_prefixes):
                continue
            self.assertIn(f"{field}:{{label:", html, field)

    def test_user_visible_copy_uses_work_control_log_name(self):
        root = Path(__file__).parent
        for name in ("index.html", "analyzer.py", "server.py", "PRODUCT.md", "DESIGN.md", "README.md", "site/index.html"):
            text = (root / name).read_text(encoding="utf-8")
            self.assertNotIn("机台Log", text, name)
            self.assertNotIn("机台工作时段", text, name)

    def test_folder_picker_cancel_preserves_previous_path(self):
        previous = r"C:\Logs\Previous-Batch"
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(server, "saved_path", return_value=previous), patch.object(
            server.subprocess, "run", return_value=completed
        ) as run, patch.dict(server.STATE, {"path": previous, "result": None}, clear=True):
            path, cancelled, changed = server.choose_folder()
        self.assertEqual(path, previous)
        self.assertTrue(cancelled)
        self.assertFalse(changed)
        self.assertIn("-STA", run.call_args.args[0])

    def test_folder_picker_changed_path_clears_old_result(self):
        with tempfile.TemporaryDirectory() as folder:
            completed = SimpleNamespace(returncode=0, stdout=folder, stderr="")
            with patch.object(server, "saved_path", return_value=r"C:\Logs\Old-Batch"), patch.object(
                server.subprocess, "run", return_value=completed
            ), patch.object(server, "save_path"), patch.dict(
                server.STATE,
                {"path": r"C:\Logs\Old-Batch", "result": object(), "fingerprint": ("old",), "correlations": object()},
                clear=True,
            ):
                path, cancelled, changed = server.choose_folder()
                self.assertEqual(path, str(Path(folder).resolve()))
                self.assertFalse(cancelled)
                self.assertTrue(changed)
                self.assertIsNone(server.STATE["result"])
                self.assertIsNone(server.STATE["fingerprint"])

    def test_desktop_uses_native_explorer_folder_dialog(self):
        with tempfile.TemporaryDirectory() as folder:
            selected = str(Path(folder).resolve())
            calls = []
            window = SimpleNamespace(
                create_file_dialog=lambda dialog, **kwargs: calls.append((dialog, kwargs)) or (selected,)
            )
            api = desktop.DesktopApi(window)
            with patch.object(server, "saved_path", return_value=selected), patch.object(server, "save_path"), patch.dict(
                server.STATE, {"path": selected, "result": object()}, clear=True
            ):
                result = api.choose_folder()
            self.assertEqual(calls[0][0], desktop.webview.FileDialog.FOLDER)
            self.assertEqual(calls[0][1]["directory"], selected)
            self.assertFalse(result["cancelled"])
            self.assertFalse(result["changed"])

    def test_desktop_api_exposes_only_callable_methods(self):
        window = SimpleNamespace()
        api = desktop.DesktopApi(window)
        public = {name: getattr(api, name) for name in dir(api) if not name.startswith("_")}
        self.assertEqual(
            set(public),
            {"choose_folder", "get_version", "open_releases", "save_export"},
        )
        self.assertTrue(all(callable(value) for value in public.values()))
        self.assertFalse(hasattr(api, "window"))
        self.assertIs(api._window, window)

    def test_desktop_api_version_release_and_export(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "layer_summary.csv"
            window = SimpleNamespace(create_file_dialog=lambda *_args, **_kwargs: (str(output),))
            api = desktop.DesktopApi(window)
            self.assertEqual(api.get_version()["version"], desktop.APP_VERSION)
            with patch.object(desktop.webbrowser, "open", return_value=True) as open_browser:
                self.assertTrue(api.open_releases())
                open_browser.assert_called_once_with(desktop.RELEASES_URL)
            result = SimpleNamespace(layer_summary=pd.DataFrame({"layer": [1]}))
            with patch.dict(server.STATE, {"result": result}, clear=True):
                saved = api.save_export("summary")
            self.assertTrue(saved["ok"])
            self.assertEqual(saved["path"], str(output))
            self.assertTrue(output.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_progress_callback_reaches_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pd.DataFrame(
                [{"Layer#": 1, "Material": "H", "PhyThick": 10, "Rate": 0.2, "Time": 50,
                  "Start T": 0.1, "End T": 0.2, "Extreme#": 1, "Method": "OMS"}]
            ).to_csv(root / "recipe.csv", index=False)
            progress = []
            analyze_folder(root, lambda phase, current, total: progress.append((phase, current, total)))
            self.assertIn(("逐层读取", 1, 1), progress)
            self.assertEqual(progress[-1], ("完成", 1, 1))

    def test_numeric_validation_keeps_blank_and_flags_invalid(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pd.DataFrame(
                [
                    {"Layer#": 1, "Material": "H", "PhyThick": 10, "Rate": "", "Time": 50,
                     "Start T": 0.1, "End T": 0.2, "Extreme#": 1, "Method": "OMS"},
                    {"Layer#": 2, "Material": "L", "PhyThick": 20, "Rate": "invalid", "Time": 60,
                     "Start T": 0.2, "End T": 0.3, "Extreme#": 2, "Method": "Timer"},
                ]
            ).to_csv(root / "recipe.csv", index=False)
            result = analyze_folder(root)
            invalid = result.data_quality[result.data_quality["issue"] == "非法数值"]
            self.assertEqual(len(invalid), 1)
            self.assertIn("Rate: 1", invalid.iloc[0]["detail"])

    def test_health_endpoint_identifies_service(self):
        httpd = server.create_server()
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_port}/api/health") as response:
                body = response.read().decode("utf-8")
            self.assertIn('"service": "coating-analyzer"', body)
            self.assertIn('"app_name": "Log Analysis"', body)
            self.assertIn(f'"app_version": "{desktop.APP_VERSION}"', body)
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=2)

    def test_desktop_token_protects_local_data_api(self):
        httpd = server.create_server(token="test-session-token")
        self.assertTrue(httpd.daemon_threads)
        self.assertFalse(httpd.block_on_close)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            with self.assertRaises(HTTPError) as denied:
                urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_port}/api/state")
            self.assertEqual(denied.exception.code, 403)
            request = urllib.request.Request(
                f"http://127.0.0.1:{httpd.server_port}/api/state",
                headers={"X-Log-Analysis-Token": "test-session-token"},
            )
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 200)
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=2)

    def test_server_uses_in_memory_cache_and_threshold_endpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pd.DataFrame(
                [{"Layer#": 1, "Material": "H", "PhyThick": 10, "Rate": 0.2, "Time": 50,
                  "Start T": 0.1, "End T": 0.2, "Extreme#": 1, "Method": "OMS"}]
            ).to_csv(root / "recipe.csv", index=False)
            initial_state = {
                "path": "", "result": None, "fingerprint": None,
                "progress": {"status": "idle", "phase": "", "current": 0, "total": 0, "elapsed": 0.0},
            }
            server.STATE.clear()
            server.STATE.update(initial_state)
            httpd = server.create_server()
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            try:
                body = json.dumps({"path": str(root), "threshold": 3.5}).encode("utf-8")
                with patch.object(server, "save_path"), patch.object(server, "analyze_folder", wraps=analyze_folder) as analyze:
                    for _ in range(2):
                        request = urllib.request.Request(
                            f"http://127.0.0.1:{httpd.server_port}/api/analyze",
                            data=body,
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                        with urllib.request.urlopen(request) as response:
                            self.assertEqual(response.status, 200)
                            analysis_response = json.loads(response.read())
                            self.assertNotIn("correlations", analysis_response)
                            self.assertNotIn("machine_events", analysis_response)
                            self.assertNotIn("cross_source_review", analysis_response)
                    self.assertEqual(analyze.call_count, 1)
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{httpd.server_port}/api/anomalies?threshold=4.0"
                ) as response:
                    self.assertIn("anomalies", json.loads(response.read()))
                with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_port}/api/progress") as response:
                    self.assertEqual(json.loads(response.read())["status"], "completed")
            finally:
                httpd.shutdown()
                httpd.server_close()
                worker.join(timeout=2)
                server.STATE.clear()
                server.STATE.update(initial_state)

    def test_server_returns_structured_unexpected_analysis_error(self):
        with tempfile.TemporaryDirectory() as folder:
            initial_state = {
                "path": "", "result": None, "fingerprint": None,
                "progress": {"status": "idle", "phase": "", "current": 0, "total": 0, "elapsed": 0.0},
            }
            server.STATE.clear()
            server.STATE.update(initial_state)
            httpd = server.create_server()
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            try:
                body = json.dumps({"path": folder, "threshold": 3.5}).encode("utf-8")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{httpd.server_port}/api/analyze",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with patch.object(server, "analyze_folder", side_effect=RuntimeError("synthetic failure")):
                    with self.assertRaises(HTTPError) as failed:
                        urllib.request.urlopen(request)
                self.assertEqual(failed.exception.code, 500)
                response = json.loads(failed.exception.read())
                self.assertEqual(response["code"], "analysis_failed")
                self.assertEqual(server.STATE["progress"]["status"], "failed")
            finally:
                httpd.shutdown()
                httpd.server_close()
                worker.join(timeout=2)
                server.STATE.clear()
                server.STATE.update(initial_state)

    def test_corrupt_settings_do_not_block_startup(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"LOCALAPPDATA": folder}), patch.object(
            server, "LEGACY_LAST_FOLDER", Path(folder) / "missing.txt"
        ):
            server.settings_path().parent.mkdir(parents=True)
            server.settings_path().write_text("not json", encoding="utf-8")
            self.assertEqual(server.saved_path(), "")

    def test_windows_launchers_use_crlf(self):
        project = Path(__file__).parent
        for name in ("run.bat", "启动镀膜分析.bat", "构建安装包.bat"):
            content = (project / name).read_bytes()
            self.assertIn(b"\r\n", content)
            self.assertNotIn(b"\n", content.replace(b"\r\n", b""))

    def test_installer_allows_directory_selection_and_copies_desktop_shortcut(self):
        project = Path(__file__).parent
        script = (project / "installer" / "LogAnalysis.iss").read_text(encoding="utf-8")
        spec = (project / "Log Analysis.spec").read_text(encoding="utf-8")
        self.assertIn("DisableDirPage=no", script)
        self.assertNotIn('Name: "{autodesktop}\\{#MyAppName}"', script)
        self.assertIn("User Shell Folders", script)
        self.assertIn("WizardIsTaskSelected('desktopicon')", script)
        self.assertNotIn("CreateShellLink(", script)
        self.assertIn("CopyFile(StartMenuShortcutPath, ShortcutPath, False)", script)
        self.assertIn("ExpandConstant('{group}\\{#MyAppName}.lnk')", script)
        self.assertIn("except", script)
        self.assertIn("已完成安装，但桌面快捷方式创建失败", script)
        self.assertIn("RegWriteStringValue(HKCU, InstallerSettingsKey", script)
        self.assertIn("DeleteFile(ShortcutPath)", script)
        self.assertIn('excludes=["pyarrow", "streamlit"]', spec)

    def test_public_site_is_local_only_and_links_to_releases(self):
        project = Path(__file__).parent
        html = (project / "site" / "index.html").read_text(encoding="utf-8")
        demo_js = (project / "site" / "demo.js").read_text(encoding="utf-8")
        readme = (project / "README.md").read_text(encoding="utf-8")
        release_notes = (project / "RELEASE_NOTES.md").read_text(encoding="utf-8")
        version = desktop.APP_VERSION
        installer_url = (
            f"https://github.com/Reyppp/log-analysis/releases/download/v{version}/"
            f"Log-Analysis-Setup-v{version}-x64.exe"
        )
        checksum_url = (
            f"https://github.com/Reyppp/log-analysis/releases/download/v{version}/"
            "SHA256SUMS.txt"
        )
        self.assertIn("数据只在本机处理", html)
        self.assertIn(installer_url, html)
        self.assertIn(checksum_url, html)
        self.assertIn(f"https://github.com/Reyppp/log-analysis/releases/tag/v{version}", html)
        self.assertIn(installer_url, readme)
        self.assertIn("Get-FileHash -Algorithm SHA256", readme)
        for scope in ("combined", "monitor", "machine"):
            self.assertIn(f'data-site-scope="{scope}"', html)
        self.assertIn("三种分析范围，同一工作台", html)
        self.assertIn("guide-sourcebar", html)
        self.assertIn("guide-module-nav", html)
        self.assertIn("异常复核", html)
        self.assertIn("实际采样点", html + demo_js)
        self.assertNotIn("8,000", html + demo_js)
        self.assertNotIn("高密度设备趋势", html + demo_js)
        self.assertNotIn("Spearman", html + demo_js)
        for content in (html, readme, release_notes):
            self.assertIn("单层详情图表或原始截图可能不显示", content)
        self.assertNotIn("https://fonts.", html)
        self.assertNotIn("analytics", html.lower())

    def test_spearman_without_scipy_dependency(self):
        frame = pd.DataFrame(
            {
                "material": ["H"] * 20,
                "fit_mae": range(20),
                "actual_time": range(0, 40, 2),
            }
        )
        result = compute_correlations(frame)
        self.assertAlmostEqual(result.iloc[0]["spearman"], 1.0)

    def test_missing_folder(self):
        with self.assertRaises(AnalysisError):
            analyze_folder(Path(tempfile.gettempdir()) / "does-not-exist-coating-log")

    def test_html_uses_progress_and_threshold_fast_path(self):
        html = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
        self.assertIn('id="analysis-progress"', html)
        self.assertIn("api('/api/progress')", html)
        self.assertIn("api('/api/anomalies?threshold='", html)
        self.assertIn("$('threshold').onchange=refreshAnomalies", html)
        self.assertIn("if(d.changed)resetAnalysisView()", html)
        self.assertIn("window.pywebview.api.choose_folder()", html)
        self.assertIn("function setScope(scope)", html)
        self.assertIn("function updateToolbar()", html)

    @unittest.skipUnless(GOLDEN_FOLDER and GOLDEN_FOLDER.is_dir(), "黄金样本目录不可用")
    def test_golden_run(self):
        result = analyze_folder(GOLDEN_FOLDER)
        self.assertEqual(len(result.layer_summary), 243)
        self.assertEqual(result.batch_summary["h_layers"], 129)
        self.assertEqual(result.batch_summary["l_layers"], 114)
        self.assertEqual(result.batch_summary["actual_seconds"], 97612.0)
        self.assertTrue(result.batch_summary["finished"])
        self.assertIn("coating_log", set(result.file_index["family"]))
        self.assertFalse(result.file_index["relative_path"].str.match(r"^\d{4}-\d{2}-\d{2}\.csv$", case=False).any())


if __name__ == "__main__":
    unittest.main()
