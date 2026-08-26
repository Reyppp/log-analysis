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
            api = desktop.DesktopApi()
            api.window = SimpleNamespace(
                create_file_dialog=lambda dialog, **kwargs: calls.append((dialog, kwargs)) or (selected,)
            )
            with patch.object(server, "saved_path", return_value=selected), patch.object(server, "save_path"), patch.dict(
                server.STATE, {"path": selected, "result": object()}, clear=True
            ):
                result = api.choose_folder()
            self.assertEqual(calls[0][0], desktop.webview.FileDialog.FOLDER)
            self.assertEqual(calls[0][1]["directory"], selected)
            self.assertFalse(result["cancelled"])
            self.assertFalse(result["changed"])

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
            self.assertIn('"app_version": "0.1.0-beta.3"', body)
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
                "path": "", "result": None, "fingerprint": None, "correlations": None,
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
                "path": "", "result": None, "fingerprint": None, "correlations": None,
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

    def test_public_site_is_local_only_and_links_to_releases(self):
        project = Path(__file__).parent
        html = (project / "site" / "index.html").read_text(encoding="utf-8")
        readme = (project / "README.md").read_text(encoding="utf-8")
        release_notes = (project / "RELEASE_NOTES.md").read_text(encoding="utf-8")
        installer_url = (
            "https://github.com/Reyppp/log-analysis/releases/download/v0.1.0-beta.3/"
            "Log-Analysis-Setup-v0.1.0-beta.3-x64.exe"
        )
        checksum_url = (
            "https://github.com/Reyppp/log-analysis/releases/download/v0.1.0-beta.3/"
            "SHA256SUMS.txt"
        )
        self.assertIn("数据只在本机处理", html)
        self.assertIn(installer_url, html)
        self.assertIn(checksum_url, html)
        self.assertIn("https://github.com/Reyppp/log-analysis/releases/tag/v0.1.0-beta.3", html)
        self.assertIn(installer_url, readme)
        self.assertIn("Get-FileHash -Algorithm SHA256", readme)
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
