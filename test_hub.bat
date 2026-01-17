@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO_ROOT=%~dp0"
pushd "%REPO_ROOT%" >nul || exit /b 1

if not defined VENV_DIR set "VENV_DIR=venv_linux"
if not exist "%VENV_DIR%\\Scripts\\activate.bat" (
    echo Virtual environment not found at "%VENV_DIR%".
    echo Set VENV_DIR to the correct path and retry.
    popd >nul
    exit /b 1
)

call "%VENV_DIR%\\Scripts\\activate.bat"
python -m pytest
set "EXIT_CODE=%ERRORLEVEL%"

popd >nul
exit /b %EXIT_CODE%
