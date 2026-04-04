"""
HFT Market Command Center
1. Analyzes Global Macro (US, Asia, Oil, War Proxies, VIX)
2. Audits your Zerodha Portfolio (Manual or Auto)
3. Generates a "Morning Briefing" with Buy/Sell signals
"""

import sys
import os
sys.path.insert(0, os.getcwd())

import yfinance as yf
import pandas as pd
from datetime import datetime
from nse_data_fetcher import NSEDataFetcher
from backtesting_engine import BacktestEngine, MovingAverageCrossoverStrategy, PercentageCommission, PercentageSlippage

# ============================================================
# CONFIGURATION
# ============================================================

# MODE: 'AUTO' (Requires Kite API) or 'MANUAL' (You type stocks)
MODE = 'MANUAL'

# If Manual, list your current holdings here
MANUAL_HOLDINGS = ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'SBIN.NS', 'TTM.NS']

# If Auto, enter your Kite Connect Credentials
KITE_API_KEY = "YOUR_API_KEY_HERE"
KITE_ACCESS_TOKEN = "YOUR_ACCESS_TOKEN_HERE"

# ============================================================

class MarketCommandCenter:
    def __init__(self):
        self.fetcher = NSEDataFetcher()
        print("🌍 Market Command Center Initialized")

    def get_global_sentiment(self):
        """Analyze global markets to determine NSE opening bias"""
        print("\n" + "="*80)
        print("🌏 GLOBAL MACRO ANALYSIS")
        print("="*80)

        # 1. US Markets (Overnight Sentiment)
        us_tickers = {'^DJI': 'Dow Jones', '^IXIC': 'Nasdaq', '^GSPC': 'S&P 500'}
        us_perf = {}
        for sym, name in us_tickers.items():
            try:
                df = yf.Ticker(sym).history(period='2d')
                if len(df) >= 2:
                    change = (df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100
                    us_perf[name] = change
            except: pass

        # 2. Asian Markets (Early Morning Trend)
        asian_tickers = {'^N225': 'Nikkei (Japan)', '^HSI': 'Hang Seng (HK)'}
        asian_perf = {}
        for sym, name in asian_tickers.items():
            try:
                df = yf.Ticker(sym).history(period='2d')
                if len(df) >= 2:
                    change = (df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100
                    asian_perf[name] = change
            except: pass

        # 3. War & Fear Proxies (Macro Stability)
        try:
            oil = yf.Ticker('CL=F').history(period='5d')['Close'].iloc[-1]
            gold = yf.Ticker('GC=F').history(period='5d')['Close'].iloc[-1]
            vix = yf.Ticker('^VIX').history(period='1d')['Close'].iloc[-1]
            defense = yf.Ticker('ITA').history(period='5d')['Close'].iloc[-1] # US Defense ETF
        except: pass

        # Analysis
        print(f"🇺🇸 US Markets: {list(us_perf.values())[0]:+.2f}% (Avg)")
        print(f"🇯🇵 Asian Markets: {list(asian_perf.values())[0]:+.2f}% (Avg)")
        print(f"🛢️  Crude Oil: {oil:.2f} | 🥇 Gold: ${gold:.2f}")
        print(f"⚠️  VIX (Fear):{vix:.2f} | 🚀 Defense Stocks: ${defense:.2f}")

        # Logic
        score = 0
        if list(us_perf.values())[0] > 0: score += 1
        if list(asian_perf.values())[0] > 0: score += 1
        if oil < 80: score += 1 # Lower oil is good for India
        if vix < 20: score += 1

        sentiment = "BULLISH 🟢" if score >= 3 else ("BEARISH 🔴" if score <= 1 else "NEUTRAL 🟡")
        print(f"\n📊 GLOBAL SENTIMENT: {sentiment}")
        return sentiment

    def analyze_portfolio(self):
        """Analyze specific stocks based on Strategy"""
        print("\n" + "="*80)
        print("📂 PORTFOLIO AUDIT")
        print("="*80)

        holdings = []

        if MODE == 'AUTO':
            # Placeholder for Kite Connect Logic
            # from kiteconnect import KiteConnect
            # kite = KiteConnect(api_key=KITE_API_KEY)
            # kite.set_access_token(KITE_ACCESS_TOKEN)
            # holdings_data = kite.holdings()
            # holdings = [h['tradingsymbol'] + '.NS' for h in holdings_data]
            print("⚠️ AUTO Mode requires Kite Connect API Key & Token. Switching to Manual for demo.")
            holdings = MANUAL_HOLDINGS
        else:
            holdings = MANUAL_HOLDINGS

        print(f"Scanning {len(holdings)} holdings...\n")

        for symbol in holdings:
            try:
                df = self.fetcher.get_historical_data(symbol, period='1y', interval='1d')
                if df.empty or len(df) < 200: continue

                timestamps, prices, highs, lows, volumes = self.fetcher.prepare_backtest_data(df)
                current_price = prices[-1]

                # Run Strategy
                engine = BacktestEngine(initial_capital=1_000_000.0)
                strategy = MovingAverageCrossoverStrategy({'short_window': 50, 'long_window': 200})
                engine.add_strategy(strategy)
                engine.load_price_data("TEST", timestamps, prices)

                # Run silently
                result = engine.run_backtest()

                # Check if Strategy is currently "In the Market"
                is_holding = result['final_equity'] > (engine.portfolio.current_cash + 1000)

                signal = "HOLD ✅" if is_holding else "SELL/AVOID ❌"

                print(f"{symbol.replace('.NS', ''):<12} ₹{current_price:<8.2f} | Strategy: {signal}")

            except Exception as e:
                print(f"Error analyzing {symbol}: {e}")

    def run_briefing(self):
        self.get_global_sentiment()
        self.analyze_portfolio()
        print("\n" + "="*80)
        print("✅ BRIEFING COMPLETE. Trade Safe!")
        print("="*80)

if __name__ == "__main__":
    center = MarketCommandCenter()
    center.run_briefing()