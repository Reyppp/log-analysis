from __future__ import annotations

import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
from plotly.offline import get_plotlyjs

from analyzer import AnalysisError, analyze_folder, compute_correlations, csv_bytes, detect_anomalies, load_layer_detail
from version import APP_NAME, APP_VERSION, BUILD_CHANNEL


SOURCE_ROOT = Path(__file__).resolve().parent
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))
LEGACY_LAST_FOLDER = SOURCE_ROOT / ".last_folder.txt"
STATE: dict[str, object] = {"path": "", "result": None}
FOLDER_DIALOG_LOCK = threading.Lock()


class FolderDialogError(RuntimeError):
    pass


def frame_records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


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


def choose_folder() -> tuple[str, bool]:
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
    selected = completed.stdout.strip().lstrip("\ufeff")
    if selected:
        path = str(Path(selected).resolve())
        save_path(path)
        STATE["path"] = path
        return path, False
    return str(STATE.get("path") or saved_path()), True


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(RESOURCE_ROOT), **kwargs)

    def log_message(self, *_: object) -> None:
        pass

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
                    path, cancelled = choose_folder()
                    self.send_json({"path": path, "cancelled": cancelled})
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
                result = analyze_folder(path)
                STATE.update(path=path, result=result)
                save_path(path)
                self.send_json(
                    {
                        "batch": result.batch_summary,
                        "summary": frame_records(result.layer_summary),
                        "anomalies": frame_records(detect_anomalies(result.layer_summary, threshold)),
                        "quality": frame_records(result.data_quality),
                        "constants": frame_records(result.constant_fields),
                        "events": result.events,
                        "correlations": frame_records(compute_correlations(result.layer_summary)),
                    }
                )
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except (AnalysisError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # Keep the local page responsive when a malformed log appears.
            self.send_json({"error": f"分析失败：{exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

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
                if params.get("kind", [""])[0] == "summary":
                    self.send_bytes(csv_bytes(result.layer_summary), "text/csv; charset=utf-8", "layer_summary.csv")
                else:
                    threshold = float(params.get("threshold", ["3.5"])[0])
                    self.send_bytes(csv_bytes(detect_anomalies(result.layer_summary, threshold)), "text/csv; charset=utf-8", "anomalies.csv")
                return
        except (AnalysisError, KeyError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        super().do_GET()


def create_server(port: int = 0, token: str = "") -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.api_token = token
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
