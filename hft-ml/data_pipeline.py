"""
High-Frequency Trading Data Pipeline
Feature engineering from raw Limit Order Book (LOB) and TAQ data
Focus: Equities and Futures (NSE India, CME)
"""

import numpy as np
import pandas as pd
from typing import Tuple, List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import warnings


class AssetClass(Enum):
    EQUITY = "equity"
    FUTURE = "future"
    FX = "fx"


class LabelType(Enum):
    CLASSIFICATION_3WAY = "classification_3way"  # Up/Down/Unchanged
    REGRESSION = "regression"  # Mid-price change
    VOLATILITY = "volatility"  # Realized vol prediction


@dataclass
class LOBSnapshot:
    """Single limit order book snapshot"""
    timestamp_ns: int  # Nanosecond timestamp
    bid_prices: np.ndarray  # Shape: (n_levels,) e.g. 10 levels
    bid_volumes: np.ndarray  # Shape: (n_levels,)
    ask_prices: np.ndarray  # Shape: (n_levels,)
    ask_volumes: np.ndarray  # Shape: (n_levels,)
    last_trade_price: float = 0.0
    last_trade_volume: float = 0.0
    trade_side: int = 0  # 1=buy, -1=sell, 0=unknown


@dataclass
class TAQEvent:
    """Trade and Quote event"""
    timestamp_ns: int
    price: float
    volume: float
    side: int  # 1=aggressive buy, -1=aggressive sell
    bid_price: float
    ask_price: float
    bid_volume: float
    ask_volume: float


@dataclass
class EngineeredFeatures:
    """All features computed from LOB"""
    timestamp_ns: int
    # Core LOB features
    ofi: float  # Order Flow Imbalance
    depth_imbalance: float
    weighted_mid_price: float
    spread_normalized: float
    bid_slope: float
    ask_slope: float
    # Volume features
    bid_volume_total: float
    ask_volume_total: float
    volume_imbalance: float
    # Price features
    mid_price: float
    log_return_1: float
    log_return_5: float
    log_return_10: float
    # Volatility features
    realized_vol_5: float
    realized_vol_10: float
    realized_vol_20: float
    realized_skew: float
    # Multi-level features
    level_imbalances: np.ndarray  # Per-level depth imbalance
    cumulative_bid_volumes: np.ndarray
    cumulative_ask_volumes: np.ndarray
    # Queue features
    queue_imbalance: float
    trade_intensity: float  # Trades per second
    cancel_ratio: float  # Cancels / (Adds + Cancels)


