@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv 2>nul
  if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
)

".venv\Scripts\python.exe" -m pip install -r requirements-build.txt || exit /b 1
".venv\Scripts\python.exe" tools\create_icon.py || exit /b 1
".venv\Scripts\pyinstaller.exe" --noconfirm --clean "Log Analysis.spec" || exit /b 1
for /f "tokens=2 delims== " %%V in ('findstr /b "APP_VERSION =" version.py') do set "APP_VERSION=%%~V"

set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files\Inno Setup 7\ISCC.exe"
if not exist "%ISCC%" (
  echo [错误] 未找到 Inno Setup 7，请先安装后重试。
  pause
  exit /b 2
)

"%ISCC%" "/DMyAppVersion=%APP_VERSION%" installer\LogAnalysis.iss || exit /b 1
powershell -NoProfile -Command "$f=Get-Item ('release\Log-Analysis-Setup-v{0}-x64.exe' -f $env:APP_VERSION); $h=(Get-FileHash -Algorithm SHA256 -LiteralPath $f.FullName).Hash.ToLowerInvariant(); \"$h  $($f.Name)\" | Set-Content -Encoding ascii release\SHA256SUMS.txt"
echo.
echo 构建完成：release 文件夹
pause
