"""
Download real historical SBIN data from Yahoo Finance and convert it
to LOB format for tactic backtests.

Usage:
    python download_real_data.py
"""
import yfinance as yf
import numpy as np
import pandas as pd
import os

SYMBOL = "SBIN.NS"
PERIOD = "7d"  # 1-min data limited to 7 days on Yahoo
INTERVAL = "1m"
FALLBACK_INTERVAL = "5m"
FALLBACK_PERIOD = "60d"
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "data", "SBIN_real.parquet")


def download_sbin_data():
    """Download SBIN data from Yahoo Finance with fallback."""
    print(f"Attempting {SYMBOL} ({INTERVAL}, {PERIOD})...")
    ticker = yf.Ticker(SYMBOL)
    df = ticker.history(period=PERIOD, interval=INTERVAL)

    if df.empty:
        print(f"  1-min data unavailable. Trying {FALLBACK_INTERVAL} ({FALLBACK_PERIOD})...")
        df = ticker.history(period=FALLBACK_PERIOD, interval=FALLBACK_INTERVAL)
        if df.empty:
            print("ERROR: No data returned. Check symbol and internet connection.")
            return None
        print(f"  Downloaded {len(df)} {FALLBACK_INTERVAL} candles from {df.index[0]} to {df.index[-1]}")
    else:
        print(f"  Downloaded {len(df)} 1-min candles from {df.index[0]} to {df.index[-1]}")

    print(f"  Price range: {df['Close'].min():.2f} - {df['Close'].max():.2f}")
    return df


def convert_to_lob_ticks(df, interval="1m"):
    """
    Convert OHLCV candles to synthetic LOB ticks.
    1-min candle → 12 ticks (every 5s)
    5-min candle → 60 ticks (every 5s)
    """
    n_ticks_per_candle = 12 if interval == "1m" else 60
    print(f"\nConverting {len(df)} {interval} candles to LOB ticks ({n_ticks_per_candle} ticks/candle)...")

    all_ticks = []

    for candle_idx, (timestamp, row) in enumerate(df.iterrows()):
        o = row["Open"]
        h = row["High"]
        l = row["Low"]
        c = row["Close"]
        v = row["Volume"]
        # Price path: O -> L -> H -> C (realistic intra-candle movement)
        n = n_ticks_per_candle
        # Build a path that visits O → L → H → C with smooth transitions
        path_prices = []
        for i in range(n):
            t = i / (n - 1) if n > 1 else 0
            if t < 0.33:
                # O → L
                frac = t / 0.33
                path_prices.append(o + (l - o) * frac)
            elif t < 0.67:
                # L → H
                frac = (t - 0.33) / 0.34
                path_prices.append(l + (h - l) * frac)
            else:
                # H → C
                frac = (t - 0.67) / 0.33
                path_prices.append(h + (c - h) * frac)
        prices = np.array(path_prices)

        # Spread: 1-3 paise
        spread = np.random.uniform(0.01, 0.03, n_ticks_per_candle)

        # DOM sizes
        bid_sizes_l0 = np.random.poisson(800, n_ticks_per_candle) + 100
        bid_sizes_l1 = np.random.poisson(600, n_ticks_per_candle) + 80
        bid_sizes_l2 = np.random.poisson(400, n_ticks_per_candle) + 50
        ask_sizes_l0 = np.random.poisson(700, n_ticks_per_candle) + 100
        ask_sizes_l1 = np.random.poisson(500, n_ticks_per_candle) + 80
        ask_sizes_l2 = np.random.poisson(350, n_ticks_per_candle) + 50

        # Trade sizes: distribute volume across ticks
        trade_sizes = np.random.poisson(max(1, v / n_ticks_per_candle), n_ticks_per_candle) + 1

        # Trade side: based on price movement
        trade_sides = []
        for i in range(n_ticks_per_candle):
            if i == 0:
                trade_sides.append("M")
            elif prices[i] > prices[i-1]:
                trade_sides.append(np.random.choice(["A", "M"], p=[0.7, 0.3]))
            elif prices[i] < prices[i-1]:
                trade_sides.append(np.random.choice(["B", "M"], p=[0.7, 0.3]))
            else:
                trade_sides.append("M")

        for i in range(n_ticks_per_candle):
            ts = timestamp + pd.Timedelta(seconds=i * 5)
            bid = round(prices[i] - spread[i] / 2, 2)
            ask = round(prices[i] + spread[i] / 2, 2)

            all_ticks.append({
                "timestamp": ts,
                "bid": bid,
                "ask": ask,
                "bid_size_l0": int(bid_sizes_l0[i]),
                "bid_size_l1": int(bid_sizes_l1[i]),
                "bid_size_l2": int(bid_sizes_l2[i]),
                "ask_size_l0": int(ask_sizes_l0[i]),
                "ask_size_l1": int(ask_sizes_l1[i]),
                "ask_size_l2": int(ask_sizes_l2[i]),
                "trade_price": prices[i],
                "trade_size": int(trade_sizes[i]),
                "trade_side": trade_sides[i],
                "volume": int(v / n_ticks_per_candle),
                "vwap": c,  # Use close as VWAP proxy per candle
                "regime": "real_data",
            })

    result = pd.DataFrame(all_ticks)
    total_ticks = len(result)
    print(f"  Generated {total_ticks:,} LOB ticks")
    print(f"  Time range: {result['timestamp'].iloc[0]} to {result['timestamp'].iloc[-1]}")
    return result


def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    # Download
    df = download_sbin_data()
    if df is None:
        return

    # Detect interval used
    interval = INTERVAL if len(df) > 500 else FALLBACK_INTERVAL

    # Convert
    lob = convert_to_lob_ticks(df, interval=interval)

    # Save
    lob.to_parquet(OUTPUT_PATH, index=False)
    print(f"\n  Saved to: {OUTPUT_PATH}")
    print(f"  File size: {os.path.getsize(OUTPUT_PATH) / 1024:.0f} KB")

    # Quick stats
    print(f"\n  Price stats:")
    print(f"    Min: {lob['bid'].min():.2f}")
    print(f"    Max: {lob['bid'].max():.2f}")
    print(f"    Mean: {lob['bid'].mean():.2f}")
    print(f"    Spread avg: {(lob['ask'] - lob['bid']).mean():.3f}")

    # Check for trading days
    days = lob['timestamp'].dt.date.nunique()
    print(f"\n  Trading days: {days}")
    print(f"  Ticks per day: {len(lob) // days:.0f} avg")


if __name__ == "__main__":
    main()
