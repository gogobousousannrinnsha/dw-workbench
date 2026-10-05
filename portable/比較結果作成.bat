@echo off
setlocal
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
chcp 65001 >nul
"%~dp0runtime\python.exe" -I -X utf8 "%~dp0scripts\compare_ab.py" %*
set "OCR_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %OCR_EXIT%
