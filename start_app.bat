@echo off
REM ============================================================
REM start_app.bat
REM Spustí backend a frontend paralelně v minimálním skrytém režimu
REM a po 3 sekundách otevře aplikaci v prohlížeči na localhost:3000.
REM ============================================================
setlocal

REM Zajistí, že uvicorn z backendu bude dostupný v PATH.
set "VENV_DIR=C:\Users\marti\Documents\muj-akcni-letak\muj-akcni-letak\backend\.venv\Scripts"
set "PATH=%VENV_DIR%;%PATH%"

REM Spuštění backendu
start "" /MIN cmd /c "cd /d ""C:\Users\marti\Documents\muj-akcni-letak\muj-akcni-letak\backend"" && uvicorn main:app --reload --env-file .env"

REM Spuštění frontendu
start "" /MIN cmd /c "cd /d ""C:\Users\marti\Documents\muj-akcni-letak\muj-akcni-letak\frontend"" && npm run dev"

REM Počká 3 sekundy na náběh serverů
timeout /t 3 /nobreak >nul

REM Otevře výchozí prohlížeč na applikaci
start "" http://localhost:3000

exit /b 0
