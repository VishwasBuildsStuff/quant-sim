"""
Backtesting Script for HFT Models
Tests trained models on historical data with realistic simulation
"""

import sys
sys.path.insert(0, r'V:\pylibs')
sys.path.insert(0, '.')

import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple
import logging
from tqdm import tqdm

from advanced_features import AdvancedFeatureEngineer
from ensemble_model import HFTEnsemble

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backtest.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BacktestResult:
    """Store backtesting results"""
    
    def __init__(self):
        self.trades = []
        self.equity_curve = []
        self.predictions = []
        self.actuals = []
        self.confidences = []
        
    def add_trade(self, trade: Dict):
        self.trades.append(trade)
        
    def add_equity_point(self, timestamp, equity: float):
        self.equity_curve.append({'timestamp': timestamp, 'equity': equity})
        
    def add_prediction(self, pred: int, confidence: float):
        self.predictions.append(pred)
        self.confidences.append(confidence)
        
    def add_actual(self, actual: int):
        self.actuals.append(actual)
        
    def summary(self) -> Dict:
        """Calculate summary statistics"""
        if not self.trades:
            return {'total_trades': 0, 'total_pnl': 0, 'win_rate': 0}
            
        total_trades = len(self.trades)
        winning_trades = sum(1 for t in self.trades if t['pnl'] > 0)
        losing_trades = sum(1 for t in self.trades if t['pnl'] < 0)
        
        total_pnl = sum(t['pnl'] for t in self.trades)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Accuracy
        correct_preds = sum(1 for p, a in zip(self.predictions, self.actuals) if p == a)
        accuracy = correct_preds / len(self.predictions) if self.predictions else 0
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'win_rate': win_rate,
            'accuracy': accuracy,
            'avg_confidence': np.mean(self.confidences) if self.confidences else 0
        }


