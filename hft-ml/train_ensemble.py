"""
Master Training Script
Combines: Advanced Features + Ensemble Model + Export for Deployment
"""

import sys
sys.path.insert(0, r'V:\pylibs')

import os
import json
import time
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import logging

from advanced_features import AdvancedFeatureEngineer
from ensemble_model import HFTEnsemble
from sklearn.metrics import accuracy_score, f1_score, classification_report

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def train_ensemble_pipeline(symbol: str = 'HNGSNGBEES',
                           data_dir: str = './data',
                           output_dir: str = './output',
                           horizon: int = 10,
                           balanced: bool = True):
    """
    Complete training pipeline with advanced features and ensemble model
    """
    
    logger.info("="*70)
    logger.info(f"🚀 HFT ENSEMBLE TRAINING PIPELINE")
    logger.info(f"   Symbol: {symbol}")
    logger.info(f"   Horizon: {horizon} ticks")
    logger.info("="*70)
    
    # 1. Load data
    filepath = os.path.join(data_dir, f'{symbol}.parquet')
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Data file not found: {filepath}")
    
    logger.info(f"\n📂 Loading data from {filepath}...")
    df = pd.read_parquet(filepath)
    logger.info(f"  ✓ Loaded {len(df):,} snapshots")
    
    # 2. Advanced feature engineering
    logger.info(f"\n🔧 Engineering advanced features...")
    start = time.time()
    feature_engineer = AdvancedFeatureEngineer(n_levels=10)
    features, feature_names = feature_engineer.engineer_features(df)
    feature_time = time.time() - start
    
    logger.info(f"  ✓ Engineered {len(feature_names)} features in {feature_time:.2f}s")
    logger.info(f"  ✓ Shape: {features.shape}")
    
    # 3. Generate labels
    logger.info(f"\n🏷️ Generating labels (horizon={horizon})...")
    mid = (df['bid_price_1'] + df['ask_price_1']) / 2
    
    # Align mid with features
    mid = mid.iloc[:len(features)]
    
    future_mid = mid.shift(-horizon)
    price_change = future_mid - mid
    
    if balanced:
        # Quantile-based labeling
        tolerance = price_change.abs().quantile(0.33)
    else:
        # Spread-based
        spread = features['spread'].median()
        tolerance = spread * 0.5
    
    labels = np.zeros(len(features), dtype=int)
    labels[price_change.values > tolerance] = 2  # Up
    labels[price_change.values < -tolerance] = 0  # Down
    labels[(price_change.values >= -tolerance) & (price_change.values <= tolerance)] = 1  # Unchanged
    
    logger.info(f"  ✓ Classes: Down={np.sum(labels==0)}, Unchanged={np.sum(labels==1)}, Up={np.sum(labels==2)}")
    
    # 4. Train/test split (time-based)
    split_idx = int(len(features) * 0.7)
    X_train = features.iloc[:split_idx].values
    y_train = labels[:split_idx]
    X_test = features.iloc[split_idx:].values
    y_test = labels[split_idx:]
    
    logger.info(f"\n📊 Train: {len(X_train):,} | Test: {len(X_test):,}")
    
    # 5. Train ensemble (use voting for speed)
    ensemble = HFTEnsemble(n_classes=3)
    ensemble.fit(X_train, y_train, feature_names=feature_names, use_stacking=False)
    
    # 6. Evaluate on test set
    logger.info(f"\n" + "="*70)
    logger.info("📊 TEST SET EVALUATION")
    logger.info("="*70)
    
    # Ensemble prediction
    test_preds = ensemble.predict(X_test)
    test_proba = ensemble.predict_proba(X_test)
    
    test_acc = accuracy_score(y_test, test_preds)
    test_f1 = f1_score(y_test, test_preds, average='macro', zero_division=0)
    test_f1_up = f1_score(y_test, test_preds, labels=[2], average='micro', zero_division=0) if 2 in y_test else 0
    test_f1_down = f1_score(y_test, test_preds, labels=[0], average='micro', zero_division=0) if 0 in y_test else 0
    
    logger.info(f"\n  ENSEMBLE:")
    logger.info(f"    Accuracy: {test_acc:.3f}")
    logger.info(f"    F1 Macro: {test_f1:.3f}")
    logger.info(f"    F1 Up:    {test_f1_up:.3f}")
    logger.info(f"    F1 Down:  {test_f1_down:.3f}")
    
    # Individual model evaluation
    for name, model in ensemble.models.items():
        preds = model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        f1 = f1_score(y_test, preds, average='macro', zero_division=0)
        logger.info(f"\n  {name.upper()}:")
        logger.info(f"    Accuracy: {acc:.3f}")
        logger.info(f"    F1 Macro: {f1:.3f}")
    
    logger.info(f"\n  CLASSIFICATION REPORT:")
    logger.info(f"\n{classification_report(y_test, test_preds, zero_division=0)}")
    
    # 7. Feature importance
    importances = ensemble.get_feature_importance()
    if importances:
        sorted_imp = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:15]
        
        logger.info(f"\n📈 TOP 15 FEATURE IMPORTANCES:")
        for rank, (feat, imp) in enumerate(sorted_imp, 1):
            bar = '█' * int(imp * 50)
            logger.info(f"  {rank:2d}. {feat:<25} {imp:.4f} {bar}")
    
    # 8. Save model
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    model_path = os.path.join(output_dir, f'{symbol}_ensemble.joblib')
    ensemble.save(model_path)
    
    # 9. Generate report
    report = {
        'timestamp': datetime.now().isoformat(),
        'symbol': symbol,
        'horizon': horizon,
        'n_features': len(feature_names),
        'feature_names': feature_names,
        'test_results': {
            'accuracy': round(float(test_acc), 4),
            'f1_macro': round(float(test_f1), 4),
            'f1_up': round(float(test_f1_up), 4),
            'f1_down': round(float(test_f1_down), 4)
        },
        'top_features': [(str(f), round(float(imp), 4)) for f, imp in sorted_imp[:15]],
        'individual_models': {}
    }
    
    for name, model in ensemble.models.items():
        preds = model.predict(X_test)
        report['individual_models'][name] = {
            'accuracy': round(float(accuracy_score(y_test, preds)), 4),
            'f1_macro': round(float(f1_score(y_test, preds, average='macro', zero_division=0)), 4)
        }
    
    report_path = os.path.join(output_dir, f'{symbol}_ensemble_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"\n💾 Model saved to: {model_path}")
    logger.info(f"💾 Report saved to: {report_path}")
    
    # 10. Performance targets
    logger.info(f"\n{'='*70}")
    logger.info("🎯 PERFORMANCE TARGETS")
    logger.info(f"{'='*70}")
    targets = {
        'Accuracy > 55%': test_acc > 0.55,
        'F1 Macro > 0.5': test_f1 > 0.5,
        'F1 Up > 0.4': test_f1_up > 0.4,
        'F1 Down > 0.4': test_f1_down > 0.4
    }
    
    for target, passed in targets.items():
        status = '✅ PASS' if passed else '❌ FAIL'
        logger.info(f"  {status}: {target}")
    
    passed_count = sum(1 for v in targets.values() if v)
    logger.info(f"\n  Passed: {passed_count}/{len(targets)} ({passed_count/len(targets)*100:.0f}%)")
    
    logger.info(f"\n{'='*70}")
    logger.info("✅ PIPELINE COMPLETE")
    logger.info(f"{'='*70}")
    
    return report

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='HFT Ensemble Training Pipeline')
    parser.add_argument('--symbol', type=str, default='HNGSNGBEES', help='Symbol to train')
    parser.add_argument('--data-dir', type=str, default='./data', help='Data directory')
    parser.add_argument('--output-dir', type=str, default='./output', help='Output directory')
    parser.add_argument('--horizon', type=int, default=10, help='Prediction horizon (ticks)')
    parser.add_argument('--no-balance', action='store_true', help='Disable balanced labeling')
    
    args = parser.parse_args()
    
    report = train_ensemble_pipeline(
        symbol=args.symbol,
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        horizon=args.horizon,
        balanced=not args.no_balance
    )
