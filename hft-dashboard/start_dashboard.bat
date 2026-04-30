@echo off
echo ============================================================
echo   HFT Bloomberg Terminal Dashboard - Startup
echo ============================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo [2/3] Dependencies installed successfully
echo.
echo [3/3] Starting Bloomberg Terminal Dashboard...
echo.
echo ============================================================
echo   Dashboard will be available at: http://localhost:8000
echo   Press Ctrl+C to stop the server
echo ============================================================
echo.

python dashboard_server.py

pause
