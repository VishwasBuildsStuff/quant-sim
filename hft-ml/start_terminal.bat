@echo off
echo ============================================================
echo   HFT Terminal Trading Dashboard
echo ============================================================
echo.
echo Starting Bloomberg Terminal-style interface...
echo.
echo CONTROLS:
echo   1-4 : Switch tabs (Overview/OrderBook/Trades/Portfolio)
echo   B   : Buy order
echo   S   : Sell order
echo   R   : Select RELIANCE
echo   T   : Select TCS
echo   I   : Select INFY
echo   H   : Select HDFCBANK
echo   M   : Select TATAMOTORS
echo   0-9 : Enter quantity
echo   ENTER: Execute order
echo   Q   : Quit
echo.
echo ============================================================
echo.

cd V:\quant_project\hft-ml
python terminal_dashboard.py

pause
