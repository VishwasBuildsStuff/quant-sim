@echo off
REM Quick Start Launcher for HFT Autonomous Trading Bot

echo.
echo ============================================================
echo   HFT AUTONOMOUS TRADING BOT - QUICK START
echo ============================================================
echo.

:menu
echo.
echo What would you like to do?
echo.
echo 1. Train multi-model ensemble on live data
echo 2. Start autonomous trading bot
echo 3. View live watchlist only
echo 4. Fetch fresh live data
echo 5. Backtest existing model
echo 6. View trade history
echo 7. Exit
echo.
set /p choice="Enter choice (1-7): "

if "%choice%"=="1" goto train
if "%choice%"=="2" goto autotrade
if "%choice%"=="3" goto watchlist
if "%choice%"=="4" goto fetch
if "%choice%"=="5" goto backtest
if "%choice%"=="6" goto history
if "%choice%"=="7" goto end
goto menu

:train
echo.
echo ============================================================
echo   TRAINING MULTI-MODEL ENSEMBLE
echo ============================================================
echo.
python multi_model_ensemble.py --data data/RELIANCE_live.parquet --output output/RELIANCE_multi_ensemble.joblib
pause
goto menu

:autotrade
echo.
echo ============================================================
echo   STARTING AUTONOMOUS TRADING BOT
echo ============================================================
echo.
echo The bot will:
echo - Monitor your watchlist
echo - Make predictions using ensemble models
echo - Execute trades automatically
echo - Manage risk and positions
echo.
echo Press Ctrl+C to stop
echo.
pause
python auto_trader.py
pause
goto menu

:watchlist
echo.
echo ============================================================
echo   LIVE WATCHLIST VIEWER
echo ============================================================
echo.
python connect_live_market.py live --symbol RELIANCE --interval 5 --duration 30
pause
goto menu

:fetch
echo.
echo ============================================================
echo   FETCHING FRESH LIVE DATA
echo ============================================================
echo.
set /p days="How many days? (default 60): "
if "%days%"=="" set days=60
python connect_live_market.py fetch --symbol RELIANCE --days %days% --data-interval 5m
pause
goto menu

:backtest
echo.
echo ============================================================
echo   BACKTESTING MODEL
echo ============================================================
echo.
python backtest_fast.py --model output/RELIANCE_live_trained.joblib --data data/RELIANCE_live.parquet --symbol RELIANCE
pause
goto menu

:history
echo.
echo ============================================================
echo   TRADE HISTORY
echo ============================================================
echo.
if exist trade_history_*.json (
    dir /b trade_history_*.json
    echo.
    set /p file="Enter filename to view: "
    type %file%
) else (
    echo No trade history found
)
pause
goto menu

:end
echo.
echo Thanks for using HFT Autonomous Trading Bot!
echo.
exit
