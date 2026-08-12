@echo off
REM ============================================================
REM start_app.bat
REM Spustí backend, počká na port 8000, potom spustí frontend,
REM počká na jeho port a nakonec otevře aplikaci v prohlížeči.
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT="

for /f %%P in ('powershell -NoProfile -Command "$ports = 3000..3010; foreach ($port in $ports) { if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port $port -InformationLevel Quiet)) { Write-Output $port; break } }"') do set "FRONTEND_PORT=%%P"

if not defined FRONTEND_PORT (
	echo Nenalezen volny frontend port v rozsahu 3000-3010.
	exit /b 1
)

set "PYTHON_EXE=%BACKEND_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

call :wait_for_port %BACKEND_PORT% 1
if errorlevel 1 (
	start "Backend" /MIN cmd /c "cd /d ""%BACKEND_DIR%"" && ""%PYTHON_EXE%"" -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT% --reload"
	call :wait_for_port %BACKEND_PORT% 120
	if errorlevel 1 (
		echo Backend nenabehl na portu %BACKEND_PORT%.
		exit /b 1
	)
)

call :wait_for_port %FRONTEND_PORT% 1
if errorlevel 1 (
	start "Frontend" /MIN cmd /c "cd /d ""%FRONTEND_DIR%"" && npm run dev -- --host 127.0.0.1 --port %FRONTEND_PORT% --strictPort"
	call :wait_for_port %FRONTEND_PORT% 120
	if errorlevel 1 (
		echo Frontend nenabehl na portu %FRONTEND_PORT%.
		exit /b 1
	)
)

start "" "http://localhost:%FRONTEND_PORT%"
exit /b 0

:wait_for_port
set "PORT=%~1"
set "MAX_WAIT=%~2"
set /a ELAPSED=0
:wait_loop
powershell -NoProfile -Command "if (Test-NetConnection -ComputerName 127.0.0.1 -Port %PORT% -InformationLevel Quiet) { exit 0 } else { exit 1 }" >nul 2>nul
if not errorlevel 1 exit /b 0
if %ELAPSED% GEQ %MAX_WAIT% exit /b 1
timeout /t 1 /nobreak >nul
set /a ELAPSED+=1
goto wait_loop
