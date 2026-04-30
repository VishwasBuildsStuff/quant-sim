"""
HFT Trading Dashboard - FastAPI Backend
Live NSE data from Yahoo Finance + SQLite database + Customizable watchlist
"""

import os
import sys
import asyncio
import json
import random
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import pandas as pd
import yfinance as yf
try:
    import hft_matching_engine
except ImportError:
    hft_matching_engine = None

# ============================================================
# CONFIGURATION
# ============================================================
DEFAULT_WATCHLIST = {
    'RELIANCE': 'RELIANCE.NS',
    'TCS': 'TCS.NS',
    'INFY': 'INFY.NS',
    'HDFCBANK': 'HDFCBANK.NS',
    'TATAMOTORS': 'TATAMOTORS.NS',
    'SBIN': 'SBIN.NS',
    'WIPRO': 'WIPRO.NS',
    'ADANIENT': 'ADANIENT.NS',
    'ICICIBANK': 'ICICIBANK.NS',
    'HCLTECH': 'HCLTECH.NS'
}

NSE_INDICES = {
    'NIFTY 50': '^NSEI',
    'BANK NIFTY': '^NSEBANK',
    'SENSEX': '^BSESN',
    'NIFTY IT': '^CNXIT'
}

INITIAL_CAPITAL = 10_000_000.0  # ₹1 Cr

# Indian Market Holidays 2026
MARKET_HOLIDAYS = [
    '2026-01-26', '2026-03-02', '2026-03-30', '2026-04-03',
    '2026-04-14', '2026-05-01', '2026-10-02', '2026-11-16', '2026-12-25',
]

