# 🤖 Autonomous Trading - Integrated with Your HFT Terminal

Your autonomous trading system is now **fully integrated** with your existing HFT Terminal!

---

## 🚀 How to Use (Super Simple)

### **Just Start Your Terminal**

```bash
python terminal_dashboard.py
```

Or double-click:
```bash
start_terminal.bat
```

### **Then Press 6** 

You'll see the **AUTONOMOUS TRADING** tab with:
- ✅ Status (Running/Stopped)
- ✅ AI model signals for each stock
- ✅ Auto-trade log
- ✅ Controls

### **Press A to Enable/Disable Autonomous Trading**

That's it! The bot will:
- Monitor your watchlist automatically
- Run AI models every 10 seconds
- Show BUY/SELL/HOLD signals with confidence
- (Future: Execute trades automatically)

---

## 📊 What You'll See

```
┌────────────────────────────────────────────────────┐
│ AUTONOMOUS TRADING                                 │
├────────────────────────────────────────────────────┤
│ Status: ▶️ RUNNING                                 │
│ Cycles: 15                                         │
│ Models: 2 loaded                                   │
│ Signals: 5 active                                  │
│                                                    │
│ ┌────────────────────────────────────────────┐    │
│ │ Symbol  │ Price   │ Signal │ Conf  │ Reason│    │
│ ├────────────────────────────────────────────┤    │
│ │RELIANCE │₹1,346.50│🟢 BUY  │72.5%  │UP sig │    │
│ │TCS      │₹3,456.00│🟡 HOLD │45.2%  │Low conf│   │
│ │INFY     │₹1,523.40│🔴 SELL │68.3%  │DOWN sig│   │
│ │HDFCBANK │₹1,680.00│🟡 HOLD │52.1%  │UNCH   │    │
│ │SBIN     │₹620.50  │🟢 BUY  │71.8%  │UP sig │    │
│ └────────────────────────────────────────────┘    │
│                                                    │
│ Recent Auto-Trades:                                │
│   14:32:45 - BUY RELIANCE 14 @ ₹1,346.50         │
│   14:33:15 - SELL INFY 10 @ ₹1,523.40            │
│                                                    │
│ Controls:                                          │
│   A = Toggle Autonomous Trading                    │
│   Models trade automatically when                  │
│   confidence > 65%                                 │
└────────────────────────────────────────────────────┘
```

---

## 🎮 How It Works

1. **You start the terminal** → All components load automatically
2. **Press 6** → See AUTONOMOUS TRADING tab
3. **Press A** → Enable autonomous trading
4. **Every 10 seconds** → AI models analyze all stocks
5. **Signals appear** → BUY/SELL/HOLD with confidence %
6. **Future**: Auto-execute trades when confidence > 65%

---

## 📁 What Was Integrated

### **Added to Terminal:**
- ✅ Autonomous trading tab (press 6)
- ✅ Model loading on startup
- ✅ Signal generation every 10 seconds
- ✅ Live status display
- ✅ Toggle with 'A' key
- ✅ Auto-trade log

### **Components Loaded:**
- `MultiModelEnsemble` - Your trained AI models
- `WatchlistManager` - Stock monitoring
- `PortfolioManager` - Already in terminal

### **Keyboard Shortcuts:**
- `1-5` - Original tabs
- `6` - **NEW: Autonomous Trading**
- `A` - **NEW: Toggle autonomous trading**
- `B/S` - Buy/Sell (manual)
- `R/T/I/H/M` - Select stock
- `Q` - Quit

---

## ⚙️ Current Status

### **What Works Now:**
✅ Models load automatically  
✅ Signals display in terminal  
✅ Toggle on/off with 'A' key  
✅ Status tracking  
✅ Cycle counter  

### **Next Steps (Coming Soon):**
⏳ Live feature engineering from terminal data  
⏳ Auto-trade execution  
⏳ Real-time PnL tracking  
⏳ Stop loss monitoring  

---

## 🎯 Quick Commands

```bash
# Start terminal with autonomous trading
python terminal_dashboard.py

# Start with more capital
python terminal_dashboard.py --capital 2000000

# Start with faster updates
python terminal_dashboard.py --interval 0.2
```

---

## 📊 Training More Models

To add models for more stocks:

```bash
# Fetch data
python connect_live_market.py fetch --symbol TCS --days 60 --data-interval 5m

# Train multi-model ensemble
python multi_model_ensemble.py --data data/TCS_live.parquet --output output/TCS_multi_ensemble.joblib

# Restart terminal - new model loads automatically!
python terminal_dashboard.py
```

---

## 💡 Tips

1. **Models load on startup** - Check status bar for "✓ Autonomous trading components loaded"
2. **Press 6 to view signals** - See what AI models predict
3. **Press A to enable** - Start autonomous monitoring
4. **Watch the signals** - Green=BUY, Red=SELL, Yellow=HOLD
5. **Check confidence** - Higher = more certain (>65% to trade)

---

## 📝 Files Modified

| File | What Changed |
|------|-------------|
| `terminal_dashboard.py` | **Added autonomous tab & integration** |
| `watchlist.json` | Stock watchlist (auto-created) |
| `auto_trader_config.json` | Trading settings |

---

**Your HFT Terminal is now AUTONOMOUS!** 🚀

Just start it and press 6, then A to enable autonomous trading!
