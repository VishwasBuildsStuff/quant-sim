"""
Generate Realistic LOB Data for Multiple NSE Stocks/ETFs
Creates data with realistic microstructure patterns for each symbol
"""

import sys
sys.path.insert(0, r'V:\pylibs')

import numpy as np
import pandas as pd
import os
from datetime import datetime, timedelta

np.random.seed(42)

# Symbol configurations (realistic parameters)
SYMBOLS = {
    'NIFTYBEES': {
        'base_price': 260.0,
        'tick_size': 0.05,
        'avg_spread': 0.05,
        'daily_vol': 0.012,  # 1.2% daily vol (ETF, lower vol)
        'avg_volume_l1': 5000,  # High liquidity
        'mean_reversion': 0.001,
        'momentum': 0.0003,
        'description': 'NIFTY 50 ETF (highly liquid)'
    },
    'BANKBEES': {
        'base_price': 520.0,
        'tick_size': 0.05,
        'avg_spread': 0.05,
        'daily_vol': 0.015,
        'avg_volume_l1': 3000,
        'mean_reversion': 0.0008,
        'momentum': 0.0004,
        'description': 'Bank NIFTY ETF'
    },
    'HNGSNGBEES': {
        'base_price': 85.0,
        'tick_size': 0.05,
        'avg_spread': 0.05,
        'daily_vol': 0.010,
        'avg_volume_l1': 2000,
        'mean_reversion': 0.0012,
        'momentum': 0.0002,
        'description': 'Hang Seng BeES (HK market ETF)'
    },
    'GOLDBEES': {
        'base_price': 65.0,
        'tick_size': 0.05,
        'avg_spread': 0.05,
        'daily_vol': 0.008,
        'avg_volume_l1': 8000,
        'mean_reversion': 0.0015,
        'momentum': 0.0002,
        'description': 'Gold ETF (low vol, high liquidity)'
    },
    'TCS': {
        'base_price': 3850.0,
        'tick_size': 0.05,
        'avg_spread': 0.10,
        'daily_vol': 0.018,
        'avg_volume_l1': 1500,
        'mean_reversion': 0.0005,
        'momentum': 0.0005,
        'description': 'TCS (large cap IT stock)'
    },
    'INFY': {
        'base_price': 1520.0,
        'tick_size': 0.05,
        'avg_spread': 0.05,
        'daily_vol': 0.020,
        'avg_volume_l1': 2000,
        'mean_reversion': 0.0006,
        'momentum': 0.0006,
        'description': 'Infosys (IT stock, higher vol)'
    },
}

