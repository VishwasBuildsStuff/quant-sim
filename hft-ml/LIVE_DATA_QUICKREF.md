# Live NSE Market Data - Quick Reference

## ✅ SETUP COMPLETE

Your live market data connection is ready and tested!

---

## 🚀 Quick Commands

### View Live Market Data
```bash
python connect_live_market.py live --symbol RELIANCE --interval 5 --duration 30
```

### Fetch Historical Data for Training
```bash
# 1-minute data (max 8 days)
python connect_live_market.py fetch --symbol RELIANCE --days 8 --data-interval 1m

# 5-minute data (max 60 days) - RECOMMENDED
python connect_live_market.py fetch --symbol RELIANCE --days 60 --data-interval 5m

# 1-hour data (max 730 days / 2 years)
python connect_live_market.py fetch --symbol RELIANCE --days 365 --data-interval 1h
```

### Record Live Data to Files
```bash
python connect_live_market.py live --symbol TCS --record --duration 60
```

---

## 📊 What Works Now

✅ **Yahoo Finance** - Free, 1-min delayed data (TESTED & WORKING)
⚠️ **NSE Python** - Available but not tested
⚠️ **Zerodha Kite** - Requires API credentials (not configured)

---

## 📁 Files Created

1. **`live_data_feed.py`** - Core live data feed system with multiple sources
2. **`connect_live_market.py`** - Simple launcher for live/fetch modes
3. **`live_config.json`** - Configuration file for live trading
4. **`LIVE_MARKET_CONNECTION.md`** - Complete documentation

---

## 🎯 Next Steps

### Option 1: Train a Model with Live Data
```bash
# Data already fetched to: data/RELIANCE_live.parquet
python orchestrator.py --symbol RELIANCE --data-dir ./data --output-dir ./output --horizon 10 --epochs 30
```

### Option 2: Go Live with Paper Trading
```bash
# After training your model
python live_trading.py --model output/RELIANCE_ensemble.joblib --symbol RELIANCE --paper --capital 1000000
```

### Option 3: Record More Live Data
```bash
# Record during market hours (9:15 AM - 3:30 PM IST)
python connect_live_market.py live --symbol INFY --record --duration 120
```

---

## 🔧 Common Symbols

| Symbol | Company | Price Range |
|--------|---------|-------------|
| RELIANCE | Reliance Industries | ₹1,300-1,400 |
| TCS | Tata Consultancy Services | ₹3,000-3,500 |
| INFY | Infosys | ₹1,400-1,600 |
| HDFCBANK | HDFC Bank | ₹1,600-1,800 |
| SBIN | State Bank of India | ₹600-700 |
| HNGSNGBEES | Nippon India ETF | ₹80-90 |

---

## ⚠️ Yahoo Finance Data Limitations

| Interval | Max Days | Best For |
|----------|----------|----------|
| `1m` | 8 days | High-frequency training |
| `5m` | 60 days | **RECOMMENDED** - Good balance |
| `15m` | 60 days | Medium-frequency |
| `30m` | 60 days | Swing trading models |
| `1h` | 730 days (2 years) | Long-term patterns |
| `1d` | 30 years | Historical analysis |

**Note:** The system will auto-adjust if you request too many days for an interval.

**NSE Market Hours (IST):**
- Pre-open: 9:00 AM - 9:15 AM
- **Regular: 9:15 AM - 3:30 PM** ← Best time
- Post-close: 3:30 PM - 4:00 PM

**UTC Time:** 3:45 AM - 10:00 AM

---

## 📝 Data Format

All live data is saved in LOB (Limit Order Book) format:
- 10-level order book (bid/ask prices and volumes)
- Trade data (last price, volume, side)
- Timestamps in nanoseconds
- Compatible with your existing training pipeline

---

## 🆘 Troubleshooting

**No data appearing?**
- Check if market is open (NSE hours)
- Try different symbol
- Check internet connection

**Import errors?**
```bash
pip install yfinance pandas numpy
```

**Want real-time data?**
- Sign up for Zerodha Kite API
- Configure credentials in `live_config.json`

---

## 📚 Full Documentation

See `LIVE_MARKET_CONNECTION.md` for complete documentation including:
- Zerodha Kite setup
- Advanced usage
- Programmatic API
- Architecture details

---

**Last Updated:** April 10, 2026
**Status:** ✅ Tested & Working
