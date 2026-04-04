"""
NSE (National Stock Exchange India) Data Fetcher
Fetches real-time and historical data from NSE

Supports:
- Real-time quotes
- Historical data (1 day to 10 years)
- Multiple timeframes (1m, 5m, 15m, 1h, 1d)
- Top NSE symbols
- Sector indices
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


# NSE Symbol Mapping
NSE_SYMBOLS = {
    # Large Cap
    'RELIANCE': 'RELIANCE.NS',
    'TCS': 'TCS.NS',
    'INFY': 'INFY.NS',
    'HDFCBANK': 'HDFCBANK.NS',
    'ICICIBANK': 'ICICIBANK.NS',
    'HINDUNILVR': 'HINDUNILVR.NS',
    'ITC': 'ITC.NS',
    'SBIN': 'SBIN.NS',
    'BHARTIARTL': 'BHARTIARTL.NS',
    'KOTAKBANK': 'KOTAKBANK.NS',
    'LT': 'LT.NS',
    'AXISBANK': 'AXISBANK.NS',
    'ASIANPAINT': 'ASIANPAINT.NS',
    'MARUTI': 'MARUTI.NS',
    'BAJFINANCE': 'BAJFINANCE.NS',
    'TITAN': 'TITAN.NS',
    'WIPRO': 'WIPRO.NS',
    'SUNPHARMA': 'SUNPHARMA.NS',
    'ULTRACEMCO': 'ULTRACEMCO.NS',
    'TATAMOTORS': 'TATAMOTORS.NS',
    
    # Mid Cap
    'ADANIENT': 'ADANIENT.NS',
    'ADANIPORTS': 'ADANIPORTS.NS',
    'POWERGRID': 'POWERGRID.NS',
    'NTPC': 'NTPC.NS',
    'ONGC': 'ONGC.NS',
    'TATASTEEL': 'TATASTEEL.NS',
    'JSWSTEEL': 'JSWSTEEL.NS',
    'HCLTECH': 'HCLTECH.NS',
    'TECHM': 'TECHM.NS',
    'M&M': 'M&M.NS',
}

# NSE Indices - Yahoo Finance uses ^ prefix
NSE_INDICES = {
    'NIFTY50': '^NSEI',
    'NIFTYBANK': '^NSEBANK',
    'NIFTYIT': '^CNXIT',
    'NIFTYAUTO': '^CNXAUTO',
    'SENSEX': '^BSESN',
}


class NSEDataFetcher:
    """
    Fetches real-time and historical data from NSE
    Uses yfinance for reliable data access
    """
    
    def __init__(self):
        self.cache = {}
    
    @staticmethod
    def get_symbol(symbol: str) -> str:
        """Convert NSE symbol to yfinance format"""
        symbol = symbol.upper()
        
        # Check if it's already in yfinance format (^ for indices)
        if symbol.startswith('^'):
            return symbol
        
        # Check if it's an index name
        if symbol in NSE_INDICES:
            return NSE_INDICES[symbol]
        
        # Check mapping for stocks
        if symbol in NSE_SYMBOLS:
            return NSE_SYMBOLS[symbol]
        
        # Add .NS suffix for NSE stocks
        if not symbol.endswith('.NS'):
            return f"{symbol}.NS"
        
        return symbol
    
    @staticmethod
    def get_index_symbol(index: str) -> str:
        """Get index symbol (Yahoo uses ^ prefix)"""
        index = index.upper()
        
        # Already has ^ prefix
        if index.startswith('^'):
            return index
        
        # Remove any .NS suffix
        index = index.replace('.NS', '')
        
        if index in NSE_INDICES:
            return NSE_INDICES[index]
        
        # Default: add ^ prefix
        return f"^{index}"
    
    def get_realtime_quote(self, symbols: List[str]) -> Dict:
        """
        Get real-time quotes for multiple symbols
        
        Args:
            symbols: List of NSE symbols
            
        Returns:
            Dict with current prices and metrics
        """
        quotes = {}
        
        for symbol in symbols:
            # Use correct symbol format for indices vs stocks
            if symbol.upper() in NSE_INDICES or symbol.startswith('^'):
                yf_symbol = self.get_index_symbol(symbol)
            else:
                yf_symbol = self.get_symbol(symbol)
            
            ticker = yf.Ticker(yf_symbol)
            
            try:
                info = ticker.fast_info
                quotes[symbol] = {
                    'price': info.last_price,
                    'open': info.open,
                    'high': info.day_high,
                    'low': info.day_low,
                    'previous_close': info.previous_close,
                    'volume': info.last_volume,
                    'market_cap': info.market_cap,
                    'pe_ratio': getattr(info, 'trailing_pe', None),
                    '52w_high': getattr(info, 'fifty_two_week_high', None),
                    '52w_low': getattr(info, 'fifty_two_week_low', None),
                }
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}: {e}")
                quotes[symbol] = None
        
        return quotes
    
    def get_historical_data(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        Fetch historical data
        
        Args:
            symbol: NSE symbol (e.g., 'RELIANCE', 'NIFTY50')
            period: Time period ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y')
            interval: Data interval ('1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '1wk', '1mo')
            start_date: Custom start date (YYYY-MM-DD)
            end_date: Custom end date (YYYY-MM-DD)
            
        Returns:
            DataFrame with OHLCV data
        """
        yf_symbol = self.get_symbol(symbol)
        
        # Handle indices
        if symbol.upper() in NSE_INDICES:
            yf_symbol = self.get_index_symbol(symbol)
        
        ticker = yf.Ticker(yf_symbol)
        
        try:
            if start_date and end_date:
                df = ticker.history(start=start_date, end=end_date, interval=interval)
            else:
                df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                logger.warning(f"No data found for {symbol}")
                return pd.DataFrame()
            
            # Clean up column names
            df.columns = [col.lower().replace(' ', '_') for col in df.columns]
            
            # Store metadata
            df.attrs = {
                'symbol': symbol,
                'yf_symbol': yf_symbol,
                'period': period,
                'interval': interval,
                'fetched_at': datetime.now()
            }
            
            logger.info(f"Fetched {len(df)} bars for {symbol} ({period}, {interval})")
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch data for {symbol}: {e}")
            return pd.DataFrame()
    
    def get_multiple_symbols(
        self,
        symbols: List[str],
        period: str = "1y",
        interval: str = "1d"
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for multiple symbols
        
        Returns:
            Dict of symbol -> DataFrame
        """
        data = {}
        
        for symbol in symbols:
            df = self.get_historical_data(symbol, period, interval)
            if not df.empty:
                data[symbol] = df
        
        return data
    
    def get_top_gainers_losers(self, n: int = 10) -> Tuple[List, List]:
        """
        Get top gainers and losers from NSE
        
        Note: This is approximate as yfinance doesn't have direct screener API
        Fetches from popular stocks and calculates
        """
        symbols = list(NSE_SYMBOLS.keys())[:30]  # Top 30 stocks
        quotes = self.get_realtime_quote(symbols)
        
        # Calculate returns
        returns = []
        for symbol, quote in quotes.items():
            if quote and quote['price'] and quote['previous_close']:
                change_pct = (quote['price'] - quote['previous_close']) / quote['previous_close'] * 100
                returns.append({
                    'symbol': symbol,
                    'price': quote['price'],
                    'change_pct': change_pct,
                    'volume': quote['volume']
                })
        
        # Sort by change
        returns.sort(key=lambda x: x['change_pct'], reverse=True)
        
        gainers = returns[:n]
        losers = returns[-n:][::-1]  # Reverse to show worst first
        
        return gainers, losers
    
    def get_sector_performance(self) -> Dict:
        """Get performance of major sectors/indices using historical data"""
        indices = list(NSE_INDICES.keys())
        performance = {}
        
        for index in indices:
            try:
                # Get recent historical data to calculate performance
                yf_symbol = self.get_index_symbol(index)
                df = yf.Ticker(yf_symbol).history(period='5d')
                
                if not df.empty and len(df) >= 2:
                    current = df['Close'].iloc[-1]
                    previous = df['Close'].iloc[-2]
                    change_pct = (current - previous) / previous * 100
                    
                    performance[index] = {
                        'value': current,
                        'change_pct': change_pct,
                        'high': df['High'].max(),
                        'low': df['Low'].min()
                    }
            except Exception as e:
                logger.debug(f"Could not fetch {index}: {e}")
        
        return performance
    
    def prepare_backtest_data(self, df: pd.DataFrame) -> Tuple:
        """
        Convert DataFrame to format compatible with backtesting engine
        
        Returns:
            (timestamps, prices, highs, lows, volumes)
        """
        if df.empty:
            return None, None, None, None, None
        
        timestamps = df.index.tolist()
        prices = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        volumes = df['volume'].values if 'volume' in df.columns else None
        
        return timestamps, prices, highs, lows, volumes


def demo_nse_data():
    """Demo: Fetch and display NSE data"""
    
    print("="*80)
    print("NSE DATA FETCHER - Real-time Market Data")
    print("="*80)
    
    fetcher = NSEDataFetcher()
    
    # 1. Real-time quotes
    print("\n[1] Real-Time Quotes - Top NSE Stocks")
    print("-"*80)
    
    top_symbols = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'TITAN', 'INFY']
    quotes = fetcher.get_realtime_quote(top_symbols)
    
    print(f"{'Symbol':<15} {'Price':>10} {'Change':>10} {'Volume':>12}")
    print("-"*50)
    
    for symbol, quote in quotes.items():
        if quote:
            change = quote['price'] - quote['previous_close']
            change_pct = (change / quote['previous_close']) * 100
            print(f"{symbol:<15} ₹{quote['price']:>9.2f} {change_pct:>+9.2f}% {quote['volume']:>12,}")
    
    # 2. Historical data
    print("\n[2] Historical Data - RELIANCE (1 Year)")
    print("-"*80)
    
    df = fetcher.get_historical_data('RELIANCE', period='1y', interval='1d')
    
    if not df.empty:
        print(f"Fetched {len(df)} trading days")
        print(f"Date Range: {df.index[0].date()} to {df.index[-1].date()}")
        print(f"\nLast 5 days:")
        print(df.tail()[['open', 'high', 'low', 'close', 'volume']])
    
    # 3. Sector performance
    print("\n[3] NSE Sector Performance")
    print("-"*80)
    
    sectors = fetcher.get_sector_performance()
    
    print(f"{'Index':<15} {'Value':>12} {'Change':>10}")
    print("-"*40)
    
    for index, perf in sorted(sectors.items(), key=lambda x: x[1]['change_pct'], reverse=True):
        print(f"{index:<15} ₹{perf['value']:>11.2f} {perf['change_pct']:>+9.2f}%")
    
    # 4. Intraday data (if market is open)
    print("\n[4] Intraday Data - TCS (5-minute bars, last 5 days)")
    print("-"*80)
    
    try:
        intraday_df = fetcher.get_historical_data('TCS', period='5d', interval='5m')
        
        if not intraday_df.empty:
            print(f"Fetched {len(intraday_df)} intraday bars")
            print(f"Last bar: {intraday_df.index[-1]}")
            print(f"Close: ₹{intraday_df['close'].iloc[-1]:.2f}")
    except Exception as e:
        print(f"Intraday data not available: {e}")
    
    # 5. Nifty 50
    print("\n[5] NIFTY 50 Index (1 Month)")
    print("-"*80)
    
    nifty_df = fetcher.get_historical_data('NIFTY50', period='1mo', interval='1d')
    
    if not nifty_df.empty:
        print(f"Current Level: ₹{nifty_df['close'].iloc[-1]:.2f}")
        monthly_change = (nifty_df['close'].iloc[-1] - nifty_df['close'].iloc[0]) / nifty_df['close'].iloc[0] * 100
        print(f"Monthly Change: {monthly_change:+.2f}%")
        print(f"Month High: ₹{nifty_df['high'].max():.2f}")
        print(f"Month Low: ₹{nifty_df['low'].min():.2f}")
    
    return fetcher


def demo_nse_backtest():
    """Demo: Run backtest with real NSE data"""
    
    from backtesting_engine import (
        BacktestEngine,
        MovingAverageCrossoverStrategy,
        MeanReversionStrategy,
        PercentageCommission,
        PercentageSlippage
    )
    
    print("\n" + "="*80)
    print("NSE BACKTEST - Real Market Data")
    print("="*80)
    
    fetcher = NSEDataFetcher()
    
    # Symbols to backtest
    symbols = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK']
    
    for symbol in symbols:
        print(f"\n{'='*70}")
        print(f"Backtesting: {symbol}")
        print(f"{'='*70}")
        
        # Fetch 2 years of daily data
        df = fetcher.get_historical_data(symbol, period='2y', interval='1d')
        
        if df.empty:
            print(f"  No data available for {symbol}")
            continue
        
        # Prepare data for backtesting
        timestamps, prices, highs, lows, volumes = fetcher.prepare_backtest_data(df)
        
        print(f"  Data: {len(prices)} trading days")
        print(f"  Price Range: ₹{prices.min():.2f} - ₹{prices.max():.2f}")
        
        # Run backtest with MA crossover
        engine = BacktestEngine(
            initial_capital=1_000_000.0,
            commission_model=PercentageCommission(0.001),
            slippage_model=PercentageSlippage(0.0005)
        )
        
        strategy = MovingAverageCrossoverStrategy({
            'short_window': 20,
            'long_window': 50
        })
        engine.add_strategy(strategy)
        engine.load_price_data(symbol, timestamps, prices, highs, lows, volumes)
        
        results = engine.run_backtest()
        
        # Print results
        print(f"\n  Backtest Results:")
        print(f"  Initial Capital:  ₹{results['initial_capital']:>12,.2f}")
        print(f"  Final Equity:     ₹{results['final_equity']:>12,.2f}")
        print(f"  Total Return:     {results['total_return_pct']:>+12.2f}%")
        print(f"  Sharpe Ratio:     {results['sharpe_ratio']:>12.2f}")
        print(f"  Max Drawdown:     {results['max_drawdown_pct']:>11.2f}%")
        print(f"  Total Trades:     {results['total_trades']:>12}")
        
        # Compare with buy & hold
        bnh_return = (prices[-1] / prices[0] - 1) * 100
        print(f"  Buy & Hold:       {bnh_return:>+12.2f}%")
        
        # Strategy alpha
        alpha = results['total_return_pct'] - bnh_return
        print(f"  Strategy Alpha:   {alpha:>+12.2f}%")
    
    print("\n" + "="*80)
    print("✅ NSE Backtest Complete!")
    print("="*80)


if __name__ == "__main__":
    demo_nse_data()
    demo_nse_backtest()
