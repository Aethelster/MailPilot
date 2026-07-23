@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" main.py
  exit /b %errorlevel%
)

where py >nul 2>nul
if %errorlevel%==0 (
  py main.py
  exit /b %errorlevel%
)

python main.py
