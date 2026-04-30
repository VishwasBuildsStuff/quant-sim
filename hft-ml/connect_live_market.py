"""
Live Market Data Launcher
Simple script to connect and display live NSE market data
"""

import sys
sys.path.insert(0, r'V:\pylibs')
sys.path.insert(0, '.')

import time
import argparse
from datetime import datetime
from live_data_feed import MultiSourceLiveFeed, LiveDataRecorder

def display_live_data(symbol='RELIANCE', source='auto', interval=5, duration=60, record=False):
    """
    Display live market data
    
    Args:
        symbol: NSE symbol name
        source: Data source ('auto', 'yahoo', 'nsepython', 'zerodha')
        interval: Update interval in seconds
        duration: How long to run in minutes
        record: Whether to record data to file
    """
    
    print(f"\n{'='*60}")
    print(f"🚀 LIVE NSE MARKET DATA FEED")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Data Source: {source}")
    print(f"Update Interval: {interval}s")
    print(f"Duration: {duration} minutes")
    print(f"{'='*60}\n")
    
    # Create live feed
    live_feed = MultiSourceLiveFeed(
        symbol=symbol,
        n_levels=10,
        update_interval=interval
    )
    
    # Setup recorder
    recorder = None
    if record:
        recorder = LiveDataRecorder(output_dir='data/live')
        recorder.start_recording(live_feed)
    
    # Display callback
    snapshot_count = [0]
    last_price = [None]
    
    def on_snapshot(snapshot):
        snapshot_count[0] += 1
        
        # Display every snapshot for first 10, then every 5th
        if snapshot_count[0] <= 10 or snapshot_count[0] % 5 == 0:
            timestamp = snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            price = snapshot.last_trade_price
            volume = snapshot.last_trade_volume
            side = 'BUY ↑' if snapshot.trade_side == 1 else 'SELL ↓'
            spread = snapshot.ask_prices[0] - snapshot.bid_prices[0]
            vwap = snapshot.vwap
            
            # Price change indicator
            price_change = ""
            if last_price[0] is not None:
                if price > last_price[0]:
                    price_change = "📈"
                elif price < last_price[0]:
                    price_change = "📉"
                else:
                    price_change = "➡️"
            
            last_price[0] = price
            
            print(f"[{timestamp}] #{snapshot_count[0]} {price_change}")
            print(f"  Price: ₹{price:.2f} | Volume: {volume:,} | Side: {side}")
            print(f"  Spread: ₹{spread:.2f} | VWAP: ₹{vwap:.2f}")
            print(f"  Best Bid: ₹{snapshot.bid_prices[0]:.2f} x {snapshot.bid_volumes[0]:,}")
            print(f"  Best Ask: ₹{snapshot.ask_prices[0]:.2f} x {snapshot.ask_volumes[0]:,}")
            print()
    
    live_feed.add_callback(on_snapshot)
    
    # Start feed
    preferred = None if source == 'auto' else source
    success = live_feed.start(preferred_source=preferred)
    
    if not success:
        print("\n❌ Failed to start live data feed")
        print("Available sources:")
        print("  - yahoo: Requires yfinance (pip install yfinance)")
        print("  - nsepython: Requires nsepython (pip install nsepython)")
        print("  - zerodha: Requires kiteconnect (pip install kiteconnect)")
        return
    
    print(f"✅ Connected to {live_feed.active_feed.upper()} data feed\n")
    print("Press Ctrl+C to stop\n")
    
    # Run for duration
    try:
        time.sleep(duration * 60)
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopped by user")
    
    # Cleanup
    if recorder:
        recorder.stop_recording()
    live_feed.stop()
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📊 SESSION SUMMARY")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Source: {live_feed.active_feed.upper()}")
    print(f"Duration: {duration} minutes")
    print(f"Total Snapshots: {snapshot_count[0]}")
    print(f"Data Points in Buffer: {len(live_feed.snapshot_buffer)}")
    print(f"{'='*60}\n")


def fetch_and_save(symbol='RELIANCE', days=7, source='auto', interval='1m'):
    """
    Fetch recent data and save to file for training
    """
    print(f"\n{'='*60}")
    print(f"📡 FETCHING HISTORICAL DATA")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Days: {days}")
    print(f"Interval: {interval}")
    print(f"Source: {source}")
    print(f"{'='*60}\n")
    
    # Use existing fetch_real_nse_data if available
    try:
        from fetch_real_nse_data import fetch_nse_minute_data, interpolate_to_lob
        import os
        
        # Fetch minute data
        minute_df = fetch_nse_minute_data(symbol, days=days, interval=interval)
        
        if minute_df is not None and len(minute_df) > 100:
            # Interpolate to LOB
            lob_df = interpolate_to_lob(minute_df, snapshots_per_minute=5)
            
            # Save
            os.makedirs('data', exist_ok=True)
            filepath = f'data/{symbol}_live.parquet'
            lob_df.to_parquet(filepath, index=False)
            
            file_size = os.path.getsize(filepath) / 1e6
            print(f"\n💾 Saved to {filepath} ({file_size:.1f} MB)")
            print(f"📊 Shape: {lob_df.shape}")
            print(f"✅ Data ready for training!\n")
        else:
            print("\n❌ Could not fetch sufficient data")
            
    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        print("Make sure fetch_real_nse_data.py is in the current directory")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Live NSE Market Data Launcher')
    parser.add_argument('mode', choices=['live', 'fetch'], 
                       help='Mode: "live" for streaming, "fetch" for historical data')
    parser.add_argument('--symbol', type=str, default='RELIANCE', help='NSE symbol')
    parser.add_argument('--source', type=str, default='auto',
                       choices=['auto', 'yahoo', 'nsepython', 'zerodha'],
                       help='Data source')
    parser.add_argument('--interval', type=int, default=5, help='Update interval in seconds (live mode)')
    parser.add_argument('--data-interval', type=str, default='1m',
                       choices=['1m', '5m', '15m', '30m', '1h', '1d'],
                       help='Data bar interval (fetch mode)')
    parser.add_argument('--days', type=int, default=7, help='Days of historical data (fetch mode)')
    parser.add_argument('--duration', type=int, default=30, help='Duration in minutes (live mode)')
    parser.add_argument('--record', action='store_true', help='Record live data to file')
    
    args = parser.parse_args()
    
    if args.mode == 'live':
        display_live_data(
            symbol=args.symbol,
            source=args.source,
            interval=args.interval,
            duration=args.duration,
            record=args.record
        )
    elif args.mode == 'fetch':
        fetch_and_save(
            symbol=args.symbol,
            days=args.days,
            source=args.source,
            interval=args.data_interval
        )
