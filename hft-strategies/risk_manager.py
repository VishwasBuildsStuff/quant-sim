"""
Risk Manager Module
Protects capital via dynamic position sizing, ATR stop-losses, and circuit breakers.
"""

import pandas as pd
import numpy as np

class RiskManager:
    def __init__(self, config):
        # Configuration
        self.max_risk_per_trade = config.get('max_risk_per_trade', 0.01)    # Risk 1% per trade
        self.max_daily_loss_limit = config.get('max_daily_loss', 5000.0)    # Halt if lost ₹5000
        self.atr_multiplier = config.get('atr_multiplier', 2.0)             # Stop loss = 2x ATR
        self.max_position_pct = config.get('max_position_pct', 0.20)        # Max 20% of cash in one stock

        # State Tracking
        self.daily_pnl = 0.0
        self.is_halted = False

        print(f"🛡️ Risk Manager Initialized: Risk{self.max_risk_per_trade*100}% | Daily Limit ₹{self.max_daily_loss_limit}")

    def calculate_atr(self, df, period=14):
        """Calculate Average True Range (Volatility)"""
        if len(df) < period + 1:
            return None

        high = df['High']
        low = df['Low']
        close = df['Close'].shift(1)

        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]

        return atr

    def calculate_position_and_sl(self, account_cash, entry_price, atr_value):
        """
        Returns: (Quantity, Stop_Loss_Price)
        Logic:
        1. Determine Stop Loss distance based on volatility (ATR).
        2. Calculate Quantity so that if SL hits, we only lose max_risk_per_trade %.
        """
        if atr_value is None or np.isnan(atr_value):
            atr_value = entry_price * 0.02 # Fallback to 2% if no data

        sl_distance = atr_value * self.atr_multiplier
        stop_loss_price = entry_price - sl_distance

        # How much money are we willing to lose on this trade?
        risk_amount = account_cash * self.max_risk_per_trade

        # How many shares can we buy before hitting that risk limit?
        if sl_distance > 0:
            risk_based_qty = int(risk_amount / sl_distance)
        else:
            risk_based_qty = 0

        # Check absolute exposure limit (e.g., don't put more than 20% of cash in one stock)
        max_exposure = account_cash * self.max_position_pct
        exposure_qty = int(max_exposure / entry_price)

        # Take the lower of the two
        final_qty = min(risk_based_qty, exposure_qty)

        # Round to nearest lot size (e.g., 1)
        final_qty = max(0, final_qty)

        return final_qty, stop_loss_price

    def check_circuit_breaker(self):
        """Returns False if we should stop trading for the day"""
        if self.daily_pnl < -self.max_daily_loss_limit:
            if not self.is_halted:
                print(f"🚨 CIRCUIT BREAKER TRIGGERED! Daily Loss limit reached (₹{self.daily_pnl:.2f}). Halting trading.")
                self.is_halted = True
            return False
        return True

    def update_daily_pnl(self, realized_pnl):
        """Update running P&L after a trade is closed"""
        self.daily_pnl += realized_pnl

    def reset_daily(self):
        """Call this at market open to reset limits"""
        self.daily_pnl = 0.0
        self.is_halted = False