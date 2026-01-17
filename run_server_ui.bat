@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Start the RTH hub + northbound API (FastAPI) + the RTH Core UI (Vite dev server).
rem Override defaults via env vars:
rem   VENV_DIR         (default: .venv)
rem   RTH_STORAGE_DIR  (default: RTH_Store)
rem   RTH_DISPLAY_NAME (default: RTH)
rem   RTH_HUB_MODE     (default: embedded)  [embedded|external]
rem   RTH_DAEMON       (default: 0)         [1 to enable daemon mode]
rem   RTH_SERVICES     (default: empty)     comma-separated (e.g. tak_cot,gpsd)
rem   RTH_API_HOST     (default: 127.0.0.1)
rem   RTH_API_PORT     (default: 8000)
rem   VITE_RTH_BASE_URL (default: http://%RTH_API_HOST%:%RTH_API_PORT%)

set "REPO_ROOT=%~dp0"
pushd "%REPO_ROOT%" >nul || exit /b 1

if not defined VENV_DIR set "VENV_DIR=.venv"
if not defined RTH_STORAGE_DIR set "RTH_STORAGE_DIR=RTH_Store"
if not defined RTH_DISPLAY_NAME set "RTH_DISPLAY_NAME=RTH"
if not defined RTH_HUB_MODE set "RTH_HUB_MODE=embedded"
if not defined RTH_DAEMON set "RTH_DAEMON=0"
if not defined RTH_SERVICES set "RTH_SERVICES="
if not defined RTH_API_HOST set "RTH_API_HOST=127.0.0.1"
if not defined RTH_API_PORT set "RTH_API_PORT=8000"
if not defined VITE_RTH_BASE_URL set "VITE_RTH_BASE_URL=http://%RTH_API_HOST%:%RTH_API_PORT%"

rem --- Python venv ---------------------------------------------------------
if exist "%VENV_DIR%\Scripts\python.exe" goto :venv_ready
call :find_python || goto :fail
echo Creating virtual environment in "%VENV_DIR%"...
%PYTHON_CMD% %PYTHON_ARGS% -m venv "%VENV_DIR%" || goto :fail

:venv_ready
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

echo Installing backend dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip || goto :fail
"%PYTHON_EXE%" -m pip install -e . || goto :fail
echo Ensuring WebSocket support for Uvicorn...
"%PYTHON_EXE%" -c "import websockets" >nul 2>nul
if errorlevel 1 (
    "%PYTHON_EXE%" -m pip install "websockets>=12,<14" || goto :fail
)

rem --- UI deps -------------------------------------------------------------
where npm >nul 2>nul
if errorlevel 1 (
    echo npm is required ^(Node.js 20 LTS recommended^) but was not found in PATH.
    goto :fail
)

if not exist "ui\node_modules" (
    echo Installing UI dependencies...
    pushd "ui" >nul || goto :fail
    call npm install
    if errorlevel 1 (
        popd >nul
        goto :fail
    )
    popd >nul
)

rem --- Launch --------------------------------------------------------------
if not exist "%RTH_STORAGE_DIR%" mkdir "%RTH_STORAGE_DIR%" >nul 2>nul

set "HUB_ARGS="
if /I "%RTH_HUB_MODE%"=="embedded" (
    set "HUB_ARGS=!HUB_ARGS! --embedded"
)
if "%RTH_DAEMON%"=="1" (
    set "HUB_ARGS=!HUB_ARGS! --daemon"
)
set "SERVICES_SPACED=%RTH_SERVICES:,= %"
set "HUB_FLAGS="
for %%S in (!SERVICES_SPACED!) do (
    if not "%%~S"=="" set "HUB_FLAGS=!HUB_FLAGS! --service %%~S"
)

echo Starting hub + northbound API at http://%RTH_API_HOST%:%RTH_API_PORT%
start "RTH Hub + API" /D "%REPO_ROOT%" cmd /k ""%PYTHON_EXE%" -m reticulum_telemetry_hub.northbound.gateway --storage_dir "%RTH_STORAGE_DIR%" --display_name "%RTH_DISPLAY_NAME%" --api-host %RTH_API_HOST% --api-port %RTH_API_PORT% !HUB_ARGS! !HUB_FLAGS!"

echo Starting UI dev server at http://localhost:5173
start "RTH UI" /D "%REPO_ROOT%ui" cmd /k "set \"VITE_RTH_BASE_URL=%VITE_RTH_BASE_URL%\" && npm run dev"

echo.
echo Hub+API: storage=%RTH_STORAGE_DIR%  mode=%RTH_HUB_MODE%  daemon=%RTH_DAEMON%  services=%RTH_SERVICES%
echo API: %VITE_RTH_BASE_URL%
echo UI:  http://localhost:5173
echo.
echo Close the spawned windows to stop.

popd >nul
exit /b 0

:find_python
where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py"
    set "PYTHON_ARGS=-3"
    exit /b 0
)
where python >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    set "PYTHON_ARGS="
    exit /b 0
)
echo Python 3.10+ is required but was not found in PATH.
exit /b 1

:fail
popd >nul
exit /b 1
