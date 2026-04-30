# Live NSE Market Data Connection Guide

This guide will help you connect to live NSE market data for your HFT-ML project.

## Overview

Your project now supports **three data sources** with automatic fallback:

1. **Yahoo Finance** (Free, 1-min delayed) - Easiest to setup
2. **NSE Python** (Free, Direct from NSE) - Good for equities
3. **Zerodha Kite** (Paid, Real-time) - Best for production trading

## Quick Start

### Option 1: Yahoo Finance (Recommended for Testing)

**Install required package:**
```bash
pip install yfinance
```

**View live market data:**
```bash
python connect_live_market.py live --symbol RELIANCE --source yahoo --interval 5 --duration 30
```

**Fetch historical data for training:**
```bash
python connect_live_market.py fetch --symbol RELIANCE --days 30
```

**Example symbols:**
- `RELIANCE` - Reliance Industries
- `TCS` - Tata Consultancy Services
- `INFY` - Infosys
- `HDFCBANK` - HDFC Bank
- `SBIN` - State Bank of India

### Option 2: NSE Python (Direct NSE Access)

**Install required package:**
```bash
pip install nsepython
```

**View live market data:**
```bash
python connect_live_market.py live --symbol RELIANCE --source nsepython --interval 5
```

### Option 3: Zerodha Kite (Real-time, Production)

**Install required package:**
```bash
pip install kiteconnect
```

**Setup Steps:**

1. **Get API Credentials:**
   - Sign up at https://kite.zerodha.com/
   - Get your API key and secret
   - Generate access token via login flow

2. **Configure credentials:**
   
   Edit `live_config.json`:
   ```json
   {
     "zerodha": {
       "enabled": true,
       "api_key": "YOUR_API_KEY",
       "access_token": "YOUR_ACCESS_TOKEN"
     }
   }
   ```

3. **Start live feed:**
   ```bash
   python connect_live_market.py live --symbol RELIANCE --source zerodha --interval 1
   ```

## Usage Modes

### 1. Live Streaming Mode

Watch real-time market data with full order book:

```bash
python connect_live_market.py live --symbol RELIANCE --interval 5 --duration 30
```

**Options:**
- `--symbol`: NSE symbol name (default: RELIANCE)
- `--source`: Data source (auto/yahoo/nsepython/zerodha)
- `--interval`: Update interval in seconds (default: 5)
- `--duration`: How long to run in minutes (default: 30)
- `--record`: Save data to file for later training

**Example with recording:**
```bash
python connect_live_market.py live --symbol TCS --source yahoo --record --duration 60
```

This will:
- Stream live data for 60 minutes
- Display snapshots in real-time
- Save data to `data/live/TCS_YYYYMMDD_HHMMSS.parquet`

### 2. Fetch Historical Mode

Download recent historical data and convert to LOB format:

```bash
python connect_live_market.py fetch --symbol RELIANCE --days 30
```

**Options:**
- `--symbol`: NSE symbol name
- `--source`: Data source (yahoo/nsepython)
- `--days`: Number of days to fetch (max 30 for Yahoo Finance)

This will:
1. Fetch minute-level OHLCV data
2. Interpolate to tick-level LOB snapshots
3. Save to `data/RELIANCE_live.parquet`

## Integration with Training Pipeline

Once you have live data, use it for training:

```bash
# Step 1: Fetch historical data
python connect_live_market.py fetch --symbol RELIANCE --days 30

# Step 2: Train model on live data
python orchestrator.py --symbol RELIANCE --data-dir ./data --output-dir ./output --horizon 10 --epochs 30
```

## Integration with Live Trading

Connect your trained model to live markets:

```bash
# Make sure you have a trained model first
python orchestrator.py --symbol RELIANCE --data-dir ./data --output-dir ./output

# Then run live trading
python live_trading.py --model output/RELIANCE_ensemble.joblib --symbol RELIANCE --paper --capital 1000000 --duration 60
```

## Data Format

Live data is saved in the same LOB parquet format as your training data:

```python
import pandas as pd

# Load live data
df = pd.read_parquet('data/live/RELIANCE_20250410_143022.parquet')

# View columns
print(df.columns)

# Sample data
print(df.head())
```

