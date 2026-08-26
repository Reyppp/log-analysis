import os
import tempfile
import threading
import unittest
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
    analyze_folder,
    compute_correlations,
    csv_bytes,
    detect_anomalies,
    parse_mixed_datetime,
    source_fingerprint,
)
import server


GOLDEN_PATH = os.environ.get("LOG_ANALYSIS_GOLDEN_FOLDER")
GOLDEN_FOLDER = Path(GOLDEN_PATH) if GOLDEN_PATH else None


class AnalyzerTests(unittest.TestCase):
    def test_mixed_clock(self):
        self.assertEqual(parse_mixed_datetime("2026-08-20  13:00:00 PM"), datetime(2026, 8, 20, 13, 0, 0))
        self.assertEqual(parse_mixed_datetime("2026-08-20  01:00:00 PM"), datetime(2026, 8, 20, 13, 0, 0))
        self.assertEqual(parse_mixed_datetime("2026-08-20  12:00:00 AM"), datetime(2026, 8, 20, 0, 0, 0))

    def test_date_csv_is_excluded_from_fingerprint(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "2026-08-20.csv").write_text("ignored", encoding="utf-8")
            (root / "Extrm.csv").write_text("ignored", encoding="utf-8")
            (root / "test_BaseLine.csv").write_text("ignored", encoding="utf-8")
            (root / "recipe.csv").write_text("kept", encoding="utf-8")
            files = [item[0] for item in source_fingerprint(root)]
            self.assertEqual(files, ["recipe.csv"])

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

    def test_html_has_folder_picker_layer_navigation_and_smooth_device_curve(self):
        html = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
        self.assertIn("选择炉次文件夹", html)
        self.assertIn('id="prev">前一层', html)
        self.assertIn('id="next">后一层', html)
        self.assertIn("shape:smooth?'spline':'linear'", html)
        self.assertIn('id="anomaly-metric"', html)
        self.assertIn('id="correlation-target"', html)
        self.assertIn('id="image-prev">前一层', html)
        self.assertIn('id="image-next">后一层', html)
        self.assertIn("监控方式", html)
        self.assertNotIn("终止方式", html)
        self.assertIn("location.protocol==='file:'", html)
        self.assertNotIn("Failed to fetch", html)

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
        )
        for field in SUMMARY_COLUMNS:
            if field.startswith(generated_device_prefixes):
                continue
            self.assertIn(f"{field}:{{label:", html, field)

    def test_folder_picker_cancel_preserves_previous_path(self):
        previous = r"C:\Logs\Previous-Batch"
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(server, "saved_path", return_value=previous), patch.object(
            server.subprocess, "run", return_value=completed
        ) as run, patch.dict(server.STATE, {"path": previous, "result": None}, clear=True):
            path, cancelled = server.choose_folder()
        self.assertEqual(path, previous)
        self.assertTrue(cancelled)
        self.assertIn("-STA", run.call_args.args[0])

    def test_health_endpoint_identifies_service(self):
        httpd = server.create_server()
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_port}/api/health") as response:
                body = response.read().decode("utf-8")
            self.assertIn('"service": "coating-analyzer"', body)
            self.assertIn('"app_name": "Log Analysis"', body)
            self.assertIn('"app_version": "0.1.0-beta.1"', body)
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=2)

    def test_desktop_token_protects_local_data_api(self):
        httpd = server.create_server(token="test-session-token")
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

    def test_corrupt_settings_do_not_block_startup(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"LOCALAPPDATA": folder}), patch.object(
            server, "LEGACY_LAST_FOLDER", Path(folder) / "missing.txt"
        ):
            server.settings_path().parent.mkdir(parents=True)
            server.settings_path().write_text("not json", encoding="utf-8")
            self.assertEqual(server.saved_path(), "")

    def test_windows_launchers_use_crlf(self):
        project = Path(__file__).parent
        for name in ("run.bat", "启动镀膜分析.bat"):
            content = (project / name).read_bytes()
            self.assertIn(b"\r\n", content)
            self.assertNotIn(b"\n", content.replace(b"\r\n", b""))

    def test_public_site_is_local_only_and_links_to_releases(self):
        site = Path(__file__).with_name("site") / "index.html"
        html = site.read_text(encoding="utf-8")
        self.assertIn("数据只在本机处理", html)
        self.assertIn("github.com/Reyppp/log-analysis/releases", html)
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
