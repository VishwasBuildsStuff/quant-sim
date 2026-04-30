"""
Time-Series Momentum (TSMOM) Strategy
======================================
Based on: Moskowitz, Ooi & Pedersen (2012) — "Time Series Momentum"
Journal of Financial Economics.

Core idea:
  Signal = sign of past return over a lookback window (default 252-21 bars).
  Position is scaled by inverse realised volatility to equalise risk contribution.
  RSI filter prevents chasing price extremes.
  Exit via momentum reversal (Z-score crosses zero) OR trailing ATR stop.

Plug-in interface: inherits BacktestEngine.Strategy
"""

import numpy as np
from collections import deque
from typing import Optional, Dict, List
from datetime import datetime

# Local imports from the existing backtesting engine
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from backtesting_engine import Strategy, SignalEvent, MarketEvent


class TSMOMStrategy(Strategy):
    """
    Time-Series Momentum Strategy.

    Parameters
    ----------
    lookback       : int   — bars used to compute trailing return (default 252)
    skip           : int   — recent bars skipped to avoid short-term reversal (default 21)
    z_entry        : float — |Z-score| threshold to enter (default 0.5)
    z_exit         : float — |Z-score| threshold to exit (default 0.0)
    rsi_period     : int   — RSI period for entry filter (default 14)
    rsi_ob         : float — RSI overbought level; block LONGs above this (default 75)
    rsi_os         : float — RSI oversold level; block SHORTs below this (default 25)
    atr_period     : int   — ATR period for trailing stop (default 14)
    atr_multiplier : float — ATR multiple for trailing stop (default 2.0)
    vol_window     : int   — window for realised vol normalisation (default 21)
    target_vol     : float — annualised target vol per position (default 0.10 = 10%)
    """

    def __init__(self, params: Dict = None):
        super().__init__("TSMOM", params)

        p = self.params
        self.lookback       = p.get('lookback', 252)
        self.skip           = p.get('skip', 21)
        self.z_entry        = p.get('z_entry', 0.5)
        self.z_exit         = p.get('z_exit', 0.0)
        self.rsi_period     = p.get('rsi_period', 14)
        self.rsi_ob         = p.get('rsi_ob', 75.0)
        self.rsi_os         = p.get('rsi_os', 25.0)
        self.atr_period     = p.get('atr_period', 14)
        self.atr_multiplier = p.get('atr_multiplier', 2.0)
        self.vol_window     = p.get('vol_window', 21)
        self.target_vol     = p.get('target_vol', 0.10)

        # Price / OHLC history buffers
        self._max_buf = max(self.lookback + 10, 300)
        self.closes : deque = deque(maxlen=self._max_buf)
        self.highs  : deque = deque(maxlen=self._max_buf)
        self.lows   : deque = deque(maxlen=self._max_buf)

        # Current state per instrument (strategy is single-instrument in this setup)
        self.position_state = "FLAT"   # FLAT | LONG | SHORT
        self.entry_price    : Optional[float] = None
        self.trailing_high  : Optional[float] = None
        self.trailing_low   : Optional[float] = None

        # Z-score history for normalisation
        self._z_history: List[float] = []

    # ------------------------------------------------------------------
    # INDICATOR HELPERS
    # ------------------------------------------------------------------

    def _log_returns(self) -> np.ndarray:
        """Compute log returns from the close buffer."""
        c = np.array(self.closes)
        return np.diff(np.log(np.maximum(c, 1e-9)))

    def _rsi(self, period: int) -> float:
        """Compute current RSI."""
        c = np.array(self.closes)
        if len(c) < period + 1:
            return 50.0
        deltas = np.diff(c[-(period + 1):])
        gains  = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_g  = np.mean(gains)
        avg_l  = np.mean(losses)
        if avg_l == 0:
            return 100.0
        rs = avg_g / avg_l
        return 100.0 - 100.0 / (1.0 + rs)

    def _atr(self) -> float:
        """Compute current ATR."""
        h = np.array(self.highs)
        l = np.array(self.lows)
        c = np.array(self.closes)
        n = self.atr_period
        if len(c) < n + 1:
            return (h[-1] - l[-1]) if len(h) > 0 else 0.0
        trs = []
        for i in range(-n, 0):
            tr = max(h[i] - l[i],
                     abs(h[i] - c[i - 1]),
                     abs(l[i] - c[i - 1]))
            trs.append(tr)
        return float(np.mean(trs))

    def _momentum_signal(self) -> Optional[float]:
        """
        Compute the momentum Z-score.

        Returns the current Z-score of the lookback return relative to its
        own rolling distribution. Returns None if insufficient data.
        """
        c = np.array(self.closes)
        total_needed = self.lookback + self.skip + 1
        if len(c) < total_needed:
            return None

        # Trailing return: from lookback to skip bars ago (skip most-recent)
        ret = (c[-(self.skip + 1)] - c[-(self.lookback + self.skip + 1)]) \
              / max(c[-(self.lookback + self.skip + 1)], 1e-9)

        # Build a rolling Z-score using the last 100 momentum observations
        self._z_history.append(ret)
        if len(self._z_history) > 100:
            self._z_history.pop(0)

        if len(self._z_history) < 10:
            return None

        mu  = np.mean(self._z_history)
        sig = np.std(self._z_history)
        if sig < 1e-9:
            return None

        return (ret - mu) / sig

    def _realised_vol(self) -> float:
        """Annualised realised volatility over vol_window."""
        rets = self._log_returns()
        if len(rets) < self.vol_window:
            return 0.20  # fallback 20% vol
        daily_vol = float(np.std(rets[-self.vol_window:]))
        return max(daily_vol * np.sqrt(252), 1e-4)

    # ------------------------------------------------------------------
    # MAIN SIGNAL GENERATION
    # ------------------------------------------------------------------

    def on_data(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        """Process a new bar and return a signal if conditions are met."""

        price  = market_event.price
        high   = market_event.high  if market_event.high  > 0 else price * 1.001
        low    = market_event.low   if market_event.low   > 0 else price * 0.999

        self.closes.append(price)
        self.highs.append(high)
        self.lows.append(low)

        z_score = self._momentum_signal()
        if z_score is None:
            return None

        rsi      = self._rsi(self.rsi_period)
        atr      = self._atr()
        real_vol = self._realised_vol()

        # ---- Trailing stop management ----
        if self.position_state == "LONG" and self.entry_price is not None:
            if self.trailing_high is None or price > self.trailing_high:
                self.trailing_high = price
            trail_stop = self.trailing_high - self.atr_multiplier * atr
            if price < trail_stop:
                self.position_state = "FLAT"
                self.entry_price    = None
                self.trailing_high  = None
                return SignalEvent(
                    timestamp=market_event.timestamp,
                    instrument=market_event.instrument,
                    signal_type="EXIT",
                    strength=1.0,
                    data={'reason': 'trailing_stop_long', 'z': round(z_score, 3)}
                )

        elif self.position_state == "SHORT" and self.entry_price is not None:
            if self.trailing_low is None or price < self.trailing_low:
                self.trailing_low = price
            trail_stop = self.trailing_low + self.atr_multiplier * atr
            if price > trail_stop:
                self.position_state = "FLAT"
                self.entry_price    = None
                self.trailing_low   = None
                return SignalEvent(
                    timestamp=market_event.timestamp,
                    instrument=market_event.instrument,
                    signal_type="EXIT",
                    strength=1.0,
                    data={'reason': 'trailing_stop_short', 'z': round(z_score, 3)}
                )

        # ---- Momentum reversal exit ----
        if self.position_state == "LONG" and z_score < self.z_exit:
            self.position_state = "FLAT"
            self.entry_price    = None
            self.trailing_high  = None
            return SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="EXIT",
                strength=abs(z_score),
                data={'reason': 'momentum_reversal', 'z': round(z_score, 3)}
            )

        if self.position_state == "SHORT" and z_score > -self.z_exit:
            self.position_state = "FLAT"
            self.entry_price    = None
            self.trailing_low   = None
            return SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="EXIT",
                strength=abs(z_score),
                data={'reason': 'momentum_reversal', 'z': round(z_score, 3)}
            )

        # ---- Entry signals ----
        # Vol-scaled strength: higher vol → smaller effective size (handled in runner)
        vol_scale = min(self.target_vol / real_vol, 2.0)   # max 2× leverage
        strength  = min(abs(z_score) * vol_scale / 3.0, 1.0)

        if z_score > self.z_entry and self.position_state != "LONG":
            # RSI filter: don't buy into overbought conditions
            if rsi > self.rsi_ob:
                return None
            # Exit existing short first
            sig_type = "SHORT_EXIT_LONG" if self.position_state == "SHORT" else "LONG"
            self.position_state = "LONG"
            self.entry_price    = price
            self.trailing_high  = price
            return SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="LONG",
                strength=strength,
                data={'z': round(z_score, 3), 'rsi': round(rsi, 1),
                      'vol_scale': round(vol_scale, 3), 'real_vol': round(real_vol, 4)}
            )

        if z_score < -self.z_entry and self.position_state != "SHORT":
            # RSI filter: don't short into oversold conditions
            if rsi < self.rsi_os:
                return None
            self.position_state = "SHORT"
            self.entry_price    = price
            self.trailing_low   = price
            return SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="SHORT",
                strength=strength,
                data={'z': round(z_score, 3), 'rsi': round(rsi, 1),
                      'vol_scale': round(vol_scale, 3), 'real_vol': round(real_vol, 4)}
            )

        return None

    def on_end(self):
        """Reset state at end of backtest."""
        self.position_state = "FLAT"
        self.entry_price    = None
        self.trailing_high  = None
        self.trailing_low   = None
        self._z_history.clear()
