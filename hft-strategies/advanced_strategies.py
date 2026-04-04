"""
Advanced Strategy Library
Includes: Pairs Trading, Momentum Breakout, VWAP Reversion
All strategies inherit from Strategy base class in backtesting_engine.py
"""

import numpy as np
import pandas as pd
from datetime import datetime
from backtesting_engine import Strategy, MarketEvent, SignalEvent

class PairsTradingStrategy(Strategy):
    """
    Statistical Arbitrage: Trades two correlated stocks when spread diverges
    Buys the underperformer, shorts the outperformer when spread > 2*std
    """
    
    def __init__(self, params=None):
        super().__init__("Pairs Trading", params)
        self.lookback = params.get('lookback', 60)  # Rolling window
        self.entry_z = params.get('entry_z', 2.0)   # Enter at 2 std dev
        self.exit_z = params.get('exit_z', 0.5)     # Exit at 0.5 std dev
        self.pair_symbol = params.get('pair_symbol', None)  # Second stock in pair
        
        self.price_history_A = []
        self.price_history_B = []
        self.spread_history = []
        self.is_holding = False
        
    def on_data(self, market_event: MarketEvent) -> SignalEvent:
        # Store prices
        if market_event.instrument == self.name:
            self.price_history_A.append(market_event.price)
        elif market_event.instrument == self.pair_symbol:
            self.price_history_B.append(market_event.price)
        else:
            return None
            
        # Need enough history
        if len(self.price_history_A) < self.lookback or len(self.price_history_B) < self.lookback:
            return None
            
        # Calculate log price ratio (spread)
        recent_A = np.log(self.price_history_A[-self.lookback:])
        recent_B = np.log(self.price_history_B[-self.lookback:])
        spread = recent_A - recent_B
        
        # Z-Score of current spread
        mean_spread = np.mean(spread[:-1])
        std_spread = np.std(spread[:-1])
        current_spread = spread[-1]
        
        if std_spread > 0:
            z_score = (current_spread - mean_spread) / std_spread
        else:
            return None
            
        self.spread_history.append(z_score)
        
        # Generate Signal
        signal = None
        
        if not self.is_holding:
            # Entry signals
            if z_score > self.entry_z:
                # Stock A overvalued vs B -> Short A, Long B
                signal = SignalEvent(
                    timestamp=market_event.timestamp,
                    instrument=self.name,
                    signal_type="SHORT",
                    strength=abs(z_score) / 4.0
                )
                self.is_holding = True
            elif z_score < -self.entry_z:
                # Stock A undervalued vs B -> Long A, Short B
                signal = SignalEvent(
                    timestamp=market_event.timestamp,
                    instrument=self.name,
                    signal_type="LONG",
                    strength=abs(z_score) / 4.0
                )
                self.is_holding = True
        else:
            # Exit signal (spread reverted to mean)
            if abs(z_score) < self.exit_z:
                signal = SignalEvent(
                    timestamp=market_event.timestamp,
                    instrument=self.name,
                    signal_type="EXIT",
                    strength=1.0
                )
                self.is_holding = False
                
        return signal


class MomentumBreakoutStrategy(Strategy):
    """
    Detects volume + price breakouts
    Buys when price breaks resistance with volume surge
    """
    
    def __init__(self, params=None):
        super().__init__("Momentum Breakout", params)
        self.lookback = params.get('lookback', 20)     # Resistance lookback
        self.vol_multiplier = params.get('vol_multiplier', 2.0)  # Volume must be 2x avg
        self.atr_multiplier = params.get('atr_multiplier', 1.5)  # Stop loss
        
        self.price_history = []
        self.volume_history = []
        self.high_history = []
        
    def on_data(self, market_event: MarketEvent) -> SignalEvent:
        self.price_history.append(market_event.price)
        self.volume_history.append(market_event.volume)
        self.high_history.append(market_event.high)
        
        if len(self.price_history) < self.lookback + 1:
            return None
            
        # Calculate Resistance (Highest high in lookback)
        resistance = max(self.high_history[-self.lookback-1:-1])
        current_price = market_event.price
        current_vol = market_event.volume
        
        # Average Volume
        avg_vol = np.mean(self.volume_history[-self.lookback:])
        
        # Breakout Condition
        price_breakout = current_price > resistance
        volume_surge = current_vol > (avg_vol * self.vol_multiplier)
        
        signal = None
        
        if price_breakout and volume_surge:
            signal = SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="LONG",
                strength=0.8
            )
            
        return signal


class VWAPReversionStrategy(Strategy):
    """
    Mean Reversion to VWAP (Volume Weighted Average Price)
    Buys when price is significantly below VWAP
    Sells when price is significantly above VWAP
    """
    
    def __init__(self, params=None):
        super().__init__("VWAP Reversion", params)
        self.entry_std = params.get('entry_std', 2.0)   # Enter at 2 std dev from VWAP
        self.exit_std = params.get('exit_std', 0.5)     # Exit at 0.5 std dev
        
        self.cum_vol_price = 0.0
        self.cum_volume = 0.0
        self.vwap_history = []
        self.price_history = []
        
    def on_data(self, market_event: MarketEvent) -> SignalEvent:
        # Update VWAP
        typical_price = (market_event.high + market_event.low + market_event.price) / 3.0
        self.cum_vol_price += typical_price * market_event.volume
        self.cum_volume += market_event.volume
        
        if self.cum_volume > 0:
            vwap = self.cum_vol_price / self.cum_volume
        else:
            return None
            
        self.vwap_history.append(vwap)
        self.price_history.append(market_event.price)
        
        if len(self.vwap_history) < 20:
            return None
            
        # Calculate distance from VWAP in standard deviations
        recent_prices = np.array(self.price_history[-20:])
        recent_vwap = np.array(self.vwap_history[-20:])
        
        # Distance
        distance = recent_prices - recent_vwap
        std_distance = np.std(distance)
        current_distance = distance[-1]
        
        if std_distance > 0:
            z_score = current_distance / std_distance
        else:
            return None
            
        signal = None
        
        # If price is way below VWAP -> Buy (Reversion expected)
        if z_score < -self.entry_std:
            signal = SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="LONG",
                strength=abs(z_score) / 4.0
            )
        # If price is way above VWAP -> Sell
        elif z_score > self.entry_std:
            signal = SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="SHORT",
                strength=abs(z_score) / 4.0
            )
            
        return signal
