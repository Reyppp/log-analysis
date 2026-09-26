import base64
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import desktop
import server


class MacSettingsTests(unittest.TestCase):
    def test_mac_fallback_and_new_settings_precedence(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(Path, 'home', return_value=Path(folder)), patch.object(server.sys, 'platform', 'darwin'):
            old = Path(folder) / 'AppData/Local/Log Analysis/settings.json'
            old.parent.mkdir(parents=True)
            old.write_text('{"last_folder":"旧炉次"}')
            self.assertEqual(server.saved_path(), '旧炉次')
            self.assertEqual(server.settings_path(), Path(folder) / 'Library/Application Support/Log Analysis/settings.json')
            server.save_path('新炉次')
            self.assertEqual(server.saved_path(), '新炉次')
            self.assertIn('旧炉次', old.read_text())

    def test_windows_settings_unchanged(self):
        with patch.object(server.sys, 'platform', 'win32'), patch.dict('os.environ', {'LOCALAPPDATA': '/tmp/windows-local'}):
            self.assertEqual(server.settings_path(), Path('/tmp/windows-local/Log Analysis/settings.json'))


class NativeExportTests(unittest.TestCase):
    def test_cancel_preserves_files(self):
        api = desktop.DesktopApi(SimpleNamespace(create_file_dialog=lambda *a, **k: None))
        self.assertEqual(api._save_bytes(b'test', 'test.csv', 'CSV (*.csv)'), {'ok': True, 'cancelled': True})

    def test_png_save_and_source_protection(self):
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
        url = 'data:image/png;base64,' + base64.b64encode(png).decode()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / '中文图表.png'
            api = desktop.DesktopApi(SimpleNamespace(create_file_dialog=lambda *a, **k: (str(output),)))
            with patch.dict(server.STATE, {'path': str(Path(folder) / 'source')}):
                self.assertTrue(api.save_image(url)['ok'])
                self.assertEqual(output.read_bytes(), png)
            output.write_bytes(b'original')
            with patch.dict(server.STATE, {'path': folder}):
                self.assertFalse(api.save_image(url)['ok'])
                self.assertEqual(output.read_bytes(), b'original')
        self.assertFalse(api.save_image('data:image/png;base64,invalid')['ok'])

    def test_save_failure_is_reported(self):
        api = desktop.DesktopApi(SimpleNamespace(create_file_dialog=lambda *a, **k: '/nonexistent-log-analysis-test/file.csv'))
        with patch.dict(server.STATE, {'path': ''}):
            self.assertFalse(api._save_bytes(b'test', 'test.csv', 'CSV (*.csv)')['ok'])


class LocalStartupTests(unittest.TestCase):
    def test_loopback_server_does_not_need_dns(self):
        with patch('socket.getfqdn', side_effect=AssertionError('DNS must not be required')):
            httpd = server.create_server(0, 'test-token')
            try:
                self.assertEqual(httpd.server_address[0], '127.0.0.1')
                self.assertEqual(httpd.server_name, 'localhost')
                self.assertGreater(httpd.server_port, 0)
            finally:
                httpd.server_close()
