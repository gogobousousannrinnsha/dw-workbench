@echo off
setlocal
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
chcp 65001 >nul
if not exist "%~dp0runtime\python.exe" (
  echo ERROR: Place this BAT next to runtime\python.exe in DW-OCR Portable.
  pause
  exit /b 1
)
"%~dp0runtime\python.exe" -I -B -X utf8 "%~dp0scripts\apply_template.py" %*
set "APPLY_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %APPLY_EXIT%
