@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Ultron

rem ===========================================================================
rem  Ultron launcher. Double-click this file. There is nothing else to do.
rem    first launch  - creates .venv and installs packages (10-20 min, once)
rem    every launch after that - starts the app immediately
rem  Nothing is installed outside this folder except, if you agree to it,
rem  Python itself. No administrator rights are needed anywhere.
rem
rem  Escape hatch: set ULTRON_SKIP_BROWSERS=1 before launching to skip the
rem  browser engine download and get to the app sooner.
rem ===========================================================================

if not exist "main.py"              goto missing
if not exist "requirements.txt"     goto missing
if not exist "scripts\bootstrap.py" goto missing

rem A .venv can outlive the Python that made it: uninstalled, upgraded, or the
rem folder copied to a different machine. Prove it runs before trusting it.
if not exist ".venv\Scripts\python.exe" goto findpython
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12),(3,13)) else 1)" >nul 2>&1
if errorlevel 1 goto healenv
goto setup

:healenv
echo.
echo The .venv in this folder does not run on this machine any more.
echo Moving it to .venv.old and building a fresh one.
if exist ".venv.old" rmdir /s /q ".venv.old" >nul 2>&1
move ".venv" ".venv.old" >nul 2>&1
goto findpython

:findpython
set "PYEXE="
call :trypy 3.12
if not defined PYEXE call :trypy 3.13
if not defined PYEXE call :trypy 3.11
if defined PYEXE goto makeenv
call :trypython
if defined PYEXE goto makeenv
goto offerpython

:makeenv
echo.
echo Using Python: %PYEXE%
"%PYEXE%" -m venv ".venv"
if not exist ".venv\Scripts\python.exe" goto envfailed
goto setup

:offerpython
echo.
echo Python was not found on this machine. Ultron needs 64-bit Python 3.11,
echo 3.12 or 3.13.
where winget >nul 2>&1
if errorlevel 1 goto nopython
echo.
echo Windows can install Python 3.12 for you now: about 30 MB, one time, into
echo your own user folder. No administrator password, nothing else touched.
echo.
set "ANSWER="
set /p "ANSWER=Install Python 3.12 now? [Y/n] "
if /i "%ANSWER%"=="n" goto nopython
echo.
echo Installing Python 3.12 through winget. One or two minutes.
winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
set "PYEXE="
call :trypy 3.12
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE goto nopython
echo Python 3.12 installed.
goto makeenv

:setup
".venv\Scripts\python.exe" "scripts\bootstrap.py"
if errorlevel 1 goto setupfailed
".venv\Scripts\python.exe" "main.py"
if errorlevel 1 goto appfailed
endlocal
exit /b 0

:setupfailed
echo.
echo Setup did not finish. The reason is above, and the whole output is in
echo setup-log.txt next to this file.
goto failed

:appfailed
echo.
echo Ultron closed with an error. The real message is the last lines above.
echo Nothing needs deleting - that text is enough to diagnose it.
goto failed

:missing
echo.
echo Extract the complete ZIP into a folder first, then run run.bat from inside
echo the extracted folder. run.bat must sit next to main.py.
goto failed

:nopython
echo.
echo Install 64-bit Python 3.11, 3.12 or 3.13, then run this file again:
echo    https://www.python.org/downloads/windows/
echo Tick "Add python.exe to PATH" in the installer. Avoid 3.14 for now: the
echo packages it needs do not have Windows builds yet.
goto failed

:envfailed
echo.
echo Could not create the .venv folder. Extract the ZIP somewhere you can write
echo to, such as your Documents folder, and run this file again from there.
goto failed

:failed
echo.
echo Press any key to close this window.
pause >nul
endlocal
exit /b 1

rem ---------------------------------------------------------------------------
rem  Find an interpreter. The .venv is built from a full path, because
rem  "py -3.12" and a path with a space in it cannot share one code path.
rem ---------------------------------------------------------------------------
:trypy
py -%1 -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12),(3,13)) else 1)" >nul 2>&1
if errorlevel 1 goto :eof
py -%1 -c "import sys; open('.ultron-python.tmp','w').write(sys.executable)" >nul 2>&1
if not exist ".ultron-python.tmp" goto :eof
set /p PYEXE=<.ultron-python.tmp
del ".ultron-python.tmp" >nul 2>&1
goto :eof

:trypython
python -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12),(3,13)) else 1)" >nul 2>&1
if errorlevel 1 goto :eof
python -c "import sys; open('.ultron-python.tmp','w').write(sys.executable)" >nul 2>&1
if not exist ".ultron-python.tmp" goto :eof
set /p PYEXE=<.ultron-python.tmp
del ".ultron-python.tmp" >nul 2>&1
goto :eof
