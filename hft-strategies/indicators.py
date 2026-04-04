"""
Technical Indicators Library
Standard technical analysis indicators for trading strategies

Includes:
- Moving Averages (SMA, EMA, WMA)
- Momentum (RSI, MACD, Stochastic)
- Volatility (Bollinger Bands, ATR, Keltner Channel)
- Volume indicators
- Pattern detection
"""

import numpy as np
from typing import Tuple, Optional, List
from dataclasses import dataclass
from scipy import stats
from scipy.signal import argrelextrema


class MovingAverage:
    """Moving average calculations"""
    
    @staticmethod
    def sma(prices: np.ndarray, period: int) -> np.ndarray:
        """Simple Moving Average"""
        sma = np.full_like(prices, np.nan)
        for i in range(period - 1, len(prices)):
            sma[i] = np.mean(prices[i - period + 1:i + 1])
        return sma
    
    @staticmethod
    def ema(prices: np.ndarray, period: int) -> np.ndarray:
        """Exponential Moving Average"""
        ema = np.full_like(prices, np.nan)
        multiplier = 2.0 / (period + 1)
        
        # Initialize with SMA
        ema[period - 1] = np.mean(prices[:period])
        
        for i in range(period, len(prices)):
            ema[i] = (prices[i] - ema[i-1]) * multiplier + ema[i-1]
        
        return ema
    
    @staticmethod
    def wma(prices: np.ndarray, period: int) -> np.ndarray:
        """Weighted Moving Average"""
        wma = np.full_like(prices, np.nan)
        weights = np.arange(1, period + 1)
        
        for i in range(period - 1, len(prices)):
            wma[i] = np.sum(prices[i - period + 1:i + 1] * weights) / np.sum(weights)
        
        return wma


