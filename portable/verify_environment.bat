@echo off
setlocal
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "DW_OCR_CACHE=%~dp0cache"
set "ROOT=%~dp0"
set "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True"
set "PADDLE_PDX_CACHE_HOME=%ROOT%ocr-cache\paddlex"
set "PADDLE_HOME=%ROOT%ocr-cache\paddle"
"%ROOT%runtime\python.exe" -I -X utf8 "%ROOT%verify_environment.py"
set RC=%ERRORLEVEL%
"%ROOT%runtime\python.exe" -I -X utf8 -m pip check
if errorlevel 1 set RC=1
exit /b %RC%
