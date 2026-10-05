@echo off
setlocal
set "PYTHONNOUSERSITE=1"
"%~dp0runtime\python.exe" -I -B -X utf8 -m docuworks_integrations template-editor --app-root "%~dp0."
if errorlevel 1 pause
endlocal
