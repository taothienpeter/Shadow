@echo off
echo ===================================================
echo   Shadow Assistant - Build Standalone Windows App
echo ===================================================
echo.

REM Stop any running instance of Shadow.exe to prevent file locking
taskkill /F /IM Shadow.exe >nul 2>&1

REM Check if PyInstaller is installed
python -m PyInstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [1/3] PyInstaller not found. Installing PyInstaller...
    pip install pyinstaller
) else (
    echo [1/3] PyInstaller is ready.
)

echo.
echo [2/3] Building Shadow executable via shadow.spec...
python -m PyInstaller --noconfirm --clean shadow.spec

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed! Please check the error output above.
    pause
    exit /b %errorlevel%
)

echo.
echo [3/3] Build completed successfully!
echo.
echo ===================================================
echo Output executable location:
echo   dist\Shadow\Shadow.exe
echo ===================================================
echo.
pause
