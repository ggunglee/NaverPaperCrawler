@echo off
setlocal
cd /d "%~dp0"

echo.
echo Naver API key setup
echo.
echo These values are only saved on this computer in:
echo %~dp0.env
echo.
set /p "CLIENT_ID=Naver Client ID: "
set /p "CLIENT_SECRET=Naver Client Secret: "

if not defined CLIENT_ID (
    echo.
    echo Client ID is empty. Nothing was saved.
    pause
    exit /b 1
)

if not defined CLIENT_SECRET (
    echo.
    echo Client Secret is empty. Nothing was saved.
    pause
    exit /b 1
)

(
    echo NAVER_CLIENT_ID=%CLIENT_ID%
    echo NAVER_CLIENT_SECRET=%CLIENT_SECRET%
) > ".env"

echo.
echo Saved .env successfully.
pause
