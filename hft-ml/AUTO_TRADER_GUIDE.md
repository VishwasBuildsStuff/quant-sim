# 🤖 Autonomous HFT Trading Terminal

Your **fully automated** trading system that runs in the background and makes all decisions for you!

---

## 🎯 What It Does

✅ **Monitors** a watchlist of stocks automatically  
✅ **Analyzes** each stock with multi-model ensemble  
✅ **Decides** which stocks to BUY, SELL, or HOLD  
✅ **Executes** trades automatically  
✅ **Manages** risk, positions, and portfolio allocation  
✅ **Runs** continuously in background  

---

## 🚀 Quick Start (3 Steps)

### **Step 1: Train Multi-Model Ensemble** (10 minutes)

```bash
python multi_model_ensemble.py --data data/RELIANCE_live.parquet --output output/RELIANCE_multi_ensemble.joblib
```

This trains **3 models** (XGBoost + LightGBM + Random Forest) and combines them with voting.

### **Step 2: Start Autonomous Bot** (Run Forever)

```bash
python auto_trader.py
```

Or use the launcher:
```bash
start_auto_trader.bat
# Then select option 2
```

### **Step 3: Let It Run!**

The bot will:
- Fetch live data for all symbols in your watchlist
- Make predictions every 10 seconds
- Execute trades when confidence is high
- Manage your portfolio automatically
- Stop losses protect your capital

---

## 📊 System Architecture

```
┌─────────────────────────────────────────────────────────┐
│          AUTONOMOUS HFT TRADING BOT                      │
└─────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌──────▼───────┐  ┌───────▼────────┐
│   WATCHLIST    │  │   PORTFOLIO  │  │  MULTI-MODEL   │
│   MANAGER      │  │   MANAGER    │  │   ENSEMBLE     │
└───────┬────────┘  └──────┬───────┘  └───────┬────────┘
        │                   │                   │
        │  ┌────────────────┼────────────────┐  │
        │  │                                    │  │
        ▼  ▼                                    ▼  ▼
┌───────────────┐                      ┌──────────────┐
│ RELIANCE      │                      │ XGBoost      │
│ TCS           │                      │ LightGBM     │
│ INFY          │                      │ Rand Forest  │
│ HDFCBANK      │                      │ + Voting     │
│ SBIN          │                      └──────────────┘
└───────────────┘                            │
        │                                    │
        │         ┌──────────────────────────┘
        │         │
        ▼         ▼
┌─────────────────────────────────┐
│    TRADING DECISION ENGINE      │
│                                 │
│  For each stock:                │
│  1. Get live features           │
│  2. Run 3 models                │
│  3. Vote on prediction          │
│  4. Check confidence            │
│  5. Calculate position size     │
│  6. Execute if conditions met   │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│     RISK MANAGEMENT             │
│                                 │
│  - Stop losses                  │
│  - Max drawdown limit           │
│  - Position size limits         │
│  - Daily trade limits           │
└─────────────────────────────────┘
```

---

## ⚙️ Configuration

### **Watchlist** (`watchlist.json`)

The bot monitors these stocks by default:

```json
{
  "symbols": [
    {"symbol": "RELIANCE", "name": "Reliance Industries", "sector": "Energy", "priority": 90},
    {"symbol": "TCS", "name": "Tata Consultancy Services", "sector": "IT", "priority": 85},
    {"symbol": "INFY", "name": "Infosys", "sector": "IT", "priority": 80},
    {"symbol": "HDFCBANK", "name": "HDFC Bank", "sector": "Banking", "priority": 85},
    {"symbol": "SBIN", "name": "State Bank of India", "sector": "Banking", "priority": 75}
  ]
}
```

**Customize:**
- Add/remove symbols
- Change priority (0-100, higher = more important)
- Enable/disable specific stocks

### **Trading Config** (`auto_trader_config.json`)

