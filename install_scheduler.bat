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

"%APP_EXE%" --install-scheduler --no-gui
if errorlevel 1 (
    echo.
    echo 작업 스케줄러 등록에 실패했습니다.
    pause
    exit /b 1
)

echo.
echo 작업 스케줄러 등록 완료.
echo - 매일 05:50 지면 기사 수집 확인 팝업
echo - 매일 05:50 시작, 3시간마다 온라인 기사 수집
pause
