@echo off
setlocal
cd /d "%~dp0"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set BUILD_STAMP=%%i
set APP_NAME=NaverPaperCrawler_%BUILD_STAMP%

set "PYTHON_CMD="
where py >nul 2>nul && set "PYTHON_CMD=py"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    echo Python was not found. Install Python 3.11+ and enable PATH, then run this file again.
    pause
    exit /b 1
)

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo Python 3.11+ was not found. Install Python 3.11+ and enable PATH, then run this file again.
    pause
    exit /b 1
)

if not exist venv (
    %PYTHON_CMD% -m venv venv
    if errorlevel 1 (
        echo Failed to create venv.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat
if errorlevel 1 (
    echo Failed to activate venv.
    pause
    exit /b 1
)

python -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name %APP_NAME% ^
  main.py
if errorlevel 1 (
    echo PyInstaller build failed.
    pause
    exit /b 1
)

copy /Y install_scheduler.bat "dist\%APP_NAME%\install_scheduler.bat" >nul
if errorlevel 1 (
    echo Failed to copy install_scheduler.bat.
    pause
    exit /b 1
)

copy /Y uninstall_scheduler.bat "dist\%APP_NAME%\uninstall_scheduler.bat" >nul
if errorlevel 1 (
    echo Failed to copy uninstall_scheduler.bat.
    pause
    exit /b 1
)

if exist ".env" copy /Y ".env" "dist\%APP_NAME%\.env" >nul
if errorlevel 1 (
    echo Failed to copy .env.
    pause
    exit /b 1
)

echo.
echo Build complete: dist\%APP_NAME%\%APP_NAME%.exe
echo Scheduler helpers copied:
echo - dist\%APP_NAME%\install_scheduler.bat
echo - dist\%APP_NAME%\uninstall_scheduler.bat
if exist "dist\%APP_NAME%\.env" echo - dist\%APP_NAME%\.env
echo.
echo Note: This build creates a new timestamped EXE and does not overwrite older builds.
pause
