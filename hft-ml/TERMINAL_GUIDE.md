# HFT Terminal Trading Dashboard

## 🚀 Bloomberg Terminal in Your CLI

A **complete terminal-based trading interface** with real-time prices, order entry, portfolio tracking, and market data - all without a browser!

---

## 📸 What It Looks Like

```
╔══════════════════════════════════════════════════════════════╗
║              HFT TERMINAL TRADING DASHBOARD                  ║
╠══════════════════════════════════════════════════════════════╣
║ TIME: 14:32:15  NIFTY 50: 22045.30 ▲0.45%  EQUITY: ₹10,234,567  P&L: +₹234,567 (+2.35%)
║ RELIANCE 2450.00 ▲0.52%  TCS 3850.00 ▼0.23%  INFY 1520.00 ▲1.12%  HDFC 1680.00 ▲0.34%
╚══════════════════════════════════════════════════════════════╝

[ OVERVIEW ] [ ORDER BOOK ] [ TRADES ] [ PORTFOLIO ]

╔═══════════════ WATCHLIST ═════════════════╗  ╔══ PORTFOLIO POSITIONS ═══╗
║ Symbol   Last    Chg   Chg%   High   Low  ║  ║Symbol  Qty  Avg   Cur  PnL║
║ RELIANCE 2450.00 ▲12.50 +0.52% 2465 2430 ║  ║RELIANCE 100 2448 2450 +200║
║ TCS      3850.00 ▼8.90  -0.23% 3870 3835 ║  ║TCS      50  3845 3850 +250║
║ INFY     1520.00 ▲16.80 +1.12% 1535 1505 ║  ║                           ║
╚═══════════════════════════════════════════╝  ╚═══════════════════════════╝

╔══════════════ ORDER ENTRY ═══════════════╗
║ Symbol: RELIANCE                          ║
║ Side: BUY                                 ║
║ Qty: 100                                  ║
║ Status: FILLED: BUY 100 RELIANCE @ 2450  ║
╚══════════════════════════════════════════╝
```

---

## 🎮 Controls

| Key | Action |
|-----|--------|
| `1` | Overview tab (watchlist + portfolio) |
| `2` | Order Book tab (Level 2 depth) |
| `3` | Trades tab (recent executions) |
| `4` | Portfolio tab (positions + P&L) |
| `B` | Set order side to BUY |
| `S` | Set order side to SELL |
| `R` | Select RELIANCE |
| `T` | Select TCS |
| `I` | Select INFY |
| `H` | Select HDFCBANK |
| `M` | Select TATAMOTORS |
| `0-9` | Enter quantity |
| `ENTER` | Execute order |
| `BACKSPACE` | Delete last digit |
| `Q` | Quit dashboard |

---

## 🚀 Quick Start

### Option 1: One-Click Start
```bash
V:\quant_project\hft-ml\start_terminal.bat
```

### Option 2: Manual Start
```bash
cd V:\quant_project\hft-ml
python terminal_dashboard.py
```

### With Custom Capital
```bash
python terminal_dashboard.py --capital 5000000
```

---

## 📊 Features

### Real-Time Market Data
- **8 NSE Stocks**: RELIANCE, TCS, INFY, HDFCBANK, TATAMOTORS, SBIN, WIPRO, ICICIBANK
- **3 Indices**: NIFTY 50, BANK NIFTY, SENSEX
- **Live Prices**: Updates every 500ms with green/red color coding
- **Ticker Line**: Scrolling price ticker at top

### Order Entry & Execution
- **Buy/Sell Orders**: Full order entry with symbol, side, quantity
- **Instant Execution**: Orders execute at current market price
- **Position Tracking**: Average price, current value, P&L per position
- **Cash Management**: Real-time cash balance tracking

### Portfolio Management
- **Positions Table**: Symbol, quantity, avg price, current price, P&L
- **Total Equity**: Cash + position values
- **Daily P&L**: Realized + unrealized gains/losses
- **Drawdown Tracking**: Peak-to-current drawdown percentage

### Order Book Visualization
- **Level 2 Depth**: 5 levels of bids and asks
- **Bid/Ask Spread**: Real-time spread calculation
- **Mid Price**: Weighted average of best bid/ask
- **Size Display**: Volume at each price level

### Trade Blotter
- **Recent Trades**: Last 10 executions
- **Details**: Time, symbol, side, quantity, price, notional, P&L
- **Color Coding**: Green for BUY, Red for SELL
- **Running Total**: Total trade count

---

## 💡 Usage Examples

### Example 1: Buy RELIANCE
```
1. Press 'R' to select RELIANCE
2. Press 'B' for Buy
3. Type '100' for quantity
4. Press ENTER
→ Order executes at current market price
```

### Example 2: Sell TCS
```
1. Press 'T' to select TCS
2. Press 'S' for Sell
3. Type '50' for quantity
4. Press ENTER
→ Order executes, P&L calculated
```

### Example 3: Monitor Portfolio
```
1. Press '4' for Portfolio tab
2. View all positions with live P&L
3. Press '1' to return to Overview
```

---

## 🎨 Color Coding

| Color | Meaning |
|-------|---------|
| 🟢 **Green** | Price up, profit, buy orders |
| 🔴 **Red** | Price down, loss, sell orders |
| 🟡 **Yellow** | Equity value, order status |
| 🔵 **Cyan** | Symbols, timestamps |
| 🟣 **Magenta** | Order entry panel |

---

## ⚙️ Customization

### Add More Stocks
Edit `terminal_dashboard.py`, line ~270:
```python
self.symbols = {
    'RELIANCE': 'RELIANCE.NS',
    'TCS': 'TCS.NS',
    'YOURSTOCK': 'YOURSTOCK.NS',  # Add here
}
```

### Change Update Speed
```bash
python terminal_dashboard.py --interval 0.2  # 200ms updates
```

### Initial Capital
```bash
python terminal_dashboard.py --capital 5000000  # ₹50 lakhs
```

---

## 📁 Files Created

| File | Description |
|------|-------------|
| `terminal_dashboard.py` | Main terminal trading interface |
| `start_terminal.bat` | Windows startup script |
| `terminal_requirements.txt` | Python dependencies (rich, yfinance) |

---

## 🎯 Terminal vs Web Dashboard

| Feature | Terminal | Web |
|---------|----------|-----|
| **Speed** | Instant | 1-2s load |
| **Keyboard** | Full control | Mouse clicks |
| **SSH** | ✅ Works | ❌ No |
| **Resources** | Minimal | Browser overhead |
| **Customization** | Easy (edit Python) | HTML/CSS needed |
| **Portability** | Anywhere Python runs | Needs browser |

---

**Built for professional traders who live in the terminal!** 🚀

*Press Q to quit anytime. All changes are in-memory (no persistence yet).*
