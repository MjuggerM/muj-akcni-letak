@echo off
REM ============================================================
REM stop_app.bat
REM Bezpečně ukončí všechny běžící procesy node.exe a uvicorn.exe.
REM ============================================================

taskkill /F /T /IM node.exe >nul 2>&1
taskkill /F /T /IM uvicorn.exe >nul 2>&1

exit /b 0
