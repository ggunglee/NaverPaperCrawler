@echo off
setlocal
set "APP_EXE="
for %%F in ("%~dp0NaverPaperCrawler*.exe") do set "APP_EXE=%%~fF"

if not defined APP_EXE (
    echo NaverPaperCrawler EXE를 찾지 못했습니다.
    echo 이 파일을 EXE와 같은 폴더에서 실행해 주세요.
    pause
    exit /b 1
)

"%APP_EXE%" --uninstall-scheduler --no-gui
if errorlevel 1 (
    echo.
    echo 작업 스케줄러 제거에 실패했습니다.
    pause
    exit /b 1
)

echo.
echo 작업 스케줄러 제거 완료.
pause
