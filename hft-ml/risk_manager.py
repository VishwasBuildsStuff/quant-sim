"""
Risk Management Overlay for HFT Trading
Position limits, volatility-based stops, drawdown control
"""

import numpy as np
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

@dataclass
class RiskLimits:
    """Risk limits configuration"""
    max_position_per_symbol: int = 10000
    max_portfolio_exposure: float = 10_000_000
    max_daily_loss: float = 50_000
    max_daily_loss_pct: float = 0.01  # 1% of capital
    max_drawdown: float = 0.05  # 5% from peak
    max_volatility: float = 0.50  # Annualized vol threshold
    max_order_rate_per_sec: int = 100
    max_position_concentration: float = 0.20  # 20% in single symbol

    # Volatility-based stops
    vol_stop_multiplier: float = 2.0  # Stop if loss > 2x daily vol
    cooling_off_period_sec: int = 300  # 5 minutes after stop

class HFT_RiskManager:
    """
    Real-time risk management for HFT system
    """

    def __init__(self, limits: RiskLimits = None, initial_capital: float = 10_000_000):
        self.limits = limits or RiskLimits()
        self.initial_capital = initial_capital

        # State tracking
        self.current_positions: Dict[str, int] = {}
        self.daily_pnl = 0.0
        self.peak_equity = initial_capital
        self.current_equity = initial_capital
        self.order_count = 0
        self.order_timestamps = []
        self.is_trading_halted = False
        self.halt_reason = ""
        self.halt_time = None
        self.daily_vol = 0.0
        self.pnl_history = []

    def check_order(self,
                   symbol: str,
                   side: int,
                   quantity: int,
                   price: float,
                   model_confidence: float = 0.0,
                   current_volatility: float = 0.0) -> Tuple[bool, str]:
        """
        Pre-trade risk check

        Returns:
            (allowed, reason)
        """
        # Check if trading halted
        if self.is_trading_halted:
            return False, f"Trading halted: {self.halt_reason}"

        # Check order rate
        if not self._check_order_rate():
            return False, "Order rate limit exceeded"

        # Check position limits
        new_position = self.current_positions.get(symbol, 0) + (quantity if side > 0 else -quantity)
        if abs(new_position) > self.limits.max_position_per_symbol:
            return False, f"Position limit exceeded for {symbol}"

        # Check portfolio exposure
        total_exposure = sum(abs(pos) for pos in self.current_positions.values())
        if total_exposure + quantity > self.limits.max_portfolio_exposure / price:
            return False, "Portfolio exposure limit exceeded"

        # Check concentration
        if abs(new_position) * price > self.limits.max_position_concentration * self.current_equity:
            return False, f"Concentration limit exceeded for {symbol}"

        # Check daily loss limit
        if self.daily_pnl < -self.limits.max_daily_loss:
            self._halt_trading("Daily loss limit exceeded")
            return False, "Daily loss limit exceeded"

        if self.daily_pnl < -self.limits.max_daily_loss_pct * self.initial_capital:
            self._halt_trading("Daily loss percentage limit exceeded")
            return False, "Daily loss percentage limit exceeded"

        # Check drawdown
        current_dd = (self.peak_equity - self.current_equity) / self.peak_equity
        if current_dd > self.limits.max_drawdown:
            self._halt_trading(f"Max drawdown exceeded: {current_dd:.2%}")
            return False, "Maximum drawdown exceeded"

        # Volatility-based stop
        if current_volatility > self.limits.max_volatility:
            self._halt_trading(f"Volatility too high: {current_volatility:.2%}")
            return False, "Volatility threshold exceeded"

        # Model confidence check (optional)
        if model_confidence > 0 and model_confidence < 0.55:
            return False, f"Model confidence too low: {model_confidence:.2f}"

        return True, "Order approved"

    def _check_order_rate(self) -> bool:
        """Check if order rate is within limits"""
        import time
        now = time.time()

        # Remove old timestamps (> 1 second ago)
        self.order_timestamps = [t for t in self.order_timestamps if now - t < 1.0]

        if len(self.order_timestamps) >= self.limits.max_order_rate_per_sec:
            return False

        self.order_timestamps.append(now)
        return True

    def update_position(self, symbol: str, delta: int, price: float, pnl: float = 0):
        """Update position after trade execution"""
        self.current_positions[symbol] = self.current_positions.get(symbol, 0) + delta
        self.daily_pnl += pnl
        self.current_equity += pnl

        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity

        self.pnl_history.append(pnl)

        # Update daily volatility
        if len(self.pnl_history) > 10:
            self.daily_vol = np.std(self.pnl_history[-100:]) * np.sqrt(252 * 390 * 6.5)

    def _halt_trading(self, reason: str):
        """Halt all trading"""
        import time
        self.is_trading_halted = True
        self.halt_reason = reason
        self.halt_time = time.time()
        print(f"TRADING HALTED: {reason}")

    def check_resume(self) -> bool:
        """Check if trading can resume after halt"""
        if not self.is_trading_halted:
            return True

        import time
        if time.time() - self.halt_time > self.limits.cooling_off_period_sec:
            # Reset daily limits for new period
            self.daily_pnl = 0.0
            self.is_trading_halted = False
            self.halt_reason = ""
            print("Trading resumed")
            return True

        return False

    def get_risk_report(self) -> Dict:
        """Get current risk report"""
        current_dd = (self.peak_equity - self.current_equity) / self.peak_equity

        return {
            'current_equity': self.current_equity,
            'peak_equity': self.peak_equity,
            'daily_pnl': self.daily_pnl,
            'daily_pnl_pct': self.daily_pnl / self.initial_capital,
            'current_drawdown': current_dd,
            'daily_volatility': self.daily_vol,
            'is_trading_halted': self.is_trading_halted,
            'halt_reason': self.halt_reason if self.is_trading_halted else None,
            'positions': dict(self.current_positions),
            'total_exposure': sum(abs(p) for p in self.current_positions.values()),
            'order_count_last_sec': len(self.order_timestamps)
        }

    def reset_daily(self):
        """Reset daily limits (call at start of trading day)"""
        self.daily_pnl = 0.0
        self.order_count = 0
        self.order_timestamps = []
        self.is_trading_halted = False
        self.halt_reason = ""
        self.pnl_history = []
        print("Daily risk limits reset")
