@echo off
setlocal
set "DATA_DIR=%USERPROFILE%\.naver_news_crawler"
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
start "" "%DATA_DIR%"
