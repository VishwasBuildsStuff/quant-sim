"""
Terminal Charting Module
Generates line and candlestick charts in the terminal using plotext
"""

import sys
sys.path.insert(0, r'V:\pylibs')

import plotext as plt
import numpy as np
from datetime import datetime, timedelta
from typing import List, Tuple

class TerminalCharts:
    """
    Generate terminal-compatible charts (line and candlestick)
    """
    
    def __init__(self):
        # Generate realistic OHLCV data
        self.ohlcv = self._generate_ohlcv_data()
        self.price_history = [d['close'] for d in self.ohlcv]
        self.dates = [d['date'] for d in self.ohlcv]
    
    def _generate_ohlcv_data(self, n: int = 100) -> List[dict]:
        """Generate realistic OHLCV data"""
        data = []
        price = 2450.0
        
        for i in range(n):
            # Random walk with mean reversion
            change = np.random.randn() * 5
            mean_rev = (2450.0 - price) * 0.01
            price += change + mean_rev
            
            # OHLC
            open_p = price
            high = price + abs(np.random.randn() * 8)
            low = price - abs(np.random.randn() * 8)
            close = price + np.random.randn() * 3
            
            # Ensure OHLC consistency
            high = max(open_p, close, high)
            low = min(open_p, close, low)
            
            volume = np.random.randint(100000, 5000000)
            
            date = (datetime.now() - timedelta(minutes=n-i)).strftime("%H:%M")
            
            data.append({
                'date': date,
                'open': round(open_p, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': volume
            })
        
        return data
    
    def get_line_chart(self, symbol: str = "RELIANCE", width: int = 80, height: int = 20) -> str:
        """
        Generate a single line chart (closing prices over time)
        
        Returns:
            String containing the chart in terminal format
        """
        plt.clf()
        plt.plotsize(width, height)
        
        # Use last 50 data points for line chart
        recent = self.ohlcv[-50:]
        dates = [d['date'] for d in recent]
        closes = [d['close'] for d in recent]
        
        plt.plot(dates, closes, marker='dot', label=symbol)
        plt.title(f"{symbol} - Closing Price (Last 50 Ticks)", color='cyan')
        plt.xlabel("Time")
        plt.ylabel("Price (₹)")
        plt.grid(True)
        
        # Get the chart as string
        chart_str = plt.build()
        return chart_str
    
    def get_candlestick_chart(self, symbol: str = "RELIANCE", width: int = 80, height: int = 20) -> str:
        """
        Generate a candlestick chart
        
        Returns:
            String containing the chart in terminal format
        """
        plt.clf()
        plt.plotsize(width, height)
        
        # Use last 40 candles for candlestick chart
        recent = self.ohlcv[-40:]
        
        dates = [d['date'] for d in recent]
        opens = [d['open'] for d in recent]
        closes = [d['close'] for d in recent]
        highs = [d['high'] for d in recent]
        lows = [d['low'] for d in recent]
        
        plt.candlestick(opens, closes, lows, highs, labels=dates)
        plt.title(f"{symbol} - Candlestick Chart (Last 40 Ticks)", color='yellow')
        plt.xlabel("Time")
        plt.ylabel("Price (₹)")
        plt.grid(True)
        
        # Get the chart as string
        chart_str = plt.build()
        return chart_str
    
    def get_volume_chart(self, symbol: str = "RELIANCE", width: int = 80, height: int = 12) -> str:
        """
        Generate a volume bar chart
        
        Returns:
            String containing the chart in terminal format
        """
        plt.clf()
        plt.plotsize(width, height)
        
        # Use last 30 data points
        recent = self.ohlcv[-30:]
        dates = [d['date'] for d in recent]
        volumes = [d['volume'] / 1000000 for d in recent]  # Convert to millions
        
        plt.bar(dates, volumes, label="Volume (M)")
        plt.title(f"{symbol} - Trading Volume (Last 30 Ticks)", color='green')
        plt.xlabel("Time")
        plt.ylabel("Volume (M)")
        plt.grid(True)
        
        chart_str = plt.build()
        return chart_str


def test_charts():
    """Test function to show all chart types"""
    charts = TerminalCharts()
    
    print("="*80)
    print("LINE CHART - CLOSING PRICES")
    print("="*80)
    print(charts.get_line_chart())
    
    print("\n" + "="*80)
    print("CANDLESTICK CHART")
    print("="*80)
    print(charts.get_candlestick_chart())
    
    print("\n" + "="*80)
    print("VOLUME CHART")
    print("="*80)
    print(charts.get_volume_chart())


if __name__ == '__main__':
    test_charts()
