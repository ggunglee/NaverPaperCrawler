@echo off
setlocal
cd /d "%~dp0"

for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('DesktopDirectory')"`) do set "DESKTOP_DIR=%%D"
set "DEFAULT_DEST=%DESKTOP_DIR%\NaverPaperCrawler"

echo.
echo NaverPaperCrawler install helper
echo.
echo Default install folder:
echo %DEFAULT_DEST%
echo.
set /p "DEST=Install folder path [press Enter for default]: "
if not defined DEST set "DEST=%DEFAULT_DEST%"

if not exist "%DEST%" mkdir "%DEST%"
if errorlevel 1 (
    echo.
    echo Failed to create install folder.
    pause
    exit /b 1
)

robocopy "%~dp0" "%DEST%" /E /XD "_temp" /XF "*.zip" >nul
if errorlevel 8 (
    echo.
    echo Failed to copy files.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$dest = '%DEST%';" ^
  "$desktop = [Environment]::GetFolderPath('DesktopDirectory');" ^
  "$exe = Get-ChildItem -LiteralPath $dest -Filter 'NaverPaperCrawler*.exe' | Select-Object -First 1;" ^
  "if (-not $exe) { throw 'NaverPaperCrawler exe not found.' }" ^
  "$shell = New-Object -ComObject WScript.Shell;" ^
  "$shortcut = $shell.CreateShortcut((Join-Path $desktop 'NaverPaperCrawler.lnk'));" ^
  "$shortcut.TargetPath = $exe.FullName;" ^
  "$shortcut.WorkingDirectory = $dest;" ^
  "$shortcut.IconLocation = $exe.FullName;" ^
  "$shortcut.Save();"
if errorlevel 1 (
    echo.
    echo Files were copied, but creating the desktop shortcut failed.
    pause
    exit /b 1
)

echo.
echo Install complete.
echo Folder: %DEST%
echo Shortcut: %DESKTOP_DIR%\NaverPaperCrawler.lnk
echo.
pause
