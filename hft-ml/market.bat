@echo off
REM Global launcher for HFT Terminal with Login
REM Access from anywhere by typing "market"

cd /d V:\quant_project\hft-ml
python terminal_login.py %*
