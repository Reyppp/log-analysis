@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv 2>nul
  if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
)

".venv\Scripts\python.exe" -c "import pandas, plotly, webview" 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 pause & exit /b 1
)

".venv\Scripts\python.exe" desktop.py
if errorlevel 1 (
  echo [错误] Log Analysis 未能启动，请检查上方提示。
  pause
)
