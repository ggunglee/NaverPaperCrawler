@echo off
setlocal
set "APP_EXE="
for %%F in ("%~dp0NaverPaperCrawler*.exe") do set "APP_EXE=%%~fF"

if not defined APP_EXE (
    if exist "%~dp0venv\Scripts\python.exe" (
        "%~dp0venv\Scripts\python.exe" "%~dp0main.py" --install-scheduler --no-gui
    ) else (
        python "%~dp0main.py" --install-scheduler --no-gui
    )
) else (
    "%APP_EXE%" --install-scheduler --no-gui
)

if errorlevel 1 (
    echo.
    echo 작업 스케줄러 등록에 실패했습니다.
    pause
    exit /b 1
)

echo.
echo 작업 스케줄러 등록 완료.
echo - 매일 오전 6시 아침보고 생성 및 텔레그램 발송
echo - 지면: 당일 지면 / 온라인: 전날 18시부터 당일 06시까지
pause
