"""
Pytest configuration for HFT multi-lot execution framework.
Shared fixtures for all tactic backtest scripts.
"""
import pytest
import numpy as np
import pandas as pd
import os
import sys

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "hft-strategies"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "hft-ml"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "hft-simulation"))


@pytest.fixture(scope="session")
def synthetic_lob_data():
    """
    Generate synthetic LOB snapshot data for testing.
    Returns DataFrame with columns:
    timestamp, bid_price, ask_price, bid_size_l0-l4, ask_size_l0-l4,
    trade_price, trade_size, trade_side, volume
    """
    np.random.seed(42)
    n = 50000

    # Price path (GBM + mean reversion to VWAP)
    vwap = 223.50
    price = np.cumsum(np.random.randn(n) * 0.02) + vwap
    price = price + (vwap - price) * 0.001  # weak mean reversion

    # Spread: 1-5 ticks, tighter when near VWAP
    spread = np.abs(price - vwap) * 0.1 + 0.02 + np.random.exponential(0.01, n)
    spread = np.clip(spread, 0.01, 0.10)

    bid = np.round(price - spread / 2, 2)
    ask = np.round(price + spread / 2, 2)

    # DOM sizes (realistic: 200-2000 lots, thinner far from VWAP)
    def gen_sizes(n, base=800):
        return np.clip(
            np.random.poisson(base, n) + np.random.randint(-200, 200, n),
            50, 3000
        )

    data = {
        "timestamp": pd.date_range("2026-04-13 09:15:00", periods=n, freq="50ms"),
        "mid_price": np.round(price, 2),
        "bid_price": bid,
        "ask_price": ask,
        "spread": np.round(ask - bid, 2),
        "bid_size_l0": gen_sizes(n, 800),
        "bid_size_l1": gen_sizes(n, 600),
        "bid_size_l2": gen_sizes(n, 400),
        "bid_size_l3": gen_sizes(n, 300),
        "bid_size_l4": gen_sizes(n, 200),
        "ask_size_l0": gen_sizes(n, 700),
        "ask_size_l1": gen_sizes(n, 500),
        "ask_size_l2": gen_sizes(n, 350),
        "ask_size_l3": gen_sizes(n, 250),
        "ask_size_l4": gen_sizes(n, 150),
        "trade_price": np.round(price + np.random.randn(n) * 0.01, 2),
        "trade_size": np.clip(np.random.exponential(50, n).astype(int), 1, 2000),
        "trade_side": np.random.choice(["B", "S", "M"], n, p=[0.45, 0.45, 0.10]),
        "volume": np.random.poisson(5000, n),
        "vwap": vwap,
    }

    df = pd.DataFrame(data)
    return df


@pytest.fixture(scope="session")
def high_vol_data(synthetic_lob_data):
    """Same data but with higher volatility regime injected."""
    df = synthetic_lob_data.copy()
    # Inject vol spike in middle 30%
    mask = (df.index > 15000) & (df.index < 35000)
    df.loc[mask, "spread"] = df.loc[mask, "spread"] * 2.5
    df.loc[mask, "trade_size"] = df.loc[mask, "trade_size"] * 2
    df.loc[mask, "bid_size_l0"] = df.loc[mask, "bid_size_l0"] // 2
    df.loc[mask, "ask_size_l0"] = df.loc[mask, "ask_size_l0"] // 2
    return df


@pytest.fixture(scope="session")
def low_vol_data(synthetic_lob_data):
    """Same data but with lower volatility regime."""
    df = synthetic_lob_data.copy()
    df["spread"] = df["spread"] * 0.6
    df["trade_size"] = df["trade_size"] * 0.7
    return df


@pytest.fixture
def default_risk_params():
    """Default risk parameters for testing."""
    return {
        "max_net_delta": 200,
        "max_gross": 500,
        "max_daily_loss": 100000,
        "tick_value": 15,
        "lot_size": 1,
        "commission_per_share": 0.05,
        "slippage_bps": 5,
    }
