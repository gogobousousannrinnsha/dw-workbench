@echo off
setlocal
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "DW_OCR_CACHE=%~dp0cache"
set "ROOT=%~dp0"
set "PATH=%ROOT%runtime;%ROOT%runtime\Scripts;%PATH%"
set "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True"
set "PADDLE_PDX_CACHE_HOME=%ROOT%ocr-cache\paddlex"
set "PADDLE_HOME=%ROOT%ocr-cache\paddle"
cmd /K "cd /d %ROOT%"
