@echo off
setlocal EnableExtensions EnableDelayedExpansion
title English Test Generator - First Run Setup

rem ===================================================================
rem  Prepares this computer to run the Test Generator: makes sure
rem  Python is installed, then builds a fresh virtual environment
rem  (.venv) and installs the app's required packages into it.
rem
rem  Safe to run more than once - it checks each step and skips what
rem  is already done. "Start Test Generator.bat" calls this
rem  automatically the first time it is needed, but you can also run
rem  it by hand to repair or re-check the setup.
rem
rem  Must stay in the project folder, next to manage.py.
rem ===================================================================

cd /d "%~dp0"

set "WANT_PYVER=3.14"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "STAMP=%~dp0.venv\.setup-complete"
set "FROM_LAUNCHER="
if /I "%~1"=="--from-launcher" set "FROM_LAUNCHER=1"

if not defined FROM_LAUNCHER (
  cls
  echo(
  echo   ENGLISH TEST GENERATOR - FIRST RUN SETUP
  echo   ------------------------------------------------------------
  echo(
)

if not exist "%~dp0manage.py" (
  echo   [X] manage.py is not in this folder.
  echo(
  echo       This file has to sit in the project folder. It is
  echo       currently in:
  echo       %~dp0
  echo(
  goto FAIL
)

rem --- Step 1: is there already a working venv? Then nothing to do. ---
if exist "%PYTHON%" (
  "%PYTHON%" -c "1" >nul 2>&1
  if not errorlevel 1 (
    echo   Already set up on this computer. Nothing to do.
    goto DONE
  )
)

echo   Setting up the app for the first time on this computer...
echo   ^(this only happens once, and can take a few minutes^)
echo(

rem --- Step 2: find a usable Python already on this computer. ---
call :FIND_SYSTEM_PYTHON
if defined SYSPY goto HAVE_PYTHON

echo   Python was not found on this computer. Installing it...
echo(

rem --- Step 3: install Python via winget (built into Windows 11). ---
where winget >nul 2>&1
if not errorlevel 1 (
  winget install --id Python.Python.%WANT_PYVER% -e --source winget --scope user --silent --accept-package-agreements --accept-source-agreements
)

rem winget just installed Python, but this window's PATH will not
rem include it yet - look for it directly instead of trusting PATH.
call :FIND_SYSTEM_PYTHON
if defined SYSPY goto HAVE_PYTHON

rem --- Step 4: winget unavailable or failed - download the official ---
rem installer directly and run it quietly for the current user only. ---
echo   Downloading the official Python installer...
set "PYEXE=%TEMP%\python-%WANT_PYVER%-setup.exe"
curl -L -s -o "%PYEXE%" "https://www.python.org/ftp/python/%WANT_PYVER%.0/python-%WANT_PYVER%.0-amd64.exe"
if not exist "%PYEXE%" (
  echo(
  echo   [X] Could not download Python. Check that this computer is
  echo       connected to the internet, then run this file again.
  echo(
  goto FAIL
)

echo   Installing Python ^(this can take a minute^)...
"%PYEXE%" /passive InstallAllUsers=0 PrependPath=1 Include_launcher=1
del "%PYEXE%" >nul 2>&1

call :FIND_SYSTEM_PYTHON
if defined SYSPY goto HAVE_PYTHON

echo(
echo   [X] Python still could not be found after trying to install it.
echo(
echo       Please install it yourself from:
echo       https://www.python.org/downloads/
echo(
echo       During setup, tick "Add python.exe to PATH", then run this
echo       file again.
echo(
goto FAIL

:HAVE_PYTHON
rem --- Step 5: build the venv with whatever Python we found/installed. ---
if exist "%~dp0.venv" rd /s /q "%~dp0.venv"

echo   Creating a private copy of Python for this app...
!SYSPY! -m venv "%~dp0.venv"
if errorlevel 1 (
  echo(
  echo   [X] Could not create the virtual environment.
  echo       Show this window to whoever maintains the app.
  echo(
  goto FAIL
)

if not exist "%PYTHON%" (
  echo(
  echo   [X] The virtual environment did not get created correctly.
  echo       Show this window to whoever maintains the app.
  echo(
  goto FAIL
)

rem --- Step 6: install the app's required packages into it. ---
echo   Installing the app's requirements ^(needs internet access^)...
"%PYTHON%" -m pip install --quiet --upgrade pip
if errorlevel 1 (
  echo(
  echo   [X] Could not update pip. Check the internet connection and
  echo       try again.
  echo(
  goto FAIL
)

"%PYTHON%" -m pip install --quiet -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo(
  echo   [X] Could not install the required packages. Check that this
  echo       computer is connected to the internet, then try again.
  echo(
  goto FAIL
)

rem --- Step 7: prove the app can actually import, not just that pip exited 0. ---
"%PYTHON%" -c "import django" >nul 2>&1
if errorlevel 1 (
  echo(
  echo   [X] Setup finished but the app still cannot start. Show this
  echo       window to whoever maintains the app.
  echo(
  goto FAIL
)

>"%STAMP%" (
  echo Set up on %DATE% %TIME%
  "%PYTHON%" --version
)

echo   Done. The app is ready to use.
echo(

:DONE
if not defined FROM_LAUNCHER (
  pause
)
exit /b 0

:FAIL
if not defined FROM_LAUNCHER (
  pause
)
exit /b 1


rem ===================================================================
:FIND_SYSTEM_PYTHON
rem Looks for a usable Python 3.12+ on this computer and sets SYSPY to
rem the command that runs it. Checks the "py" launcher and PATH first,
rem then common install folders directly - this matters right after
rem installing Python in this same window, before PATH has refreshed.
rem Leaves SYSPY undefined if nothing suitable is found.
set "SYSPY="

py -3 -c "import sys; exit(0 if sys.version_info>=(3,12) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "SYSPY=py -3"
  exit /b 0
)

python -c "import sys; exit(0 if sys.version_info>=(3,12) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "SYSPY=python"
  exit /b 0
)

for %%D in (
  "%LocalAppData%\Programs\Python\Python314"
  "%LocalAppData%\Programs\Python\Python313"
  "%LocalAppData%\Programs\Python\Python312"
  "%ProgramFiles%\Python314"
  "%ProgramFiles%\Python313"
  "%ProgramFiles%\Python312"
) do (
  if exist "%%~D\python.exe" (
    "%%~D\python.exe" -c "1" >nul 2>&1
    if not errorlevel 1 (
      set "SYSPY="%%~D\python.exe""
      exit /b 0
    )
  )
)

exit /b 1
