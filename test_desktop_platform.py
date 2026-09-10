import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import desktop


class _UnexpectedWindll:
    def __getattr__(self, name):
        raise AssertionError(f"ctypes.windll was accessed on macOS: {name}")


class _FakeAlert:
    def __init__(self):
        self.message = None
        self.informative = None
        self.button = None

    @classmethod
    def alloc(cls):
        return cls()

    def init(self):
        return self

    def setMessageText_(self, message):
        self.message = message

    def setInformativeText_(self, message):
        self.informative = message

    def addButtonWithTitle_(self, title):
        self.button = title

    def runModal(self):
        return 0


class DesktopPlatformTests(unittest.TestCase):
    def test_windows_keeps_edgechromium_and_mutex_path(self):
        kernel32 = SimpleNamespace(
            CreateMutexW=lambda *_args: object(),
            GetLastError=lambda: 0,
            CloseHandle=lambda *_args: None,
        )
        user32 = SimpleNamespace(FindWindowW=lambda *_args: 0)
        fake_windll = SimpleNamespace(kernel32=kernel32, user32=user32)
        with patch.object(desktop, "IS_WINDOWS", True), patch.object(
            desktop.ctypes, "windll", fake_windll, create=True
        ):
            self.assertEqual(desktop.webview_backend(), "edgechromium")
            self.assertIsNotNone(desktop.acquire_single_instance())

    def test_mac_uses_cocoa_without_touching_windll(self):
        with patch.object(desktop, "IS_WINDOWS", False), patch.object(
            desktop.ctypes, "windll", _UnexpectedWindll(), create=True
        ), patch.dict(os.environ, {}, clear=True), patch.dict(
            sys.modules, {"AppKit": SimpleNamespace(NSAlert=_FakeAlert)}
        ):
            self.assertEqual(desktop.webview_backend(), "cocoa")
            self.assertEqual(desktop.configure_webview_backend(), "cocoa")
            self.assertEqual(os.environ["PYWEBVIEW_GUI"], "cocoa")
            self.assertEqual(desktop.acquire_single_instance(), 1)
            desktop.show_message("test")


if __name__ == "__main__":
    unittest.main()
