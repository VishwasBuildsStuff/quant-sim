"""
Watchlist Manager for Automated HFT Trading
Manages stock watchlist with live data monitoring
"""

import sys
sys.path.insert(0, r'V:\pylibs')

import json
import time
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from live_data_feed import MultiSourceLiveFeed, LOBSnapshot

logger = logging.getLogger(__name__)


class WatchlistManager:
    """
    Manages multiple stocks with live data monitoring
    
    Features:
    - Multi-symbol watchlist
    - Live data fetching for all symbols
    - Automatic data buffering
    - Callback system for price updates
    """
    
    def __init__(self, 
                 watchlist_path: str = 'watchlist.json',
                 update_interval: int = 10,
                 max_symbols: int = 10):
        
        self.update_interval = update_interval
        self.max_symbols = max_symbols
        
        # Watchlist
        self.watchlist: Dict[str, Dict] = {}
        self.live_feeds: Dict[str, MultiSourceLiveFeed] = {}
        self.price_buffer: Dict[str, List[LOBSnapshot]] = {}
        
        # Callbacks
        self.callbacks: List[Callable] = []
        
        # State
        self.is_running = False
        self.last_update: Dict[str, datetime] = {}
        
        # Load watchlist
        self.load_watchlist(watchlist_path)
    
    def load_watchlist(self, path: str):
        """Load watchlist from JSON file"""
        try:
            if Path(path).exists():
                with open(path, 'r') as f:
                    data = json.load(f)
                
                for symbol_info in data.get('symbols', []):
                    symbol = symbol_info['symbol']
                    self.watchlist[symbol] = {
                        'name': symbol_info.get('name', symbol),
                        'sector': symbol_info.get('sector', 'Unknown'),
                        'max_position': symbol_info.get('max_position', 100),
                        'priority': symbol_info.get('priority', 50),
                        'enabled': symbol_info.get('enabled', True)
                    }
                    self.price_buffer[symbol] = []
                
                logger.info(f"✅ Loaded {len(self.watchlist)} symbols from {path}")
            else:
                # Create default watchlist
                self._create_default_watchlist(path)
        except Exception as e:
            logger.error(f"Error loading watchlist: {e}")
            self._create_default_watchlist(path)
    
    def _create_default_watchlist(self, path: str):
        """Create default NSE watchlist"""
        default_symbols = [
            {'symbol': 'RELIANCE', 'name': 'Reliance Industries', 'sector': 'Energy', 'priority': 90},
            {'symbol': 'TCS', 'name': 'Tata Consultancy Services', 'sector': 'IT', 'priority': 85},
            {'symbol': 'INFY', 'name': 'Infosys', 'sector': 'IT', 'priority': 80},
            {'symbol': 'HDFCBANK', 'name': 'HDFC Bank', 'sector': 'Banking', 'priority': 85},
            {'symbol': 'SBIN', 'name': 'State Bank of India', 'sector': 'Banking', 'priority': 75},
            {'symbol': 'ICICIBANK', 'name': 'ICICI Bank', 'sector': 'Banking', 'priority': 75},
            {'symbol': 'WIPRO', 'name': 'Wipro', 'sector': 'IT', 'priority': 70},
            {'symbol': 'TATAMOTORS', 'name': 'Tata Motors', 'sector': 'Auto', 'priority': 70},
            {'symbol': 'TATASTEEL', 'name': 'Tata Steel', 'sector': 'Metal', 'priority': 65},
            {'symbol': 'HCLTECH', 'name': 'HCL Technologies', 'sector': 'IT', 'priority': 70},
        ]
        
        watchlist_data = {
            'symbols': default_symbols,
            'last_updated': datetime.now().isoformat()
        }
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(watchlist_data, f, indent=2)
        
        logger.info(f"📝 Created default watchlist: {path}")
        
        for sym in default_symbols:
            symbol = sym['symbol']
            self.watchlist[symbol] = {
                'name': sym['name'],
                'sector': sym['sector'],
                'max_position': 100,
                'priority': sym['priority'],
                'enabled': True
            }
            self.price_buffer[symbol] = []
    
    def start_live_feeds(self):
        """Start live data feeds for all enabled symbols"""
        enabled_symbols = [s for s, info in self.watchlist.items() if info['enabled']]
        
        if len(enabled_symbols) > self.max_symbols:
            # Sort by priority and take top N
            enabled_symbols.sort(key=lambda s: self.watchlist[s]['priority'], reverse=True)
            enabled_symbols = enabled_symbols[:self.max_symbols]
            logger.warning(f"⚠️ Too many symbols, monitoring top {self.max_symbols} by priority")
        
        logger.info(f"\n📡 Starting live feeds for {len(enabled_symbols)} symbols...")
        
        for symbol in enabled_symbols:
            try:
                feed = MultiSourceLiveFeed(
                    symbol=symbol,
                    n_levels=10,
                    update_interval=self.update_interval
                )
                
                # Add callback
                def on_snapshot(snapshot, sym=symbol):
                    self.price_buffer[sym].append(snapshot)
                    # Keep only last 200 snapshots
                    if len(self.price_buffer[sym]) > 200:
                        self.price_buffer[sym] = self.price_buffer[sym][-200:]
                    
                    # Notify callbacks
                    for cb in self.callbacks:
                        try:
                            cb(sym, snapshot)
                        except Exception as e:
                            logger.error(f"Callback error: {e}")
                
                feed.add_callback(on_snapshot)
                feed.start()
                
                self.live_feeds[symbol] = feed
                self.last_update[symbol] = datetime.now()
                
                logger.info(f"  ✓ {symbol} - Live feed started")
                time.sleep(0.5)  # Stagger starts
                
            except Exception as e:
                logger.error(f"  ✗ {symbol} - Failed: {e}")
        
        self.is_running = True
        logger.info(f"\n✅ All live feeds started!")
    
    def stop_live_feeds(self):
        """Stop all live data feeds"""
        self.is_running = False
        
        for symbol, feed in self.live_feeds.items():
            try:
                feed.stop()
            except:
                pass
        
        logger.info("⏹️ All live feeds stopped")
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get latest price for a symbol"""
        if symbol in self.price_buffer and self.price_buffer[symbol]:
            return self.price_buffer[symbol][-1].last_trade_price
        return None
    
    def get_price_history(self, symbol: str, n: int = 100) -> Optional[pd.DataFrame]:
        """Get recent price history as DataFrame"""
        if symbol not in self.price_buffer or len(self.price_buffer[symbol]) < 10:
            return None
        
        snapshots = self.price_buffer[symbol][-n:]
        
        data = []
        for snap in snapshots:
            data.append({
                'timestamp': snap.timestamp,
                'price': snap.last_trade_price,
                'volume': snap.last_trade_volume,
                'trade_side': snap.trade_side,
                'bid_price': snap.bid_prices[0],
                'ask_price': snap.ask_prices[0],
                'bid_volume': snap.bid_volumes[0],
                'ask_volume': snap.ask_volumes[0]
            })
        
        return pd.DataFrame(data)
    
    def get_features_for_symbol(self, symbol: str) -> Optional[np.ndarray]:
        """
        Get latest feature vector for a symbol
        Returns feature array or None if insufficient data
        """
        from advanced_features import AdvancedFeatureEngineer
        
        if symbol not in self.price_buffer or len(self.price_buffer[symbol]) < 20:
            return None
        
        # Convert snapshots to DataFrame
        snapshots = self.price_buffer[symbol][-100:]  # Use last 100 for features
        
        data = []
        for snap in snapshots:
            row = {
                'bid_price_1': snap.bid_prices[0],
                'ask_price_1': snap.ask_prices[0],
                'bid_volume_1': snap.bid_volumes[0],
                'ask_volume_1': snap.ask_volumes[0],
                'last_trade_price': snap.last_trade_price,
                'last_trade_volume': snap.last_trade_volume,
                'trade_side': snap.trade_side
            }
            
            # Add more levels
            for i in range(1, 10):
                if i < len(snap.bid_prices):
                    row[f'bid_price_{i+1}'] = snap.bid_prices[i]
                    row[f'ask_price_{i+1}'] = snap.ask_prices[i]
                    row[f'bid_volume_{i+1}'] = snap.bid_volumes[i]
                    row[f'ask_volume_{i+1}'] = snap.ask_volumes[i]
            
            data.append(row)
        
        df = pd.DataFrame(data)
        
        # Engineer features
        try:
            feature_engineer = AdvancedFeatureEngineer()
            features_df, feature_names = feature_engineer.engineer_features(df)
            
            # Return last row
            return features_df.iloc[-1:].values, feature_names
            
        except Exception as e:
            logger.error(f"Feature engineering error for {symbol}: {e}")
            return None
    
    def get_all_signals(self) -> Dict[str, Dict]:
        """
        Get current status for all symbols
        
        Returns:
            Dict of {symbol: {price, change, volume, ...}}
        """
        signals = {}
        
        for symbol in self.watchlist:
            if not self.watchlist[symbol]['enabled']:
                continue
            
            price = self.get_latest_price(symbol)
            
            if price is None:
                signals[symbol] = {
                    'price': 0,
                    'status': 'NO_DATA',
                    'name': self.watchlist[symbol]['name']
                }
                continue
            
            # Calculate change (if we have history)
            history = self.get_price_history(symbol, n=50)
            
            if history is not None and len(history) > 1:
                open_price = history.iloc[0]['price']
                change = price - open_price
                change_pct = (change / open_price) * 100
                avg_volume = history['volume'].mean()
            else:
                change = 0
                change_pct = 0
                avg_volume = 0
            
            signals[symbol] = {
                'price': price,
                'change': change,
                'change_pct': change_pct,
                'volume': avg_volume,
                'status': 'LIVE',
                'name': self.watchlist[symbol]['name'],
                'sector': self.watchlist[symbol]['sector'],
                'buffer_size': len(self.price_buffer.get(symbol, []))
            }
        
        return signals
    
    def add_callback(self, callback: Callable):
        """Add callback for price updates"""
        self.callbacks.append(callback)
    
    def get_watchlist_summary(self) -> str:
        """Get formatted watchlist summary"""
        signals = self.get_all_signals()
        
        lines = []
        lines.append(f"\n{'='*80}")
        lines.append(f"📊 WATCHLIST - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"{'='*80}")
        lines.append(f"{'Symbol':<12} {'Name':<25} {'Price':>10} {'Change':>10} {'Change%':>10} {'Status':<10}")
        lines.append(f"{'-'*80}")
        
        for symbol, info in signals.items():
            if info['status'] == 'NO_DATA':
                lines.append(f"{symbol:<12} {info['name']:<25} {'N/A':>10} {'N/A':>10} {'N/A':>10} {'⏳ Loading':<10}")
            else:
                change_str = f"+{info['change']:.2f}" if info['change'] >= 0 else f"{info['change']:.2f}"
                change_pct_str = f"+{info['change_pct']:.2f}%" if info['change_pct'] >= 0 else f"{info['change_pct']:.2f}%"
                arrow = "📈" if info['change'] >= 0 else "📉"
                lines.append(f"{symbol:<12} {info['name']:<25} {info['price']:>10.2f} {change_str:>10} {change_pct_str:>10} {arrow} LIVE")
        
        lines.append(f"{'='*80}")
        
        return '\n'.join(lines)
