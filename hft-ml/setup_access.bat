@echo off
echo ============================================================
echo   Setting up Global Access for HFT Terminal
echo ============================================================
echo.

set LAUNCHER_PATH=%LOCALAPPDATA%\Microsoft\WindowsApps\market.cmd

:: Create the launcher script
echo @echo off > "%LAUNCHER_PATH%"
echo. >> "%LAUNCHER_PATH%"
echo if "%%1"=="vishwas20065" ^( >> "%LAUNCHER_PATH%"
echo     echo. >> "%LAUNCHER_PATH%"
echo     echo ======================================== >> "%LAUNCHER_PATH%"
echo     echo   AUTHENTICATED: vishwas20065 >> "%LAUNCHER_PATH%"
echo     echo ======================================== >> "%LAUNCHER_PATH%"
echo     echo. >> "%LAUNCHER_PATH%"
echo     echo Launching HFT Terminal Dashboard... >> "%LAUNCHER_PATH%"
echo     cd /d V:\quant_project\hft-ml >> "%LAUNCHER_PATH%"
echo     python terminal_dashboard.py >> "%LAUNCHER_PATH%"
echo ^) else ^( >> "%LAUNCHER_PATH%"
echo     echo. >> "%LAUNCHER_PATH%"
echo     echo ACCESS DENIED. >> "%LAUNCHER_PATH%"
echo     echo. >> "%LAUNCHER_PATH%"
echo     echo Usage: market vishwas20065 >> "%LAUNCHER_PATH%"
echo     echo. >> "%LAUNCHER_PATH%"
echo ^) >> "%LAUNCHER_PATH%"

:: Verify
if exist "%LAUNCHER_PATH%" (
    echo.
    echo SUCCESS!
    echo.
    echo The command "market vishwas20065" is now available globally.
    echo.
    echo 1. Close this window.
    echo 2. Open a NEW terminal (cmd or PowerShell).
    echo 3. Type: market vishwas20065
    echo.
    echo Press any key to exit...
) else (
    echo.
    echo FAILED to create launcher.
    echo Please run this script as Administrator.
    echo.
    echo Press any key to exit...
)
pause >nul