# ============================================================
# SQLITE DATABASE
# ============================================================
class TradeDatabase:
    """SQLite database for storing trades, positions, and portfolio history"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), 'trading_data.db')
        self.db_path = db_path
        self.conn = None
        self.init_database()
    
    def init_database(self):
        """Create tables if they don't exist"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()
        
        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                qty INTEGER NOT NULL,
                notional REAL NOT NULL,
                agent TEXT NOT NULL,
                pnl REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Positions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                symbol TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                avg_price REAL DEFAULT 0,
                current_price REAL DEFAULT 0,
                unrealized_pnl REAL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(agent, symbol)
            )
        ''')
        
        # Portfolio history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolio_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                total_equity REAL NOT NULL,
                total_pnl REAL NOT NULL,
                sharpe_ratio REAL,
                max_drawdown REAL,
                var_95 REAL,
                total_trades INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Watchlist table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL UNIQUE,
                is_active INTEGER DEFAULT 1,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert default watchlist if empty
        cursor.execute('SELECT COUNT(*) FROM watchlist')
        if cursor.fetchone()[0] == 0:
            for name, symbol in DEFAULT_WATCHLIST.items():
                cursor.execute(
                    'INSERT INTO watchlist (name, symbol) VALUES (?, ?)',
                    (name, symbol)
                )
        
        self.conn.commit()
        print(f"💾 Database initialized: {self.db_path}")
    
    def insert_trade(self, timestamp, symbol, side, price, qty, notional, agent, pnl=0):
        """Insert a new trade"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO trades (timestamp, symbol, side, price, qty, notional, agent, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (timestamp, symbol, side, price, qty, notional, agent, pnl))
        self.conn.commit()
        return cursor.lastrowid
    
    def update_position(self, agent, symbol, qty_change, price):
        """Update agent position"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO positions (agent, symbol, qty, avg_price, current_price, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(agent, symbol) DO UPDATE SET
                qty = qty + ?,
                current_price = ?,
                avg_price = CASE WHEN qty + ? = 0 THEN 0 
                            ELSE ((avg_price * qty) + (? * ?)) / (qty + ?) END,
                updated_at = CURRENT_TIMESTAMP
        ''', (agent, symbol, qty_change, price, price, qty_change, price, qty_change, price, price, qty_change))
        self.conn.commit()
    
    def get_positions(self, agent=None):
        """Get current positions"""
        cursor = self.conn.cursor()
        if agent:
            cursor.execute('SELECT * FROM positions WHERE agent = ? AND qty != 0', (agent,))
        else:
            cursor.execute('SELECT * FROM positions WHERE qty != 0')
        return [dict(row) for row in cursor.fetchall()]
    
    def get_trades(self, limit=100, agent=None, symbol=None):
        """Get recent trades with optional filters"""
        cursor = self.conn.cursor()
        query = 'SELECT * FROM trades WHERE 1=1'
        params = []
        
        if agent:
            query += ' AND agent = ?'
            params.append(agent)
        if symbol:
            query += ' AND symbol = ?'
            params.append(symbol)
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_portfolio_history(self, limit=1000):
        """Get portfolio history"""
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT * FROM portfolio_history ORDER BY timestamp DESC LIMIT ?',
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def insert_portfolio_snapshot(self, timestamp, total_equity, total_pnl, sharpe_ratio, max_drawdown, var_95, total_trades):
        """Insert portfolio snapshot"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO portfolio_history (timestamp, total_equity, total_pnl, sharpe_ratio, max_drawdown, var_95, total_trades)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (timestamp, total_equity, total_pnl, sharpe_ratio, max_drawdown, var_95, total_trades))
        self.conn.commit()
    
    def get_watchlist(self, active_only=True):
        """Get watchlist"""
        cursor = self.conn.cursor()
        if active_only:
            cursor.execute('SELECT name, symbol, is_active FROM watchlist WHERE is_active = 1 ORDER BY name')
        else:
            cursor.execute('SELECT name, symbol, is_active FROM watchlist ORDER BY name')
        return [dict(row) for row in cursor.fetchall()]
    
    def add_to_watchlist(self, name, symbol):
        """Add stock to watchlist"""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO watchlist (name, symbol, is_active) VALUES (?, ?, 1)',
                (name, symbol)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Update existing
            cursor.execute(
                'UPDATE watchlist SET is_active = 1 WHERE name = ? OR symbol = ?',
                (name, symbol)
            )
            self.conn.commit()
            return True
    
    def remove_from_watchlist(self, name):
        """Remove stock from watchlist"""
        cursor = self.conn.cursor()
        cursor.execute('UPDATE watchlist SET is_active = 0 WHERE name = ?', (name,))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

# ============================================================
# LIVE NSE DATA FETCHER
# ============================================================
class LiveNSEDataFetcher:
    """Fetches live NSE data from Yahoo Finance with smart caching"""
    
    def __init__(self):
        self.cache = {}
        self.last_fetch_time = None
        self.cache_duration = timedelta(seconds=30)  # Cache for 30 seconds
    
    def fetch_prices(self, watchlist_dict):
        """Fetch live prices for all stocks in watchlist"""
        now = datetime.now()
        
        # Check cache
        if (self.last_fetch_time and 
            (now - self.last_fetch_time) < self.cache_duration):
            return self.cache.get('prices', {})
        
        try:
            tickers = list(watchlist_dict.values())
            print(f"\n📡 Fetching live NSE prices from Yahoo Finance...")
            
            data = yf.download(tickers, period='2d', interval='1d', progress=False, group_by='ticker')
            
            prices = {}
            for name, symbol in watchlist_dict.items():
                try:
                    if len(data.columns.levels) > 1:
                        stock_data = data[symbol]
                    else:
                        stock_data = data
                    
                    if len(stock_data) >= 1:
                        close = float(stock_data['Close'].iloc[-1])
                        prev_close = float(stock_data['Close'].iloc[-2]) if len(stock_data) >= 2 else close
                        high = float(stock_data['High'].iloc[-1])
                        low = float(stock_data['Low'].iloc[-1])
                        volume = int(stock_data['Volume'].iloc[-1])
                        
                        prices[name] = {
                            'price': close,
                            'prev_close': prev_close,
                            'high': high,
                            'low': low,
                            'volume': volume,
                            'change': close - prev_close,
                            'change_pct': ((close - prev_close) / prev_close) * 100 if prev_close else 0,
                            'timestamp': now.isoformat()
                        }
                        print(f"  ✓ {name}: ₹{close:.2f} ({((close - prev_close) / prev_close) * 100:+.2f}%)")
                except Exception as e:
                    print(f"  ⚠ Could not fetch {name}: {e}")
            
            self.cache['prices'] = prices
            self.last_fetch_time = now
            print("✅ Live prices fetched!\n")
            return prices
            
        except Exception as e:
            print(f"\n❌ Error fetching live prices: {e}")
            return self.cache.get('prices', {})
    
    def fetch_indices(self):
        """Fetch NSE indices"""
        try:
            indices_data = {}
            for name, symbol in NSE_INDICES.items():
                try:
                    data = yf.download(symbol, period='2d', interval='1d', progress=False)
                    if len(data) >= 2:
                        close = float(data['Close'].iloc[-1])
                        prev_close = float(data['Close'].iloc[-2])
                        indices_data[name] = {
                            'value': close,
                            'change': ((close - prev_close) / prev_close) * 100
                        }
                except:
                    pass
            return indices_data
        except Exception as e:
            print(f"❌ Error fetching indices: {e}")
            return {}
    
    def fetch_intraday_data(self, symbol, period='1d', interval='5m'):
        """Fetch intraday data for charts"""
        try:
            data = yf.download(symbol, period=period, interval=interval, progress=False)
            return data
        except:
            return None

# ============================================================
# MARKET DATA SIMULATOR
# ============================================================
class MarketDataSimulator:
    """Market data with live NSE prices + simulated tick movements"""
    
    def __init__(self, db: TradeDatabase, fetcher: LiveNSEDataFetcher):
        self.db = db
        self.fetcher = fetcher
        self.base_prices = {}
        self.current_prices = {}
        self.previous_prices = {}
        self.price_history = {sym: [] for sym in DEFAULT_WATCHLIST.keys()}
        self.order_books = {}
        self.agent_positions = {}
        self.current_portfolio_value = INITIAL_CAPITAL
        self.live_prices_cache = {}
        
        # Initialize Rust Matching Engine
        self.rust_engine = None
        if hft_matching_engine:
            try:
                self.rust_engine = hft_matching_engine.EngineWrapper()
                print("✅ Rust Matching Engine initialized via PyO3")
            except Exception as e:
                print(f"⚠️ Failed to initialize Rust engine: {e}")
        
        # Load watchlist from database
        self.load_watchlist()
        
        # Fetch live data
        self.fetch_live_data()
        
        # Initialize order books and agents
        for sym in self.base_prices.keys():
            if self.rust_engine:
                self.rust_engine.add_instrument(sym)
            self.order_books[sym] = self._generate_order_book(sym)
        self._init_agent_positions()
    
    def load_watchlist(self):
        """Load watchlist from database"""
        watchlist_items = self.db.get_watchlist()
        self.watchlist = {item['name']: item['symbol'] for item in watchlist_items}
        if not self.watchlist:
            self.watchlist = DEFAULT_WATCHLIST.copy()
    
    def is_market_open(self) -> bool:
        """Check if NSE is currently open (IST timezone)"""
        try:
            import pytz
            ist = pytz.timezone('Asia/Kolkata')
            now = datetime.now(ist)
        except:
            now = datetime.now()
        
        if now.weekday() >= 5:
            return False
        
        today_str = now.strftime('%Y-%m-%d')
        if today_str in MARKET_HOLIDAYS:
            return False
        
        time_now = now.hour * 100 + now.minute
        if time_now < 915 or time_now > 1530:
            return False
        
        return True
    
    def get_next_market_open(self) -> str:
        """Get next market open time"""
        try:
            import pytz
            ist = pytz.timezone('Asia/Kolkata')
            now = datetime.now(ist)
        except:
            now = datetime.now()
        
        if now.weekday() < 5:
            today_str = now.strftime('%Y-%m-%d')
            if today_str not in MARKET_HOLIDAYS and now.hour * 100 + now.minute < 915:
                return f"Today at 9:15 AM IST"
        
        next_day = now + timedelta(days=1)
        for i in range(7):
            if next_day.weekday() < 5:
                day_str = next_day.strftime('%Y-%m-%d')
                if day_str not in MARKET_HOLIDAYS:
                    return f"{next_day.strftime('%A, %B %d')} at 9:15 AM IST"
            next_day += timedelta(days=1)
        
        return "Unknown"
    
    def fetch_live_data(self):
        """Fetch live data from Yahoo Finance"""
        live_prices = self.fetcher.fetch_prices(self.watchlist)
        
        fallback_prices = {
            'RELIANCE': 2450.0, 'TCS': 3850.0, 'INFY': 1520.0,
            'HDFCBANK': 1680.0, 'TATAMOTORS': 920.0, 'SBIN': 620.0,
            'WIPRO': 480.0, 'ADANIENT': 2850.0, 'ICICIBANK': 980.0,
            'HCLTECH': 1380.0
        }
        
        self.live_indices = self.fetcher.fetch_indices()
        
        for name in self.watchlist.keys():
            if name in live_prices:
                lp = live_prices[name]
                self.base_prices[name] = lp['prev_close']
                self.current_prices[name] = lp['price']
                self.previous_prices[name] = lp['prev_close']
            else:
                price = fallback_prices.get(name, 1000.0)
                self.base_prices[name] = price
                self.current_prices[name] = price
                self.previous_prices[name] = price
    
    def refresh_live_data(self):
        """Force refresh live data"""
        self.fetch_live_data()
        for sym in self.current_prices.keys():
            self.order_books[sym] = self._generate_order_book(sym)
    
    def _generate_order_book(self, symbol: str) -> Dict:
        """Generate Level 2 order book using Rust engine or Python fallback"""
        price = self.current_prices.get(symbol, 1000)
        spread = price * 0.0002
        
        if hasattr(self, 'rust_engine') and self.rust_engine:
            # Generate random orders and feed to Rust engine
            for i in range(10):
                bid_price = int((price - (spread * i) - (random.uniform(0.01, 0.05) * price * 0.001)) * 100)
                ask_price = int((price + (spread * i) + (random.uniform(0.01, 0.05) * price * 0.001)) * 100)
                
                try:
                    self.rust_engine.add_order(symbol, "BUY", bid_price, random.randint(100, 5000), 1)
                    self.rust_engine.add_order(symbol, "SELL", ask_price, random.randint(100, 5000), 1)
                except Exception as e:
                    pass
            
            try:
                # Get snapshot from Rust engine
                snapshot = self.rust_engine.get_snapshot(symbol, 10)
                
                bids = [{'price': round(p / 100, 2), 'size': q, 'orders': random.randint(1, 15)} for p, q in snapshot.get('bids', [])]
                asks = [{'price': round(p / 100, 2), 'size': q, 'orders': random.randint(1, 15)} for p, q in snapshot.get('asks', [])]
                
                bids = sorted(bids, key=lambda x: x['price'], reverse=True)
                asks = sorted(asks, key=lambda x: x['price'])
                
                return {
                    'symbol': symbol,
                    'bids': bids,
                    'asks': asks,
                    'spread': round(asks[0]['price'] - bids[0]['price'], 2) if asks and bids else round(spread, 2),
                    'mid_price': round((bids[0]['price'] + asks[0]['price']) / 2, 2) if asks and bids else round(price, 2)
                }
            except Exception as e:
                print(f"Error fetching from rust engine: {e}")
        
        # Fallback to Python simulation
        bids = []
        asks = []
        for i in range(10):
            bid_price = price - (spread * i) - (random.uniform(0.01, 0.05) * price * 0.001)
            ask_price = price + (spread * i) + (random.uniform(0.01, 0.05) * price * 0.001)
            bids.append({'price': round(bid_price, 2), 'size': random.randint(100, 5000), 'orders': random.randint(1, 15)})
            asks.append({'price': round(ask_price, 2), 'size': random.randint(100, 5000), 'orders': random.randint(1, 15)})
        
        return {
            'symbol': symbol,
            'bids': sorted(bids, key=lambda x: x['price'], reverse=True),
            'asks': sorted(asks, key=lambda x: x['price']),
            'spread': round(asks[0]['price'] - bids[0]['price'], 2),
            'mid_price': round((bids[0]['price'] + asks[0]['price']) / 2, 2)
        }
    
    def _init_agent_positions(self):
        """Initialize simulated agent positions"""
        self.agent_positions = {
            'HFT Market Maker': {'type': 'HFT', 'capital': 10_000_000, 'positions': {sym: random.randint(-500, 500) for sym in list(self.base_prices.keys())[:5]}, 'pnl': random.uniform(-50000, 80000), 'trades': random.randint(800, 1500), 'win_rate': random.uniform(58, 72)},
            'HFT Arbitrageur': {'type': 'HFT', 'capital': 5_000_000, 'positions': {sym: random.randint(-200, 200) for sym in list(self.base_prices.keys())[:3]}, 'pnl': random.uniform(-20000, 45000), 'trades': random.randint(400, 900), 'win_rate': random.uniform(62, 78)},
            'Institutional Algo': {'type': 'Institutional', 'capital': 50_000_000, 'positions': {sym: random.randint(1000, 5000) for sym in list(self.base_prices.keys())[:4]}, 'pnl': random.uniform(-100000, 250000), 'trades': random.randint(50, 150), 'win_rate': random.uniform(52, 65)},
            'Semi-Pro Trader': {'type': 'Semi-Pro', 'capital': 2_000_000, 'positions': {sym: random.randint(-100, 300) for sym in list(self.base_prices.keys())[:6]}, 'pnl': random.uniform(-80000, 120000), 'trades': random.randint(100, 250), 'win_rate': random.uniform(45, 60)},
            'Retail Trader': {'type': 'Retail', 'capital': 500_000, 'positions': {sym: random.randint(10, 100) for sym in list(self.base_prices.keys())[:3]}, 'pnl': random.uniform(-150000, 50000), 'trades': random.randint(30, 80), 'win_rate': random.uniform(35, 52), 'fear_greed_index': random.uniform(20, 80)}
        }
    
    def update_prices(self):
        """Simulate small tick movements around live base"""
        self.previous_prices = self.current_prices.copy()
        
        for sym in self.current_prices.keys():
            base = self.base_prices.get(sym, self.current_prices[sym])
            if base == 0:
                base = self.current_prices[sym]
            
            drift = random.gauss(0, 0.0003)
            mean_reversion = (base - self.current_prices[sym]) / base * 0.003 if base > 0 else 0
            change = drift + mean_reversion
            self.current_prices[sym] *= (1 + change)
            
            self.price_history[sym].append({'timestamp': datetime.now().isoformat(), 'price': round(self.current_prices[sym], 2)})
            if len(self.price_history[sym]) > 1000:
                self.price_history[sym] = self.price_history[sym][-1000:]
        
        for sym in self.current_prices.keys():
            self.order_books[sym] = self._generate_order_book(sym)
    
    def get_price_data(self) -> List[Dict]:
        """Get current prices"""
        data = []
        for sym, price in self.current_prices.items():
            prev = self.previous_prices.get(sym, price)
            change = price - prev
            change_pct = (change / prev) * 100 if prev else 0
            
            live = self.live_prices_cache.get(sym, {})
            day_high = max([p['price'] for p in self.price_history[sym][-100:]] + [price])
            day_low = min([p['price'] for p in self.price_history[sym][-100:]] + [price])
            
            data.append({
                'symbol': sym, 'price': round(price, 2), 'change': round(change, 2),
                'change_pct': round(change_pct, 2), 'high': round(day_high, 2),
                'low': round(day_low, 2), 'volume': live.get('volume', random.randint(100000, 5000000)),
                'timestamp': datetime.now().isoformat()
            })
        return data
    
    def get_indices(self) -> List[Dict]:
        """Get NSE indices"""
        if hasattr(self, 'live_indices') and self.live_indices:
            return [{'name': name, 'value': round(data.get('value', 0), 2), 'change': round(data.get('change', 0), 2)} for name, data in self.live_indices.items()]
        return [
            {'name': 'NIFTY 50', 'value': 22045.30, 'change': 0.45},
            {'name': 'BANK NIFTY', 'value': 48123.45, 'change': -0.32},
            {'name': 'SENSEX', 'value': 72845.20, 'change': 0.28},
            {'name': 'NIFTY IT', 'value': 33567.80, 'change': 0.67}
        ]
    
    def get_order_book(self, symbol: str) -> Dict:
        return self.order_books.get(symbol, {})
    
    def get_agents_performance(self) -> List[Dict]:
        """Get agent performance"""
        data = []
        for name, agent in self.agent_positions.items():
            agent['pnl'] += random.uniform(-500, 800)
            agent['trades'] += random.randint(0, 5)
            data.append({
                'name': name, 'type': agent['type'], 'capital': agent['capital'],
                'pnl': round(agent['pnl'], 2), 'pnl_pct': round((agent['pnl'] / agent['capital']) * 100, 2),
                'trades': agent['trades'], 'win_rate': round(agent['win_rate'], 2),
                'positions': agent['positions'], 'fear_greed_index': agent.get('fear_greed_index', None)
            })
        return data
    
    def get_portfolio_metrics(self) -> Dict:
        """Get portfolio metrics"""
        total_pnl = sum(a['pnl'] for a in self.agent_positions.values())
        self.current_portfolio_value = INITIAL_CAPITAL + total_pnl
        
        returns = [random.gauss(0.001, 0.02) for _ in range(100)]
        sharpe = round(np.mean(returns) / np.std(returns) * np.sqrt(252), 2)
        sortino = round(np.mean(returns) / np.std([r for r in returns if r < 0]) * np.sqrt(252), 2)
        
        metrics = {
            'total_equity': round(self.current_portfolio_value, 2),
            'total_pnl': round(total_pnl, 2),
            'total_pnl_pct': round((total_pnl / INITIAL_CAPITAL) * 100, 2),
            'sharpe_ratio': sharpe, 'sortino_ratio': sortino,
            'max_drawdown': round(random.uniform(-15, -2), 2),
            'var_95': round(random.uniform(-2, -0.5), 2),
            'cvar_95': round(random.uniform(-3, -1), 2),
            'total_trades': sum(a['trades'] for a in self.agent_positions.values()),
            'avg_win_rate': round(np.mean([a['win_rate'] for a in self.agent_positions.values()]), 2),
            'timestamp': datetime.now().isoformat()
        }
        
        # Save to database every minute
        if random.random() < 0.05:  # ~5% chance each call
            self.db.insert_portfolio_snapshot(
                metrics['timestamp'], metrics['total_equity'], metrics['total_pnl'],
                metrics['sharpe_ratio'], metrics['max_drawdown'], metrics['var_95'],
                metrics['total_trades']
            )
        
        return metrics
    
    def generate_and_store_trades(self, limit: int = 50) -> List[Dict]:
        """Generate trades and store in database"""
        trades = []
        symbols = list(self.current_prices.keys())
        agents = list(self.agent_positions.keys())
        
        for _ in range(limit):
            sym = random.choice(symbols)
            agent = random.choice(agents)
            side = random.choice(['BUY', 'SELL'])
            price = self.current_prices[sym] * (1 + random.uniform(-0.001, 0.001))
            qty = random.randint(10, 1000)
            notional = round(price * qty, 2)
            pnl = random.uniform(-500, 800)
            
            trade = {
                'timestamp': datetime.now().isoformat(), 'symbol': sym, 'side': side,
                'price': round(price, 2), 'qty': qty, 'notional': notional, 'agent': agent, 'pnl': round(pnl, 2)
            }
            trades.append(trade)
            
            # Store in database
            self.db.insert_trade(
                trade['timestamp'], trade['symbol'], trade['side'],
                trade['price'], trade['qty'], trade['notional'],
                trade['agent'], trade['pnl']
            )
            
            # Update positions
            qty_change = qty if side == 'BUY' else -qty
            self.db.update_position(agent, sym, qty_change, price)
            
            # Update agent positions in memory
            if agent in self.agent_positions and sym in self.agent_positions[agent]['positions']:
                self.agent_positions[agent]['positions'][sym] += qty_change
        
        return sorted(trades, key=lambda x: x['timestamp'], reverse=True)
    
    def get_market_regime(self) -> Dict:
        """Get market regime"""
        return {
            'regime': random.choice(['Risk-On', 'Risk-Off', 'High Volatility', 'Low Volatility', 'Trending', 'Range-bound']),
            'volatility': round(random.uniform(12, 35), 2),
            'trend_strength': round(random.uniform(-1, 1), 2),
            'liquidity_score': round(random.uniform(40, 95), 2),
            'correlation_breakdown': random.choice([True, False]),
            'timestamp': datetime.now().isoformat()
        }
    
    # Watchlist management
    def get_watchlist(self):
        """Get watchlist from database"""
        return self.db.get_watchlist()
    
    def add_to_watchlist(self, name: str, symbol: str) -> bool:
        """Add stock to watchlist"""
        success = self.db.add_to_watchlist(name, symbol)
        if success:
            self.load_watchlist()
            if name not in self.base_prices:
                # Fetch live price for new stock
                live = self.fetcher.fetch_prices({name: symbol})
                if name in live:
                    self.base_prices[name] = live[name]['prev_close']
                    self.current_prices[name] = live[name]['price']
                    self.previous_prices[name] = live[name]['prev_close']
                    self.price_history[name] = []
                    if hasattr(self, 'rust_engine') and self.rust_engine:
                        self.rust_engine.add_instrument(name)
                    self.order_books[name] = self._generate_order_book(name)
        return success
    
    def remove_from_watchlist(self, name: str) -> bool:
        """Remove stock from watchlist"""
        success = self.db.remove_from_watchlist(name)
        if success:
            self.load_watchlist()
        return success

# ============================================================
# FASTAPI APP
# ============================================================
app = FastAPI(title="HFT Trading Dashboard", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database and fetcher
db = TradeDatabase()
fetcher = LiveNSEDataFetcher()
simulator = MarketDataSimulator(db, fetcher)

# ============================================================
# WEBSOCKET MANAGER
# ============================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# ============================================================
# FASTAPI ROUTES
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    with open(os.path.join(os.path.dirname(__file__), 'public', 'index.html'), 'r', encoding='utf-8') as f:
        return f.read()

@app.get("/api/prices")
async def get_prices():
    return simulator.get_price_data()

@app.get("/api/indices")
async def get_indices():
    return simulator.get_indices()

@app.get("/api/orderbook/{symbol}")
async def get_orderbook(symbol: str):
    return simulator.get_order_book(symbol)

@app.get("/api/agents")
async def get_agents():
    return simulator.get_agents_performance()

@app.get("/api/portfolio")
async def get_portfolio():
    return simulator.get_portfolio_metrics()

@app.get("/api/trades")
async def get_trades(limit: int = 50):
    # Return from database if available, else generate
    db_trades = db.get_trades(limit=limit)
    if db_trades:
        return db_trades
    return simulator.generate_and_store_trades(limit)

@app.get("/api/regime")
async def get_regime():
    return simulator.get_market_regime()

@app.get("/api/market-status")
async def get_market_status():
    is_open = simulator.is_market_open()
    next_open = simulator.get_next_market_open()
    return {'is_open': is_open, 'next_open_time': next_open, 'current_time': datetime.now().isoformat()}

# Watchlist Management APIs
@app.get("/api/watchlist")
async def get_watchlist():
    """Get current watchlist"""
    return simulator.get_watchlist()

@app.post("/api/watchlist")
async def add_to_watchlist(name: str, symbol: str):
    """Add stock to watchlist"""
    if not name or not symbol:
        raise HTTPException(status_code=400, detail="Name and symbol required")
    
    success = simulator.add_to_watchlist(name.upper(), symbol.upper())
    if success:
        return {"message": f"Added {name} to watchlist", "name": name.upper(), "symbol": symbol.upper()}
    raise HTTPException(status_code=500, detail="Failed to add to watchlist")

@app.delete("/api/watchlist/{name}")
async def remove_from_watchlist(name: str):
    """Remove stock from watchlist"""
    success = simulator.remove_from_watchlist(name)
    if success:
        return {"message": f"Removed {name} from watchlist"}
    raise HTTPException(status_code=404, detail=f"Stock {name} not found")

@app.post("/api/watchlist/refresh")
async def refresh_live_data():
    """Force refresh live data"""
    simulator.refresh_live_data()
    return {"message": "Live data refreshed"}

# Database queries
@app.get("/api/db/positions")
async def get_positions(agent: str = None):
    """Get positions from database"""
    return db.get_positions(agent)

@app.get("/api/db/portfolio-history")
async def get_portfolio_history(limit: int = 1000):
    """Get portfolio history"""
    return db.get_portfolio_history(limit)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ============================================================
# BACKGROUND TASKS
# ============================================================
async def stream_market_data():
    while True:
        simulator.update_prices()
        await manager.broadcast({"type": "prices", "data": simulator.get_price_data(), "timestamp": datetime.now().isoformat()})
        await asyncio.sleep(0.5)

async def stream_order_books():
    while True:
        # Stream order books for RELIANCE and TCS as an example
        for symbol in ['RELIANCE', 'TCS']:
            ob = simulator.get_order_book(symbol)
            if ob:
                await manager.broadcast({
                    "type": "orderbook",
                    "symbol": symbol,
                    "data": ob,
                    "timestamp": datetime.now().isoformat()
                })
        # If we want to stream high frequency, we do it fast
        await asyncio.sleep(0.2)

async def stream_portfolio():
    while True:
        await manager.broadcast({"type": "portfolio", "data": simulator.get_portfolio_metrics(), "timestamp": datetime.now().isoformat()})
        await asyncio.sleep(1.0)

async def stream_agents():
    while True:
        await manager.broadcast({"type": "agents", "data": simulator.get_agents_performance(), "timestamp": datetime.now().isoformat()})
        await asyncio.sleep(2.0)

async def stream_trades():
    while True:
        trades = simulator.generate_and_store_trades(5)
        await manager.broadcast({"type": "trades", "data": trades, "timestamp": datetime.now().isoformat()})
        await asyncio.sleep(5.0)

@app.on_event("startup")
async def startup_event():
    print("\n" + "=" * 60)
    print("🗄️  Database Features:")
    print("  ✓ Trades stored in SQLite")
    print("  ✓ Positions tracked per agent")
    print("  ✓ Portfolio history saved")
    print("  ✓ Customizable watchlist")
    print("=" * 60)
    
    asyncio.create_task(stream_market_data())
    asyncio.create_task(stream_order_books())
    asyncio.create_task(stream_portfolio())
    asyncio.create_task(stream_agents())
    asyncio.create_task(stream_trades())

@app.on_event("shutdown")
async def shutdown_event():
    db.close()

# ============================================================
# RUN SERVER
# ============================================================
if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("🚀 HFT Trading Dashboard v2.0")
    print("=" * 60)
    print("🌐 Dashboard URL: http://localhost:8000")
    print("📊 WebSocket: ws://localhost:8000/ws")
    print("=" * 60)
    print("✨ Features:")
    print("  ✓ Live NSE prices from Yahoo Finance")
    print("  ✓ SQLite database for trades & positions")
    print("  ✓ Customizable watchlist")
    print("  ✓ Market holiday detection")
    print("=" * 60)
    print("⌨️ Keyboard Shortcuts:")
    print("  1 - Overview | 2 - Prices | 3 - Order Book")
    print("  4 - Agents | 5 - Trades | 6 - Risk")
    print("  R - Refresh | F - Fullscreen | W - Watchlist")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
