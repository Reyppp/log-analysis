from __future__ import annotations

import os
import secrets
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import quote

import webview

import server
from analyzer import csv_bytes, detect_anomalies
from version import APP_NAME, APP_VERSION, BUILD_CHANNEL, RELEASES_URL


class DesktopApi:
    def __init__(self) -> None:
        self.window = None

    def get_version(self) -> dict[str, str]:
        return {"name": APP_NAME, "version": APP_VERSION, "channel": BUILD_CHANNEL}

    def open_releases(self) -> bool:
        return webbrowser.open(RELEASES_URL)

    def save_export(self, kind: str, threshold: float = 3.5) -> dict[str, object]:
        result = server.STATE.get("result")
        if result is None:
            return {"ok": False, "error": "请先完成炉次分析。"}
        name = "layer_summary.csv" if kind == "summary" else "anomalies.csv"
        selected = self.window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=str(Path.home() / "Downloads"),
            save_filename=name,
            file_types=("CSV 文件 (*.csv)",),
        )
        if not selected:
            return {"ok": True, "cancelled": True}
        path = Path(selected[0] if isinstance(selected, (tuple, list)) else selected)
        frame = result.layer_summary if kind == "summary" else detect_anomalies(result.layer_summary, float(threshold))
        path.write_bytes(csv_bytes(frame))
        return {"ok": True, "cancelled": False, "path": str(path)}


def smoke_test() -> None:
    httpd = server.create_server(0, secrets.token_urlsafe(32))
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_port}/api/health", timeout=5) as response:
            if APP_VERSION not in response.read().decode("utf-8"):
                raise RuntimeError("packaged health check returned the wrong version")
        with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_port}/", timeout=5) as response:
            if b"Log Analysis" not in response.read():
                raise RuntimeError("packaged HTML resource is missing")
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=3)


def main() -> None:
    os.environ.setdefault("PYWEBVIEW_GUI", "edgechromium")
    token = secrets.token_urlsafe(32)
    server.STATE["path"] = server.saved_path()
    httpd = server.create_server(0, token)
    worker = threading.Thread(target=httpd.serve_forever, name="log-analysis-http", daemon=True)
    worker.start()
    api = DesktopApi()
    url = f"http://127.0.0.1:{httpd.server_port}/?token={quote(token)}"
    api.window = webview.create_window(
        APP_NAME,
        url,
        js_api=api,
        width=1440,
        height=900,
        min_size=(960, 640),
        text_select=True,
    )
    try:
        webview.start(gui="edgechromium", debug=False)
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=3)


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        smoke_test()
    else:
        main()