**Columns:**
- `timestamp`: Data timestamp
- `bid_price_1` to `bid_price_10`: Bid prices at each level
- `bid_volume_1` to `bid_volume_10`: Bid volumes at each level
- `ask_price_1` to `ask_price_10`: Ask prices at each level
- `ask_volume_1` to `ask_volume_10`: Ask volumes at each level
- `last_trade_price`: Last traded price
- `last_trade_volume`: Last traded volume
- `trade_side`: 1 for buy, -1 for sell
- `vwap`: Volume-weighted average price

## Programmatic Usage

You can also use the live feed in your own scripts:

```python
from live_data_feed import MultiSourceLiveFeed

# Create feed
live_feed = MultiSourceLiveFeed(
    symbol='RELIANCE',
    n_levels=10,
    update_interval=5
)

# Add callback
def on_snapshot(snapshot):
    print(f"Price: {snapshot.last_trade_price:.2f}")
    print(f"Bid: {snapshot.bid_prices[0]:.2f} x {snapshot.bid_volumes[0]}")
    print(f"Ask: {snapshot.ask_prices[0]:.2f} x {snapshot.ask_volumes[0]}")

live_feed.add_callback(on_snapshot)

# Start
live_feed.start()

# Run for 5 minutes
import time
time.sleep(300)

# Stop
live_feed.stop()

# Get recent data as DataFrame
df = live_feed.get_snapshots_as_dataframe(n=100)
print(df)
```

## Troubleshooting

### "No data feeds available"
Install at least one data source:
```bash
pip install yfinance  # Easiest
```

### "yfinance not installed"
```bash
pip install yfinance
```

### "nsepython not installed"
```bash
pip install nsepython
```

### "kiteconnect not installed"
```bash
pip install kiteconnect
```

### Insufficient data
- Yahoo Finance max is 30 days for 1-minute data
- Try different symbols (some have more data than others)
- Use `--days 7` for a week of data

### Market hours
NSE market hours: 9:15 AM - 3:30 PM IST (Monday-Friday)
- Data outside market hours will be stale
- Best to fetch during market hours for live data

## Configuration File

Edit `live_config.json` to set defaults:

```json
{
  "symbol": "RELIANCE",              // Default symbol
  "data_source": "auto",             // auto/yahoo/nsepython/zerodha
  "update_interval_sec": 5,          // Update frequency
  "order_book_levels": 10,           // LOB levels
  "recording": {
    "enabled": true,                 // Auto-record
    "output_dir": "data/live",       // Where to save
    "flush_interval": 100            // Snapshots per file
  },
  "zerodha": {
    "enabled": false,                // Enable Zerodha
    "api_key": "YOUR_KEY",
    "access_token": "YOUR_TOKEN"
  },
  "trading": {
    "paper_trading": true,           // Paper trading mode
    "capital": 1000000,              // Starting capital
    "risk_per_trade": 0.02,          // 2% risk
    "max_position": 1000             // Max position size
  }
}
```

## Architecture

```
connect_live_market.py
        ↓
live_data_feed.py
        ↓
┌──────────────────────────────────┐
│   MultiSourceLiveFeed            │
│   (Automatic Fallback)           │
└──────────────────────────────────┘
        ↓
┌──────────┬──────────┬──────────┐
│ Yahoo    │ NSE      │ Zerodha  │
│ Finance  │ Python   │ Kite     │
└──────────┴──────────┴──────────┘
        ↓
┌──────────────────────────────────┐
│   LOB Snapshots                  │
│   (10-level order book)          │
└──────────────────────────────────┘
        ↓
┌─────────────┬──────────────┐
│ Display     │ Record to    │
│ on Screen   │ Parquet File │
└─────────────┴──────────────┘
        ↓
┌──────────────────────────────────┐
│   Use for Training or Trading    │
└──────────────────────────────────┘
```

## Next Steps

1. **Test with Yahoo Finance:**
   ```bash
   python connect_live_market.py live --symbol RELIANCE --source yahoo --duration 10
   ```

2. **Fetch training data:**
   ```bash
   python connect_live_market.py fetch --symbol RELIANCE --days 30
   ```

3. **Train your model:**
   ```bash
   python orchestrator.py --symbol RELIANCE --data-dir ./data --output-dir ./output
   ```

4. **Go live with paper trading:**
   ```bash
   python live_trading.py --model output/RELIANCE_ensemble.joblib --symbol RELIANCE --paper
   ```

## Support

- Check logs: `live_data_feed.log`
- Check trading logs: `trading.log`
- Data files: `data/live/*.parquet`
