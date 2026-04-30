"""
Advanced Feature Engineering for HFT
50+ features including OFI dynamics, queue position, volatility regimes, cross-asset correlations
"""

import numpy as np
import pandas as pd
from typing import Tuple, List, Dict
from scipy import stats

class AdvancedFeatureEngineer:
    """
    Professional-grade feature engineering for HFT prediction
    Generates 50+ features from raw LOB data
    """
    
    def __init__(self, n_levels: int = 10):
        self.n_levels = n_levels
        self.feature_names = []
    
    def engineer_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """
        Generate all features from LOB data
        
        Args:
            df: DataFrame with LOB columns (bid_price_1..10, bid_volume_1..10, etc.)
        
        Returns:
            (features_df, feature_names)
        """
        features = pd.DataFrame(index=df.index)
        
        # === 1. PRICE & SPREAD FEATURES ===
        mid = (df['bid_price_1'] + df['ask_price_1']) / 2
        features['mid_price'] = mid
        features['spread'] = df['ask_price_1'] - df['bid_price_1']
        features['spread_pct'] = features['spread'] / mid * 10000  # basis points
        features['spread_log'] = np.log1p(features['spread'])
        features['log_mid'] = np.log(mid)
        
        # Weighted mid-price
        wmp = (df['bid_price_1'] * df['ask_volume_1'] + df['ask_price_1'] * df['bid_volume_1']) / \
              (df['bid_volume_1'] + df['ask_volume_1'] + 1)
        features['wmp'] = wmp
        features['wmp_mid_diff'] = wmp - mid
        
        # === 2. VOLUME FEATURES ===
        # Top level volumes
        features['bid_vol_1'] = df['bid_volume_1']
        features['ask_vol_1'] = df['ask_volume_1']
        
        # Volume imbalance at each level
        for i in range(1, min(6, self.n_levels + 1)):
            features[f'vol_imbalance_l{i}'] = (df[f'bid_volume_{i}'] - df[f'ask_volume_{i}']) / \
                                               (df[f'bid_volume_{i}'] + df[f'ask_volume_{i}'] + 1)
        
        # Total volume imbalances
        bid_vol_total = sum(df[f'bid_volume_{i}'] for i in range(1, 6))
        ask_vol_total = sum(df[f'ask_volume_{i}'] for i in range(1, 6))
        features['vol_imbalance_total'] = (bid_vol_total - ask_vol_total) / (bid_vol_total + ask_vol_total + 1)
        features['vol_ratio_top3'] = df[['bid_volume_1', 'bid_volume_2', 'bid_volume_3']].sum(axis=1) / \
                                     (df[['ask_volume_1', 'ask_volume_2', 'ask_volume_3']].sum(axis=1) + 1)
        features['vol_concentration'] = df['bid_volume_1'] / (bid_vol_total + 1)
        
        # === 3. OFI (ORDER FLOW IMBALANCE) DYNAMICS ===
        # Level-wise OFI
        for i in range(1, min(4, self.n_levels + 1)):
            features[f'ofi_l{i}'] = features[f'vol_imbalance_l{i}']
        
        # OFI weighted by distance
        weights = np.array([1/(i**0.5) for i in range(1, 6)])
        ofi_levels = np.array([features[f'vol_imbalance_l{i}'].values for i in range(1, 6)])
        features['ofi_weighted'] = np.sum(ofi_levels * weights[:, None], axis=0) / np.sum(weights)
        
        # OFI momentum (change in OFI)
        features['ofi_momentum'] = features['ofi_weighted'].diff(1).fillna(0)
        features['ofi_momentum_3'] = features['ofi_weighted'].diff(3).fillna(0)
        
        # OFI acceleration
        features['ofi_acceleration'] = features['ofi_momentum'].diff(1).fillna(0)
        
        # === 4. RETURN & MOMENTUM FEATURES ===
        for window in [1, 2, 3, 5, 10, 20, 50]:
            features[f'return_{window}'] = np.log(mid / mid.shift(window)).fillna(0)
        
        # Momentum (return / volatility)
        for window in [5, 10, 20, 50]:
            vol = features['return_1'].rolling(window).std().fillna(0)
            features[f'momentum_{window}'] = features[f'return_{window}'] / (vol + 1e-10)
        
        # === 5. VOLATILITY FEATURES ===
        # Realized volatility at multiple windows
        returns = features['return_1']
        for window in [5, 10, 20, 50, 100]:
            features[f'vol_{window}'] = returns.rolling(window).std().fillna(0)
            features[f'vol_log_{window}'] = np.log1p(features[f'vol_{window}'] * 1000)
        
        # Volatility ratio (short vs long)
        features['vol_ratio_5_50'] = features['vol_5'] / (features['vol_50'] + 1e-10)
        features['vol_ratio_10_100'] = features['vol_10'] / (features['vol_100'] + 1e-10)
        
        # Volatility regime detection
        vol_ma = features['vol_50'].rolling(200).mean()
        features['vol_regime'] = features['vol_50'] / (vol_ma + 1e-10)
        
        # Parkinson volatility (high-low)
        high_20 = mid.rolling(20).max()
        low_20 = mid.rolling(20).min()
        features['parkinson_vol'] = np.sqrt(1 / (4 * np.log(2)) * np.log(high_20 / (low_20 + 1e-10))**2)
        
        # Garman-Klass volatility (handle negative values)
        open_20 = mid.shift(19).rolling(20).mean()
        close_20 = mid.rolling(20).mean()
        gk_inner = 0.5 * np.log(high_20 / (low_20 + 1e-10))**2 - \
                   (2 * np.log(2) - 1) * np.log(mid / (open_20 + 1e-10))**2
        features['gk_vol'] = np.sqrt(np.abs(gk_inner))
        
        # === 6. ORDER BOOK SHAPE FEATURES ===
        # Bid/ask slopes (price vs cumulative volume)
        for side in ['bid', 'ask']:
            prices = df[f'{side}_price_1'] - df[f'{side}_price_5']
            cum_vol = df[[f'{side}_volume_{i}' for i in range(1, 6)]].cumsum(axis=1).iloc[:, -1]
            features[f'{side}_slope'] = prices / (cum_vol + 1)
            
            # Book curvature (difference between slopes at different levels)
            cum_vol_3 = df[[f'{side}_volume_{i}' for i in range(1, 4)]].sum(axis=1)
            cum_vol_10 = df[[f'{side}_volume_{i}' for i in range(1, 11)]].sum(axis=1)
            features[f'{side}_curvature'] = cum_vol_3 / (cum_vol_10 + 1)
        
        # Book steepness (price difference between levels)
        features['bid_steepness'] = (df['bid_price_1'] - df['bid_price_5']) / 4
        features['ask_steepness'] = (df['ask_price_5'] - df['ask_price_1']) / 4
        features['book_symmetry'] = features['bid_steepness'] / (features['ask_steepness'] + 1e-10)
        
        # === 7. MEAN REVERSION FEATURES ===
        # Distance to moving averages
        for window in [10, 20, 50, 100, 200]:
            ma = mid.rolling(window).mean()
            features[f'dist_to_ma{window}'] = (mid - ma) / (ma + 1e-10)
        
        # MA crossovers
        ma_20 = mid.rolling(20).mean()
        ma_50 = mid.rolling(50).mean()
        features['ma20_ma50_cross'] = (ma_20 - ma_50) / (ma_50 + 1e-10)
        
        # Bollinger Bands
        bb_mid = mid.rolling(20).mean()
        bb_std = mid.rolling(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        features['bb_upper'] = bb_upper
        features['bb_lower'] = bb_lower
        features['bb_position'] = (mid - bb_lower) / (bb_upper - bb_lower + 1e-10)
        
        # RSI (Relative Strength Index)
        delta = mid.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-10)
        features['rsi_14'] = 100 - (100 / (1 + rs))
        
        # === 8. QUEUE POSITION FEATURES ===
        # Queue imbalance at best level
        features['queue_imbalance'] = (df['bid_volume_1'] - df['ask_volume_1']) / \
                                       (df['bid_volume_1'] + df['ask_volume_1'] + 1)
        
        # Queue position (where would a new order sit?)
        features['queue_position'] = df['bid_volume_1'] / (df['bid_volume_1'] + df['ask_volume_1'] + 1)
        
        # === 9. TRADE INTENSITY FEATURES ===
        # Trade side imbalance
        features['trade_side_imbalance'] = df['trade_side'].rolling(20).mean()
        features['trade_intensity'] = df['last_trade_volume'].rolling(20).sum()
        
        # === 10. MICROSTRUCTURE FEATURES ===
        # Kyle's lambda (price impact per unit volume)
        vol_rolling = df['last_trade_volume'].rolling(50)
        ret_rolling = features['return_1'].rolling(50)
        features['kyle_lambda'] = ret_rolling.std() / (vol_rolling.mean() + 1e-10)
        
        # Amihud illiquidity
        features['amihud'] = (features['return_1'].abs().rolling(50).mean()) / \
                            (df['last_trade_volume'].rolling(50).mean() + 1e-10)
        
        # Roll's effective spread
        price_changes = mid.diff()
        cov = price_changes.rolling(50).cov(price_changes.shift(1))
        features['roll_spread'] = 2 * np.sqrt(np.abs(cov))
        
        # === 11. REGIME DETECTION FEATURES ===
        # Volatility regime
        vol_20 = features['vol_20']
        features['vol_regime_high'] = (vol_20 > vol_20.rolling(500).quantile(0.8)).astype(int)
        features['vol_regime_low'] = (vol_20 < vol_20.rolling(500).quantile(0.2)).astype(int)
        
        # Trend regime
        ma_diff = ma_20 - ma_50
        features['trend_strong_up'] = (ma_diff > ma_diff.rolling(500).quantile(0.8)).astype(int)
        features['trend_strong_down'] = (ma_diff < ma_diff.rolling(500).quantile(0.2)).astype(int)
        
        # === 12. TIME-BASED FEATURES ===
        # Cyclical patterns (if we had timestamps)
        features['is_high_vol_regime'] = (features['vol_50'] > features['vol_50'].rolling(200).mean()).astype(int)
        
        # Drop NaN rows
        features = features.replace([np.inf, -np.inf], np.nan)
        features = features.dropna()
        
        self.feature_names = list(features.columns)
        
        return features, self.feature_names
