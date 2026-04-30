"""
Live Trading Deployment Script
Integrates trained XGBoost ensemble with real-time market data and execution
"""

import sys
sys.path.insert(0, r'V:\pylibs')

import os
import time
import json
import logging
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

from advanced_features import AdvancedFeatureEngineer
from ensemble_model import HFTEnsemble

# Try to import broker APIs
try:
    from kiteconnect import KiteConnect
    HAS_ZERODHA = True
except:
    HAS_ZERODHA = False

try:
    import yfinance as yf
    HAS_YAHOO = True
except:
    HAS_YAHOO = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class LiveTradingSystem:
    """
    Production-ready live trading system
    
    Features:
    - Real-time market data fetching
    - Feature engineering on live data
    - Model inference with confidence scoring
    - Risk management overlay
    - Trade execution (paper or live)
    - Performance tracking
    """
    
    def __init__(self, 
                 model_path: str,
                 symbol: str,
                 paper_trading: bool = True,
                 capital: float = 1_000_000.0,
                 risk_per_trade: float = 0.02,
                 max_position: int = 1000,
                 prediction_horizon: int = 10,
                 update_interval_sec: int = 5):
        
        self.symbol = symbol
        self.paper_trading = paper_trading
        self.capital = capital
        self.risk_per_trade = risk_per_trade
        self.max_position = max_position
        self.prediction_horizon = prediction_horizon
        self.update_interval = update_interval_sec

        # Load model
        logger.info(f"Loading model from {model_path}...")
        
        model_data = joblib.load(model_path)
        
        # Handle both ensemble and single model formats
        if 'models' in model_data:
            # Ensemble model format
            self.ensemble = HFTEnsemble.load(model_path)
            self.is_ensemble = True
            logger.info("Loaded ENSEMBLE model")
        elif 'model' in model_data:
            # Single XGBoost model format
            self.single_model = model_data['model']
            self.feature_names = model_data['feature_names']
            self.is_ensemble = False
            logger.info("Loaded single XGBoost model")
        else:
            raise ValueError(f"Unknown model format in {model_path}")
        
        self.feature_engineer = AdvancedFeatureEngineer()
        
        # Trading state
        self.current_position = 0
        self.entry_price = 0
        self.total_pnl = 0
        self.trades_today = 0
        self.last_prediction = None
        self.last_confidence = 0
        
        # Data buffer (store live ticks)
        self.data_buffer = []
        self.buffer_size = 500  # Need 500 ticks for some features
        
        # Trade log
        self.trade_log = []
        
        # Risk limits
        self.max_daily_loss = capital * 0.02  # 2% daily loss limit
        self.max_drawdown = capital * 0.05  # 5% max drawdown
        self.daily_pnl = 0
        self.peak_capital = capital
        
        logger.info(f"✅ System initialized:")
        logger.info(f"   Symbol: {symbol}")
        logger.info(f"   Mode: {'PAPER' if paper_trading else 'LIVE'}")
        logger.info(f"   Capital: ₹{capital:,.0f}")
        logger.info(f"   Risk/Trade: {risk_per_trade*100:.1f}%")
        logger.info(f"   Update Interval: {update_interval_sec}s")
    
    def fetch_live_data(self) -> pd.DataFrame:
        """
        Fetch live market data
        
        Options:
        1. Yahoo Finance (free, 1-min delayed)
        2. Zerodha Kite (live, requires API)
        3. CSV file (for backtesting)
        """
        if HAS_YAHOO:
            return self._fetch_yahoo_data()
        else:
            logger.warning("⚠️ No data source available. Using synthetic data.")
            return self._generate_synthetic_tick()
    
    def _fetch_yahoo_data(self) -> pd.DataFrame:
        """Fetch from Yahoo Finance"""
        try:
            ticker = f"{self.symbol}.NS" if not self.symbol.endswith('.NS') else self.symbol

            # Get recent 1-min data
            df = yf.download(ticker, period='5d', interval='1m', progress=False)

            if df.empty or len(df) < 50:
                logger.warning(f"⚠️ Insufficient Yahoo data for {ticker}")
                return None
            
            # Handle multi-level columns (newer yfinance versions)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Convert to LOB format
            lob_data = self._ohlcv_to_lob(df)
            return lob_data

        except Exception as e:
            logger.error(f"❌ Yahoo fetch error: {e}")
            return None
    
    def _ohlcv_to_lob(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Convert OHLCV to fake LOB data for model compatibility
        """
        n = len(df)
        mid = df['Close'].values
        spread = 0.05  # Default spread
        
        # Create pseudo-LOB structure
        data = {
            'bid_price_1': mid - spread/2,
            'ask_price_1': mid + spread/2,
            'bid_volume_1': df['Volume'].values // 2,
            'ask_volume_1': df['Volume'].values // 2,
            'last_trade_price': mid,
            'last_trade_volume': df['Volume'].values,
            'trade_side': np.where(df['Close'] >= df['Open'], 1, -1)
        }
        
        # Create 10 levels
        for i in range(2, 11):
            data[f'bid_price_{i}'] = mid - spread/2 - 0.05 * i
            data[f'ask_price_{i}'] = mid + spread/2 + 0.05 * i
            data[f'bid_volume_{i}'] = df['Volume'].values // (2 * i)
            data[f'ask_volume_{i}'] = df['Volume'].values // (2 * i)
        
        return pd.DataFrame(data)
    
    def _generate_synthetic_tick(self) -> pd.DataFrame:
        """Generate synthetic tick for testing"""
        base_price = 85.0  # HNGSNGBEES
        n = 100
        
        data = {
            'bid_price_1': base_price + np.random.randn(n) * 0.05 - 0.025,
            'ask_price_1': base_price + np.random.randn(n) * 0.05 + 0.025,
            'bid_volume_1': np.random.randint(100, 1000, n),
            'ask_volume_1': np.random.randint(100, 1000, n),
            'last_trade_price': base_price + np.random.randn(n) * 0.05,
            'last_trade_volume': np.random.randint(1, 100, n),
            'trade_side': np.random.choice([1, -1], n)
        }
        
        for i in range(2, 11):
            data[f'bid_price_{i}'] = data['bid_price_1'] - 0.05 * i
            data[f'ask_price_{i}'] = data['ask_price_1'] + 0.05 * i
            data[f'bid_volume_{i}'] = np.random.randint(50, 500, n)
            data[f'ask_volume_{i}'] = np.random.randint(50, 500, n)
        
        return pd.DataFrame(data)
    
    def update_data_buffer(self, new_tick: pd.DataFrame):
        """Add new tick to buffer"""
        self.data_buffer.append(new_tick)
        
        # Keep only recent ticks
        if len(self.data_buffer) > self.buffer_size:
            self.data_buffer = self.data_buffer[-self.buffer_size:]
    
    def engineer_features(self) -> Optional[np.ndarray]:
        """
        Engineer features from data buffer

        Returns:
            Feature vector or None if insufficient data
        """
        if len(self.data_buffer) < 20:  # Reduced from 100 to start faster
            return None
        
        # Concatenate buffer
        df = pd.concat(self.data_buffer, ignore_index=True)
        
        # Engineer features
        features, feature_names = self.feature_engineer.engineer_features(df)
        
        # Take last row (most recent)
        if len(features) > 0:
            return features.iloc[-1:].values
        else:
            return None
    
    def predict(self, features: np.ndarray) -> Dict:
        """
        Predict price direction
        
        Returns:
            Dictionary with prediction and confidence
        """
        # Get prediction
        if self.is_ensemble:
            pred = self.ensemble.predict(features)[0]
            proba = self.ensemble.predict_proba(features)[0]
        else:
            pred = self.single_model.predict(features)[0]
            proba = self.single_model.predict_proba(features)[0]
        
        # Map prediction to direction
        direction_map = {0: 'DOWN', 1: 'UNCHANGED', 2: 'UP'}
        direction = direction_map.get(pred, 'UNKNOWN')
        
        # Get confidence (max probability)
        confidence = np.max(proba)
        
        return {
            'direction': direction,
            'prediction': int(pred),
            'confidence': float(confidence),
            'probabilities': {
                'DOWN': float(proba[0]),
                'UNCHANGED': float(proba[1]),
                'UP': float(proba[2])
            },
            'timestamp': datetime.now().isoformat()
        }
    
    def should_trade(self, prediction: Dict, current_price: float) -> tuple:
        """
        Risk-managed trading decision
        
        Returns:
            (should_trade, action, quantity)
        """
        # Check risk limits first
        if not self._check_risk_limits():
            return False, 'HOLD', 0
        
        # Only trade if confidence is high enough
        if prediction['confidence'] < 0.6:
            return False, 'HOLD', 0
        
        # Only trade on clear UP or DOWN signals
        if prediction['direction'] == 'UNCHANGED':
            return False, 'HOLD', 0
        
        # Determine action
        if prediction['direction'] == 'UP':
            if self.current_position >= 0:
                return True, 'BUY', self._calculate_position_size(current_price)
            else:
                return True, 'CLOSE_SHORT', abs(self.current_position)
        elif prediction['direction'] == 'DOWN':
            if self.current_position <= 0:
                return True, 'SELL', self._calculate_position_size(current_price)
            else:
                return True, 'CLOSE_LONG', abs(self.current_position)
        
        return False, 'HOLD', 0
    
    def _check_risk_limits(self) -> bool:
        """Check if trading is allowed under risk limits"""
        # Daily loss limit
        if self.daily_pnl < -self.max_daily_loss:
            logger.warning("🛑 Daily loss limit hit. Trading halted.")
            return False
        
        # Drawdown limit
        if (self.peak_capital - self.capital) > self.max_drawdown:
            logger.warning("🛑 Max drawdown hit. Trading halted.")
            return False
        
        # Max trades per day (prevent overtrading)
        if self.trades_today > 50:
            logger.warning("⚠️ Max trades per day reached.")
            return False
        
        return True
    
    def _calculate_position_size(self, current_price: float) -> int:
        """Calculate position size based on risk"""
        risk_amount = self.capital * self.risk_per_trade
        position_size = int(risk_amount / current_price)
        
        # Cap at max position
        position_size = min(position_size, self.max_position)
        
        # Cap based on current capital
        max_affordable = int(self.capital * 0.9 / current_price)
        position_size = min(position_size, max_affordable)
        
        return max(1, position_size)  # At least 1 share
    
    def execute_trade(self, action: str, quantity: int, price: float) -> Dict:
        """
        Execute trade (paper or live)
        
        Returns:
            Trade result dictionary
        """
        timestamp = datetime.now().isoformat()
        
        if self.paper_trading:
            result = self._paper_trade(action, quantity, price, timestamp)
        else:
            result = self._live_trade(action, quantity, price, timestamp)
        
        # Log trade
        self.trade_log.append(result)
        self.trades_today += 1
        
        logger.info(f"📊 TRADE: {action} {quantity} @{price:.2f} | PnL: {result.get('pnl', 0):.2f}")
        
        return result
    
    def _paper_trade(self, action: str, quantity: int, price: float, timestamp: str) -> Dict:
        """Paper trading execution"""
        if action in ['BUY', 'CLOSE_SHORT']:
            # Update position
            if action == 'BUY':
                self.current_position += quantity
            else:
                self.current_position += quantity  # Closing short
            
            # Calculate PnL if closing
            pnl = 0
            if self.entry_price > 0 and action == 'CLOSE_SHORT':
                pnl = (self.entry_price - price) * quantity
            
            self.entry_price = price if self.current_position > 0 else 0
            
            return {
                'action': action,
                'quantity': quantity,
                'price': price,
                'pnl': pnl,
                'position': self.current_position,
                'timestamp': timestamp
            }
        
        elif action in ['SELL', 'CLOSE_LONG']:
            if action == 'SELL':
                self.current_position -= quantity
            else:
                self.current_position -= quantity  # Closing long
            
            pnl = 0
            if self.entry_price > 0 and action == 'CLOSE_LONG':
                pnl = (price - self.entry_price) * quantity
            
            self.entry_price = price if self.current_position < 0 else 0
            
            return {
                'action': action,
                'quantity': quantity,
                'price': price,
                'pnl': pnl,
                'position': self.current_position,
                'timestamp': timestamp
            }
    
    def _live_trade(self, action: str, quantity: int, price: float, timestamp: str) -> Dict:
        """Live trading via broker API"""
        if HAS_ZERODHA:
            # Implement Zerodha Kite execution
            pass
        else:
            logger.warning("⚠️ Live trading not implemented. Falling back to paper.")
            return self._paper_trade(action, quantity, price, timestamp)
    
    def run_live(self, duration_minutes: int = 60):
        """
        Run live trading loop
        
        Args:
            duration_minutes: How long to run (in minutes)
        """
        logger.info("="*60)
        logger.info(f"🚀 STARTING LIVE TRADING")
        logger.info(f"   Duration: {duration_minutes} minutes")
        logger.info(f"   Update Interval: {self.update_interval}s")
        logger.info("="*60)
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        iteration = 0
        
        while time.time() < end_time:
            iteration += 1
            logger.info(f"\n{'─'*40}")
            logger.info(f"Iteration {iteration}")
            
            try:
                # 1. Fetch live data
                tick_data = self.fetch_live_data()
                if tick_data is None:
                    logger.warning("⚠️ No data fetched. Skipping.")
                    time.sleep(self.update_interval)
                    continue
                
                # 2. Update buffer
                self.update_data_buffer(tick_data)
                
                # 3. Engineer features
                features = self.engineer_features()
                if features is None:
                    logger.info("⏳ Insufficient data for features. Waiting...")
                    time.sleep(self.update_interval)
                    continue
                
                # 4. Predict
                prediction = self.predict(features)
                self.last_prediction = prediction
                self.last_confidence = prediction['confidence']
                
                logger.info(f"🔮 Prediction: {prediction['direction']} "
                          f"(Confidence: {prediction['confidence']:.1%})")
                logger.info(f"   UP: {prediction['probabilities']['UP']:.1%}, "
                          f"UNCHANGED: {prediction['probabilities']['UNCHANGED']:.1%}, "
                          f"DOWN: {prediction['probabilities']['DOWN']:.1%}")
                
                # 5. Get current price
                current_price = tick_data['last_trade_price'].iloc[-1]
                
                # 6. Decide whether to trade
                should_trade, action, quantity = self.should_trade(prediction, current_price)
                
                if should_trade:
                    logger.info(f"✅ Trading signal: {action} {quantity} shares")
                    result = self.execute_trade(action, quantity, current_price)
                else:
                    logger.info(f"⏸️ HOLD (Confidence too low or risk limits)")
                
                # 7. Update PnL tracking
                if self.last_prediction:
                    self.daily_pnl += result.get('pnl', 0) if 'result' in dir() else 0
                    self.capital += result.get('pnl', 0) if 'result' in dir() else 0
                    self.peak_capital = max(self.peak_capital, self.capital)
                
                # 8. Status update
                logger.info(f"📊 Position: {self.current_position} | "
                          f"PnL: ₹{self.daily_pnl:.2f} | "
                          f"Capital: ₹{self.capital:,.0f} | "
                          f"Trades: {self.trades_today}")
                
                # Wait for next update
                time.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in trading loop: {e}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(self.update_interval)
        
        # End of session
        self._end_session()
    
    def _end_session(self):
        """End trading session and generate report"""
        logger.info("\n" + "="*60)
        logger.info("📊 TRADING SESSION COMPLETE")
        logger.info("="*60)
        
        # Summary
        logger.info(f"Total Trades: {self.trades_today}")
        logger.info(f"Final Position: {self.current_position}")
        logger.info(f"Daily PnL: ₹{self.daily_pnl:.2f}")
        logger.info(f"Final Capital: ₹{self.capital:,.0f}")
        logger.info(f"Return: {((self.capital - self.peak_capital) / self.peak_capital)*100:.2f}%")
        
        # Save trade log
        log_path = f'trade_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(log_path, 'w') as f:
            json.dump(self.trade_log, f, indent=2, default=str)
        
        logger.info(f"💾 Trade log saved to {log_path}")

# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='HFT Live Trading System')
    parser.add_argument('--model', type=str, default='output/HNGSNGBEES_ensemble.joblib',
                       help='Path to trained model')
    parser.add_argument('--symbol', type=str, default='HNGSNGBEES', help='Symbol to trade')
    parser.add_argument('--paper', action='store_true', help='Paper trading mode (default)')
    parser.add_argument('--live', action='store_true', help='Live trading mode')
    parser.add_argument('--capital', type=float, default=1000000, help='Trading capital')
    parser.add_argument('--duration', type=int, default=60, help='Duration in minutes')
    parser.add_argument('--interval', type=int, default=5, help='Update interval (seconds)')
    
    args = parser.parse_args()
    
    # Initialize system
    system = LiveTradingSystem(
        model_path=args.model,
        symbol=args.symbol,
        paper_trading=not args.live,
        capital=args.capital,
        update_interval_sec=args.interval
    )
    
    # Run live trading
    system.run_live(duration_minutes=args.duration)
