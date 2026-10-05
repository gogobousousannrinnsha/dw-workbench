@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0repeat_integration.ps1"
exit /b %ERRORLEVEL%
