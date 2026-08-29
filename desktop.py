from __future__ import annotations

import os
import secrets
import sys
import threading
import urllib.request
import webbrowser
import ctypes
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import quote

import webview

from version import APP_NAME, APP_VERSION, BUILD_CHANNEL, RELEASES_URL


LOGGER = logging.getLogger(__name__)
MUTEX_NAME = "Local\\LogAnalysisDesktop"


def configure_logging() -> Path:
    from server import settings_path

    log_path = settings_path().parent / "logs" / "app.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    return log_path


def show_message(message: str, title: str = APP_NAME) -> None:
    ctypes.windll.user32.MessageBoxW(None, message, title, 0x40)


def acquire_single_instance() -> int | None:
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if handle and kernel32.GetLastError() != 183:
        return handle
    if handle:
        kernel32.CloseHandle(handle)
    window = user32.FindWindowW(None, APP_NAME)
    if window:
        user32.ShowWindow(window, 9)
        user32.SetForegroundWindow(window)
    else:
        show_message("Log Analysis 已在运行。若窗口没有显示，请先在任务管理器中结束旧进程后重试。")
    return None


class DesktopApi:
    def __init__(self, window) -> None:
        self._window = window

    def get_version(self) -> dict[str, str]:
        return {"name": APP_NAME, "version": APP_VERSION, "channel": BUILD_CHANNEL}

    def open_releases(self) -> bool:
        return webbrowser.open(RELEASES_URL)

    def choose_folder(self) -> dict[str, object]:
        import server

        previous = server.saved_path()
        directory = previous if Path(previous).is_dir() else str(Path.home())
        try:
            selected = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=directory)
            path, cancelled, changed = server.apply_folder_selection(selected[0] if selected else "")
            return {"path": path, "cancelled": cancelled, "changed": changed}
        except Exception as exc:
            return {
                "error": f"无法打开 Windows 文件夹选择器：{exc}",
                "code": "folder_picker_failed",
                "recovery": "请关闭残留的选择窗口后重试；如仍失败，请重新启动 Log Analysis。",
            }

    def save_export(self, kind: str, threshold: float = 3.5) -> dict[str, object]:
        import server
        from analyzer import csv_bytes

        result = server.STATE.get("result")
        if result is None:
            return {"ok": False, "error": "请先完成炉次分析。"}
        try:
            frame, name = server.export_frame(result, kind, float(threshold))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        selected = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=str(Path.home() / "Downloads"),
            save_filename=name,
            file_types=("CSV 文件 (*.csv)",),
        )
        if not selected:
            return {"ok": True, "cancelled": True}
        path = Path(selected[0] if isinstance(selected, (tuple, list)) else selected)
        path.write_bytes(csv_bytes(frame))
        return {"ok": True, "cancelled": False, "path": str(path)}


def smoke_test() -> None:
    import server

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
    mutex = acquire_single_instance()
    if mutex is None:
        return
    import server

    try:
        log_path = configure_logging()
    except OSError:
        log_path = server.settings_path().parent / "logs" / "app.log"
        logging.basicConfig(level=logging.INFO, force=True)
    LOGGER.info("starting version=%s channel=%s", APP_VERSION, BUILD_CHANNEL)
    os.environ.setdefault("PYWEBVIEW_GUI", "edgechromium")
    httpd = None
    worker = None
    ready = threading.Event()
    stopped = threading.Event()
    try:
        token = secrets.token_urlsafe(32)
        server.STATE["path"] = server.saved_path()
        httpd = server.create_server(0, token)
        worker = threading.Thread(target=httpd.serve_forever, name="log-analysis-http", daemon=True)
        worker.start()
        LOGGER.info("local service ready port=%s", httpd.server_port)
        url = f"http://127.0.0.1:{httpd.server_port}/?token={quote(token)}"
        window = webview.create_window(
            APP_NAME,
            url,
            width=1440,
            height=900,
            min_size=(960, 640),
            text_select=True,
        )
        api = DesktopApi(window)
        window.expose(api.get_version, api.open_releases, api.choose_folder, api.save_export)

        def page_loaded() -> None:
            ready.set()
            LOGGER.info("window loaded")

        window.events.loaded += page_loaded

        def watch_startup() -> None:
            if not ready.wait(15) and not stopped.is_set():
                LOGGER.error("window did not load within 15 seconds")
                show_message(f"Log Analysis 启动时间过长。请关闭后重试；诊断日志位于：\n{log_path}")

        threading.Thread(target=watch_startup, name="startup-watchdog", daemon=True).start()
        webview.start(gui="edgechromium", debug=False)
    except Exception as exc:
        LOGGER.exception("desktop startup failed")
        show_message(f"Log Analysis 启动失败：{exc}\n\n诊断日志：{log_path}")
    finally:
        stopped.set()
        ready.set()
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if worker is not None:
            worker.join(timeout=3)
        LOGGER.info("stopped")
        ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        smoke_test()
    else:
        main()
