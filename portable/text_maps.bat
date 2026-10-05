@echo off
setlocal
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "DW_OCR_CACHE=%~dp0cache"
set "ROOT=%~dp0"
if not exist "%ROOT%runtime\python.exe" (
  echo ERROR: Extract these files next to runtime\python.exe.
  exit /b 2
)
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True"
set "PADDLE_PDX_CACHE_HOME=%ROOT%ocr-cache\paddlex"
set "PADDLE_HOME=%ROOT%ocr-cache\paddle"
if "%~1"=="" (
  echo Usage: text_maps.bat BUNDLE_DIR [options]
  echo BUNDLE_DIR must contain manifest.json.
  exit /b 2
)
"%ROOT%runtime\python.exe" -I -X utf8 "%ROOT%scripts\generate_bundle_text_maps.py" %*
exit /b %ERRORLEVEL%
