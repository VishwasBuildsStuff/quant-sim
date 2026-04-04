"""
Tick Database & Replay Engine
Stores 1-minute tick data locally in SQLite for instant backtesting.
Replays historical data bar-by-bar as if it were live.
"""

import sqlite3
import os
import pandas as pd
import numpy as np
from datetime import datetime
import yfinance as yf

DB_PATH = 'tick_database.db'

class TickDatabase:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self._create_tables()
        print(f"💾 Tick Database Initialized: {db_path}")

    def _create_tables(self):
        """Create tables if they don't exist"""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS ticks (
                symbol TEXT,
                timestamp TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                PRIMARY KEY (symbol, timestamp)
            )
        ''')
        self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_symbol_time 
            ON ticks (symbol, timestamp)
        ''')
        self.conn.commit()

    def fetch_and_store(self, symbol, period='60d', interval='1m'):
        """
        Download data from Yahoo Finance and store in DB
        """
        try:
            print(f"📥 Downloading {symbol} ({period}, {interval})...")
            df = yf.download(symbol, period=period, interval=interval, progress=False)
            
            if df.empty:
                print(f"⚠️ No data for {symbol}")
                return 0
                
            # Flatten columns if multi-index
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = ['_'.join(col).strip() for col in df.columns]
                df = df.rename(columns={
                    'Open_': 'open', 'High_': 'high', 
                    'Low_': 'low', 'Close_': 'close', 'Volume_': 'volume'
                })
            else:
                df.columns = [c.lower() for c in df.columns]
                
            rows_inserted = 0
            
            for idx, row in df.iterrows():
                ts = idx.strftime('%Y-%m-%d %H:%M:%S')
                self.cursor.execute('''
                    INSERT OR REPLACE INTO ticks 
                    (symbol, timestamp, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol, ts,
                    float(row.get('open', 0)),
                    float(row.get('high', 0)),
                    float(row.get('low', 0)),
                    float(row.get('close', 0)),
                    int(row.get('volume', 0))
                ))
                rows_inserted += 1
                
            self.conn.commit()
            print(f"✅ Stored {rows_inserted} bars for {symbol}")
            return rows_inserted
            
        except Exception as e:
            print(f"❌ Error storing data for {symbol}: {e}")
            return 0

    def get_historical_data(self, symbol, start_date, end_date):
        """Fetch stored data for backtesting"""
        query = '''
            SELECT timestamp, open, high, low, close, volume
            FROM ticks
            WHERE symbol = ? AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp
        '''
        df = pd.read_sql_query(query, self.conn, params=(symbol, start_date, end_date))
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        return df

    def count_records(self, symbol=None):
        """Count total stored ticks"""
        if symbol:
            self.cursor.execute('SELECT COUNT(*) FROM ticks WHERE symbol = ?', (symbol,))
        else:
            self.cursor.execute('SELECT COUNT(*) FROM ticks')
        return self.cursor.fetchone()[0]


class MarketReplayer:
    """
    Replays historical data bar-by-bar to simulate live market.
    Feeds data to strategies exactly as if they were running live.
    """
    
    def __init__(self, db_path=DB_PATH):
        self.db = TickDatabase(db_path)
        self.current_bar = None
        self.is_running = False
        
    def replay(self, symbol, start_date, end_date, callback):
        """
        Replay market data and call callback(bar) for each tick
        
        Args:
            symbol: Stock symbol
            start_date: 'YYYY-MM-DD HH:MM'
            end_date: 'YYYY-MM-DD HH:MM'
            callback: Function to call with each bar (receives dict)
        """
        print(f"🔄 Replaying {symbol} from {start_date} to {end_date}...")
        
        df = self.db.get_historical_data(symbol, start_date, end_date)
        
        if df.empty:
            print("⚠️ No data found for replay")
            return
            
        self.is_running = True
        total_bars = len(df)
        
        for i, (ts, row) in enumerate(df.iterrows()):
            bar = {
                'timestamp': ts,
                'symbol': symbol,
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume'],
                'bar_index': i,
                'total_bars': total_bars
            }
            
            callback(bar)
            
            if not self.is_running:
                print("⏹️ Replay stopped by user")
                break
                
        print(f"✅ Replay complete: {total_bars} bars processed")
        
    def stop(self):
        self.is_running = False

    def run_backtest_on_stored_data(self, symbol, strategy, start_capital=1_000_000):
        """
        Run a full backtest using stored database data (much faster than live fetch)
        """
        from backtesting_engine import BacktestEngine
        
        # Fetch all data from DB
        # For 1-min data, get last 60 days
        df = self.db.get_historical_data(symbol, '2020-01-01', '2030-12-31')
        
        if df.empty:
            print("No data in database. Run fetch_and_store first.")
            return None
            
        engine = BacktestEngine(initial_capital=start_capital)
        engine.add_strategy(strategy)
        engine.load_price_data(
            symbol,
            df.index.tolist(),
            df['close'].values,
            df['high'].values if 'high' in df.columns else None,
            df['low'].values if 'low' in df.columns else None,
            df['volume'].values if 'volume' in df.columns else None
        )
        
        return engine.run_backtest()
