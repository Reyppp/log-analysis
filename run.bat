@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8502/api/health' -TimeoutSec 1; if ($r.service -eq 'coating-analyzer') { exit 0 } } catch {}; exit 1" >nul 2>nul
if not errorlevel 1 (
  start "" "http://127.0.0.1:8502"
  exit /b 0
)

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8502 -State Listen -ErrorAction SilentlyContinue) { exit 0 }; exit 1" >nul 2>nul
if not errorlevel 1 (
  echo [错误] 端口 8502 已被其他程序占用，镀膜分析服务无法启动。
  echo 请关闭占用该端口的程序后，再次双击本启动文件。
  pause
  exit /b 2
)

if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv 2>nul
  if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
)

".venv\Scripts\python.exe" -c "import pandas, plotly" 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 pause & exit /b 1
)

".venv\Scripts\python.exe" server.py
