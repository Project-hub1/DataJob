@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CareerHub - Diagnostics

echo ==================================================
echo             CAREERHUB DIAGNOSTICS
echo ==================================================
echo.
where python
if errorlevel 1 echo System Python: NOT FOUND
if exist venv\Scripts\python.exe (
  echo Virtual environment: FOUND
  venv\Scripts\python.exe --version
  echo.
  echo Flask:
  venv\Scripts\python.exe -c "import flask; print(flask.__version__)" 2>nul || echo Flask: NOT INSTALLED
  echo.
  echo Database:
  venv\Scripts\python.exe -c "from run import app; from sqlalchemy import text; from app.extensions import db; ctx=app.app_context(); ctx.push(); db.session.execute(text('SELECT 1')); db.session.rollback(); print('Database connection: OK'); print('Database driver: '+db.engine.dialect.name); ctx.pop()" 2>nul || echo Database connection: FAILED
  echo.
  echo Migration status:
  venv\Scripts\python.exe -m flask --app run:app db current
) else (
  echo Virtual environment: NOT FOUND
)
echo.
pause
