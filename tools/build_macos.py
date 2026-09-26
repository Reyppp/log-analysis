"""Build the self-contained Apple Silicon application and local DMG."""
from pathlib import Path
import hashlib
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import APP_VERSION


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def main():
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise SystemExit('Build this package on an Apple Silicon Mac.')
    from PIL import Image, ImageDraw, ImageFont

    work = ROOT / 'build' / 'mac'
    work.mkdir(parents=True, exist_ok=True)
    icon = Image.new('RGBA', (1024, 1024))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((30, 30, 994, 994), radius=210, fill='#075e91')
    font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 380)
    draw.text((512, 480), 'LA', anchor='mm', font=font, fill='white')
    draw.rounded_rectangle((200, 740, 824, 778), radius=19, fill='#9fd7ef')
    icon.save(work / 'icon.icns')
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', 'Log Analysis macOS.spec')
    executable = ROOT / 'dist' / 'Log Analysis.app' / 'Contents' / 'MacOS' / 'Log Analysis'
    run(str(executable), '--smoke-test')
    stage = work / 'dmg'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    run('/usr/bin/ditto', str(ROOT / 'dist' / 'Log Analysis.app'), str(stage / 'Log Analysis.app'))
    (stage / 'Applications').symlink_to('/Applications')
    shutil.copy2(ROOT / 'MAC_USAGE.md', stage / '安装说明.md')
    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    name = f'Log-Analysis-v{APP_VERSION}-macOS-arm64.dmg'
    output = release / name
    run('/usr/bin/hdiutil', 'create', '-volname', 'Log Analysis', '-srcfolder', str(stage),
        '-ov', '-format', 'UDZO', str(output))
    checksum = release / f'{name}.sha256'
    checksum.write_text(f'{hashlib.sha256(output.read_bytes()).hexdigest()}  {name}\n')
    downloads = Path.home() / 'Downloads'
    downloads.mkdir(exist_ok=True)
    for source in (output, checksum):
        shutil.copy2(source, downloads / source.name)
    print(downloads / name)


if __name__ == '__main__':
    main()