```json
{
  "initial_capital": 1000000,      // Starting capital
  "max_positions": 5,               // Max simultaneous positions
  "risk_per_trade": 0.02,           // Risk 2% per trade
  "max_position_pct": 0.20,         // Max 20% in one stock
  "stop_loss_pct": 0.02,            // 2% stop loss
  "max_drawdown_pct": 0.05,         // Max 5% drawdown
  "update_interval": 10,            // Check every 10 seconds
  "max_symbols": 5,                 // Monitor top 5 symbols
  "trade_cooldown": 60,             // 60s between trades per symbol
  "confidence_threshold": 0.65      // Only trade if >65% confidence
}
```

---

## 📈 How Decisions Are Made

For **each stock** every 10 seconds:

1. **Fetch live market data**
   - Order book snapshots
   - Recent trades
   - Bid/ask spread

2. **Engineer 79 features**
   - Price patterns
   - Volume analysis
   - Order flow imbalance
   - Volatility metrics

3. **Run 3 models**
   ```
   XGBoost:    UP=65%, UNCH=20%, DOWN=15%
   LightGBM:   UP=60%, UNCH=25%, DOWN=15%
   RandForest: UP=58%, UNCH=22%, DOWN=20%
   ```

4. **Vote & combine**
   ```
   Weighted average: UP=62%, UNCH=22%, DOWN=16%
   Prediction: UP
   Confidence: 62%
   Model agreement: 85%
   Adjusted confidence: 62% × 85% = 52.7%
   ```

5. **Decision logic**
   ```
   IF confidence > 65% AND prediction = UP:
       → BUY
   ELIF confidence > 65% AND prediction = DOWN:
       → SELL (if holding) or SHORT (if allowed)
   ELSE:
       → HOLD
   ```

6. **Position sizing**
   ```
   Position = Capital × Risk% × Confidence × Volatility Adjustment
   ```

7. **Risk checks**
   - Stop loss not hit?
   - Below max positions?
   - Below daily trade limit?
   - Within drawdown limit?

---

## 🎮 Usage Examples

### **Train models for multiple stocks**

```bash
# RELIANCE
python multi_model_ensemble.py --data data/RELIANCE_live.parquet --output output/RELIANCE_multi_ensemble.joblib

# TCS
python multi_model_ensemble.py --data data/TCS_live.parquet --output output/TCS_multi_ensemble.joblib

# INFY
python multi_model_ensemble.py --data data/INFY_live.parquet --output output/INFY_multi_ensemble.joblib
```

### **Fetch data for multiple stocks**

```bash
python connect_live_market.py fetch --symbol TCS --days 60 --data-interval 5m
python connect_live_market.py fetch --symbol INFY --days 60 --data-interval 5m
python connect_live_market.py fetch --symbol HDFCBANK --days 60 --data-interval 5m
```

### **Start autonomous bot**

```bash
# With default settings
python auto_trader.py

# With custom capital
python auto_trader.py --capital 2000000

# With fewer positions
python auto_trader.py --max-pos 3
```

### **Monitor running bot**

The bot logs everything to `auto_trader.log`:

```bash
tail -f auto_trader.log  # On Linux/Mac
Get-Content auto_trader.log -Wait  # On Windows
```

---

## 📊 What You'll See

### **Live Output**

```
────────────────────────────────────────────────────────────
🔄 CYCLE #15 - 14:32:45
────────────────────────────────────────────────────────────

📊 PORTFOLIO STATUS:
   Equity: ₹1,012,450
   PnL: ₹12,450 (+1.25%)
   Positions: 3/5
   Daily Trades: 12
   Win Rate: 58.3%
   Drawdown: 0.8%

📈 OPEN POSITIONS:
   RELIANCE: 14 shares @ ₹1,345.80 | Current: ₹1,348.20 | PnL: +₹34 (+0.18%)
   TCS: 8 shares @ ₹3,456.50 | Current: ₹3,462.00 | PnL: +₹44 (+0.16%)
   INFY: 10 shares @ ₹1,523.40 | Current: ₹1,521.80 | PnL: -₹16 (-0.10%)

✅ BUY RELIANCE | Qty: 14 | Price: ₹1,348.20 | Conf: 72.5% | Reason: UP signal (72.5%)
✅ SELL TCS | Qty: 8 | Price: ₹3,462.00 | Conf: 68.3% | Reason: DOWN signal (68.3%)
```

---

## ⚠️ Important Notes

