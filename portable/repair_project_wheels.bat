@echo off
setlocal
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "DW_OCR_CACHE=%~dp0cache"
set "ROOT=%~dp0"
"%ROOT%runtime\python.exe" -I -X utf8 -m pip install --no-index --find-links "%ROOT%wheelhouse" --force-reinstall --no-deps docuworks-ctypes==1.0.1 docuworks-integrations==0.13.0 XlsxWriter==3.2.9
"%ROOT%runtime\python.exe" -I -X utf8 -m pip check
