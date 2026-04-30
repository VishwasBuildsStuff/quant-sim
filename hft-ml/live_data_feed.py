"""
Live NSE Data Feed System
Provides real-time market data from NSE via multiple sources
"""

import sys
sys.path.insert(0, r'V:\pylibs')

import time
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue, Empty
import threading
import requests
from collections import deque

# Try to import optional dependencies
try:
    from kiteconnect import KiteConnect, KiteTicker
    HAS_ZERODHA = True
except ImportError:
    HAS_ZERODHA = False

try:
    import yfinance as yf
    HAS_YAHOO = True
except ImportError:
    HAS_YAHOO = False

try:
    from nsepython import nse_fo, nse_eq, stock_footy, nse_optionchain
    HAS_NSEPYTHON = True
except ImportError:
    HAS_NSEPYTHON = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('live_data_feed.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class TickData:
    """Single tick data point"""
    timestamp: datetime
    symbol: str
    last_price: float
    last_volume: int
    bid_price: float
    bid_volume: int
    ask_price: float
    ask_volume: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int
    vwap: float
    ticks: List[Dict] = field(default_factory=list)


@dataclass
class LOBSnapshot:
    """Limit Order Book snapshot"""
    timestamp: datetime
    symbol: str
    bid_prices: np.ndarray
    bid_volumes: np.ndarray
    ask_prices: np.ndarray
    ask_volumes: np.ndarray
    last_trade_price: float
    last_trade_volume: int
    trade_side: int
    vwap: float = 0.0
    oi: int = 0  # Open interest for futures


class LiveDataFeed:
    """
    Abstract base class for live data feeds
    """

    def __init__(self, symbol: str, n_levels: int = 10):
        self.symbol = symbol
        self.n_levels = n_levels
        self.callbacks: List[Callable] = []
        self.is_running = False
        self.last_snapshot: Optional[LOBSnapshot] = None

    def add_callback(self, callback: Callable):
        """Add callback for new data"""
        self.callbacks.append(callback)

    def remove_callback(self, callback: Callable):
        """Remove callback"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    def _notify_callbacks(self, snapshot: LOBSnapshot):
        """Notify all callbacks with new snapshot"""
        for callback in self.callbacks:
            try:
                callback(snapshot)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def start(self):
        """Start data feed"""
        raise NotImplementedError

    def stop(self):
        """Stop data feed"""
        raise NotImplementedError

    def get_latest_snapshot(self) -> Optional[LOBSnapshot]:
        """Get latest LOB snapshot"""
        return self.last_snapshot


class YahooFinanceFeed(LiveDataFeed):
    """
    Live data feed via Yahoo Finance API
    Free, 1-minute delayed data
    """

    def __init__(self, symbol: str, n_levels: int = 10, update_interval: int = 5):
        super().__init__(symbol, n_levels)
        self.update_interval = update_interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.price_buffer: deque = deque(maxlen=100)
        self.volume_buffer: deque = deque(maxlen=100)

    def start(self):
        """Start Yahoo Finance feed"""
        if not HAS_YAHOO:
            logger.error("yfinance not installed")
            return False

        self.is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._thread.start()
        logger.info(f"✅ Yahoo Finance feed started for {self.symbol}")
        return True

    def stop(self):
        """Stop Yahoo Finance feed"""
        self.is_running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info(f"⏹️ Yahoo Finance feed stopped")

    def _fetch_loop(self):
        """Main fetch loop"""
        while not self._stop_event.is_set():
            try:
                snapshot = self._fetch_snapshot()
                if snapshot:
                    self.last_snapshot = snapshot
                    self._notify_callbacks(snapshot)
                self._stop_event.wait(self.update_interval)
            except Exception as e:
                logger.error(f"Fetch error: {e}")
                self._stop_event.wait(10)  # Wait longer on error

    def _fetch_snapshot(self) -> Optional[LOBSnapshot]:
        """Fetch single snapshot from Yahoo Finance"""
        try:
            ticker = f"{self.symbol}.NS" if not self.symbol.endswith('.NS') else self.symbol

            # Get recent data
            df = yf.download(ticker, period='1d', interval='1m', progress=False)

            if df.empty or len(df) < 1:
                return None

            # Handle multi-level columns (newer yfinance versions)
            if isinstance(df.columns, pd.MultiIndex):
                # Flatten columns - take first level
                df.columns = df.columns.get_level_values(0)
            
            # Get latest bar
            latest = df.iloc[-1]
            timestamp = df.index[-1]
            if hasattr(timestamp, 'to_pydatetime'):
                timestamp = timestamp.to_pydatetime()

            # Extract values properly
            close_price = float(latest['Close']) if hasattr(latest, '__getitem__') else float(latest.iloc[-1])
            open_price = float(latest['Open'])
            high_price = float(latest['High'])
            low_price = float(latest['Low'])
            volume = int(latest['Volume'])
            
            # Store in buffer
            self.price_buffer.append(close_price)
            self.volume_buffer.append(volume)

            # Create pseudo-LOB from OHLCV
            mid_price = close_price
            spread = 0.05  # Default spread for equities

            # Generate 10-level order book
            bid_prices = np.array([mid_price - spread/2 - 0.05*i for i in range(self.n_levels)])
            ask_prices = np.array([mid_price + spread/2 + 0.05*i for i in range(self.n_levels)])

            # Volumes decrease with depth
            base_volume = max(100, volume // 10)
            bid_volumes = np.array([base_volume // (i+1) for i in range(self.n_levels)])
            ask_volumes = np.array([base_volume // (i+1) for i in range(self.n_levels)])

            # Determine trade side
            trade_side = 1 if close_price >= open_price else -1

            snapshot = LOBSnapshot(
                timestamp=timestamp,
                symbol=self.symbol,
                bid_prices=bid_prices,
                bid_volumes=bid_volumes,
                ask_prices=ask_prices,
                ask_volumes=ask_volumes,
                last_trade_price=mid_price,
                last_trade_volume=volume,
                trade_side=trade_side,
                vwap=close_price
            )

            return snapshot

        except Exception as e:
            logger.error(f"Snapshot fetch error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None


class NSEPythonFeed(LiveDataFeed):
    """
    Live data feed via nsepython library
    Direct NSE website scraping
    """

    def __init__(self, symbol: str, n_levels: int = 10, update_interval: int = 5):
        super().__init__(symbol, n_levels)
        self.update_interval = update_interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        """Start NSE Python feed"""
        if not HAS_NSEPYTHON:
            logger.error("nsepython not installed. Install with: pip install nsepython")
            return False

        self.is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._thread.start()
        logger.info(f"✅ NSE Python feed started for {self.symbol}")
        return True

    def stop(self):
        """Stop NSE Python feed"""
        self.is_running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info(f"⏹️ NSE Python feed stopped")

    def _fetch_loop(self):
        """Main fetch loop"""
        while not self._stop_event.is_set():
            try:
                snapshot = self._fetch_snapshot()
                if snapshot:
                    self.last_snapshot = snapshot
                    self._notify_callbacks(snapshot)
                self._stop_event.wait(self.update_interval)
            except Exception as e:
                logger.error(f"Fetch error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self._stop_event.wait(10)

    def _fetch_snapshot(self) -> Optional[LOBSnapshot]:
        """Fetch single snapshot from NSE"""
        try:
            from nsepython import nse_eq

            # Get equity data
            data = nse_eq(self.symbol)

            if not data or 'priceInfo' not in data:
                return None

            price_info = data['priceInfo']
            timestamp = datetime.now()

            mid_price = price_info.get('lastPrice', 0)
            if mid_price == 0:
                return None

            spread = 0.05
            total_volume = price_info.get('totalTradedVolume', 0)

            # Create LOB
            bid_prices = np.array([mid_price - spread/2 - 0.05*i for i in range(self.n_levels)])
            ask_prices = np.array([mid_price + spread/2 + 0.05*i for i in range(self.n_levels)])

            base_volume = max(100, total_volume // 10)
            bid_volumes = np.array([base_volume // (i+1) for i in range(self.n_levels)])
            ask_volumes = np.array([base_volume // (i+1) for i in range(self.n_levels)])

            # Trade side
            day_change = price_info.get('change', 0)
            trade_side = 1 if day_change >= 0 else -1

            snapshot = LOBSnapshot(
                timestamp=timestamp,
                symbol=self.symbol,
                bid_prices=bid_prices,
                bid_volumes=bid_volumes,
                ask_prices=ask_prices,
                ask_volumes=ask_volumes,
                last_trade_price=mid_price,
                last_trade_volume=total_volume,
                trade_side=trade_side,
                vwap=price_info.get('averagePrice', mid_price)
            )

            return snapshot

        except Exception as e:
            logger.error(f"NSE snapshot error: {e}")
            return None


class ZerodhaKiteFeed(LiveDataFeed):
    """
    Live data feed via Zerodha Kite Connect API
    Real-time data (requires paid API access)
    """

    def __init__(self, symbol: str, api_key: str, access_token: str, n_levels: int = 10):
        super().__init__(symbol, n_levels)
        self.api_key = api_key
        self.access_token = access_token
        self.kite: Optional[KiteConnect] = None
        self.kws: Optional[KiteTicker] = None
        self.tick_buffer: deque = deque(maxlen=500)

    def start(self):
        """Start Zerodha Kite feed"""
        if not HAS_ZERODHA:
            logger.error("kiteconnect not installed. Install with: pip install kiteconnect")
            return False

        try:
            # Initialize Kite
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)

            # Initialize WebSocket
            self.kws = KiteTicker(self.api_key, self.access_token)

            # Set callbacks
            self.kws.on_ticks = self._on_ticks
            self.kws.on_connect = self._on_connect
            self.kws.on_close = self._on_close
            self.kws.on_error = self._on_error
            self.kws.on_reconnect = self._on_reconnect

            # Start WebSocket connection
            self.kws.connect(threaded=True)

            self.is_running = True
            logger.info(f"✅ Zerodha Kite feed started for {self.symbol}")
            return True

        except Exception as e:
            logger.error(f"Kite connect error: {e}")
            return False

    def stop(self):
        """Stop Zerodha Kite feed"""
        if self.kws:
            self.kws.close()
        self.is_running = False
        logger.info(f"⏹️ Zerodha Kite feed stopped")

    def _on_connect(self, ws, response):
        """On WebSocket connect"""
        # Subscribe to symbol
        token = self._get_instrument_token()
        if token:
            ws.subscribe([token])
            ws.set_mode(ws.MODE_FULL, [token])
            logger.info(f"Subscribed to {self.symbol} (token: {token})")

    def _on_ticks(self, ws, ticks):
        """On receiving ticks"""
        for tick in ticks:
            self.tick_buffer.append(tick)

            # Convert to LOB snapshot
            snapshot = self._tick_to_snapshot(tick)
            if snapshot:
                self.last_snapshot = snapshot
                self._notify_callbacks(snapshot)

    def _on_close(self, ws, code, reason):
        """On WebSocket close"""
        logger.warning(f"Kite WebSocket closed: {code} - {reason}")

    def _on_error(self, ws, code, reason):
        """On WebSocket error"""
        logger.error(f"Kite WebSocket error: {code} - {reason}")

    def _on_reconnect(self, ws, attempts_count):
        """On WebSocket reconnect"""
        logger.info(f"Kite reconnecting... Attempt {attempts_count}")

    def _get_instrument_token(self) -> Optional[int]:
        """Get instrument token for symbol"""
        try:
            # Get all instruments
            instruments = self.kite.instruments("NSE")

            # Find symbol
            for inst in instruments:
                if inst['tradingsymbol'] == self.symbol:
                    return inst['instrument_token']

            logger.warning(f"Instrument token not found for {self.symbol}")
            return None

        except Exception as e:
            logger.error(f"Get instrument token error: {e}")
            return None

    def _tick_to_snapshot(self, tick: Dict) -> Optional[LOBSnapshot]:
        """Convert Kite tick to LOB snapshot"""
        try:
            timestamp = datetime.now()
            mid_price = tick.get('last_price', 0)

            if mid_price == 0:
                return None

            # Depth data (if available)
            depth = tick.get('depth', {})
            bid_depth = depth.get('buy', [])
            ask_depth = depth.get('sell', [])

            # Build order book
            bid_prices = np.zeros(self.n_levels)
            bid_volumes = np.zeros(self.n_levels)
            ask_prices = np.zeros(self.n_levels)
            ask_volumes = np.zeros(self.n_levels)

            # Fill from depth data
            for i in range(min(len(bid_depth), self.n_levels)):
                bid_prices[i] = bid_depth[i]['price']
                bid_volumes[i] = bid_depth[i]['quantity']

            for i in range(min(len(ask_depth), self.n_levels)):
                ask_prices[i] = ask_depth[i]['price']
                ask_volumes[i] = ask_depth[i]['quantity']

            # Fill remaining with synthetic data if needed
            spread = tick.get('ohlc', {}).get('close', mid_price * 0.0001)
            spread = max(0.05, spread)

            for i in range(len(bid_depth), self.n_levels):
                bid_prices[i] = mid_price - spread/2 - 0.05 * i
                bid_volumes[i] = max(100, tick.get('volume', 1000) // (i+1))

            for i in range(len(ask_depth), self.n_levels):
                ask_prices[i] = mid_price + spread/2 + 0.05 * i
                ask_volumes[i] = max(100, tick.get('volume', 1000) // (i+1))

            trade_side = 1 if tick.get('last_price', 0) >= tick.get('ohlc', {}).get('open', 0) else -1

            snapshot = LOBSnapshot(
                timestamp=timestamp,
                symbol=self.symbol,
                bid_prices=bid_prices,
                bid_volumes=bid_volumes,
                ask_prices=ask_prices,
                ask_volumes=ask_volumes,
                last_trade_price=mid_price,
                last_trade_volume=tick.get('volume', 0),
                trade_side=trade_side,
                vwap=tick.get('avg_trade_price', mid_price)
            )

            return snapshot

        except Exception as e:
            logger.error(f"Tick to snapshot error: {e}")
            return None


class MultiSourceLiveFeed:
    """
    Aggregates multiple data sources with fallback
    """

    def __init__(self, symbol: str, n_levels: int = 10, update_interval: int = 5):
        self.symbol = symbol
        self.n_levels = n_levels
        self.update_interval = update_interval
        self.feeds: Dict[str, LiveDataFeed] = {}
        self.active_feed: Optional[str] = None
        self.callbacks: List[Callable] = []
        self.snapshot_buffer: deque = deque(maxlen=1000)
        self.is_running = False

        # Initialize available feeds
        self._initialize_feeds()

    def _initialize_feeds(self):
        """Initialize all available data feeds"""
        # Yahoo Finance (free, delayed)
        if HAS_YAHOO:
            self.feeds['yahoo'] = YahooFinanceFeed(
                self.symbol, self.n_levels, self.update_interval
            )
            logger.info("✓ Yahoo Finance feed available")

        # NSE Python (free, direct)
        if HAS_NSEPYTHON:
            self.feeds['nsepython'] = NSEPythonFeed(
                self.symbol, self.n_levels, self.update_interval
            )
            logger.info("✓ NSE Python feed available")

        # Zerodha Kite (paid, real-time)
        if HAS_ZERODHA:
            # Will be configured manually
            pass

    def configure_zerodha(self, api_key: str, access_token: str):
        """Configure Zerodha Kite feed"""
        if HAS_ZERODHA:
            self.feeds['zerodha'] = ZerodhaKiteFeed(
                self.symbol, api_key, access_token, self.n_levels
            )
            logger.info("✓ Zerodha Kite feed configured")
        else:
            logger.warning("kiteconnect not installed")

    def add_callback(self, callback: Callable):
        """Add callback for new snapshots"""
        self.callbacks.append(callback)

    def start(self, preferred_source: str = None):
        """
        Start live feed

        Args:
            preferred_source: 'zerodha', 'nsepython', 'yahoo', or None (auto)
        """
        if not self.feeds:
            logger.error("No data feeds available")
            return False

        # Select feed
        if preferred_source and preferred_source in self.feeds:
            self.active_feed = preferred_source
        elif 'zerodha' in self.feeds:
            self.active_feed = 'zerodha'
        elif 'nsepython' in self.feeds:
            self.active_feed = 'nsepython'
        elif 'yahoo' in self.feeds:
            self.active_feed = 'yahoo'
        else:
            logger.error("No suitable feed found")
            return False

        # Add callback
        def on_snapshot(snapshot):
            self.snapshot_buffer.append(snapshot)
            for callback in self.callbacks:
                try:
                    callback(snapshot)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

        self.feeds[self.active_feed].add_callback(on_snapshot)

        # Start feed
        success = self.feeds[self.active_feed].start()
        if success:
            self.is_running = True
            logger.info(f"🚀 Live feed started: {self.active_feed} -> {self.symbol}")
        else:
            logger.error(f"Failed to start {self.active_feed} feed")

        return success

    def stop(self):
        """Stop live feed"""
        for feed_name, feed in self.feeds.items():
            try:
                feed.stop()
            except:
                pass
        self.is_running = False
        logger.info("⏹️ All live feeds stopped")

    def get_latest_snapshot(self) -> Optional[LOBSnapshot]:
        """Get latest snapshot from buffer"""
        if self.snapshot_buffer:
            return self.snapshot_buffer[-1]
        return None

    def get_recent_snapshots(self, n: int = 100) -> List[LOBSnapshot]:
        """Get recent snapshots"""
        return list(self.snapshot_buffer)[-n:]

    def get_snapshots_as_dataframe(self, n: int = 100) -> Optional[pd.DataFrame]:
        """Convert recent snapshots to DataFrame"""
        snapshots = self.get_recent_snapshots(n)
        if not snapshots:
            return None

        # Convert to dict list
        data = []
        for snap in snapshots:
            row = {
                'timestamp': snap.timestamp,
                'last_trade_price': snap.last_trade_price,
                'last_trade_volume': snap.last_trade_volume,
                'trade_side': snap.trade_side,
                'vwap': snap.vwap
            }

            # Add LOB levels
            for i in range(self.n_levels):
                row[f'bid_price_{i+1}'] = snap.bid_prices[i]
                row[f'bid_volume_{i+1}'] = snap.bid_volumes[i]
                row[f'ask_price_{i+1}'] = snap.ask_prices[i]
                row[f'ask_volume_{i+1}'] = snap.ask_volumes[i]

            data.append(row)

        return pd.DataFrame(data)


class LiveDataRecorder:
    """
    Records live market data to parquet files
    """

    def __init__(self, output_dir: str = 'data/live'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.buffer: List[LOBSnapshot] = []
        self.flush_interval = 100  # Snapshots
        self.is_recording = False

    def start_recording(self, live_feed: MultiSourceLiveFeed):
        """Start recording data"""
        self.is_recording = True
        live_feed.add_callback(self._on_snapshot)
        logger.info(f"📹 Recording started: {self.output_dir}")

    def stop_recording(self):
        """Stop and flush data"""
        self.is_recording = False
        self._flush_buffer()
        logger.info("⏹️ Recording stopped")

    def _on_snapshot(self, snapshot: LOBSnapshot):
        """On new snapshot"""
        if self.is_recording:
            self.buffer.append(snapshot)

            if len(self.buffer) >= self.flush_interval:
                self._flush_buffer()

    def _flush_buffer(self):
        """Flush buffer to file"""
        if not self.buffer:
            return

        # Convert to DataFrame
        snapshots = []
        for snap in self.buffer:
            row = {'timestamp': snap.timestamp}
            row['last_trade_price'] = snap.last_trade_price
            row['last_trade_volume'] = snap.last_trade_volume
            row['trade_side'] = snap.trade_side
            row['vwap'] = snap.vwap

            for i in range(len(snap.bid_prices)):
                row[f'bid_price_{i+1}'] = snap.bid_prices[i]
                row[f'bid_volume_{i+1}'] = snap.bid_volumes[i]
                row[f'ask_price_{i+1}'] = snap.ask_prices[i]
                row[f'ask_volume_{i+1}'] = snap.ask_volumes[i]

            snapshots.append(row)

        df = pd.DataFrame(snapshots)

        # Save to parquet
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{snapshots[0].get('symbol', 'UNKNOWN')}_{timestamp}.parquet"
        filepath = self.output_dir / filename

        df.to_parquet(filepath, index=False)
        logger.info(f"💾 Saved {len(df)} snapshots to {filepath}")

        # Clear buffer
        self.buffer = []


# ============================================================
# MAIN - Example usage
# ============================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Live NSE Data Feed')
    parser.add_argument('--symbol', type=str, default='RELIANCE', help='NSE symbol')
    parser.add_argument('--source', type=str, default='auto',
                       choices=['auto', 'yahoo', 'nsepython', 'zerodha'],
                       help='Data source')
    parser.add_argument('--levels', type=int, default=10, help='Order book levels')
    parser.add_argument('--interval', type=int, default=5, help='Update interval (seconds)')
    parser.add_argument('--record', action='store_true', help='Record to file')
    parser.add_argument('--duration', type=int, default=60, help='Duration in minutes')
    parser.add_argument('--api-key', type=str, help='Zerodha API key')
    parser.add_argument('--access-token', type=str, help='Zerodha access token')

    args = parser.parse_args()

    # Create live feed
    live_feed = MultiSourceLiveFeed(
        symbol=args.symbol,
        n_levels=args.levels,
        update_interval=args.interval
    )

    # Configure Zerodha if provided
    if args.api_key and args.access_token:
        live_feed.configure_zerodha(args.api_key, args.access_token)

    # Callback for displaying data
    snapshot_count = [0]

    def on_snapshot(snapshot):
        snapshot_count[0] += 1
        if snapshot_count[0] % 10 == 0:  # Print every 10 snapshots
            logger.info(
                f"\n📊 Snapshot #{snapshot_count[0]} | "
                f"{snapshot.timestamp.strftime('%H:%M:%S')} | "
                f"Price: ₹{snapshot.last_trade_price:.2f} | "
                f"Side: {'BUY' if snapshot.trade_side == 1 else 'SELL'} | "
                f"Spread: ₹{snapshot.ask_prices[0] - snapshot.bid_prices[0]:.2f}"
            )

    live_feed.add_callback(on_snapshot)

    # Setup recorder if requested
    recorder = None
    if args.record:
        recorder = LiveDataRecorder(output_dir='data/live')
        recorder.start_recording(live_feed)

    # Start feed
    preferred = None if args.source == 'auto' else args.source
    live_feed.start(preferred_source=preferred)

    # Run for duration
    logger.info(f"\n🚀 Running live feed for {args.duration} minutes...")
    logger.info("Press Ctrl+C to stop\n")

    try:
        time.sleep(args.duration * 60)
    except KeyboardInterrupt:
        logger.info("\n⏹️ Interrupted by user")

    # Cleanup
    if recorder:
        recorder.stop_recording()
    live_feed.stop()

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 SESSION SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Symbol: {args.symbol}")
    logger.info(f"Source: {live_feed.active_feed}")
    logger.info(f"Duration: {args.duration} minutes")
    logger.info(f"Snapshots: {snapshot_count[0]}")
    logger.info(f"Buffer Size: {len(live_feed.snapshot_buffer)}")

    # Display recent data
    df = live_feed.get_snapshots_as_dataframe(n=5)
    if df is not None:
        logger.info(f"\n📈 Recent snapshots:")
        logger.info(f"\n{df[['timestamp', 'last_trade_price', 'last_trade_volume', 'trade_side']].to_string()}")
