# Build on Apple Silicon with: python -m PyInstaller 'Log Analysis macOS.spec'
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

version = {}
exec((Path(SPECPATH) / 'version.py').read_text(), version)
a = Analysis(
    ['desktop.py'], pathex=[], binaries=[],
    datas=[('index.html', '.'), ('LICENSE', '.'), ('THIRD_PARTY_NOTICES.md', '.')]
          + collect_data_files('plotly'),
    hiddenimports=['webview.platforms.cocoa'],
    excludes=['pyarrow', 'streamlit', 'matplotlib', 'scipy', 'IPython', 'pytest',
              'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'tkinter'],
    noarchive=False, optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Log Analysis',
          debug=False, strip=False, upx=False, console=False, target_arch='arm64')
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Log Analysis')
app = BUNDLE(coll, name='Log Analysis.app', icon='build/mac/icon.icns',
             bundle_identifier='com.rey.loganalysis', version=version['APP_VERSION'],
             info_plist={'CFBundleShortVersionString': '0.1.0',
                         'NSHighResolutionCapable': True,
                         'NSDocumentsFolderUsageDescription': '选择并只读分析镀膜日志。',
                         'NSDownloadsFolderUsageDescription': '保存分析结果和图表。'})