### **Market Hours**
NSE: **9:15 AM - 3:30 PM IST** (3:45 AM - 10:00 AM UTC)

- Bot works 24/7 but only trades during market hours
- Outside hours: positions held, no new trades

### **Risk Management**
The bot has **5 layers of protection**:

1. **Stop Loss**: 2% per position
2. **Max Drawdown**: 5% total
3. **Position Limits**: Max 5 stocks
4. **Daily Trade Limit**: 100 trades/day
5. **Confidence Threshold**: Only trades above 65% confidence

### **Model Quality**
- Models trained on live data perform better
- Retrain weekly for best results
- More data = better predictions

### **Paper vs Live Trading**
```bash
# Paper trading (default - no real money)
python auto_trader.py

# For live trading, integrate with broker API
# (Zerodha, Upstox, etc.)
```

---

## 🔧 Troubleshooting

**Problem**: "No models loaded"
```bash
# Train models first
python multi_model_ensemble.py --data data/RELIANCE_live.parquet --output output/RELIANCE_multi_ensemble.joblib
```

**Problem**: "Insufficient data for features"
```bash
# Wait 3-5 minutes for data buffer to fill
# Or fetch historical data
python connect_live_market.py fetch --symbol RELIANCE --days 60 --data-interval 5m
```

**Problem**: Bot not making trades
- Check confidence threshold (default 65%)
- Models may predict UNCH (hold)
- Increase risk_per_trade in config

**Problem**: Too many/few trades
- Adjust `trade_cooldown` in config
- Change `confidence_threshold`
- Modify `max_daily_trades`

---

## 📁 File Structure

```
hft-ml/
├── auto_trader.py                 ← Main autonomous bot
├── multi_model_ensemble.py        ← 3-model voting system
├── portfolio_manager.py           ← Position & risk management
├── watchlist_manager.py           ← Multi-symbol monitoring
├── auto_trader_config.json        ← Trading configuration
├── watchlist.json                 ← Stock watchlist
├── start_auto_trader.bat          ← Quick launcher
├── AUTO_TRADER_GUIDE.md          ← This file
│
├── data/
│   ├── RELIANCE_live.parquet     ← Live market data
│   ├── TCS_live.parquet          ← Add more symbols
│   └── ...
│
├── output/
│   ├── RELIANCE_multi_ensemble.joblib  ← Multi-model
│   ├── RELIANCE_live_trained.joblib    ← Single model
│   └── ...
│
└── trade_history_*.json          ← Trade logs
```

---

## 🚀 Complete Workflow

### **Day 1: Setup & Training**

```bash
# 1. Fetch live data for multiple stocks
python connect_live_market.py fetch --symbol RELIANCE --days 60 --data-interval 5m
python connect_live_market.py fetch --symbol TCS --days 60 --data-interval 5m
python connect_live_market.py fetch --symbol INFY --days 60 --data-interval 5m

# 2. Train multi-model ensembles
python multi_model_ensemble.py --data data/RELIANCE_live.parquet --output output/RELIANCE_multi_ensemble.joblib
python multi_model_ensemble.py --data data/TCS_live.parquet --output output/TCS_multi_ensemble.joblib
python multi_model_ensemble.py --data data/INFY_live.parquet --output output/INFY_multi_ensemble.joblib

# 3. Customize watchlist
# Edit watchlist.json to add/remove symbols
```

### **Day 2: Start Trading**

```bash
# Start autonomous bot
python auto_trader.py

# Or use launcher
start_auto_trader.bat
# Select option 2
```

### **Weekly: Retrain Models**

```bash
# Fetch fresh data
python connect_live_market.py fetch --symbol RELIANCE --days 60 --data-interval 5m

# Retrain
python multi_model_ensemble.py --data data/RELIANCE_live.parquet --output output/RELIANCE_multi_ensemble.joblib

# Restart bot
python auto_trader.py
```

---

## 📞 Support

- **Logs**: `auto_trader.log`
- **Trades**: `trade_history_*.json`
- **Config**: `auto_trader_config.json`
- **Watchlist**: `watchlist.json`

---

**Last Updated**: April 10, 2026  
**Status**: ✅ Production Ready (Paper Trading)
