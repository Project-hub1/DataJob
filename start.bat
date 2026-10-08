@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CareerHub

if not exist venv\Scripts\python.exe (
    echo CareerHub is not set up yet.
    echo.
    echo Starting setup automatically...
    call setup.bat
    if errorlevel 1 exit /b 1
)

set "PY=venv\Scripts\python.exe"
if not exist .env (
    echo Configuration is missing. Running setup...
    call setup.bat
    if errorlevel 1 exit /b 1
)

%PY% --version >nul 2>nul
if errorlevel 1 (
    echo CareerHub virtual environment is broken.
    echo Delete the venv folder and run START.BAT again.
    pause
    exit /b 1
)

echo.
echo Preparing local database schema...
%PY% -c "from run import app; from app.extensions import db; app.app_context().push(); db.create_all()"
if errorlevel 1 goto :migration_error

echo Checking database migrations...
set "AUTO_CREATE_DB=1"
%PY% -m flask --app run:app db upgrade
if errorlevel 1 goto :migration_error

echo Verifying the configured database connection...
%PY% -c "from run import app; from sqlalchemy import text; from app.extensions import db; ctx=app.app_context(); ctx.push(); db.session.execute(text('SELECT 1')); db.session.rollback(); print('Database connection: OK ('+db.engine.dialect.name+')'); ctx.pop()"
if errorlevel 1 goto :migration_error

cls
echo ==================================================
echo              CAREERHUB IS STARTING
echo ==================================================
echo.
echo URL: http://127.0.0.1:5000
echo.
echo Browser will open automatically.
echo Keep this window open while using CareerHub.
echo Press Ctrl+C here to stop the server.
echo.

start "CareerHub Browser" http://127.0.0.1:5000
%PY% run.py

if errorlevel 1 goto :server_error
exit /b 0

:migration_error
echo.
echo ERROR: Database setup or migration failed.
echo Copy the COMPLETE error above and send it to ChatGPT.
pause
exit /b 1

:server_error
echo.
echo ERROR: CareerHub stopped unexpectedly.
echo Copy the COMPLETE error above and send it to ChatGPT.
pause
exit /b 1
