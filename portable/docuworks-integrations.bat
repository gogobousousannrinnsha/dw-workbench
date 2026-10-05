@echo off
setlocal
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "DW_OCR_CACHE=%~dp0cache"
set "ROOT=%~dp0"
"%ROOT%runtime\python.exe" -I -X utf8 -m docuworks_integrations %*
