@echo off
rem Attiva o disattiva l'avvio automatico dell'app quando accendi il PC.
cd /d "%~dp0"
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Trascrizione.lnk"
if exist "%LINK%" (
  del "%LINK%"
  echo Avvio automatico DISATTIVATO.
) else (
  powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LINK); $s.TargetPath='wscript.exe'; $s.Arguments='\"%~dp0avvia-nascosto.vbs\"'; $s.WorkingDirectory='%~dp0'; $s.Save()"
  echo Avvio automatico ATTIVATO: l'app si accendera' da sola all'accensione del PC.
  echo Per disattivarlo, esegui di nuovo questo file.
)
pause
