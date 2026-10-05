@echo off
setlocal
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "DW_OCR_CACHE=%~dp0cache"
if "%~1"=="" (
  echo Usage: ocr_xdw.bat INPUT.xdw RUN_DIR [PAGE] [DPI]
  exit /b 2
)
if "%~2"=="" (
  echo Usage: ocr_xdw.bat INPUT.xdw RUN_DIR [PAGE] [DPI]
  exit /b 2
)
set "ROOT=%~dp0"
set "PAGE=%~3"
if "%PAGE%"=="" set "PAGE=1"
set "DPI=%~4"
if "%DPI%"=="" set "DPI=300"
set "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True"
set "PADDLE_PDX_CACHE_HOME=%ROOT%ocr-cache\paddlex"
set "PADDLE_HOME=%ROOT%ocr-cache\paddle"
"%ROOT%runtime\python.exe" -I -X utf8 -m docuworks_integrations ocr-xdw --input-xdw "%~1" --run-dir "%~2" --model-root "%ROOT%models" --page %PAGE% --dpi %DPI%
