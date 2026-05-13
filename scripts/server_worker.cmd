@echo off
setlocal

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "PYTHON=C:\Python313\python.exe"
if exist "%ROOT%\.venv\Scripts\python.exe" set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

cd /d "%ROOT%"
"%PYTHON%" run.py 1>>"%ROOT%\logs\server.out.log" 2>>"%ROOT%\logs\server.err.log"
