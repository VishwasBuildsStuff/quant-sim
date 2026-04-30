"""
Real NSE Data Fetcher
Downloads from Yahoo Finance and interpolates to LOB snapshots
"""

import sys
sys.path.insert(0, r'V:\pylibs')

import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta

def fetch_nse_minute_data(symbol, days=30, interval='1m'):
    """
    Fetch real minute-level data from Yahoo Finance
    
    Note: Yahoo Finance limitations:
    - 1m interval: max 8 days
    - 5m, 15m, 30m: max 60 days  
    - 1h: max 730 days
    """
    ticker = f"{symbol}.NS"
    
    # Adjust days based on interval limitations
    if interval == '1m' and days > 8:
        print(f"⚠️ Yahoo Finance limits 1m data to 8 days. Adjusting from {days} to 8 days.")
        print(f"   For more history, use: --interval 5m (60 days) or --interval 1h (730 days)")
        days = 8
    elif interval in ['5m', '15m', '30m', '90m'] and days > 60:
        print(f"⚠️ Yahoo Finance limits {interval} data to 60 days. Adjusting from {days} to 60 days.")
        days = 60
    elif interval == '1h' and days > 730:
        print(f"⚠️ Yahoo Finance limits 1h data to 730 days. Adjusting from {days} to 730 days.")
        days = 730
    
    print(f"📡 Fetching {days} days of {ticker} data from Yahoo Finance...")
    print(f"   Interval: {interval}")

    # Download data with specified interval
    df = yf.download(ticker, period=f'{days}d', interval=interval, progress=False)

    if df.empty or len(df) < 100:
        print(f"⚠️ Not enough data for {symbol}")
        return None

    # Handle multi-level columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    print(f"  ✓ Downloaded {len(df)} bars")
    print(f"  ✓ Date range: {df.index[0]} to {df.index[-1]}")
    print(f"  ✓ Price range: ₹{float(df['Close'].min()):.2f} - ₹{float(df['Close'].max()):.2f}")

    return df

def interpolate_to_lob(minute_data, snapshots_per_minute=5):
    """
    Interpolate minute OHLCV to tick-level LOB snapshots
    
    Creates realistic order book dynamics within each minute bar
    """
    print(f"\n🔧 Interpolating to LOB snapshots ({snapshots_per_minute} per minute)...")
    
    n_minutes = len(minute_data)
    n_snapshots = n_minutes * snapshots_per_minute
    
    all_snapshots = []
    
    for i, (idx, row) in enumerate(minute_data.iterrows()):
        open_p = row['Open']
        high = row['High']
        low = row['Low']
        close = row['Close']
        volume = row['Volume']
        
        # Generate snapshots within this minute
        for j in range(snapshots_per_minute):
            t = j / snapshots_per_minute
            
            # Interpolate price within bar
            if i == 0 and j == 0:
                mid = open_p
            else:
                # Smooth transition from previous close
                mid = open_p + (close - open_p) * t + np.random.randn() * 0.1
            
            # Spread (wider at highs/lows)
            spread = 0.05 + 0.02 * abs(mid - open_p) / open_p * 100
            spread = max(0.05, round(spread / 0.05) * 0.05)
            
            # 10-level order book
            snapshot = {'timestamp_ns': int(idx.timestamp() * 1e9 + j * 200_000_000)}  # 200ms apart
            
            for level in range(10):
                tick_offset = 0.05 * (level + 1)
                vol_base = int(1000 / (level + 1)**0.5 * (1 + np.random.randn() * 0.3))
                vol_base = max(100, vol_base)
                
                snapshot[f'bid_price_{level+1}'] = round((mid - spread/2 - tick_offset) / 0.05) * 0.05
                snapshot[f'bid_volume_{level+1}'] = vol_base
                snapshot[f'ask_price_{level+1}'] = round((mid + spread/2 + tick_offset) / 0.05) * 0.05
                snapshot[f'ask_volume_{level+1}'] = vol_base
            
            # Trade data
            snapshot['last_trade_price'] = round(mid, 2)
            snapshot['last_trade_volume'] = int(volume / snapshots_per_minute)
            snapshot['trade_side'] = np.random.choice([1, -1])
            
            all_snapshots.append(snapshot)
        
        if (i + 1) % 100 == 0:
            print(f"  Progress: {i+1}/{n_minutes} minutes ({(i+1)/n_minutes*100:.0f}%)")
    
    df = pd.DataFrame(all_snapshots)
    
    # Ensure no crossed books
    crossed = (df['bid_price_1'] >= df['ask_price_1']).sum()
    if crossed > 0:
        print(f"  ⚠️ Fixed {crossed} crossed books")
        df.loc[df['bid_price_1'] >= df['ask_price_1'], 'bid_price_1'] -= 0.05
        df.loc[df['bid_price_1'] >= df['ask_price_1'], 'ask_price_1'] += 0.05
    
    return df

if __name__ == '__main__':
    symbol = 'RELIANCE'
    
    # Step 1: Fetch real minute data
    minute_df = fetch_nse_minute_data(symbol, days=30)
    
    if minute_df is not None and len(minute_df) > 100:
        # Step 2: Interpolate to LOB
        lob_df = interpolate_to_lob(minute_df, snapshots_per_minute=5)
        
        # Step 3: Save
        os.makedirs('data', exist_ok=True)
        filepath = f'data/{symbol}_real.parquet'
        lob_df.to_parquet(filepath, index=False)
        
        file_size = os.path.getsize(filepath) / 1e6
        print(f"\n💾 Saved to {filepath} ({file_size:.1f} MB)")
        print(f"📊 Shape: {lob_df.shape}")
        print(f"\n✅ Real NSE data ready!")
        print(f"\nNext step:")
        print(f"  python orchestrator.py --symbol {symbol} --data-dir ./data --output-dir ./output --horizon 10 --epochs 30")
    else:
        print("\n❌ Could not fetch sufficient data.")
        print("   Using realistic synthetic data instead...")
        print("   Run: python generate_realistic_data.py")
