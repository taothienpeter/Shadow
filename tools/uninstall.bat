@echo off
echo ===================================================
echo   Shadow Assistant - Clean Uninstall Tool
echo ===================================================
echo.
echo WARNING: This will stop Shadow, remove autostart entries,
echo and clean AppData (a backup will be created automatically).
echo.
set /p confirm="Are you sure you want to proceed? (Y/N): "
if /i not "%confirm%"=="Y" (
    echo Uninstall cancelled.
    pause
    exit /b 0
)

echo.
python "%~dp0uninstall.py"
echo.
pause
