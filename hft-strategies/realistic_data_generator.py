"""
Shared Realistic LOB Data Generator for Tactic Backtests.

Generates synthetic LOB tick data with realistic market microstructure:
- Regime-switching: calm, trending, mean-reverting, high-vol, pin
- Realistic V_t spikes correlated with price moves
- IR regimes (bid-heavy / ask-heavy) aligned with price direction
- VWAP mean-reversion episodes
- End-of-day pin behavior
- Block prints (large trades) at key levels

Usage:
    from realistic_data_generator import generate_realistic_lob_data
    df = generate_realistic_lob_data(n_ticks=50000, seed=42)
    df.to_parquet("SBIN_realistic.parquet")
"""
import numpy as np
import pandas as pd
from datetime import datetime


def generate_realistic_lob_data(n_ticks=50000, seed=42, vwap=223.50):
    """
    Generate realistic LOB tick data with regime-switching.

    Regimes (as % of session):
    - Calm/Chop (25%): low V_t (20-50), IR ~1.0, tight spread
    - Trending Up (15%): V_t 80-150, IR 1.5-2.5, price trends up
    - Trending Down (15%): V_t 80-150, IR 0.4-0.7, price trends down
    - Mean-Reverting (20%): V_t 40-80, IR oscillates 0.8-1.5, price oscillates around VWAP
    - High-Vol Spike (10%): V_t 150-300, IR extreme (0.3 or 3.0), wide spread
    - EOD Pin (15%): last 15% of ticks, price converges to pin_price

    Returns DataFrame with columns:
        timestamp, bid, ask, bid_size_l0-l4, ask_size_l0-l4,
        trade_price, trade_size, trade_side, volume, vwap
    """
    np.random.seed(seed)

    timestamps = pd.date_range("2026-04-13 09:15:00", periods=n_ticks, freq="50ms")

    # ---- Regime schedule ----
    regime_map = _build_regime_schedule(n_ticks, seed=seed)

    # ---- Price path with regime-dependent dynamics ----
    price = np.full(n_ticks, vwap, dtype=np.float64)
    drift = np.zeros(n_ticks)

    for i in range(1, n_ticks):
        regime = regime_map[i]

        if regime == "calm":
            # Random walk, tiny drift
            drift[i] = np.random.randn() * 0.003
        elif regime == "trend_up":
            # Persistent upward drift
            drift[i] = 0.015 + np.random.randn() * 0.005
        elif regime == "trend_down":
            # Persistent downward drift
            drift[i] = -0.015 + np.random.randn() * 0.005
        elif regime == "mean_revert":
            # Mean-revert to VWAP
            drift[i] = 0.002 * (vwap - price[i - 1]) + np.random.randn() * 0.005
        elif regime == "high_vol":
            # Big jumps
            drift[i] = np.random.choice([-1, 1]) * np.random.exponential(0.04)
        elif regime == "eod_pin":
            pin_price = vwap + 0.10  # pin slightly above VWAP
            drift[i] = 0.005 * (pin_price - price[i - 1]) + np.random.randn() * 0.002

        price[i] = price[i - 1] + drift[i]

    # ---- Spread: regime-dependent ----
    spread = np.full(n_ticks, 0.02)
    for i in range(n_ticks):
        regime = regime_map[i]
        if regime == "calm":
            spread[i] = 0.01 + np.random.exponential(0.003)
        elif regime in ("trend_up", "trend_down"):
            spread[i] = 0.02 + np.random.exponential(0.005)
        elif regime == "high_vol":
            spread[i] = 0.05 + np.random.exponential(0.02)
        elif regime == "eod_pin":
            spread[i] = 0.01 + np.random.exponential(0.002)
        else:
            spread[i] = 0.015 + np.random.exponential(0.004)
    spread = np.clip(spread, 0.01, 0.15)

    bid = np.round(price - spread / 2, 2)
    ask = np.round(price + spread / 2, 2)

    # ---- DOM sizes: regime-dependent with IR aligned to drift ----
    n = n_ticks
    bid_l0 = np.zeros(n, dtype=int)
    bid_l1 = np.zeros(n, dtype=int)
    bid_l2 = np.zeros(n, dtype=int)
    ask_l0 = np.zeros(n, dtype=int)
    ask_l1 = np.zeros(n, dtype=int)
    ask_l2 = np.zeros(n, dtype=int)

    for i in range(n):
        regime = regime_map[i]
        d = drift[i] if i > 0 else 0

        if regime == "trend_up" or d > 0.01:
            # Bid-heavy book (bullish)
            bid_l0[i] = np.random.poisson(1000) + 200
            bid_l1[i] = np.random.poisson(800) + 150
            bid_l2[i] = np.random.poisson(500) + 100
            ask_l0[i] = np.random.poisson(400) + 50
            ask_l1[i] = np.random.poisson(300) + 50
            ask_l2[i] = np.random.poisson(200) + 30
        elif regime == "trend_down" or d < -0.01:
            # Ask-heavy book (bearish)
            bid_l0[i] = np.random.poisson(400) + 50
            bid_l1[i] = np.random.poisson(300) + 50
            bid_l2[i] = np.random.poisson(200) + 30
            ask_l0[i] = np.random.poisson(1000) + 200
            ask_l1[i] = np.random.poisson(800) + 150
            ask_l2[i] = np.random.poisson(500) + 100
        elif regime == "high_vol":
            # Thin and erratic
            side = np.random.choice(["bid", "ask"])
            if side == "bid":
                bid_l0[i] = np.random.poisson(600) + 100
                ask_l0[i] = np.random.poisson(200) + 30
            else:
                bid_l0[i] = np.random.poisson(200) + 30
                ask_l0[i] = np.random.poisson(600) + 100
            bid_l1[i] = np.random.poisson(300)
            bid_l2[i] = np.random.poisson(200)
            ask_l1[i] = np.random.poisson(300)
            ask_l2[i] = np.random.poisson(200)
        elif regime == "eod_pin":
            # Symmetrical, thick
            pin_price = vwap + 0.10
            dist = abs(price[i] - pin_price)
            thickness = max(200, int(1500 - dist * 5000))
            bid_l0[i] = np.random.poisson(thickness)
            bid_l1[i] = np.random.poisson(max(100, thickness - 200))
            bid_l2[i] = np.random.poisson(max(50, thickness - 400))
            ask_l0[i] = np.random.poisson(thickness)
            ask_l1[i] = np.random.poisson(max(100, thickness - 200))
            ask_l2[i] = np.random.poisson(max(50, thickness - 400))
        else:
            # Calm / mean-revert: balanced
            base = 600 if regime == "calm" else 500
            bid_l0[i] = np.random.poisson(base) + 100
            bid_l1[i] = np.random.poisson(base - 100) + 80
            bid_l2[i] = np.random.poisson(base - 200) + 50
            ask_l0[i] = np.random.poisson(base) + 100
            ask_l1[i] = np.random.poisson(base - 100) + 80
            ask_l2[i] = np.random.poisson(base - 200) + 50

    # Clamp to positive
    for arr in [bid_l0, bid_l1, bid_l2, ask_l0, ask_l1, ask_l2]:
        np.clip(arr, 50, 3000, out=arr)

    # ---- Trade prints: side correlated with regime + size correlated with V_t ----
    trade_side = np.empty(n, dtype="U1")
    trade_size = np.zeros(n, dtype=int)

    for i in range(n):
        regime = regime_map[i]
        d = drift[i] if i > 0 else 0

        if regime == "trend_up":
            # 70% ask lifts (buying pressure)
            trade_side[i] = np.random.choice(["A", "B", "M"], p=[0.70, 0.25, 0.05])
            trade_size[i] = np.random.exponential(60) + 10
        elif regime == "trend_down":
            # 70% bid hits (selling pressure)
            trade_side[i] = np.random.choice(["B", "A", "M"], p=[0.70, 0.25, 0.05])
            trade_size[i] = np.random.exponential(60) + 10
        elif regime == "high_vol":
            # Extreme sizes, mixed sides
            trade_side[i] = np.random.choice(["A", "B", "M"], p=[0.45, 0.45, 0.10])
            trade_size[i] = np.random.exponential(150) + 20
        elif regime == "eod_pin":
            # Balanced, moderate sizes
            trade_side[i] = np.random.choice(["A", "B", "M"], p=[0.40, 0.40, 0.20])
            trade_size[i] = np.random.exponential(30) + 5
        else:
            # Calm / mean-revert: small prints
            trade_side[i] = np.random.choice(["A", "B", "M"], p=[0.35, 0.35, 0.30])
            trade_size[i] = np.random.exponential(25) + 5

    trade_size = np.clip(trade_size, 1, 2000).astype(int)

    trade_price = np.round(
        price + np.where(trade_side == "A", spread / 2, -spread / 2) + np.random.randn(n) * 0.002,
        2
    )

    # ---- Volume ----
    volume = np.zeros(n, dtype=int)
    for i in range(n):
        regime = regime_map[i]
        base = {"calm": 2000, "trend_up": 5000, "trend_down": 5000,
                "high_vol": 8000, "mean_revert": 3000, "eod_pin": 4000}[regime]
        volume[i] = np.random.poisson(base)

    # ---- VWAP ----
    cum_pv = np.cumsum(trade_price * trade_size)
    cum_v = np.cumsum(trade_size).astype(float)
    cum_v[cum_v == 0] = 1
    session_vwap = cum_pv / cum_v

    return pd.DataFrame({
        "timestamp": timestamps,
        "bid": bid,
        "ask": ask,
        "bid_size_l0": bid_l0,
        "bid_size_l1": bid_l1,
        "bid_size_l2": bid_l2,
        "ask_size_l0": ask_l0,
        "ask_size_l1": ask_l1,
        "ask_size_l2": ask_l2,
        "trade_price": trade_price,
        "trade_size": trade_size,
        "trade_side": trade_side,
        "volume": volume,
        "vwap": session_vwap,
        "regime": [regime_map[i] for i in range(n)],
    })


