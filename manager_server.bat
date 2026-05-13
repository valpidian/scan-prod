@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0manager_server.ps1" %*
exit /b %errorlevel%
