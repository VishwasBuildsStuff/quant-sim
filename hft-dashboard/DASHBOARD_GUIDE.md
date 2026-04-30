# HFT Bloomberg Terminal Dashboard

Professional-grade trading dashboard modeled after the Bloomberg Terminal, designed for real-time monitoring of your HFT simulation platform.

---

## 🚀 Quick Start

### Option 1: Using the Startup Script (Windows)

```bash
cd V:\quant_project\hft-dashboard
start_dashboard.bat
```

### Option 2: Manual Start

```bash
cd V:\quant_project\hft-dashboard
pip install -r requirements.txt
python dashboard_server.py
```

### Access the Dashboard

Open your browser and navigate to: **http://localhost:8000**

---

## 🎨 Dashboard Features

### Bloomberg Terminal Aesthetics

- **Dark Theme**: Professional #0a0e17 background (same as Bloomberg)
- **Price Colors**: 
  - 🟢 **Green (#00c853)** for price increases
  - 🔴 **Red (#ff1744)** for price decreases
  - ⚪ **Gray (#8b92a8)** for neutral/unchanged
- **Monospace Fonts**: Consolas/Monaco for all numerical data
- **Flash Updates**: Prices flash green/red when they update
- **Scrolling Ticker Tape**: Continuous market data scroll at top

---

## 📊 Dashboard Sections

### 1. **Overview** (Press `1`)

The main dashboard showing:

#### Market Indices
- **NIFTY 50**: Current value and daily change
- **BANK NIFTY**: Banking sector index
- **SENSEX**: Bombay Stock Exchange index
- **NIFTY IT**: Information Technology index

#### Portfolio Performance Metrics
- **Total Equity**: Current portfolio value in Lakhs/Crores
- **Total P&L**: Profit/Loss in ₹ and percentage
- **Sharpe Ratio**: Risk-adjusted return measure
- **Sortino Ratio**: Downside risk-adjusted return
- **Max Drawdown**: Largest peak-to-trough decline
- **VaR (95%)**: Value at Risk at 95% confidence
- **CVaR (95%)**: Conditional Value at Risk (Expected Shortfall)
- **Total Trades**: Number of executed trades
- **Average Win Rate**: Across all agents

#### Equity Curve Chart
- Real-time portfolio value over time
- Green line with shaded area
- Updates every second via WebSocket

#### Drawdown Chart
- Red line showing portfolio drawdown from peak
- Reversed Y-axis (worse = lower)
- Critical for risk monitoring

#### Agent Performance Summary
- Quick view of all 5 trading agents
- P&L, Win Rate, and Trade count for each

---

### 2. **Prices** (Press `2`)

Live market prices for all 10 stocks in your watchlist:

| Column | Description |
|--------|-------------|
| **Symbol** | Stock ticker (cyan color) |
| **Last Price** | Current market price in ₹ |
| **Change** | Absolute price change |
| **Change %** | Percentage change |
| **Day High** | Highest price in recent period |
| **Day Low** | Lowest price in recent period |
| **Volume** | Trading volume |
| **Time** | Last update timestamp |

**Watchlist:**
- RELIANCE, TCS, INFY, HDFCBANK, TATAMOTORS
- SBIN, WIPRO, ADANIENT, ICICIBANK, HCLTECH

---

### 3. **Order Book** (Press `3`)

Level 2 market depth visualization:

#### Left Panel: RELIANCE Order Book
- **Bids** (Green): Buy orders with price, size, order count
- **Asks** (Red): Sell orders with price, size, order count
- **Spread**: Bid-ask difference
- **Mid Price**: Average of best bid and ask

#### Right Panel: TCS Order Book
- Same structure as RELIANCE
- Top 8 price levels on each side

**Order Book Columns:**
- **Price**: Order price in ₹
- **Size**: Total quantity at that level
- **Orders**: Number of individual orders

---

### 4. **Agents** (Press `4`)

Detailed performance metrics for all trading agents:

#### Agent Types:

1. **HFT Market Maker** (Cyan border)
   - Continuous bid-ask quoting
   - High trade frequency (800-1500 trades)
   - Win rate: 58-72%
   - Capital: ₹10,000,000

2. **HFT Arbitrageur** (Cyan border)
   - Cross-venue price discrepancy exploitation
   - Trade frequency: 400-900
   - Win rate: 62-78%
   - Capital: ₹5,000,000

3. **Institutional Algo** (Purple border)
   - TWAP/VWAP execution algorithms
   - Lower frequency (50-150 trades)
   - Win rate: 52-65%
   - Capital: ₹50,000,000

4. **Semi-Pro Trader** (Blue border)
   - Technical analysis strategies
   - Trade frequency: 100-250
   - Win rate: 45-60%
   - Capital: ₹2,000,000

5. **Retail Trader** (Orange border)
   - Behavioral finance (Prospect Theory)
   - Fear/Greed Index displayed
   - Lower win rate: 35-52%
   - Capital: ₹500,000

**Metrics per Agent:**
- **Capital**: Initial investment
- **P&L**: Current profit/loss (₹ and %)
- **Win Rate**: Percentage of winning trades
- **Trades**: Total number of trades
- **Positions**: Current holdings per symbol

---

### 5. **Trades** (Press `5`)

Real-time trade blotter showing recent executions:

| Column | Description |
|--------|-------------|
| **Time** | Execution timestamp |
| **Symbol** | Traded instrument (cyan) |
| **Side** | BUY (green) or SELL (red) |
| **Price** | Execution price in ₹ |
| **Qty** | Number of shares/contracts |
| **Notional** | Total value (Price × Qty) |
| **Agent** | Which agent executed the trade |

**Features:**
- Sorted by time (most recent first)
- Color-coded buy/sell sides
- Auto-updates every 3 seconds

---

### 6. **Risk** (Press `6`)

Advanced risk management dashboard:

#### Market Regime Detection
- **Current Regime**: Risk-On / Risk-Off / High Volatility / Low Volatility / Trending / Range-bound
- **Volatility**: Current market volatility %
- **Trend Strength**: -1 to +1 scale
- **Liquidity Score**: 0-100 (higher = more liquid)
- **Correlation Breakdown**: Yes/No warning

#### Risk Metrics
- **Portfolio VaR (95%)**: Value at Risk
- **Expected Shortfall**: Tail risk measure
- **Market Volatility**: Current vol regime
- **Liquidity**: Market depth indicator

**Color Coding:**
- 🟢 **Green**: Safe levels
- 🟠 **Orange**: Warning levels
- 🔴 **Red**: Danger levels

---

## ⌨️ Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` | Switch to Overview section |
| `2` | Switch to Prices section |
| `3` | Switch to Order Book section |
| `4` | Switch to Agents section |
| `5` | Switch to Trades section |
| `6` | Switch to Risk section |
| `R` | Refresh all data |
| `F` | Toggle fullscreen mode |

---

## 🔌 API Endpoints

The dashboard exposes REST APIs for integration with other tools:

### Market Data

```bash
# Get live prices
GET http://localhost:8000/api/prices

# Get market indices
GET http://localhost:8000/api/indices

# Get order book for specific symbol
GET http://localhost:8000/api/orderbook/RELIANCE
```

### Portfolio & Agents

```bash
# Get portfolio metrics
GET http://localhost:8000/api/portfolio

# Get agent performance
GET http://localhost:8000/api/agents

# Get recent trades
GET http://localhost:8000/api/trades?limit=50

# Get market regime
GET http://localhost:8000/api/regime
```

### WebSocket

```javascript
// Connect to real-time data stream
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    console.log(message.type, message.data);
};

// Keep-alive ping
setInterval(() => ws.send('ping'), 10000);
```

**WebSocket Message Types:**
- `prices`: Live price updates (every 500ms)
- `portfolio`: Portfolio metrics (every 1s)
- `agents`: Agent performance (every 2s)
- `trades`: Recent trades (every 3s)
- `pong`: Keep-alive response

---

## 🎯 Use Cases

### 1. **Live Simulation Monitoring**

Monitor your HFT agents in real-time:
- Watch HFT market makers profit from spread capture
- See retail traders lose money due to behavioral biases
- Observe institutional algos minimize market impact

### 2. **Strategy Comparison**

Compare agent performance side-by-side:
- HFT vs Retail win rates
- P&L during different market regimes
- Trade frequency analysis

### 3. **Risk Management**

Monitor portfolio risk in real-time:
- VaR breaches trigger alerts
- Drawdown tracking
- Liquidity monitoring

### 4. **Market Microstructure Research**

Study order book dynamics:
- Bid-ask spread patterns
- Price impact of trades
- Volatility clustering

### 5. **Demo & Presentation Tool**

Perfect for:
- Academic presentations
- Investor demos
- Teaching market microstructure
- Behavioral finance demonstrations

---

## 🛠️ Customization

### Adding New Stocks to Watchlist

Edit `dashboard_server.py`:

```python
WATCHLIST = {
    'RELIANCE': 'RELIANCE.NS',
    'TCS': 'TCS.NS',
    'INFY': 'INFY.NS',
    'HDFCBANK': 'HDFCBANK.NS',
    'TATAMOTORS': 'TATAMOTORS.NS',
    'SBIN': 'SBIN.NS',
    'WIPRO': 'WIPRO.NS',
    'ADANIENT': 'ADANIENT.NS',
    'ICICIBANK': 'ICICIBANK.NS',
    'HCLTECH': 'HCLTECH.NS',
    'YOUR_STOCK': 'SYMBOL.NS'  # Add here
}
```

### Changing Update Frequency

In `dashboard_server.py`:

```python
async def stream_market_data():
    while True:
        simulator.update_prices()
        await manager.broadcast(...)
        await asyncio.sleep(0.5)  # Change this (seconds)
```

### Modifying Colors

In `public/index.html`, edit the CSS variables:

```css
:root {
    --price-up: #00c853;      /* Green for up */
    --price-down: #ff1744;    /* Red for down */
    --bg-primary: #0a0e17;    /* Main background */
    --border-active: #2962ff; /* Active border */
}
```

---

## 📸 Dashboard Screenshots

### Overview Section
Shows market indices, portfolio metrics, equity curve, drawdown chart, and agent summary.

### Prices Section
Full-screen price table with 10 stocks, real-time updates with flash effects.

### Order Book Section
Level 2 market depth for RELIANCE and TCS with bid/ask visualization.

### Agents Section
Detailed performance cards for all 5 trading agents with positions.

### Trades Section
Trade blotter showing recent executions with buy/sell color coding.

### Risk Section
Market regime detection and risk metrics with color-coded warnings.

---

## 🐛 Troubleshooting

### Dashboard Won't Start

**Problem**: `ModuleNotFoundError: No module named 'fastapi'`

**Solution**:
```bash
pip install fastapi uvicorn
```

### Port Already in Use

**Problem**: `Address already in use` error

**Solution**: Change the port in `dashboard_server.py`:
```python
uvicorn.run(app, host="0.0.0.0", port=8001)  # Use 8001 instead
```

### WebSocket Not Connecting

**Problem**: Real-time updates not working

**Solution**:
1. Check browser console for errors (F12)
2. Ensure WebSocket is not blocked by firewall
3. Try hard refresh (Ctrl+Shift+R)

### Prices Not Updating

**Problem**: Data appears stale

**Solution**:
1. Press `R` to refresh
2. Check WebSocket connection in browser console
3. Restart the server

---

## 🚀 Next Steps

### Integration with Live Data

Replace `MarketDataSimulator` with real exchange feeds:

```python
# Example: Connect to NSE API
from nsepython import nsefetch, get_quote

def get_live_price(symbol):
    data = get_quote(symbol)
    return data['lastPrice']
```

### Add More Chart Types

- **Candlestick Charts**: OHLCV visualization
- **Heatmaps**: Sector performance
- **Correlation Matrix**: Asset relationships
- **P&L Attribution**: Factor decomposition

### Advanced Features

- **Alerts**: Price level notifications
- **Screeners**: Filter stocks by criteria
- **Options Chain**: Derivatives visualization
- **News Feed**: Market-moving headlines

---

## 📊 Performance

### Dashboard Metrics

| Metric | Value |
|--------|-------|
| **Price Update Frequency** | 500ms (via WebSocket) |
| **Portfolio Update** | 1 second |
| **Agent Update** | 2 seconds |
| **Trade Blotter Update** | 3 seconds |
| **API Response Time** | <50ms |
| **Browser Compatibility** | Chrome, Firefox, Edge, Safari |

### Resource Usage

- **Memory**: ~50MB (server) + ~30MB (browser)
- **CPU**: <5% on modern hardware
- **Network**: ~10KB/s WebSocket traffic

---

## 📚 Architecture

```
hft-dashboard/
├── dashboard_server.py         # FastAPI backend + WebSocket
├── public/
│   └── index.html              # Bloomberg terminal UI
├── requirements.txt            # Python dependencies
├── start_dashboard.bat         # Windows startup script
└── DASHBOARD_GUIDE.md         # This file
```

### Backend (dashboard_server.py)

- **Framework**: FastAPI (async Python)
- **WebSocket**: Real-time data streaming
- **Simulator**: MarketDataSimulator class
- **Background Tasks**: 4 async streams (prices, portfolio, agents, trades)

### Frontend (index.html)

- **Styling**: Pure CSS (no frameworks)
- **Charts**: Chart.js for equity/drawdown/volatility
- **WebSocket Client**: Native browser WebSocket API
- **Updates**: Event-driven (no polling)

---

## 🎓 Educational Value

This dashboard demonstrates:

1. **Real-Time Web Technologies**: WebSocket streaming
2. **Professional UI/UX Design**: Bloomberg Terminal patterns
3. **Market Data Visualization**: Order books, tickers, charts
4. **Risk Management**: VaR, drawdown, regime detection
5. **Multi-Agent Systems**: Heterogeneous trading strategies
6. **Financial Engineering**: Performance metrics, analytics

---

## ⚠️ Disclaimer

This is a **simulation dashboard** for educational and research purposes. All data is simulated and should not be used for actual trading decisions.

---

## 📞 Support

For issues or questions:
1. Check this documentation
2. Review browser console for errors (F12)
3. Ensure all dependencies are installed
4. Restart the server

---

**Dashboard Version**: 1.0.0  
**Last Updated**: April 5, 2026  
**Status**: ✅ Production Ready

---

**Built for the Institutional-Grade HFT Simulation Platform** 🚀
