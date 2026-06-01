@echo off
REM ============================================================
REM  Build script per Redact PDF v2.0
REM  Requisiti: Python 3.8+
REM ============================================================

echo.
echo === Build Redact PDF ===
echo.

echo Installazione dipendenze...
pip install -r requirements.txt --quiet

if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo.
echo Compilazione EXE...
pyinstaller ^
    --onefile ^
    --noconsole ^
    --name "redact_pdf" ^
    --hidden-import windnd ^
    --hidden-import customtkinter ^
    --clean ^
    redact_pdf.py

if %ERRORLEVEL%==0 (
    echo.
    echo ============================================================
    echo  BUILD COMPLETATO!
    echo  EXE: dist\redact_pdf.exe
    echo ============================================================
    echo.
    echo Copia dist\redact_pdf.exe nella share di rete, es:
    echo   \\server\tools$\RedactPDF\redact_pdf.exe
    echo.
) else (
    echo ERRORE nella compilazione!
)

pause
