@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
fc /b requirements.txt .venv\installed.txt >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto failed
  copy /y requirements.txt .venv\installed.txt >nul
)
".venv\Scripts\python.exe" app.py %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Launch failed. Check Python and the messages above.
pause
exit /b 1
