"""
HFT Mobile Dashboard Server
Flask-based web API + Mobile-responsive frontend
Serves: Live Prices, Paper Trader Signals, Portfolio, Market Insights
"""

import os
import sys
sys.path.insert(0, os.getcwd())

import yfinance as yf
import pandas as pd
import numpy as np
import time  # Added for delays
from flask import Flask, jsonify, render_template_string
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================
WATCHLIST = {
    'RELIANCE': 'RELIANCE.NS',
    'TCS': 'TCS.NS',
    'INFY': 'INFY.NS',
    'HDFCBANK': 'HDFCBANK.NS',
    'TTM': 'TTM.NS',
    'SBIN': 'SBIN.NS',
    'WIPRO': 'WIPRO.NS',
    'ADANIENT': 'ADANIENT.NS'
}

NSE_GAUGES = {
    'NIFTY50': '^NSEI',
    'BANKNIFTY': '^NSEBANK',
    'SENSEX': '^BSESN'
}

LOG_FILE = 'paper_trading_log.csv'
INITIAL_CAPITAL = 1_000_000.0

# ============================================================
# FLASK APP
# ============================================================
app = Flask(__name__)

def get_market_overview():
    """Fetch NSE index status"""
    data = {}
    for name, sym in NSE_GAUGES.items():
        try:
            df = yf.download(sym, period='2d', interval='1d', progress=False)
            if len(df) >= 2:
                # Convert to float explicitly
                close = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2])
                change = ((close - prev) / prev) * 100
                data[name] = {'value': round(close, 2), 'change': round(change, 2)}
            else:
                data[name] = {'value': 'N/A', 'change': 0.0}
        except Exception as e:
            print(f"Warning: Could not fetch {name}: {e}")
            data[name] = {'value': 'N/A', 'change': 0.0}
    return data

def get_live_prices():
    """Fetch current prices for watchlist"""
    data = []
    # Fix TTM -> TATAMOTORS
    safe_watchlist = {k: v if 'TTM' not in v else 'TATAMOTORS.NS' for k, v in WATCHLIST.items()}

    for name, sym in safe_watchlist.items():
        try:
            df = yf.download(sym, period='2d', interval='1d', progress=False)
            if len(df) >= 2:
                close = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2])
                change = ((close - prev) / prev) * 100

                # Fallback values
                day_high = close * 1.01
                day_low = close * 0.99

                try:
                    info = yf.Ticker(sym).fast_info
                    if info.last_price:
                        close = float(info.last_price)
                    if info.day_high:
                        day_high = float(info.day_high)
                    if info.day_low:
                        day_low = float(info.day_low)
                except:
                    pass  # Use fallback if fast_info fails

                data.append({
                    'name': name,
                    'price': round(close, 2),
                    'change': round(change, 2),
                    'high': round(day_high, 2),
                    'low': round(day_low, 2)
                })
            time.sleep(0.5)  # Add delay to avoid Yahoo rate limiting
        except Exception as e:
            print(f"Warning: Could not fetch {name}: {e}")

    return data

def get_signals():
    """Read paper trading log"""
    if not os.path.exists(LOG_FILE):
        return []

    df = pd.read_csv(LOG_FILE)
    df = df.sort_values('Time', ascending=False)
    return df.head(20).to_dict('records')

def get_portfolio():
    """Calculate current paper portfolio value"""
    if not os.path.exists(LOG_FILE):
        return {'equity': INITIAL_CAPITAL, 'pnl': 0.0, 'pnl_pct': 0.0, 'cash': INITIAL_CAPITAL}

    df = pd.read_csv(LOG_FILE)
    if df.empty:
        return {'equity': INITIAL_CAPITAL, 'pnl': 0.0, 'pnl_pct': 0.0, 'cash': INITIAL_CAPITAL}

    last_cash = df.iloc[-1]['Cash_Balance']
    total_pnl = df['PnL'].sum()

    # Get current holdings
    current_holdings = {}
    for _, row in df.iterrows():
        sym = row['Symbol'] + '.NS'
        if row['Action'] == 'BUY':
            current_holdings[row['Symbol']] = row['Qty']
        elif row['Action'] == 'SELL':
            if row['Symbol'] in current_holdings:
                current_holdings[row['Symbol']] -= row['Qty']
                if current_holdings[row['Symbol']] <= 0:
                    del current_holdings[row['Symbol']]

    # Calculate holding value
    holding_value = 0.0
    for sym_name, qty in current_holdings.items():
        try:
            price = yf.Ticker(sym_name).fast_info.last_price
            holding_value += price * qty
        except:
            pass

    total_equity = last_cash + holding_value
    pnl = total_equity - INITIAL_CAPITAL
    pnl_pct = (pnl / INITIAL_CAPITAL) * 100

    return {
        'equity': round(total_equity, 2),
        'pnl': round(pnl, 2),
        'pnl_pct': round(pnl_pct, 2),
        'cash': round(last_cash, 2),
        'holdings_value': round(holding_value, 2)
    }

