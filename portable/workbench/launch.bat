@echo off
setlocal
set "ROOT=%~dp0"
if not exist "%ROOT%runtime\python.exe" set "ROOT=%~dp0..\"
cd /d "%ROOT%"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONUTF8=1"
"%ROOT%runtime\python.exe" -I -B -X utf8 -m dw_workbench %*
if errorlevel 1 pause
endlocal
