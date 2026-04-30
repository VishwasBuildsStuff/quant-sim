"""
Quick Training on Live Data
Trains XGBoost model on RELIANCE_live.parquet
"""

import sys
sys.path.insert(0, r'V:\pylibs')
sys.path.insert(0, '.')

import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import xgboost as xgb
import logging

from advanced_features import AdvancedFeatureEngineer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('train_live.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def train_on_live_data(
    data_path: str = 'data/RELIANCE_live.parquet',
    output_path: str = 'output/RELIANCE_live_trained.joblib',
    prediction_horizon: int = 10
):
    """
    Train XGBoost model on live market data
    """
    
    logger.info("\n" + "="*60)
    logger.info("🚀 TRAINING ON LIVE DATA")
    logger.info("="*60)
    
    # Load live data
    logger.info(f"Loading live data: {data_path}")
    if not os.path.exists(data_path):
        logger.error(f"❌ File not found: {data_path}")
        return None
    
    df = pd.read_parquet(data_path)
    logger.info(f"✅ Loaded {len(df)} live LOB snapshots")
    
    # Engineer features
    logger.info("\n🔧 Engineering features...")
    feature_engineer = AdvancedFeatureEngineer()
    features_df, feature_names = feature_engineer.engineer_features(df)
    
    # Remove NaN/Inf
    features_df = features_df.fillna(0)
    features_df = features_df.replace([np.inf, -np.inf], 0)
    
    logger.info(f"✅ Features shape: {features_df.shape}")
    logger.info(f"   Feature count: {len(feature_names)}")
    
    # Calculate mid prices
    mid_prices = (df['bid_price_1'].values + df['ask_price_1'].values) / 2.0
    
    # Generate labels (future price direction)
    logger.info(f"\n📌 Generating labels (horizon={prediction_horizon} ticks)...")
    
    future_returns = np.zeros(len(mid_prices))
    for i in range(len(mid_prices) - prediction_horizon):
        future_returns[i] = (mid_prices[i + prediction_horizon] - mid_prices[i]) / mid_prices[i]
    
    # Classify: 0=DOWN, 1=UNCHANGED, 2=UP
    labels = np.ones(len(mid_prices), dtype=int)
    labels[future_returns > 0.0001] = 2  # UP
    labels[future_returns < -0.0001] = 0  # DOWN
    
    # Align features and labels
    n_samples = len(features_df)
    features = features_df.values[:n_samples]
    y = labels[:n_samples]
    
    # Remove last 'horizon' samples (no future labels)
    features = features[:-prediction_horizon]
    y = y[:-prediction_horizon]
    
    logger.info(f"   DOWN: {np.sum(y==0)} ({np.sum(y==0)/len(y)*100:.1f}%)")
    logger.info(f"   UNCHANGED: {np.sum(y==1)} ({np.sum(y==1)/len(y)*100:.1f}%)")
    logger.info(f"   UP: {np.sum(y==2)} ({np.sum(y==2)/len(y)*100:.1f}%)")
    
    # Split data (time-series split)
    split_idx = int(len(features) * 0.8)
    X_train = features[:split_idx]
    y_train = y[:split_idx]
    X_test = features[split_idx:]
    y_test = y[split_idx:]
    
    logger.info(f"\n📊 Train/Test split: {len(X_train)}/{len(X_test)}")
    
    # Train XGBoost
    logger.info("\n🎯 Training XGBoost model...")
    
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        objective='multi:softprob',
        num_class=3,
        eval_metric='mlogloss',
        use_label_encoder=False,
        n_jobs=-1
    )
    
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=True
    )
    
    # Evaluate
    logger.info("\n📈 Evaluating model...")
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)
    
    accuracy = accuracy_score(y_test, y_pred)
    logger.info(f"\n✅ Test Accuracy: {accuracy:.1%}")
    logger.info(f"\nClassification Report:")
    logger.info(f"\n{classification_report(y_test, y_pred, target_names=['DOWN', 'UNCH', 'UP'])}")
    
    # Get confidence stats
    confidences = np.max(y_proba, axis=1)
    logger.info(f"📊 Confidence Stats:")
    logger.info(f"   Mean: {confidences.mean():.1%}")
    logger.info(f"   Median: {np.median(confidences):.1%}")
    logger.info(f"   >60%: {np.sum(confidences > 0.6) / len(confidences) * 100:.1f}%")
    
    # Save model
    logger.info(f"\n💾 Saving model to: {output_path}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    model_data = {
        'model': model,
        'feature_names': feature_names,
        'feature_mean': X_train.mean(axis=0),
        'feature_std': X_train.std(axis=0) + 1e-10,
        'prediction_horizon': prediction_horizon,
        'accuracy': accuracy,
        'training_date': datetime.now().isoformat(),
        'data_source': data_path
    }
    
    joblib.dump(model_data, output_path)
    logger.info(f"✅ Model saved!")
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("📊 TRAINING SUMMARY")
    logger.info("="*60)
    logger.info(f"Data: {data_path}")
    logger.info(f"Samples: {len(features)}")
    logger.info(f"Features: {features.shape[1]}")
    logger.info(f"Horizon: {prediction_horizon} ticks")
    logger.info(f"Accuracy: {accuracy:.1%}")
    logger.info(f"Model: {output_path}")
    logger.info("="*60)
    
    return model_data


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Train on Live Data')
    parser.add_argument('--data', type=str, default='data/RELIANCE_live.parquet', help='Live data path')
    parser.add_argument('--output', type=str, default='output/RELIANCE_live_trained.joblib', help='Output path')
    parser.add_argument('--horizon', type=int, default=10, help='Prediction horizon')
    
    args = parser.parse_args()
    
    train_on_live_data(
        data_path=args.data,
        output_path=args.output,
        prediction_horizon=args.horizon
    )