def get_market_insights():
    """Top gainers and losers in NSE"""
    try:
        stocks = list(WATCHLIST.values())
        data = []

        for sym in stocks:
            try:
                # Skip TTM, use TATAMOTORS
                if 'TTM' in sym:
                    sym = 'TATAMOTORS.NS'

                df = yf.download(sym, period='2d', interval='1d', progress=False)
                if len(df) >= 2:
                    close = float(df['Close'].iloc[-1])
                    prev = float(df['Close'].iloc[-2])
                    change = ((close - prev) / prev) * 100
                    name = sym.replace('.NS', '')
                    data.append({'name': name, 'change': round(change, 2)})
                time.sleep(0.3)  # Rate limit delay
            except:
                pass

        data.sort(key=lambda x: x['change'], reverse=True)

        return {
            'top_gainers': data[:3] if data else [],
            'top_losers': data[-3:][::-1] if data else [],
            'market_status': 'CLOSED'  # Default to closed, will update on market hours
        }
    except Exception as e:
        print(f"Error fetching insights: {e}")
        return {'top_gainers': [], 'top_losers': [], 'market_status': 'CLOSED'}

# ============================================================
# MOBILE FRONTEND TEMPLATE
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>HFT Mobile Dashboard</title>
    <style>
        :root {
            --bg: #0a0e17;
            --card: #141926;
            --green: #00c853;
            --red: #ff1744;
            --text: #ffffff;
            --sub: #8b9bb4;
            --accent: #2962ff;
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            background: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            padding-bottom: 70px;
        }
        
        /* Header */
        .header {
            background: linear-gradient(135deg, #1a237e, #0d47a1);
            padding: 20px;
            text-align: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .header h1 { font-size: 1.2em; font-weight: 600; }
        .header .status { font-size: 0.8em; opacity: 0.8; margin-top: 4px; }
        
        /* Cards */
        .card {
            background: var(--card);
            margin: 12px;
            padding: 16px;
            border-radius: 16px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .card-title {
            font-size: 0.85em;
            color: var(--sub);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        /* Portfolio Card */
        .portfolio-value { font-size: 2.2em; font-weight: bold; }
        .portfolio-pnl { font-size: 1.1em; margin-top: 4px; }
        .positive { color: var(--green); }
        .negative { color: var(--red); }
        
        /* Market Indices */
        .indices {
            display: flex;
            gap: 10px;
            overflow-x: auto;
            padding: 4px;
        }
        .index-chip {
            background: #1e2738;
            padding: 10px 14px;
            border-radius: 12px;
            min-width: 110px;
            text-align: center;
        }
        .index-name { font-size: 0.75em; color: var(--sub); }
        .index-val { font-size: 1.1em; font-weight: 600; margin: 4px 0; }
        
        /* Stock List */
        .stock-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid #1e2738;
        }
        .stock-item:last-child { border-bottom: none; }
        .stock-name { font-weight: 600; }
        .stock-meta { font-size: 0.8em; color: var(--sub); }
        .stock-price { text-align: right; }
        
        /* Signals */
        .signal-item {
            display: flex;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #1e2738;
        }
        .signal-icon {
            font-size: 1.5em;
            margin-right: 12px;
        }
        .signal-details { flex: 1; }
        .signal-time { font-size: 0.75em; color: var(--sub); }
        
        /* Navigation */
        .nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--card);
            display: flex;
            justify-content: space-around;
            padding: 12px 0;
            border-top: 1px solid #1e2738;
            z-index: 100;
        }
        .nav-item {
            text-align: center;
            font-size: 0.7em;
            color: var(--sub);
            cursor: pointer;
        }
        .nav-item.active { color: var(--accent); }
        .nav-icon { font-size: 1.4em; margin-bottom: 4px; }
        
        /* Hide/Show Sections */
        .section { display: none; }
        .section.active { display: block; }
        
        /* Loading */
        .loading { text-align: center; padding: 40px; color: var(--sub); }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 HFT Dashboard</h1>
        <div class="status" id="marketStatus">Loading...</div>
    </div>

    <!-- PORTFOLIO SECTION -->
    <div id="sec-portfolio" class="section active">
        <div class="card">
            <div class="card-title">Portfolio Equity</div>
            <div class="portfolio-value" id="equity">₹1,000,000</div>
            <div class="portfolio-pnl" id="pnl">₹0.00 (0.00%)</div>
        </div>
        
        <div class="card">
            <div class="card-title">Market Indices</div>
            <div class="indices" id="indices">
                <!-- Filled via JS -->
            </div>
        </div>
        
        <div class="card">
            <div class="card-title">Today's Insights</div>
            <div id="insights">Loading...</div>
        </div>
    </div>

    <!-- PRICES SECTION -->
    <div id="sec-prices" class="section">
        <div class="card">
            <div class="card-title">Watchlist Prices</div>
            <div id="stockList">Loading...</div>
        </div>
    </div>

    <!-- SIGNALS SECTION -->
    <div id="sec-signals" class="section">
        <div class="card">
            <div class="card-title">Trading Signals</div>
            <div id="signalList">Loading...</div>
        </div>
    </div>

    <!-- BOTTOM NAV -->
    <div class="nav">
        <div class="nav-item active" onclick="showSection('portfolio')">
            <div class="nav-icon">📊</div>
            Portfolio
        </div>
        <div class="nav-item" onclick="showSection('prices')">
            <div class="nav-icon">💹</div>
            Prices
        </div>
        <div class="nav-item" onclick="showSection('signals')">
            <div class="nav-icon">📡</div>
            Signals
        </div>
    </div>

    <script>
        function showSection(id) {
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('sec-' + id).classList.add('active');
            event.currentTarget.classList.add('active');
        }

        function updateDashboard() {
            fetch('/api/portfolio')
                .then(r => r.json())
                .then(d => {
                    document.getElementById('equity').textContent = '₹' + d.equity.toLocaleString();
                    const pnlEl = document.getElementById('pnl');
                    const sign = d.pnl >= 0 ? '+' : '';
                    pnlEl.textContent = sign + '₹' + d.pnl.toFixed(2) + ' (' + sign + d.pnl_pct.toFixed(2) + '%)';
                    pnlEl.className = 'portfolio-pnl ' + (d.pnl >= 0 ? 'positive' : 'negative');
                });

            fetch('/api/market')
                .then(r => r.json())
                .then(d => {
                    let html = '';
                    for(let [name, val] of Object.entries(d.indices)) {
                        const cls = val.change >= 0 ? 'positive' : 'negative';
                        const sign = val.change >= 0 ? '+' : '';
                        html += '<div class="index-chip">' +
                                '<div class="index-name">' + name + '</div>' +
                                '<div class="index-val">' + val.value + '</div>' +
                                '<div class="' + cls + '">' + sign + val.change.toFixed(2) + '%</div></div>';
                    }
                    document.getElementById('indices').innerHTML = html;
                    document.getElementById('marketStatus').textContent = 'Market Status: ' + d.status;
                });

            fetch('/api/prices')
                .then(r => r.json())
                .then(d => {
                    let html = '';
                    d.forEach(s => {
                        const cls = s.change >= 0 ? 'positive' : 'negative';
                        const sign = s.change >= 0 ? '+' : '';
                        html += '<div class="stock-item">' +
                                '<div><div class="stock-name">' + s.name + '</div>' +
                                '<div class="stock-meta">H: ' + s.high + ' L: ' + s.low + '</div></div>' +
                                '<div class="stock-price"><div>₹' + s.price + '</div>' +
                                '<div class="' + cls + '">' + sign + s.change.toFixed(2) + '%</div></div></div>';
                    });
                    document.getElementById('stockList').innerHTML = html;
                });

            fetch('/api/signals')
                .then(r => r.json())
                .then(d => {
                    let html = d.length === 0 ? '<div class="loading">No signals yet</div>' : '';
                    d.forEach(s => {
                        const icon = s.Action === 'BUY' ? '🟢' : '🔴';
                        html += '<div class="signal-item"><div class="signal-icon">' + icon + '</div>' +
                                '<div class="signal-details"><div><b>' + s.Action + ' ' + s.Symbol + '</b></div>' +
                                '<div>₹' + s.Price + ' | Qty: ' + s.Qty + '</div></div>' +
                                '<div class="signal-time">' + s.Time.split(' ')[1].substring(0,5) + '</div></div>';
                    });
                    document.getElementById('signalList').innerHTML = html;
                });
                
            fetch('/api/insights')
                .then(r => r.json())
                .then(d => {
                    let html = '<div><b>📈 Top Gainers:</b> ';
                    d.top_gainers.forEach(g => html += g.name + ' (+' + g.change.toFixed(1) + '%) ');
                    html += '</div><div style="margin-top:8px"><b>📉 Top Losers:</b> ';
                    d.top_losers.forEach(l => html += l.name + ' (' + l.change.toFixed(1) + '%) ');
                    html += '</div>';
                    document.getElementById('insights').innerHTML = html;
                });
        }

        // Initial load
        updateDashboard();
        // Auto-refresh every 60 seconds
        setInterval(updateDashboard, 60000);
    </script>
</body>
</html>
"""

# ============================================================
# API ROUTES
# ============================================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/portfolio')
def api_portfolio():
    return jsonify(get_portfolio())

@app.route('/api/market')
def api_market():
    return jsonify({
        'indices': get_market_overview(),
        'status': get_market_insights()['market_status']
    })

@app.route('/api/prices')
def api_prices():
    return jsonify(get_live_prices())

@app.route('/api/signals')
def api_signals():
    return jsonify(get_signals())

@app.route('/api/insights')
def api_insights():
    return jsonify(get_market_insights())

# ============================================================
# RUN SERVER
# ============================================================
if __name__ == '__main__':
    print("📱 Starting Mobile Dashboard Server...")
    print("🌐 Open on your mobile: http://YOUR_LOCAL_IP:5000")
    print("   (Make sure your phone is on the same WiFi)")
    app.run(host='0.0.0.0', port=5000, debug=False)