class HFTBacktester:
    """
    Backtest HFT model on historical data
    
    Simulates:
    - Feature engineering on historical LOB data
    - Model predictions
    - Trade execution with realistic costs
    - PnL tracking
    """
    
    def __init__(self,
                 model_path: str,
                 data_path: str,
                 symbol: str,
                 initial_capital: float = 1_000_000,
                 transaction_cost_bps: float = 5.0,
                 slippage_bps: float = 2.0,
                 prediction_horizon: int = 10,
                 confidence_threshold: float = 0.6,
                 max_position: int = 100):
        
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.transaction_cost_bps = transaction_cost_bps
        self.slippage_bps = slippage_bps
        self.prediction_horizon = prediction_horizon
        self.confidence_threshold = confidence_threshold
        self.max_position = max_position
        
        # Load model
        logger.info(f"Loading model from {model_path}...")
        model_data = joblib.load(model_path)
        
        if 'models' in model_data:
            self.ensemble = HFTEnsemble.load(model_path)
            self.is_ensemble = True
            logger.info("✅ Loaded ENSEMBLE model")
        elif 'model' in model_data:
            self.model = model_data['model']
            self.feature_names = model_data['feature_names']
            self.is_ensemble = False
            logger.info("✅ Loaded XGBoost model")
        else:
            raise ValueError(f"Unknown model format in {model_path}")
        
        # Load data
        logger.info(f"Loading data from {data_path}...")
        self.data = pd.read_parquet(data_path)
        logger.info(f"✅ Loaded {len(self.data)} LOB snapshots")
        
        # Feature engineer
        self.feature_engineer = AdvancedFeatureEngineer()
        
        # Trading state
        self.position = 0
        self.entry_price = 0
        self.capital = initial_capital
        self.equity = initial_capital
        
        # Results
        self.results = BacktestResult()
        
    def run_backtest(self, use_recent_data: bool = True):
        """
        Run backtest on historical data
        
        Args:
            use_recent_data: If True, use most recent data (better for live models)
        """
        logger.info("\n" + "="*60)
        logger.info(f"📊 STARTING BACKTEST")
        logger.info(f"{'='*60}")
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Initial Capital: ₹{self.initial_capital:,.0f}")
        logger.info(f"Transaction Cost: {self.transaction_cost_bps} bps")
        logger.info(f"Slippage: {self.slippage_bps} bps")
        logger.info(f"Confidence Threshold: {self.confidence_threshold:.0%}")
        logger.info(f"Data Points: {len(self.data)}")
        
        # Use recent portion of data if requested
        if use_recent_data and len(self.data) > 10000:
            logger.info(f"\n📌 Using most recent 10,000 data points")
            df = self.data.tail(10000).reset_index(drop=True)
        else:
            df = self.data.reset_index(drop=True)
        
        # Prepare features and labels
        logger.info("\n🔧 Engineering features...")
        features_list = []
        labels_list = []
        
        # Calculate mid prices for labels
        mid_prices = (df['bid_price_1'].values + df['ask_price_1'].values) / 2.0
        
        # Generate labels (future price direction)
        for i in range(len(df)):
            if i + self.prediction_horizon < len(df):
                future_price = mid_prices[i + self.prediction_horizon]
                current_price = mid_prices[i]
                return_pct = (future_price - current_price) / current_price
                
                if return_pct > 0.0001:
                    label = 2  # UP
                elif return_pct < -0.0001:
                    label = 0  # DOWN
                else:
                    label = 1  # UNCHANGED
            else:
                label = 1  # Default
            
            labels_list.append(label)
        
        # Add labels to dataframe temporarily
        df['label'] = labels_list + [1] * (len(df) - len(labels_list))
        
        # Feature engineering - batch process
        logger.info("Computing features for all snapshots...")
        
        try:
            # Use the engineer_features method which works on DataFrames
            features_df, feature_names = self.feature_engineer.engineer_features(df)
            
            # Convert to numpy array
            feature_matrix = features_df.values
            
            logger.info(f"✅ Computed {len(feature_matrix)} feature vectors with {feature_matrix.shape[1]} features")
            
        except Exception as e:
            logger.error(f"Feature engineering error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self.results
        
        # Normalize features
        feature_mean = feature_matrix.mean(axis=0)
        feature_std = feature_matrix.std(axis=0) + 1e-10
        feature_matrix = (feature_matrix - feature_mean) / feature_std
        
        # Handle NaN/Inf
        feature_matrix = np.nan_to_num(feature_matrix, nan=0.0, posinf=1e10, neginf=-1e10)
        
        logger.info(f"\n🚀 Running backtest simulation...")
        
        # Trading simulation
        for i in tqdm(range(100, len(feature_matrix) - self.prediction_horizon), desc="Backtesting"):
            # Get features
            features = feature_matrix[i:i+1]
            
            # Get prediction
            if self.is_ensemble:
                pred = self.ensemble.predict(features)[0]
                proba = self.ensemble.predict_proba(features)[0]
            else:
                pred = self.model.predict(features)[0]
                proba = self.model.predict_proba(features)[0]
            
            confidence = np.max(proba)
            
            # Store prediction and actual
            self.results.add_prediction(int(pred), confidence)
            
            # Get current price
            current_price = mid_prices[i]
            
            # Trading logic
            if confidence >= self.confidence_threshold:
                if pred == 2 and self.position <= 0:  # UP signal
                    # Close short if any
                    if self.position < 0:
                        pnl = (self.entry_price - current_price) * abs(self.position)
                        cost = self._calculate_cost(current_price, abs(self.position))
                        self.capital += pnl - cost
                        self.results.add_trade({
                            'type': 'CLOSE_SHORT',
                            'price': current_price,
                            'quantity': abs(self.position),
                            'pnl': pnl - cost,
                            'confidence': confidence,
                            'index': i
                        })
                    
                    # Open long
                    position_size = min(self.max_position, int(self.capital * 0.1 / current_price))
                    if position_size > 0:
                        cost = self._calculate_cost(current_price, position_size)
                        self.capital -= cost
                        self.position = position_size
                        self.entry_price = current_price
                        
                elif pred == 0 and self.position >= 0:  # DOWN signal
                    # Close long if any
                    if self.position > 0:
                        pnl = (current_price - self.entry_price) * self.position
                        cost = self._calculate_cost(current_price, self.position)
                        self.capital += pnl - cost
                        self.results.add_trade({
                            'type': 'CLOSE_LONG',
                            'price': current_price,
                            'quantity': self.position,
                            'pnl': pnl - cost,
                            'confidence': confidence,
                            'index': i
                        })
                        self.position = 0
                    
                    # Open short
                    position_size = min(self.max_position, int(self.capital * 0.1 / current_price))
                    if position_size > 0:
                        cost = self._calculate_cost(current_price, position_size)
                        self.capital -= cost
                        self.position = -position_size
                        self.entry_price = current_price
            
            # Track actual outcome
            if i + self.prediction_horizon < len(df):
                actual = df.iloc[i + self.prediction_horizon]['label']
                self.results.add_actual(actual)
            
            # Update equity (mark to market)
            if self.position != 0:
                if self.position > 0:
                    unrealized_pnl = (current_price - self.entry_price) * self.position
                else:
                    unrealized_pnl = (self.entry_price - current_price) * abs(self.position)
                self.equity = self.capital + unrealized_pnl
            else:
                self.equity = self.capital
            
            self.results.add_equity_point(i, self.equity)
        
        # Close any open positions at end
        if self.position != 0:
            final_price = mid_prices[-1]
            if self.position > 0:
                pnl = (final_price - self.entry_price) * self.position
            else:
                pnl = (self.entry_price - final_price) * abs(self.position)
            
            cost = self._calculate_cost(final_price, abs(self.position))
            self.capital += pnl - cost
            
            self.results.add_trade({
                'type': 'FORCE_CLOSE',
                'price': final_price,
                'quantity': abs(self.position),
                'pnl': pnl - cost,
                'confidence': 0,
                'index': len(feature_matrix) - 1
            })
            
            self.position = 0
            self.equity = self.capital
        
        # Print results
        self._print_results()
        
        return self.results
    
    def _calculate_cost(self, price: float, quantity: int) -> float:
        """Calculate transaction costs"""
        trade_value = price * quantity
        transaction_cost = trade_value * (self.transaction_cost_bps / 10000)
        slippage = trade_value * (self.slippage_bps / 10000)
        return transaction_cost + slippage
    
    def _print_results(self):
        """Print backtest results"""
        summary = self.results.summary()
        
        logger.info("\n" + "="*60)
        logger.info("📊 BACKTEST RESULTS")
        logger.info("="*60)
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Period: {len(self.results.trades)} trading decisions")
        logger.info(f"")
        logger.info(f"💰 Capital Performance:")
        logger.info(f"  Initial Capital: ₹{self.initial_capital:,.0f}")
        logger.info(f"  Final Capital: ₹{self.equity:,.2f}")
        logger.info(f"  Total PnL: ₹{self.equity - self.initial_capital:,.2f}")
        logger.info(f"  Return: {((self.equity - self.initial_capital) / self.initial_capital * 100):.2f}%")
        logger.info(f"")
        logger.info(f"📈 Trading Performance:")
        logger.info(f"  Total Trades: {summary['total_trades']}")
        logger.info(f"  Winning Trades: {summary['winning_trades']}")
        logger.info(f"  Losing Trades: {summary['losing_trades']}")
        logger.info(f"  Win Rate: {summary['win_rate']:.1%}")
        logger.info(f"  Avg PnL per Trade: ₹{summary['avg_pnl']:.2f}")
        logger.info(f"")
        logger.info(f"🎯 Prediction Accuracy:")
        logger.info(f"  Accuracy: {summary['accuracy']:.1%}")
        logger.info(f"  Avg Confidence: {summary['avg_confidence']:.1%}")
        logger.info(f"")
        logger.info(f"💾 Results saved to: backtest_{self.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        
        # Save results
        import json
        results_dict = {
            'summary': summary,
            'trades': self.results.trades,
            'equity_curve': self.results.equity_curve[-100:]  # Last 100 points
        }
        
        filename = f"backtest_{self.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(results_dict, f, indent=2, default=str)
        
        logger.info(f"✅ Saved to {filename}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='HFT Model Backtester')
    parser.add_argument('--model', type=str, default='output/RELIANCE_ensemble.joblib',
                       help='Path to trained model')
    parser.add_argument('--data', type=str, default='data/RELIANCE_live.parquet',
                       help='Path to historical data')
    parser.add_argument('--symbol', type=str, default='RELIANCE', help='Symbol')
    parser.add_argument('--capital', type=float, default=1000000, help='Initial capital')
    parser.add_argument('--horizon', type=int, default=10, help='Prediction horizon')
    parser.add_argument('--confidence', type=float, default=0.6, help='Confidence threshold')
    parser.add_argument('--max-position', type=int, default=100, help='Max position size')
    parser.add_argument('--transaction-cost', type=float, default=5.0, help='Transaction cost (bps)')
    parser.add_argument('--slippage', type=float, default=2.0, help='Slippage (bps)')
    
    args = parser.parse_args()
    
    # Check files exist
    if not os.path.exists(args.model):
        logger.error(f"❌ Model not found: {args.model}")
        return
    
    if not os.path.exists(args.data):
        logger.error(f"❌ Data not found: {args.data}")
        return
    
    # Run backtest
    backtester = HFTBacktester(
        model_path=args.model,
        data_path=args.data,
        symbol=args.symbol,
        initial_capital=args.capital,
        transaction_cost_bps=args.transaction_cost,
        slippage_bps=args.slippage,
        prediction_horizon=args.horizon,
        confidence_threshold=args.confidence,
        max_position=args.max_position
    )
    
    backtester.run_backtest()


if __name__ == '__main__':
    main()
