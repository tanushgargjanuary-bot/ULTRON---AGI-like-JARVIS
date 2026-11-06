@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  Ultron — data collector
REM
REM  Double-click to see what data your install actually holds, or pass options:
REM
REM    collect-data.bat --bundle data.zip        one ZIP of the data files
REM    collect-data.bat --watch                  watch for new files until Ctrl+C
REM    collect-data.bat --path "D:\somewhere"    scan a different folder
REM
REM  Secrets are blanked in the bundle unless --include-secrets is given.
REM  Nothing is uploaded; the only output is the file you ask for.
REM ─────────────────────────────────────────────────────────────────────────────
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

"%PY%" "scripts\collect_install.py" %*
set "CODE=%ERRORLEVEL%"
echo.
if not "%CODE%"=="0" echo Collector exited with code %CODE%.
pause
endlocal
