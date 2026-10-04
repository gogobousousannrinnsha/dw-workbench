@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Restore-Portable.ps1" -Extract
if errorlevel 1 (
  echo.
  echo Restoration failed. Read the message above. Existing work was preserved.
  pause
  exit /b 1
)
echo.
echo Restoration completed.
pause