class MomentumIndicators:
    """Momentum-based technical indicators"""
    
    @staticmethod
    def rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
        """
        Relative Strength Index (RSI)
        Measures speed and magnitude of price changes
        Range: 0-100, overbought > 70, oversold < 30
        """
        rsi = np.full_like(prices, np.nan, dtype=float)
        
        if len(prices) < period + 1:
            return rsi
        
        # Calculate price changes
        deltas = np.diff(prices)
        
        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # Initialize with average
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        if avg_loss == 0:
            rsi[period] = 100
        else:
            rs = avg_gain / avg_loss
            rsi[period] = 100 - (100 / (1 + rs))
        
        # Smoothed averages
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            
            if avg_loss == 0:
                rsi[i + 1] = 100
            else:
                rs = avg_gain / avg_loss
                rsi[i + 1] = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def macd(prices: np.ndarray, 
             fast_period: int = 12, 
             slow_period: int = 26, 
             signal_period: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Moving Average Convergence Divergence (MACD)
        Returns: (macd_line, signal_line, histogram)
        """
        ema_fast = MovingAverage.ema(prices, fast_period)
        ema_slow = MovingAverage.ema(prices, slow_period)
        
        macd_line = ema_fast - ema_slow
        
        # Signal line is EMA of MACD
        # Skip NaN values
        valid_macd = macd_line[~np.isnan(macd_line)]
        signal_values = MovingAverage.ema(valid_macd, signal_period)
        
        signal_line = np.full_like(prices, np.nan)
        signal_line[-len(signal_values):] = signal_values
        
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def stochastic(prices: np.ndarray, 
                   highs: np.ndarray, 
                   lows: np.ndarray,
                   k_period: int = 14, 
                   d_period: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        """
        Stochastic Oscillator
        Returns: (%K, %D)
        """
        k_line = np.full_like(prices, np.nan, dtype=float)
        
        for i in range(k_period - 1, len(prices)):
            recent_high = np.max(highs[i - k_period + 1:i + 1])
            recent_low = np.min(lows[i - k_period + 1:i + 1])
            
            if recent_high != recent_low:
                k_line[i] = 100 * (prices[i] - recent_low) / (recent_high - recent_low)
            else:
                k_line[i] = 50
        
        # %D is SMA of %K
        d_line = MovingAverage.sma(k_line, d_period)
        
        return k_line, d_line
    
    @staticmethod
    def williams_r(prices: np.ndarray, 
                   highs: np.ndarray, 
                   lows: np.ndarray, 
                   period: int = 14) -> np.ndarray:
        """Williams %R (similar to Stochastic but inverted)"""
        wr = np.full_like(prices, np.nan, dtype=float)
        
        for i in range(period - 1, len(prices)):
            recent_high = np.max(highs[i - period + 1:i + 1])
            recent_low = np.min(lows[i - period + 1:i + 1])
            
            if recent_high != recent_low:
                wr[i] = -100 * (recent_high - prices[i]) / (recent_high - recent_low)
        
        return wr


class VolatilityIndicators:
    """Volatility-based indicators"""
    
    @staticmethod
    def bollinger_bands(prices: np.ndarray, 
                        period: int = 20, 
                        num_std: float = 2.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Bollinger Bands
        Returns: (upper_band, middle_band, lower_band)
        """
        middle_band = MovingAverage.sma(prices, period)
        
        bands = np.full_like(prices, np.nan, dtype=float)
        for i in range(period - 1, len(prices)):
            bands[i] = np.std(prices[i - period + 1:i + 1])
        
        upper_band = middle_band + num_std * bands
        lower_band = middle_band - num_std * bands
        
        return upper_band, middle_band, lower_band
    
    @staticmethod
    def atr(highs: np.ndarray, 
            lows: np.ndarray, 
            closes: np.ndarray, 
            period: int = 14) -> np.ndarray:
        """
        Average True Range (ATR)
        Measures market volatility
        """
        true_ranges = np.zeros(len(highs))
        true_ranges[0] = highs[0] - lows[0]
        
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_ranges[i] = tr
        
        # Wilder's smoothing (similar to EMA)
        atr = np.full_like(closes, np.nan, dtype=float)
        atr[period - 1] = np.mean(true_ranges[:period])
        
        for i in range(period, len(true_ranges)):
            atr[i] = (atr[i-1] * (period - 1) + true_ranges[i]) / period
        
        return atr
    
    @staticmethod
    def keltner_channel(highs: np.ndarray, 
                        lows: np.ndarray, 
                        closes: np.ndarray,
                        ema_period: int = 20, 
                        atr_period: int = 10, 
                        multiplier: float = 2.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Keltner Channels (EMA-based bands using ATR)
        Returns: (upper, middle, lower)
        """
        middle = MovingAverage.ema(closes, ema_period)
        atr_values = VolatilityIndicators.atr(highs, lows, closes, atr_period)
        
        upper = middle + multiplier * atr_values
        lower = middle - multiplier * atr_values
        
        return upper, middle, lower


class VolumeIndicators:
    """Volume-based indicators"""
    
    @staticmethod
    def obv(closes: np.ndarray, volumes: np.ndarray) -> np.ndarray:
        """
        On-Balance Volume (OBV)
        Cumulative volume indicator
        """
        obv = np.zeros(len(closes))
        obv[0] = volumes[0]
        
        for i in range(1, len(closes)):
            if closes[i] > closes[i-1]:
                obv[i] = obv[i-1] + volumes[i]
            elif closes[i] < closes[i-1]:
                obv[i] = obv[i-1] - volumes[i]
            else:
                obv[i] = obv[i-1]
        
        return obv
    
    @staticmethod
    def vwap(highs: np.ndarray, 
             lows: np.ndarray, 
             closes: np.ndarray, 
             volumes: np.ndarray) -> np.ndarray:
        """
        Volume Weighted Average Price (VWAP)
        Intraday benchmark price
        """
        typical_prices = (highs + lows + closes) / 3
        cumulative_vp = np.cumsum(typical_prices * volumes)
        cumulative_v = np.cumsum(volumes)
        
        vwap = cumulative_vp / cumulative_v
        return vwap
    
    @staticmethod
    def money_flow_index(highs: np.ndarray, 
                         lows: np.ndarray, 
                         closes: np.ndarray, 
                         volumes: np.ndarray, 
                         period: int = 14) -> np.ndarray:
        """
        Money Flow Index (MFI)
        Volume-weighted RSI
        """
        typical_prices = (highs + lows + closes) / 3
        money_flow = typical_prices * volumes
        
        mfi = np.full_like(closes, np.nan, dtype=float)
        
        for i in range(period, len(closes)):
            positive_flow = 0
            negative_flow = 0
            
            for j in range(i - period + 1, i + 1):
                if typical_prices[j] > typical_prices[j-1]:
                    positive_flow += money_flow[j]
                else:
                    negative_flow += money_flow[j]
            
            if negative_flow == 0:
                mfi[i] = 100
            else:
                money_ratio = positive_flow / negative_flow
                mfi[i] = 100 - (100 / (1 + money_ratio))
        
        return mfi


class PatternDetection:
    """Detect common price patterns"""
    
    @staticmethod
    def support_resistance(prices: np.ndarray, 
                           order: int = 5) -> Tuple[List[int], List[int]]:
        """
        Find support and resistance levels using local extrema
        Returns: (support_indices, resistance_indices)
        """
        # Find local minima (support)
        support_indices = argrelextrema(prices, np.less, order=order)[0]
        
        # Find local maxima (resistance)
        resistance_indices = argrelextrema(prices, np.greater, order=order)[0]
        
        return support_indices.tolist(), resistance_indices.tolist()
    
    @staticmethod
    def trend_direction(prices: np.ndarray, period: int = 20) -> float:
        """
        Calculate trend direction and strength
        Returns: Value between -1 (strong downtrend) and 1 (strong uptrend)
        """
        if len(prices) < period + 1:
            return 0.0
        
        recent_prices = prices[-period:]
        x = np.arange(len(recent_prices))
        
        # Linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, recent_prices)
        
        # Normalize slope by price level
        normalized_slope = slope / np.mean(recent_prices)
        
        # Scale by R-squared to account for trend quality
        return normalized_slope * (r_value ** 2) * 100
    
    @staticmethod
    def is_double_top(prices: np.ndarray, tolerance: float = 0.02) -> bool:
        """Detect double top pattern"""
        if len(prices) < 20:
            return False
        
        peaks, _ = PatternDetection.support_resistance(prices)
        
        if len(peaks) < 2:
            return False
        
        # Check if two peaks are at similar levels
        for i in range(len(peaks) - 1):
            for j in range(i + 1, len(peaks)):
                peak1 = prices[peaks[i]]
                peak2 = prices[peaks[j]]
                
                if abs(peak1 - peak2) / peak1 < tolerance:
                    return True
        
        return False
    
    @staticmethod
    def is_head_and_shoulders(prices: np.ndarray, 
                              highs: np.ndarray, 
                              tolerance: float = 0.03) -> bool:
        """Detect head and shoulders pattern"""
        if len(prices) < 30:
            return False
        
        _, resistance_indices = PatternDetection.support_resistance(highs)
        
        if len(resistance_indices) < 3:
            return False
        
        # Look for three peaks with middle one highest
        for i in range(len(resistance_indices) - 2):
            left = highs[resistance_indices[i]]
            head = highs[resistance_indices[i + 1]]
            right = highs[resistance_indices[i + 2]]
            
            # Head should be highest, shoulders similar
            if (head > left and head > right and 
                abs(left - right) / left < tolerance):
                return True
        
        return False


class TechnicalAnalysis:
    """
    Comprehensive technical analysis wrapper
    Calculates all indicators at once
    """
    
    def __init__(self, lookback: int = 100):
        self.lookback = lookback
        self.prices = []
        self.highs = []
        self.lows = []
        self.volumes = []
    
    def update(self, price: float, high: float, low: float, volume: float):
        """Add new price bar"""
        self.prices.append(price)
        self.highs.append(high)
        self.lows.append(low)
        self.volumes.append(volume)
        
        # Keep only lookback period
        if len(self.prices) > self.lookback:
            self.prices.pop(0)
            self.highs.pop(0)
            self.lows.pop(0)
            self.volumes.pop(0)
    
    def calculate_all(self) -> dict:
        """Calculate all technical indicators"""
        if len(self.prices) < 30:
            return {}
        
        prices = np.array(self.prices)
        highs = np.array(self.highs)
        lows = np.array(self.lows)
        volumes = np.array(self.volumes)
        
        result = {
            'price': prices[-1],
            'returns': np.diff(np.log(prices)) if len(prices) > 1 else np.array([0]),
        }
        
        # Moving averages
        if len(prices) >= 50:
            result['sma_20'] = MovingAverage.sma(prices, 20)[-1]
            result['sma_50'] = MovingAverage.sma(prices, 50)[-1]
            result['ema_12'] = MovingAverage.ema(prices, 12)[-1]
            result['ema_26'] = MovingAverage.ema(prices, 26)[-1]
        
        # Momentum
        if len(prices) >= 15:
            result['rsi_14'] = MomentumIndicators.rsi(prices, 14)[-1]
        
        if len(prices) >= 27:
            macd_line, signal, hist = MomentumIndicators.macd(prices)
            result['macd'] = macd_line[-1]
            result['macd_signal'] = signal[-1]
            result['macd_histogram'] = hist[-1]
        
        # Volatility
        if len(prices) >= 20:
            upper, middle, lower = VolatilityIndicators.bollinger_bands(prices)
            result['bb_upper'] = upper[-1]
            result['bb_middle'] = middle[-1]
            result['bb_lower'] = lower[-1]
            result['bb_width'] = (upper[-1] - lower[-1]) / middle[-1] if middle[-1] != 0 else 0
        
        if len(prices) >= 15:
            result['atr_14'] = VolatilityIndicators.atr(highs, lows, prices, 14)[-1]
        
        # Volume
        if len(prices) >= 15:
            result['vwap'] = VolumeIndicators.vwap(highs, lows, prices, volumes)[-1]
            result['obv'] = VolumeIndicators.obv(prices, volumes)[-1]
        
        # Trend
        result['trend'] = PatternDetection.trend_direction(prices)
        
        return result
