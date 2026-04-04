"""
Live Paper Trading Engine
Simulates real-time trading using Yahoo Finance data.
Logs all actions to paper_trades.csv for analysis.
"""

import yfinance as yf
import pandas as pd
import time
import os
from datetime import datetime, time as dt_time
from risk_manager import RiskManager
import requests
from telegram_notifier import send_telegram_alert

# ============================================================
# CONFIGURATION
# ============================================================
WATCHLIST = {
    'RELIANCE': 'RELIANCE.NS',
    'TCS': 'TCS.NS',
    'INFY': 'INFY.NS',
    'HDFCBANK': 'HDFCBANK.NS',
    'TTM': 'TTM.NS'
}

INITIAL_CAPITAL = 1_000_000.0  # Fake starting money (₹10 Lakh)
STRATEGY = {'short_ma': 20, 'long_ma': 50}
UPDATE_INTERVAL = 300  # Seconds (5 Minutes)
LOG_FILE = 'paper_trading_log.csv'

# Risk Management
SLIPPAGE_PCT = 0.0005  # 0.05% slippage per trade
COMMISSION_PCT = 0.0003 # Brokerage + Taxes

# Telegram credentials (replace with your own)
TELEGRAM_TOKEN = "8444142086:AAGwgdhCpt40bINFIYVY9SN7acJXdhU1ego"
TELEGRAM_CHAT_ID = "vishydareal_bot"

# ============================================================

