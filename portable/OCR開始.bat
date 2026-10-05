@echo off
setlocal
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
chcp 65001 >nul
set "PYTHONDONTWRITEBYTECODE=1"
"%~dp0runtime\python.exe" -I -X utf8 "%~dp0scripts\start_ocr.py" %*
set "OCR_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %OCR_EXIT%
