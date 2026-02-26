@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO_ROOT=%~dp0"
pushd "%REPO_ROOT%ui" >nul || exit /b 1

where npm >nul 2>nul
if errorlevel 1 (
    echo npm is required to run UI tests but was not found in PATH.
    popd >nul
    exit /b 1
)

if not exist "node_modules" (
    echo Installing UI dependencies...
    call npm install
    if errorlevel 1 (
        popd >nul
        exit /b 1
    )
)

call npm run test
set "EXIT_CODE=%ERRORLEVEL%"

popd >nul
exit /b %EXIT_CODE%
