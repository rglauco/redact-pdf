@echo off
REM ============================================================
REM  Deploy Redact PDF via GPO
REM
REM  Crea un collegamento (.lnk) nella cartella "Invia a"
REM  dell'utente che punta all'EXE sulla share di rete.
REM
REM  Eseguire come logon script GPO:
REM    User Configuration > Policies > Windows Settings > 
REM    Scripts > Logon
REM
REM  CONFIGURAZIONE: Modifica il percorso della share qui sotto
REM ============================================================

set "EXE_PATH=\\SERVER\tools$\RedactPDF\redact_pdf.exe"
set "LNK_NAME=Redact PDF.lnk"
set "SENDTO=%APPDATA%\Microsoft\Windows\SendTo"

REM Verifica accesso alla share
if not exist "%EXE_PATH%" exit /b 0

REM Crea il collegamento .lnk con PowerShell
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%SENDTO%\%LNK_NAME%'); $s.TargetPath = '%EXE_PATH%'; $s.Description = 'Applica redazione vera ai PDF con annotazioni'; $s.Save()"

REM Pulizia vecchie versioni
del "%SENDTO%\Redact PDF.bat" >nul 2>&1
del "%SENDTO%\Redact PDF.vbs" >nul 2>&1

exit /b 0
