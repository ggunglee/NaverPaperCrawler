@echo off
setlocal
cd /d "%~dp0"

set "APP_EXE="
for %%F in ("NaverPaperCrawler*.exe") do set "APP_EXE=%%~fF"

if not defined APP_EXE (
    echo NaverPaperCrawler executable was not found in this folder.
    pause
    exit /b 1
)

start "" "%APP_EXE%"
