@echo off
rem Avvia l'app Trascrizione e apre il browser. Lascia aperta la finestra mentre usi l'app.
cd /d "%~dp0"
title Trascrizione
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente Python non trovato in %~dp0.venv
  echo Segui le istruzioni di installazione nel README.
  pause
  exit /b 1
)
start "" cmd /c "timeout /t 5 /nobreak >nul & start http://localhost:8000"
".venv\Scripts\python.exe" -m app.server
pause