class LOBFeatureEngineer:
    """
    Computes all features from raw LOB snapshots
    Optimized for low-latency (avoids Python loops where possible)
    """

    def __init__(self, n_levels: int = 10, tick_size: float = 0.05):
        self.n_levels = n_levels
        self.tick_size = tick_size
        self.price_history = []
        self.trade_times = []
        self._reset_buffers()

    def _reset_buffers(self):
        self.price_history = []
        self.trade_times = []
        self.prev_lob = None
        self.trade_count_window = []

    def compute_features(self, snapshot: LOBSnapshot) -> EngineeredFeatures:
        """Compute all features from a single LOB snapshot"""

        # === CORE LOB FEATURES ===

        # Order Flow Imbalance (OFI)
        ofi = self._compute_ofi(snapshot)

        # Depth imbalance
        bid_vol_total = np.sum(snapshot.bid_volumes)
        ask_vol_total = np.sum(snapshot.ask_volumes)
        depth_imbalance = (bid_vol_total - ask_vol_total) / (bid_vol_total + ask_vol_total + 1e-10)

        # Weighted mid-price
        wmp = (snapshot.bid_prices[0] * snapshot.ask_volumes[0] +
               snapshot.ask_prices[0] * snapshot.bid_volumes[0]) / \
              (snapshot.bid_volumes[0] + snapshot.ask_volumes[0] + 1e-10)

        # Spread normalized by tick size
        spread = snapshot.ask_prices[0] - snapshot.bid_prices[0]
        spread_normalized = spread / self.tick_size

        # Order book slopes (log-log regression of price vs cumulative volume)
        bid_slope = self._compute_book_slope(snapshot.bid_prices, snapshot.bid_volumes, is_bid=True)
        ask_slope = self._compute_book_slope(snapshot.ask_prices, snapshot.ask_volumes, is_bid=False)

        # === VOLUME FEATURES ===
        volume_imbalance = (snapshot.bid_volumes[0] - snapshot.ask_volumes[0]) / \
                          (snapshot.bid_volumes[0] + snapshot.ask_volumes[0] + 1e-10)

        # === PRICE FEATURES ===
        mid_price = (snapshot.bid_prices[0] + snapshot.ask_prices[0]) / 2.0
        self.price_history.append(mid_price)
        if len(self.price_history) > 100:
            self.price_history = self.price_history[-100:]

        # Log returns
        log_returns = self._compute_log_returns(mid_price)

        # === VOLATILITY FEATURES ===
        realized_vol_5 = self._compute_realized_vol(window=5)
        realized_vol_10 = self._compute_realized_vol(window=10)
        realized_vol_20 = self._compute_realized_vol(window=20)
        realized_skew = self._compute_realized_skew(window=20)

        # === MULTI-LEVEL FEATURES ===
        level_imbalances = self._compute_level_imbalances(snapshot.bid_volumes, snapshot.ask_volumes)
        cum_bid = np.cumsum(snapshot.bid_volumes)
        cum_ask = np.cumsum(snapshot.ask_volumes)

        # === QUEUE FEATURES ===
        queue_imbalance = (snapshot.bid_volumes[0] - snapshot.ask_volumes[0]) / \
                         (snapshot.bid_volumes[0] + snapshot.ask_volumes[0] + 1e-10)

        # Trade intensity (trades per second in last 100ms)
        if snapshot.last_trade_volume > 0:
            self.trade_count_window.append(snapshot.timestamp_ns)
        cutoff = snapshot.timestamp_ns - 100_000_000  # 100ms
        self.trade_count_window = [t for t in self.trade_count_window if t > cutoff]
        trade_intensity = len(self.trade_count_window) / 0.1  # per second

        self.prev_lob = snapshot

        return EngineeredFeatures(
            timestamp_ns=snapshot.timestamp_ns,
            ofi=ofi,
            depth_imbalance=depth_imbalance,
            weighted_mid_price=wmp,
            spread_normalized=spread_normalized,
            bid_slope=bid_slope,
            ask_slope=ask_slope,
            bid_volume_total=bid_vol_total,
            ask_volume_total=ask_vol_total,
            volume_imbalance=volume_imbalance,
            mid_price=mid_price,
            log_return_1=log_returns.get(1, 0.0),
            log_return_5=log_returns.get(5, 0.0),
            log_return_10=log_returns.get(10, 0.0),
            realized_vol_5=realized_vol_5,
            realized_vol_10=realized_vol_10,
            realized_vol_20=realized_vol_20,
            realized_skew=realized_skew,
            level_imbalances=level_imbalances,
            cumulative_bid_volumes=cum_bid,
            cumulative_ask_volumes=cum_ask,
            queue_imbalance=queue_imbalance,
            trade_intensity=trade_intensity,
            cancel_ratio=0.0  # Requires order lifecycle tracking
        )

    def _compute_ofi(self, snapshot: LOBSnapshot) -> float:
        """Order Flow Imbalance - predicts short-term price direction"""
        if self.prev_lob is None:
            return 0.0

        ofi = 0.0

        # Level 1 OFI
        if snapshot.bid_prices[0] == self.prev_lob.bid_prices[0]:
            ofi += snapshot.bid_volumes[0] - self.prev_lob.bid_volumes[0]
        elif snapshot.bid_prices[0] > self.prev_lob.bid_prices[0]:
            ofi += snapshot.bid_volumes[0]
        else:
            ofi -= self.prev_lob.bid_volumes[0]

        if snapshot.ask_prices[0] == self.prev_lob.ask_prices[0]:
            ofi -= snapshot.ask_volumes[0] - self.prev_lob.ask_volumes[0]
        elif snapshot.ask_prices[0] < self.prev_lob.ask_prices[0]:
            ofi -= snapshot.ask_volumes[0]
        else:
            ofi += self.prev_lob.ask_volumes[0]

        # Normalize
        total_vol = snapshot.bid_volumes[0] + snapshot.ask_volumes[0] + 1e-10
        return ofi / total_vol

    def _compute_book_slope(self, prices: np.ndarray, volumes: np.ndarray, is_bid: bool) -> float:
        """Order book slope from log-log regression"""
        cum_vol = np.cumsum(volumes) + 1e-10
        log_prices = np.log(np.abs(prices))
        log_cumvol = np.log(cum_vol)

        if len(log_prices) < 3:
            return 0.0

        # Simple linear regression
        x = log_cumvol
        y = log_prices
        n = len(x)

        slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / \
                (n * np.sum(x**2) - np.sum(x)**2 + 1e-10)

        return slope if np.isfinite(slope) else 0.0

    def _compute_log_returns(self, current_mid: float) -> Dict[int, float]:
        """Compute log returns at various horizons"""
        returns = {}
        if len(self.price_history) < 2:
            return {1: 0.0, 5: 0.0, 10: 0.0}

        prices = np.array(self.price_history)

        for horizon in [1, 5, 10]:
            if len(prices) > horizon:
                ret = np.log(current_mid / prices[-(horizon + 1)])
                returns[horizon] = ret if np.isfinite(ret) else 0.0
            else:
                returns[horizon] = 0.0

        return returns

    def _compute_realized_vol(self, window: int) -> float:
        """Realized volatility over window"""
        if len(self.price_history) < window + 1:
            return 0.0

        prices = np.array(self.price_history[-(window+1):])
        returns = np.diff(np.log(prices + 1e-10))

        vol = np.std(returns) * np.sqrt(252 * 390 * 60 * 6.5)  # Annualized
        return vol if np.isfinite(vol) else 0.0

    def _compute_realized_skew(self, window: int) -> float:
        """Realized skewness"""
        if len(self.price_history) < window + 1:
            return 0.0

        prices = np.array(self.price_history[-(window+1):])
        returns = np.diff(np.log(prices + 1e-10))

        if len(returns) < 3:
            return 0.0

        from scipy.stats import skew
        sk = skew(returns)
        return sk if np.isfinite(sk) else 0.0

    def _compute_level_imbalances(self, bid_vols: np.ndarray, ask_vols: np.ndarray) -> np.ndarray:
        """Per-level depth imbalance"""
        total = bid_vols + ask_vols + 1e-10
        return (bid_vols - ask_vols) / total


