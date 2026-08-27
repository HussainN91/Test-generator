@echo off
setlocal EnableExtensions EnableDelayedExpansion
title STEP Platform

rem ===================================================================
rem  Double-click this file to start the website and open it in Chrome.
rem  Leave the black window open while you are using it; closing that
rem  window is what stops the server.
rem
rem  NOTE ON WHAT THIS OPENS
rem  The STEP teacher and administrator screens are not built yet. This
rem  launcher therefore opens the ADMIN area, which is currently the
rem  only way to see the roster, obligation types, submissions and
rem  review queue. When the real screens exist, change LANDING below
rem  from "admin/" to "" and this file keeps working unchanged.
rem
rem  This launcher must stay in the project folder, next to manage.py.
rem  It is self-contained: if the .venv folder is missing or broken
rem  (e.g. because the project was copied to a new computer), it will
rem  build a fresh one on this machine automatically, as long as
rem  Python is installed here.
rem
rem  It shares one server with "Start Test Generator.bat" - they are the
rem  same website on the same port. If one is already running, this file
rem  will not start a second one; it just opens a window on it.
rem ===================================================================

cd /d "%~dp0"

set "PORT=8000"
set "LANDING=admin/"
set "BASE=http://127.0.0.1:%PORT%/"
set "URL=%BASE%%LANDING%"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "PFX86=%ProgramFiles(x86)%"

rem The script calls itself with this flag to open the browser once the
rem server starts answering.  Everything from :OPEN_WHEN_READY down is
rem that second, background run.
if /I "%~1"=="--open-when-ready" goto OPEN_WHEN_READY

cls
echo(
echo   STEP PLATFORM
echo   ------------------------------------------------------------
echo(

if not exist "%~dp0manage.py" (
  echo   [X] manage.py is not in this folder.
  echo(
  echo       This launcher has to sit in the project folder. It is
  echo       currently in:
  echo       %~dp0
  echo(
  pause
  exit /b 1
)

rem --- Make sure we have a working virtual environment on THIS machine. ---
rem A .venv folder is tied to the computer it was created on (it points
rem at one specific Python install), so it cannot just be copied to a
rem different computer or folder. If it is missing, or was copied from
rem another machine and does not actually work here, First Run Setup
rem rebuilds it (installing Python itself first, if needed).
set "VENV_OK="
if exist "%PYTHON%" (
  "%PYTHON%" -c "1" >nul 2>&1
  if not errorlevel 1 set "VENV_OK=1"
)

if not defined VENV_OK (
  if not exist "%~dp0First Run Setup.bat" (
    echo   [X] Could not find this project's Python, and
    echo       "First Run Setup.bat" is missing so it cannot be set up
    echo       automatically.
    echo(
    echo       Make sure "First Run Setup.bat" is in the same folder as
    echo       this file, then run this file again.
    echo(
    pause
    exit /b 1
  )

  call "%~dp0First Run Setup.bat" --from-launcher
  if errorlevel 1 (
    echo(
    echo   [X] Setup did not finish successfully, so the website cannot
    echo       start. See the messages above for what went wrong.
    echo(
    pause
    exit /b 1
  )

  "%PYTHON%" -c "1" >nul 2>&1
  if errorlevel 1 (
    echo(
    echo   [X] Setup finished but the website still cannot start.
    echo       Show this window to whoever maintains it.
    echo(
    pause
    exit /b 1
  )
)

rem --- Is it already running?  Then just open another window on it. ---
rem "Start Test Generator.bat" runs the same server on the same port, so
rem finding it already up is normal and not a problem.
curl -s --max-time 3 "%BASE%login/" | findstr /C:"English Test" >nul 2>&1
if not errorlevel 1 (
  echo   The website is already running - opening it in Chrome.
  call :OPEN_BROWSER
  ping -n 3 127.0.0.1 >nul
  exit /b 0
)

rem --- Port busy, but not with us?  Say so instead of crashing. ---
netstat -ano | findstr ":%PORT% " | findstr /I "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo   [X] Something else on this computer is already using port %PORT%,
  echo       so the website cannot start.
  echo(
  echo       Close the other program and try again, or ask whoever
  echo       maintains it to change PORT at the top of this file.
  echo(
  pause
  exit /b 1
)

rem --- Make sure the database is up to date before anyone sees it. ---
echo   Checking the database...
"%PYTHON%" manage.py migrate --check >nul 2>&1
if errorlevel 1 (
  echo   Applying pending database updates...
  "%PYTHON%" manage.py migrate --noinput
  if errorlevel 1 (
    echo(
    echo   [X] The database could not be updated, so nothing was started.
    echo       Show this window to whoever maintains it.
    echo(
    pause
    exit /b 1
  )
)

rem --- Reference data STEP needs to be usable at all. ---
rem Both commands are safe to run every time: they update in place and
rem never duplicate. Without them the admin has no regions to file
rem teachers under and no roles to assign, which looks like a bug.
echo   Checking reference data...
"%PYTHON%" manage.py seed_geography >nul 2>&1
if errorlevel 1 (
  echo(
  echo   [!] Could not load the region list. The website will still
  echo       start, but regions may be missing.
  echo(
)
"%PYTHON%" manage.py seed_roles >nul 2>&1
if errorlevel 1 (
  echo(
  echo   [!] Could not create the user roles. The website will still
  echo       start, but roles may be missing.
  echo(
)

rem --- Open Chrome as soon as the server answers, then start it. ---
start "" /b cmd /c ""%~f0" --open-when-ready"

echo   Starting the website...
echo(
echo   Chrome will open on its own in a few seconds.
echo   If it does not, go to:  %URL%
echo(
echo   Sign in with your admin account. The teacher and administrator
echo   screens are not built yet - for now this opens the admin area.
echo(
echo   ** Keep this window open while you are using the website. **
echo      Closing it, or pressing Ctrl+C, shuts it down.
echo   ------------------------------------------------------------
echo(

"%PYTHON%" manage.py runserver 127.0.0.1:%PORT%

echo(
echo   The website has stopped. You can close this window.
echo(
pause
exit /b 0


rem ===================================================================
:OPEN_WHEN_READY
rem Runs in the background: wait for the server to answer, then open
rem Chrome. Gives up quietly after about a minute.
set /a TRIES=0
:WAIT_LOOP
set /a TRIES+=1
curl -s --max-time 2 -o nul "%BASE%login/"
if not errorlevel 1 goto WAIT_DONE
if %TRIES% GEQ 60 exit /b 1
ping -n 2 127.0.0.1 >nul
goto WAIT_LOOP
:WAIT_DONE
call :OPEN_BROWSER
exit /b 0


rem ===================================================================
:OPEN_BROWSER
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%PFX86%\Google\Chrome\Application\chrome.exe" set "CHROME=%PFX86%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if defined CHROME (
  start "" "%CHROME%" --new-window "%URL%"
) else (
  rem Chrome is not installed here - use whatever the default browser is.
  start "" "%URL%"
)
exit /b 0
