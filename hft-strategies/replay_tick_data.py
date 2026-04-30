"""
Tick Data Extraction and Loading Script
Connects to tick_database.db (SQLite), pulls last 5 trading days of SBIN tick data.
If database is empty, generates synthetic tick data as fallback.
Saves to parquet: data/SBIN_ticks.parquet

Usage:
    python replay_tick_data.py
    python replay_tick_data.py --symbol SBIN --days 5 --output data/SBIN_ticks.parquet
"""

import os
import sys
import argparse
import sqlite3
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

DB_PATH = os.path.join(SCRIPT_DIR, "tick_database.db")
DATA_DIR = os.path.join(SCRIPT_DIR, "data")


# ========================================================================
# Database Reader
# ========================================================================

def connect_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Connect to the tick database."""
    if not os.path.exists(db_path):
        print(f"[INFO] Database not found at {db_path}; will generate synthetic data")
        return None
    conn = sqlite3.connect(db_path)
    print(f"  Connected to tick database: {db_path}")
    return conn


def pull_sbin_ticks(
    conn: sqlite3.Connection,
    symbol: str = "SBIN",
    days: int = 5,
) -> Optional[List[dict]]:
    """Pull last N trading days of tick data from database."""
    cursor = conn.cursor()

    # Check if ticks table exists and has data
    cursor.execute("SELECT COUNT(*) FROM ticks WHERE symbol = ?", (symbol,))
    count = cursor.fetchone()[0]

    if count == 0:
        print(f"[INFO] No tick data found for {symbol} in database ({count} rows)")
        return None

    # Get date range
    end_date = datetime.now().strftime("%Y-%m-%d 23:59:59")
    start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d 00:00:00")

    query = """
        SELECT timestamp, open, high, low, close, volume
        FROM ticks
        WHERE symbol = ? AND timestamp BETWEEN ? AND ?
        ORDER BY timestamp
    """
    cursor.execute(query, (symbol, start_date, end_date))
    rows = cursor.fetchall()

    if not rows:
        print(f"[INFO] No data for {symbol} in last {days} trading days")
        return None

    print(f"  Pulled {len(rows):,} bars for {symbol} from {rows[0][0]} to {rows[-1][0]}")
    return rows


def rows_to_tick_dicts(rows: List, columns: List[str] = None) -> List[dict]:
    """Convert database rows to list of tick dictionaries."""
    if columns is None:
        columns = ["timestamp", "open", "high", "low", "close", "volume"]

    ticks = []
    for row in rows:
        tick = dict(zip(columns, row))
        # Ensure numeric types
        for col in ("open", "high", "low", "close"):
            if col in tick:
                tick[col] = float(tick[col])
        if "volume" in tick:
            tick["volume"] = int(tick["volume"])
        ticks.append(tick)

    return ticks


# ========================================================================
# Synthetic Tick Generator (fallback)
# ========================================================================

def generate_synthetic_tick_data(
    symbol: str = "SBIN",
    days: int = 5,
    ticks_per_day: int = 20000,
    seed: int = 42,
) -> List[dict]:
    """
    Generate synthetic 1-minute tick data for N trading days.
    Falls back to this if database is empty.
    """
    np.random.seed(seed)

    base_price = 580.0
    vwap = base_price
    all_ticks = []

    for day_offset in range(days):
        day_date = datetime.now() - timedelta(days=day_offset)
        # Skip weekends
        if day_date.weekday() >= 5:
            continue

        start = day_date.replace(hour=9, minute=15, second=0)
        n_ticks = ticks_per_day
        interval_ms = int(375 * 60 * 1000 / n_ticks)  # 375 min trading day

        # Price path with mean reversion
        returns = np.random.randn(n_ticks) * 0.008
        price_path = np.cumsum(returns)
        price_path = price_path - np.mean(price_path)
        for i in range(1, n_ticks):
            price_path[i] += 0.002 * (-price_path[i - 1])

        prices = base_price + price_path
        prices = np.clip(prices, base_price - 5, base_price + 5)

        # Generate OHLCV bars (aggregate ticks into 1-minute bars)
        bars_per_day = 375  # 375 1-minute bars per day
        bar_size = max(1, n_ticks // bars_per_day)

        for b in range(bars_per_day):
            bar_start = b * bar_size
            bar_end = min((b + 1) * bar_size, n_ticks)
            bar_prices = prices[bar_start:bar_end]

            if len(bar_prices) == 0:
                continue

            bar_open = bar_prices[0]
            bar_close = bar_prices[-1]
            bar_high = max(bar_prices)
            bar_low = min(bar_prices)
            bar_volume = int(np.random.poisson(50000))

            ts = start + timedelta(minutes=b)

            spread = np.clip(0.03 + np.random.exponential(0.01), 0.01, 0.10)
            bid = round(bar_close - spread / 2, 2)
            ask = round(bar_close + spread / 2, 2)

            all_ticks.append({
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol,
                "open": round(bar_open, 2),
                "high": round(bar_high, 2),
                "low": round(bar_low, 2),
                "close": round(bar_close, 2),
                "volume": bar_volume,
                "bid": bid,
                "ask": ask,
                "bid_size": int(np.clip(np.random.poisson(400), 50, 3000)),
                "ask_size": int(np.clip(np.random.poisson(400), 50, 3000)),
                "trade_price": round(bar_close + np.random.randn() * 0.003, 2),
                "trade_size": int(np.clip(np.random.exponential(30), 1, 500)),
                "trade_side": np.random.choice(["B", "A", "M"], p=[0.45, 0.45, 0.10]),
                "vwap": round(vwap + np.random.randn() * 0.1, 2),
            })

    print(f"  Generated {len(all_ticks):,} synthetic ticks for {symbol} ({days} trading days)")
    return all_ticks


# ========================================================================
# Parquet Export
# ========================================================================

def save_to_parquet(
    ticks: List[dict],
    symbol: str = "SBIN",
    output_path: str = None,
) -> str:
    """Save tick data to parquet file."""
    try:
        import pandas as pd
    except ImportError:
        print("[ERROR] pandas and pyarrow required. Install: pip install pandas pyarrow")
        sys.exit(1)

    if output_path is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        output_path = os.path.join(DATA_DIR, f"{symbol}_ticks.parquet")

    df = pd.DataFrame(ticks)

    # Ensure timestamp is datetime type
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    df.to_parquet(output_path, index=False, engine="pyarrow")
    print(f"  Saved {len(df):,} ticks to {output_path}")
    return output_path


# ========================================================================
# Main
# ========================================================================

def main():
    parser = argparse.ArgumentParser(description="Tick Data Extraction and Loading")
    parser.add_argument("--symbol", default="SBIN", help="Symbol to extract")
    parser.add_argument("--days", type=int, default=5, help="Number of trading days")
    parser.add_argument("--output", default=None, help="Output parquet path")
    parser.add_argument("--db", default=DB_PATH, help="Database path")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"  TICK DATA EXTRACTION  |  {args.symbol}")
    print(f"{'='*60}")

    ticks = None

    # Try database first
    conn = connect_db(args.db)
    if conn:
        rows = pull_sbin_ticks(conn, args.symbol, args.days)
        if rows:
            ticks = rows_to_tick_dicts(rows)

    # Fallback to synthetic
    if not ticks:
        print("\n  [FALLBACK] Generating synthetic tick data...")
        ticks = generate_synthetic_tick_data(
            symbol=args.symbol,
            days=args.days,
        )

    # Save to parquet
    output_path = save_to_parquet(ticks, args.symbol, args.output)

    # Summary
    timestamps = [t["timestamp"] for t in ticks]
    if timestamps:
        ts_strs = [str(ts) for ts in timestamps]
        print(f"\n  Loaded {len(ticks):,} ticks from {ts_strs[0]} to {ts_strs[-1]}")
    print(f"  Output: {output_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