class PaperTrader:
    def __init__(self):
        self.cash = INITIAL_CAPITAL
        self.portfolio = {sym: {'qty': 0, 'avg_price': 0.0} for sym in WATCHLIST}
        self.trades_log = []

        # Setup CSV
        if not os.path.exists(LOG_FILE):
            headers = ['Time', 'Symbol', 'Action', 'Price', 'Qty', 'Total', 'Cash_Balance', 'PnL']
            pd.DataFrame(columns=headers).to_csv(LOG_FILE, index=False)

        self.risk_config = {
            'max_risk_per_trade' : 0.01, 
            'max_daily_loss' : 5000.0 ,
            'atr_multiplier' : 2.0, 
            'max_position_pct' : 0.20
        }
        self.risk_manager = RiskManager(self.risk_config)

        print("🚀 PAPER TRADER INITIALIZED")
        print(f"💰 Wallet: ₹{self.cash:,.2f}")
        print(f"📅 Monitoring: {list(WATCHLIST.keys())}")
        print("="*60)

    def fetch_live_data(self, symbol):
        """Fetch latest 5-min candle"""
        try:
            # Yahoo Finance '5m' interval
            df = yf.download(symbol, period='5d', interval='5m', progress=False)
            if df.empty: return None

            # Get the last complete candle
            last_row = df.iloc[-1]
            return {
                'close': last_row['Close'],
                'high': last_row['High'],
                'low': last_row['Low']
            }
        except Exception as e:
            print(f"❌ Error fetching {symbol}: {e}")
            return None

    def get_signal(self, symbol):
        """Calculate MAs and return BUY/SELL/HOLD"""
        try:
            # Fetch more data for accurate MA calculation
            df = yf.download(symbol, period='3mo', interval='5m', progress=False)
            if len(df) < STRATEGY['long_ma']:
                return 'HOLD', 0.0, 0.0

            df['MA_Short'] = df['Close'].rolling(window=STRATEGY['short_ma']).mean()
            df['MA_Long'] = df['Close'].rolling(window=STRATEGY['long_ma']).mean()

            current_price = df['Close'].iloc[-1]
            ma_short = df['MA_Short'].iloc[-1]
            ma_long = df['MA_Long'].iloc[-1]
            ma_short_prev = df['MA_Short'].iloc[-2]
            ma_long_prev = df['MA_Long'].iloc[-2]

            # Crossover Logic
            if ma_short_prev <= ma_long_prev and ma_short > ma_long:
                return 'BUY', ma_short, ma_long
            elif ma_short_prev >= ma_long_prev and ma_short < ma_long:
                return 'SELL', ma_short, ma_long
            else:
                return 'HOLD', ma_short, ma_long
        except Exception:
            return 'HOLD', 0.0, 0.0

    def execute_trade(self, symbol, signal, current_price):
        """Simulate the trade (with Telegram alerts)"""
        ticker = symbol.split('.')[0] # Clean name for logs
        pos = self.portfolio[symbol]

        # Adjust price for slippage (make it realistic)
        if signal == 'BUY':
            exec_price = current_price * (1 + SLIPPAGE_PCT)
            cost = exec_price * 10 * (1 + COMMISSION_PCT) # Buying 10 shares

            if self.cash >= cost and pos['qty'] == 0:
                self.cash -= cost
                pos['qty'] = 10
                pos['avg_price'] = exec_price
                self.log_trade(ticker, 'BUY', exec_price, 10, self.cash, 0)
                print(f"🟢 BUY {ticker} @ ₹{exec_price:.2f}")

                # --- Telegram alert for BUY ---
                msg = f"🟢 *BUY SIGNAL*\nStock: {ticker}\nPrice: ₹{exec_price:.2f}\nQty: {pos['qty']}\nStop Loss: N/A (fixed size)"
                send_telegram_alert(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

        elif signal == 'SELL':
            if pos['qty'] > 0:
                exec_price = current_price * (1 - SLIPPAGE_PCT)
                revenue = exec_price * pos['qty'] * (1 - COMMISSION_PCT)

                # Calculate Realized PnL
                pnl = (exec_price - pos['avg_price']) * pos['qty']

                # Update daily P&L in risk manager (so Telegram alert shows correct value)
                self.risk_manager.update_daily_pnl(pnl)

                self.cash += revenue
                self.log_trade(ticker, 'SELL', exec_price, pos['qty'], self.cash, pnl)
                print(f"🔴 SELL {ticker} @ ₹{exec_price:.2f} | PnL: ₹{pnl:.2f}")

                # --- Telegram alert for SELL ---
                msg = f"🔴 *SELL SIGNAL*\nStock: {ticker}\nPrice: ₹{exec_price:.2f}\nPnL: ₹{pnl:.2f}\n\nDaily P&L: ₹{self.risk_manager.daily_pnl:.2f}"
                send_telegram_alert(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

                pos['qty'] = 0
                pos['avg_price'] = 0.0

    def log_trade(self, ticker, action, price, qty, balance, pnl):
        log_entry = {
            'Time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'Symbol': ticker,
            'Action': action,
            'Price': price,
            'Qty': qty,
            'Total': price * qty,
            'Cash_Balance': balance,
            'PnL': pnl
        }

        # Create a single-row dataframe
        df_new = pd.DataFrame([log_entry])

        # Append to existing file without reading the whole thing
        # header=False ensures we don't repeat column names
        df_new.to_csv(LOG_FILE, mode='a', header=False, index=False)

    def run(self):
        """Main Loop"""
        print("⏳ Waiting for Market Open (9:15 AM IST)...")

        while True:
            now = datetime.now().time()

            # Market Hours Check (9:15 AM to 3:30 PM IST)
            if dt_time(9, 15) <= now <= dt_time(15, 30):
                print(f"\n🔔 Checking Market at {now.strftime('%H:%M')}...")

                for name, symbol in WATCHLIST.items():
                    signal, ma_s, ma_l = self.get_signal(symbol)
                    data = self.fetch_live_data(symbol)

                    if data and signal != 'HOLD':
                        self.execute_trade(symbol, signal, data['close'])
                    elif data:
                        print(f"  {name}: ₹{data['close']:.2f} (MA: {ma_s:.1f}/{ma_l:.1f}) - HOLD")

                time.sleep(UPDATE_INTERVAL)
            else:
                time.sleep(60) # Sleep 1 min until market opens

if __name__ == "__main__":
    bot = PaperTrader()
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n🛑 Paper Trader Stopped.")