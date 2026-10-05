@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Restore-Portable.ps1" -Extract
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Restore-Portable.ps1" -Extract -Destination "%~1"
)
if errorlevel 1 (
  echo.
  echo Restoration failed. Read the message above or Restore-Portable-error-*.txt.
  echo The verified ZIP and existing work are preserved.
  pause
  exit /b 1
)
echo.
echo Restoration completed.
pause