def _build_regime_schedule(n_ticks, seed=42):
    """
    Build a regime schedule that switches between market states.

    Regimes: calm, trend_up, trend_down, mean_revert, high_vol, eod_pin
    """
    np.random.seed(seed)
    regime_map = np.empty(n_ticks, dtype="U15")

    # Define regime blocks (start_frac, end_frac, regime)
    blocks = [
        (0.00, 0.08, "calm"),            # Open chaos — calm
        (0.08, 0.18, "trend_up"),         # Morning trend up
        (0.18, 0.28, "mean_revert"),      # Mid-morning revert
        (0.28, 0.35, "trend_down"),       # Late morning sell-off
        (0.35, 0.45, "calm"),             # Lunch lull
        (0.45, 0.50, "high_vol"),         # Post-lunch spike
        (0.50, 0.60, "mean_revert"),      # Afternoon revert
        (0.60, 0.68, "trend_up"),         # Afternoon trend up
        (0.68, 0.75, "high_vol"),         # Late vol spike
        (0.75, 0.85, "mean_revert"),      # Pre-close revert
        (0.85, 1.00, "eod_pin"),          # End-of-day pin
    ]

    for start_f, end_f, regime in blocks:
        start_i = int(start_f * n_ticks)
        end_i = int(end_f * n_ticks)
        regime_map[start_i:end_i] = regime

    # Add short sub-regime switches within blocks for variety
    n_switches = max(1, n_ticks // 5000)
    for _ in range(n_switches):
        idx = np.random.randint(0, n_ticks)
        regime_map[idx:idx + 100] = "high_vol"  # Short vol burst

    return regime_map


if __name__ == "__main__":
    print("Generating realistic LOB data (50,000 ticks)...")
    df = generate_realistic_lob_data(n_ticks=50000, seed=42)

    # Save to parquet
    import os
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "hft-ml", "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "SBIN_realistic.parquet")
    df.to_parquet(out_path, index=False)

    print(f"\nSaved to {out_path}")
    print(f"\nRegime distribution:")
    print(df["regime"].value_counts())
    print(f"\nPrice range: {df['bid'].min():.2f} — {df['bid'].max():.2f}")
    print(f"VWAP end: {df['vwap'].iloc[-1]:.4f}")

    # Quick stats
    for regime in df["regime"].unique():
        mask = df["regime"] == regime
        avg_size = df.loc[mask, "trade_size"].mean()
        n = mask.sum()
        print(f"  {regime:15s}: {n:6d} ticks, avg trade size {avg_size:.0f}")