class LabelGenerator:
    """
    Generates training labels from LOB data
    Handles classification and regression targets
    """

    def __init__(self, 
                 horizons: List[int] = [1, 5, 10, 50, 100],
                 tolerance_spread_mult: float = 1.0,
                 smoothing_window: int = 3):
        self.horizons = horizons
        self.tolerance_spread_mult = tolerance_spread_mult
        self.smoothing_window = smoothing_window

    def generate_labels(self,
                        mid_prices: np.ndarray,
                        spreads: np.ndarray,
                        timestamps_ns: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Generate all label types

        Args:
            mid_prices: Array of mid-prices
            spreads: Array of spreads (bid-ask)
            timestamps_ns: Nanosecond timestamps

        Returns:
            Dictionary of labels for each horizon
        """
        labels = {}
        n = len(mid_prices)

        for horizon in self.horizons:
            if n <= horizon + self.smoothing_window:
                continue

            # Smoothed future mid-price change
            future_prices = np.zeros(n)
            for i in range(n - horizon):
                window_end = min(i + horizon + self.smoothing_window, n)
                future_prices[i] = np.mean(mid_prices[i + horizon:window_end])

            price_change = future_prices - mid_prices
            # Use ROLLING median spread (adapts to volatility changes)
            rolling_spread = pd.Series(spreads).rolling(window=500, min_periods=100).median().values
            tolerance = self.tolerance_spread_mult * rolling_spread
            
            # Classification labels: 0=down, 1=unchanged, 2=up
            class_labels = np.zeros(n, dtype=np.int32)
            class_labels[price_change > tolerance] = 2  # Up
            class_labels[price_change < -tolerance] = 0  # Down
            # else: Unchanged (1)
            class_labels[np.abs(price_change) <= tolerance] = 1

            # Regression label: smoothed price change
            reg_labels = price_change

            # Volatility label: rolling std of returns
            returns = np.diff(np.log(mid_prices + 1e-10))
            vol_labels = np.zeros(n)
            vol_window = min(50, n // 2)
            for i in range(vol_window, n):
                vol_labels[i] = np.std(returns[max(0, i-vol_window):i])

            labels[f'h{horizon}'] = {
                'classification': class_labels,
                'regression': reg_labels,
                'volatility': vol_labels,
                'price_change': price_change
            }

        return labels

    def compute_class_weights(self, labels: np.ndarray) -> np.ndarray:
        """Compute class weights for imbalanced data"""
        classes, counts = np.unique(labels, return_counts=True)
        total = len(labels)
        n_classes = len(classes)

        weights = np.ones(n_classes)
        for cls in classes:
            if counts[cls] > 0:
                weights[cls] = total / (n_classes * counts[cls])

        return weights
