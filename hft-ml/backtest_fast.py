"""
Fast Backtesting Script for HFT Models
Vectorized predictions for quick backtesting
"""

import sys
sys.path.insert(0, r'V:\pylibs')
sys.path.insert(0, '.')

import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
import logging

from advanced_features import AdvancedFeatureEngineer
from ensemble_model import HFTEnsemble

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backtest_fast.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_fast_backtest(
    model_path: str = 'output/RELIANCE_ensemble.joblib',
    data_path: str = 'data/RELIANCE_live.parquet',
    symbol: str = 'RELIANCE',
    initial_capital: float = 1_000_000,
    confidence_threshold: float = 0.6,
    prediction_horizon: int = 10
):
    """
    Fast backtest with vectorized operations
    """
    
    logger.info("\n" + "="*60)
    logger.info("📊 FAST BACKTEST")
    logger.info("="*60)
    
    # Load model
    logger.info(f"Loading model: {model_path}")
    model_data = joblib.load(model_path)
    
    if 'models' in model_data:
        ensemble = HFTEnsemble.load(model_path)
        is_ensemble = True
        logger.info("✅ ENSEMBLE model loaded")
    elif 'model' in model_data:
        # Single model (XGBoost)
        model = model_data['model']
        feature_mean = model_data.get('feature_mean')
        feature_std = model_data.get('feature_std')
        is_ensemble = False
        logger.info("✅ XGBoost model loaded")
    else:
        logger.error("❌ Unknown model format")
        return
    
    # Load data
    logger.info(f"Loading data: {data_path}")
    df = pd.read_parquet(data_path)
    logger.info(f"✅ Loaded {len(df)} snapshots")
    
    # Use recent data
    if len(df) > 5000:
        df = df.tail(5000).reset_index(drop=True)
        logger.info(f"📌 Using most recent 5,000 points")
    
    # Engineer features
    logger.info("\n🔧 Engineering features...")
    feature_engineer = AdvancedFeatureEngineer()
    features_df, feature_names = feature_engineer.engineer_features(df)
    
    # Normalize features
    if not is_ensemble:
        # Use saved normalization parameters
        if feature_mean is not None and feature_std is not None:
            features_normalized = (features_df.values - feature_mean) / feature_std
            features_normalized = np.nan_to_num(features_normalized, nan=0.0, posinf=1e10, neginf=-1e10)
            logger.info(f"✅ Features normalized (using model stats)")
        else:
            # Compute on the fly
            feature_mean = features_df.values.mean(axis=0)
            feature_std = features_df.values.std(axis=0) + 1e-10
            features_normalized = (features_df.values - feature_mean) / feature_std
            features_normalized = np.nan_to_num(features_normalized, nan=0.0, posinf=1e10, neginf=-1e10)
    else:
        # Ensemble model - normalize normally
        feature_mean = features_df.values.mean(axis=0)
        feature_std = features_df.values.std(axis=0) + 1e-10
        features_normalized = (features_df.values - feature_mean) / feature_std
        features_normalized = np.nan_to_num(features_normalized, nan=0.0, posinf=1e10, neginf=-1e10)
    
    logger.info(f"✅ Features shape: {features_normalized.shape}")
    
    # Calculate mid prices
    mid_prices = (df['bid_price_1'].values + df['ask_price_1'].values) / 2.0
    
    # Generate labels (future direction)
    logger.info("📌 Generating labels...")
    future_returns = np.zeros(len(mid_prices))
    for i in range(len(mid_prices) - prediction_horizon):
        future_returns[i] = (mid_prices[i + prediction_horizon] - mid_prices[i]) / mid_prices[i]
    
    # Classify: 0=DOWN, 1=UNCHANGED, 2=UP
    labels = np.ones(len(mid_prices), dtype=int)  # Default UNCHANGED
    labels[future_returns > 0.0001] = 2  # UP
    labels[future_returns < -0.0001] = 0  # DOWN
    
    # Make predictions in batches
    logger.info("\n🔮 Making predictions...")
    batch_size = 1000
    all_preds = []
    all_probas = []
    
    for i in range(0, len(features_normalized), batch_size):
        batch = features_normalized[i:i+batch_size]
        
        if is_ensemble:
            preds = ensemble.predict(batch)
            probas = ensemble.predict_proba(batch)
        else:
            preds = model.predict(batch)
            probas = model.predict_proba(batch)
        
        all_preds.extend(preds)
        all_probas.extend(probas)
    
    all_preds = np.array(all_preds)
    all_probas = np.array(all_probas)
    confidences = np.max(all_probas, axis=1)
    
    logger.info(f"✅ Made {len(all_preds)} predictions")
    
    # Align labels with features (features are shorter due to rolling windows)
    n_features = len(all_preds)
    labels = labels[:n_features]
    mid_prices = mid_prices[:n_features]
    
    # Calculate accuracy
    valid_mask = labels < 3  # Valid labels
    accuracy = (all_preds[valid_mask] == labels[valid_mask]).mean()
    logger.info(f"📈 Prediction Accuracy: {accuracy:.1%}")
    logger.info(f"📊 Class distribution: DOWN={np.sum(all_preds==0)}, UNCH={np.sum(all_preds==1)}, UP={np.sum(all_preds==2)}")
    
    # Trading simulation
    logger.info("\n💰 Running trading simulation...")
    
    capital = initial_capital
    position = 0
    entry_price = 0
    trades = []
    equity_curve = []
    
    transaction_cost_bps = 5.0
    slippage_bps = 2.0
    max_position_size = 100
    
    for i in range(100, len(all_preds) - prediction_horizon):
        pred = all_preds[i]
        confidence = confidences[i]
        current_price = mid_prices[i]
        
        # Trading logic
        if confidence >= confidence_threshold:
            if pred == 2 and position <= 0:  # UP signal
                # Close short if open
                if position < 0:
                    pnl = (entry_price - current_price) * abs(position)
                    cost = current_price * abs(position) * (transaction_cost_bps + slippage_bps) / 10000
                    capital += pnl - cost
                    trades.append({
                        'type': 'CLOSE_SHORT',
                        'price': current_price,
                        'quantity': abs(position),
                        'pnl': pnl - cost,
                        'confidence': confidence
                    })
                    position = 0
                
                # Open long
                size = min(max_position_size, int(capital * 0.1 / current_price))
                if size > 0:
                    cost = current_price * size * (transaction_cost_bps + slippage_bps) / 10000
                    capital -= cost
                    position = size
                    entry_price = current_price
                    
            elif pred == 0 and position >= 0:  # DOWN signal
                # Close long if open
                if position > 0:
                    pnl = (current_price - entry_price) * position
                    cost = current_price * position * (transaction_cost_bps + slippage_bps) / 10000
                    capital += pnl - cost
                    trades.append({
                        'type': 'CLOSE_LONG',
                        'price': current_price,
                        'quantity': position,
                        'pnl': pnl - cost,
                        'confidence': confidence
                    })
                    position = 0
                
                # Open short
                size = min(max_position_size, int(capital * 0.1 / current_price))
                if size > 0:
                    cost = current_price * size * (transaction_cost_bps + slippage_bps) / 10000
                    capital -= cost
                    position = -size
                    entry_price = current_price
        
        # Calculate equity (mark to market)
        if position > 0:
            unrealized = (current_price - entry_price) * position
        elif position < 0:
            unrealized = (entry_price - current_price) * abs(position)
        else:
            unrealized = 0
        
        equity = capital + unrealized
        equity_curve.append(equity)
    
    # Close any open position
    if position != 0:
        final_price = mid_prices[-1]
        if position > 0:
            pnl = (final_price - entry_price) * position
        else:
            pnl = (entry_price - final_price) * abs(position)
        
        cost = final_price * abs(position) * (transaction_cost_bps + slippage_bps) / 10000
        capital += pnl - cost
        
        trades.append({
            'type': 'CLOSE_FINAL',
            'price': final_price,
            'quantity': abs(position),
            'pnl': pnl - cost,
            'confidence': 0
        })
        
        position = 0
    
    final_equity = capital
    total_pnl = final_equity - initial_capital
    return_pct = (total_pnl / initial_capital) * 100
    
    # Summary statistics
    total_trades = len(trades)
    winning_trades = sum(1 for t in trades if t['pnl'] > 0)
    losing_trades = sum(1 for t in trades if t['pnl'] < 0)
    win_rate = winning_trades / total_trades if total_trades > 0 else 0
    avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
    
    # Print results
    logger.info("\n" + "="*60)
    logger.info("📊 BACKTEST RESULTS")
    logger.info("="*60)
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Model: {model_path}")
    logger.info(f"Data: {data_path}")
    logger.info(f"")
    logger.info(f"💰 Capital Performance:")
    logger.info(f"  Initial Capital: ₹{initial_capital:,.0f}")
    logger.info(f"  Final Capital: ₹{final_equity:,.2f}")
    logger.info(f"  Total PnL: ₹{total_pnl:,.2f}")
    logger.info(f"  Return: {return_pct:.2f}%")
    logger.info(f"")
    logger.info(f"📈 Trading Performance:")
    logger.info(f"  Total Trades: {total_trades}")
    logger.info(f"  Winning Trades: {winning_trades}")
    logger.info(f"  Losing Trades: {losing_trades}")
    logger.info(f"  Win Rate: {win_rate:.1%}")
    logger.info(f"  Avg PnL/Trade: ₹{avg_pnl:.2f}")
    logger.info(f"")
    logger.info(f"🎯 Prediction Quality:")
    logger.info(f"  Accuracy: {accuracy:.1%}")
    logger.info(f"  Avg Confidence: {confidences.mean():.1%}")
    logger.info(f"")
    
    # Save results
    import json
    results = {
        'symbol': symbol,
        'model': model_path,
        'initial_capital': initial_capital,
        'final_capital': final_equity,
        'total_pnl': total_pnl,
        'return_pct': return_pct,
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'win_rate': win_rate,
        'accuracy': accuracy,
        'avg_confidence': float(confidences.mean()),
        'timestamp': datetime.now().isoformat()
    }
    
    filename = f"backtest_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"💾 Results saved to: {filename}")
    logger.info("="*60)
    
    return results


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Fast HFT Backtester')
    parser.add_argument('--model', type=str, default='output/RELIANCE_ensemble.joblib', help='Model path')
    parser.add_argument('--data', type=str, default='data/RELIANCE_live.parquet', help='Data path')
    parser.add_argument('--symbol', type=str, default='RELIANCE', help='Symbol')
    parser.add_argument('--capital', type=float, default=1000000, help='Initial capital')
    parser.add_argument('--confidence', type=float, default=0.6, help='Confidence threshold')
    parser.add_argument('--horizon', type=int, default=10, help='Prediction horizon')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.model):
        logger.error(f"❌ Model not found: {args.model}")
    elif not os.path.exists(args.data):
        logger.error(f"❌ Data not found: {args.data}")
    else:
        run_fast_backtest(
            model_path=args.model,
            data_path=args.data,
            symbol=args.symbol,
            initial_capital=args.capital,
            confidence_threshold=args.confidence,
            prediction_horizon=args.horizon
        )
