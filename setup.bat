@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CareerHub - Setup

set "PY=python"
if exist venv\Scripts\python.exe set "PY=venv\Scripts\python.exe"

echo ==================================================
echo              CAREERHUB - FIRST SETUP
echo ==================================================
echo.

where python >nul 2>nul
if errorlevel 1 goto :python_missing

if not exist venv\Scripts\python.exe (
    echo [1/5] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 goto :venv_error
) else (
    echo [1/5] Virtual environment already exists.
)

set "PY=venv\Scripts\python.exe"

echo [2/5] Checking Python...
%PY% --version
if errorlevel 1 goto :python_error

echo.
echo [3/5] Installing dependencies...
%PY% -m pip install --disable-pip-version-check --upgrade pip
if errorlevel 1 goto :pip_error
%PY% -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :pip_error

echo.
if not exist .env (
    echo [4/5] Creating local configuration...
    %PY% -c "import secrets; from pathlib import Path; p=Path('.env'); p.write_text('SECRET_KEY='+secrets.token_urlsafe(48)+'\nDATABASE_URL=sqlite:///careerhub.db\nDEV_SHOW_RESET_LINK=1\nREQUIRE_EMAIL_VERIFICATION=0\nSESSION_COOKIE_SECURE=0\nREMEMBER_COOKIE_SECURE=0\nRATELIMIT_STORAGE_URI=memory://\nMAX_CONTENT_LENGTH=12582912\nMAX_RESUME_SIZE=4194304\nMAX_PHOTO_SIZE=2097152\nAPP_BASE_URL=http://127.0.0.1:5000\nAUTO_CREATE_DB=1\nTRUST_PROXY=0\nAUTO_APPROVE_RECRUITER_COMPANIES=1\nHEALTHCHECK_ENABLED=1\nMAX_SEARCH_RESULTS=500\n', encoding='utf-8')"
    if errorlevel 1 goto :config_error
) else (
    echo [4/5] Existing .env found - keeping it.
)

echo.
echo [5/5] Creating/upgrading database...
rem AUTO_CREATE_DB bootstraps the current model schema before Alembic
rem applies the legacy/Phase 3/Phase 4 migration history.
set "AUTO_CREATE_DB=1"
%PY% -m flask --app run:app db upgrade
if errorlevel 1 goto :migration_error

if exist seed.py (
    echo.
    echo Loading demo data...
    %PY% seed.py
    if errorlevel 1 echo WARNING: Demo data was not loaded. CareerHub can still start.
)

echo.
echo Verifying the configured database connection...
%PY% -c "from run import app; from sqlalchemy import text; from app.extensions import db; ctx=app.app_context(); ctx.push(); db.session.execute(text('SELECT 1')); db.session.rollback(); print('Database connection: OK ('+db.engine.dialect.name+')'); ctx.pop()"
if errorlevel 1 goto :migration_error

echo.
echo ==================================================
echo       SETUP COMPLETED SUCCESSFULLY
echo ==================================================
echo.
echo Now double-click START.BAT
pause
exit /b 0

:python_missing
echo.
echo ERROR: Python was not found.
echo Install Python 3.11 or newer and enable "Add Python to PATH".
pause
exit /b 1

:venv_error
echo.
echo ERROR: Could not create the virtual environment.
pause
exit /b 1

:python_error
echo.
echo ERROR: The virtual-environment Python could not start.
pause
exit /b 1

:pip_error
echo.
echo ERROR: Dependency installation failed.
echo Check your internet connection and run SETUP.BAT again.
pause
exit /b 1

:config_error
echo.
echo ERROR: Could not create .env configuration.
pause
exit /b 1

:migration_error
echo.
echo ERROR: Database setup or migration failed.
echo Copy the COMPLETE error shown above and send it to ChatGPT.
pause
exit /b 1