def generate_realistic_lob_for_symbol(symbol, n_snapshots=50000):
    """Generate realistic LOB data for a specific symbol"""
    
    if symbol not in SYMBOLS:
        raise ValueError(f"Symbol {symbol} not in configuration. Available: {list(SYMBOLS.keys())}")
    
    config = SYMBOLS[symbol]
    base_price = config['base_price']
    tick_size = config['tick_size']
    
    print(f"\n{'='*60}")
    print(f"🎨 Generating {n_snapshots:,} LOB snapshots for {symbol}")
    print(f"   {config['description']}")
    print(f"   Base Price: ₹{base_price}, Tick: ₹{tick_size}")
    print(f"{'='*60}")
    
    timestamps = np.arange(n_snapshots, dtype=np.int64) * 1_000_000_000
    
    # === VOLATILITY CLUSTERING (GARCH-like) ===
    volatility = np.zeros(n_snapshots)
    volatility[0] = config['daily_vol'] / np.sqrt(390 * 6.5 * 60)  # Convert to per-tick
    
    for i in range(1, n_snapshots):
        volatility[i] = volatility[0] * 0.1 + 0.85 * volatility[i-1] + 0.1 * np.random.randn()**2 * volatility[0]
        volatility[i] = max(volatility[0] * 0.3, min(volatility[i], volatility[0] * 5))
    
    # === PRICE DYNAMICS ===
    mid_prices = np.zeros(n_snapshots)
    mid_prices[0] = base_price
    trend = 0.0
    
    for i in range(1, n_snapshots):
        # Mean reversion
        mean_rev = -config['mean_reversion'] * (mid_prices[i-1] - base_price) / base_price
        
        # Momentum
        trend = 0.3 * trend + volatility[i] * np.random.randn() * config['momentum'] * 10
        
        # Regime switches
        if i % 8000 == 0:
            trend = np.random.randn() * volatility[i] * 5
        
        # Price update (±10% clamp)
        mid_prices[i] = mid_prices[i-1] * (1 + mean_rev + trend)
        mid_prices[i] = max(base_price * 0.9, min(mid_prices[i], base_price * 1.1))
    
    # === SPREAD ===
    base_spread = config['avg_spread']
    spreads = base_spread + 5 * volatility + 0.01 * np.abs(np.random.randn(n_snapshots))
    spreads = np.round(spreads / tick_size) * tick_size
    spreads = np.maximum(spreads, base_spread)
    
    # === ORDER BOOK ===
    bid_prices = np.zeros((n_snapshots, 10))
    ask_prices = np.zeros((n_snapshots, 10))
    
    for level in range(10):
        tick_offset = tick_size * (level + 1)
        noise = np.random.randn(n_snapshots) * tick_size * 0.2 * (level + 1)
        
        bid_prices[:, level] = mid_prices - spreads/2 - tick_offset - noise
        ask_prices[:, level] = mid_prices + spreads/2 + tick_offset + noise
        
        # Round to tick
        bid_prices[:, level] = np.round(bid_prices[:, level] / tick_size) * tick_size
        ask_prices[:, level] = np.round(ask_prices[:, level] / tick_size) * tick_size
    
    # Fix crossed books
    for i in range(n_snapshots):
        for level in range(10):
            if bid_prices[i, level] >= ask_prices[i, level]:
                mid = (bid_prices[i, level] + ask_prices[i, level]) / 2
                bid_prices[i, level] = mid - tick_size
                ask_prices[i, level] = mid + tick_size
    
    # === VOLUMES ===
    volume_regime = np.zeros(n_snapshots)
    volume_regime[0] = 1.0
    for i in range(1, n_snapshots):
        volume_regime[i] = 0.9 * volume_regime[i-1] + 0.1 * np.random.randn()
        volume_regime[i] = max(0.3, volume_regime[i])
    
    bid_volumes = np.zeros((n_snapshots, 10))
    ask_volumes = np.zeros((n_snapshots, 10))
    
    for level in range(10):
        base_vol = config['avg_volume_l1'] / (level + 1)**0.5
        
        # OFI pattern (predictive)
        if level == 0:
            imballance_signal = 0.3 * np.sin(np.arange(n_snapshots) / 500)
            bid_volumes[:, level] = base_vol * volume_regime * (1 + imballance_signal) * (1 + 0.3 * np.random.randn(n_snapshots))
            ask_volumes[:, level] = base_vol * volume_regime * (1 - imballance_signal) * (1 + 0.3 * np.random.randn(n_snapshots))
        else:
            bid_volumes[:, level] = base_vol * volume_regime * (1 + 0.3 * np.random.randn(n_snapshots))
            ask_volumes[:, level] = base_vol * volume_regime * (1 + 0.3 * np.random.randn(n_snapshots))
        
        bid_volumes[:, level] = np.maximum(100, bid_volumes[:, level]).astype(int)
        ask_volumes[:, level] = np.maximum(100, ask_volumes[:, level]).astype(int)
    
    # === TRADE DATA ===
    last_trade_price = mid_prices + np.random.randn(n_snapshots) * tick_size * 0.5
    last_trade_volume = np.random.randint(1, max(500, config['avg_volume_l1']), n_snapshots)
    trade_side = np.where(np.random.randn(n_snapshots) > 0, 1, -1)
    
    # === BUILD DATAFRAME ===
    data = {'timestamp_ns': timestamps}
    
    for level in range(10):
        data[f'bid_price_{level+1}'] = bid_prices[:, level]
        data[f'bid_volume_{level+1}'] = bid_volumes[:, level]
        data[f'ask_price_{level+1}'] = ask_prices[:, level]
        data[f'ask_volume_{level+1}'] = ask_volumes[:, level]
    
    data['last_trade_price'] = last_trade_price
    data['last_trade_volume'] = last_trade_volume
    data['trade_side'] = trade_side
    
    df = pd.DataFrame(data)
    
    # Stats
    crossed = (df['bid_price_1'] >= df['ask_price_1']).sum()
    price_range = f"₹{df['last_trade_price'].min():.2f} - ₹{df['last_trade_price'].max():.2f}"
    avg_spread = df['ask_price_1'].mean() - df['bid_price_1'].mean()
    avg_vol_l1 = df['bid_volume_1'].mean()
    
    print(f"  ✓ Crossed books: {crossed}")
    print(f"  ✓ Price range: {price_range}")
    print(f"  ✓ Avg spread: ₹{avg_spread:.2f}")
    print(f"  ✓ Avg L1 volume: {avg_vol_l1:.0f}")
    
    return df

def generate_all_symbols(n_snapshots=50000):
    """Generate data for all configured symbols"""
    os.makedirs('data', exist_ok=True)
    
    results = {}
    for symbol in SYMBOLS.keys():
        df = generate_realistic_lob_for_symbol(symbol, n_snapshots)
        filepath = f'data/{symbol}.parquet'
        df.to_parquet(filepath, index=False)
        file_size = os.path.getsize(filepath) / 1e6
        results[symbol] = {'file': filepath, 'size_mb': file_size, 'rows': len(df)}
        print(f"  💾 Saved to {filepath} ({file_size:.1f} MB)\n")
    
    return results

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        # Generate specific symbol
        symbol = sys.argv[1].upper()
        if symbol == 'ALL':
            results = generate_all_symbols()
        elif symbol in SYMBOLS:
            df = generate_realistic_lob_for_symbol(symbol)
            filepath = f'data/{symbol}.parquet'
            df.to_parquet(filepath, index=False)
            print(f"\n💾 Saved to {filepath}")
        else:
            print(f"❌ Symbol {symbol} not found. Available: {list(SYMBOLS.keys())}")
    else:
        # Default: Generate HNGSNGBEES (user requested)
        symbol = 'HNGSNGBEES'
        df = generate_realistic_lob_for_symbol(symbol)
        filepath = f'data/{symbol}.parquet'
        df.to_parquet(filepath, index=False)
        print(f"\n💾 Saved to {filepath}")
        print(f"\n✅ Ready! Train with:")
        print(f"   python orchestrator.py --symbol {symbol} --data-dir ./data --output-dir ./output --horizon 10 --epochs 20")
