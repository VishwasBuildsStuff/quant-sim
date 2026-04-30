"""
XGBoost/Random Forest Training Pipeline for HFT
Walk-forward cross-validation, feature importance, model export
Fast alternative to deep learning for tick-level prediction
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
from typing import Dict, List, Tuple, Optional
import logging

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix
from sklearn.preprocessing import StandardScaler
import joblib

# Try XGBoost, fallback to sklearn if not available
try:
    from xgboost import XGBClassifier
    HAS_XGBOOST = True
except:
    HAS_XGBOOST = False
    print("⚠️ XGBoost not installed. Using sklearn GradientBoosting")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# FEATURE ENGINEERING
# ============================================================

class HFTFeatureEngineer:
    """
    Optimized feature engineering for tree-based models
    """
    
    def __init__(self, n_levels: int = 10):
        self.n_levels = n_levels
        self.scaler = StandardScaler()
        self.feature_names = []
    
    def engineer_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """
        Create features optimized for tree-based models
        
        Args:
            df: DataFrame with LOB columns
            
        Returns:
            (features_df, feature_names)
        """
        features = pd.DataFrame(index=df.index)
        
        # === PRICE FEATURES ===
        mid = (df['bid_price_1'] + df['ask_price_1']) / 2
        features['mid_price'] = mid
        features['spread'] = df['ask_price_1'] - df['bid_price_1']
        features['spread_pct'] = features['spread'] / mid * 10000  # basis points
        
        # === VOLUME FEATURES ===
        features['bid_vol_1'] = df['bid_volume_1']
        features['ask_vol_1'] = df['ask_volume_1']
        features['vol_imbalance'] = (df['bid_volume_1'] - df['ask_volume_1']) / \
                                    (df['bid_volume_1'] + df['ask_volume_1'] + 1)
        
        # Total volume top 3 levels
        features['bid_vol_top3'] = df[['bid_volume_1', 'bid_volume_2', 'bid_volume_3']].sum(axis=1)
        features['ask_vol_top3'] = df[['ask_volume_1', 'ask_volume_2', 'ask_volume_3']].sum(axis=1)
        features['vol_ratio_top3'] = features['bid_vol_top3'] / (features['ask_vol_top3'] + 1)
        
        # === RETURN FEATURES ===
        for window in [1, 3, 5, 10, 20]:
            features[f'return_{window}'] = np.log(mid / mid.shift(window)).fillna(0)
        
        # === VOLATILITY FEATURES ===
        returns_1 = features['return_1']
        for window in [5, 10, 20, 50]:
            features[f'vol_{window}'] = returns_1.rolling(window).std().fillna(0)
        
        # === MOMENTUM FEATURES ===
        for window in [5, 10, 20]:
            features[f'momentum_{window}'] = features[f'return_{window}'] / \
                                              (features[f'vol_{window}'] + 1e-10)
        
        # === ORDER BOOK SHAPE ===
        # Bid/ask slope (price vs cumulative volume)
        for side in ['bid', 'ask']:
            cum_vol = df[[f'{side}_volume_{i}' for i in range(1, 6)]].cumsum(axis=1).iloc[:, -1]
            prices = df[f'{side}_price_1'] - df[f'{side}_price_5']
            features[f'{side}_slope'] = prices / (cum_vol + 1)
        
        # === OFI (Order Flow Imbalance) ===
        # Simplified OFI calculation
        for i in range(1, 4):
            features[f'ofi_level{i}'] = (df[f'bid_volume_{i}'] - df[f'ask_volume_{i}']) / \
                                         (df[f'bid_volume_{i}'] + df[f'ask_volume_{i}'] + 1)
        
        features['ofi_total'] = (features['ofi_level1'] + features['ofi_level2'] + features['ofi_level3']) / 3
        
        # === MEAN REVERSION ===
        ma_20 = mid.rolling(20).mean()
        ma_50 = mid.rolling(50).mean()
        features['dist_to_ma20'] = (mid - ma_20) / ma_20
        features['dist_to_ma50'] = (mid - ma_50) / ma_50
        features['ma20_ma50_cross'] = ma_20 - ma_50
        
        # === VOLUME PROFILE ===
        features['vol_concentration'] = df['bid_volume_1'] / features['bid_vol_top3']
        
        # Drop NaN rows
        features = features.dropna()
        
        self.feature_names = list(features.columns)
        logger.info(f"✓ Engineered {len(self.feature_names)} features")
        logger.info(f"  Shape: {features.shape}")
        
        return features, self.feature_names
    
    def generate_labels(self, mid: pd.Series, horizon: int = 10, 
                       balanced: bool = True) -> np.ndarray:
        """
        Generate 3-class labels (Down=0, Unchanged=1, Up=2)
        
        Args:
            mid: Mid-price series
            horizon: Prediction horizon (ticks ahead)
            balanced: If True, use quantile-based labeling for balance
        """
        future_mid = mid.shift(-horizon)
        price_change = future_mid - mid
        
        # Drop last `horizon` rows (no future data)
        price_change = price_change.iloc[:len(price_change) - horizon]
        
        if balanced:
            # Quantile-based: 33% each class
            tolerance = price_change.abs().quantile(0.33)
        else:
            # Spread-based: use median spread as tolerance
            spread = mid.rolling(100).std().median() * 2
            tolerance = spread
        
        labels = np.zeros(len(price_change), dtype=int)
        labels[price_change.values > tolerance] = 2  # Up
        labels[price_change.values < -tolerance] = 0  # Down
        labels[(price_change.values >= -tolerance) & (price_change.values <= tolerance)] = 1
        
        return labels

# ============================================================
# WALK-FORWARD VALIDATOR
# ============================================================

class WalkForwardValidator:
    """
    Walk-forward validation for tree-based models
    Much faster than deep learning (seconds vs hours)
    """
    
    def __init__(self, 
                 train_size: int = 30000,
                 test_size: int = 5000,
                 step_size: int = 5000):
        self.train_size = train_size
        self.test_size = test_size
        self.step_size = step_size
    
    def generate_splits(self, n_samples: int) -> List[Tuple[slice, slice]]:
        """Generate train/test splits"""
        splits = []
        start = 0
        
        while start + self.train_size + self.test_size <= n_samples:
            train_end = start + self.train_size
            test_end = train_end + self.test_size
            
            splits.append((
                slice(start, train_end),
                slice(train_end, test_end)
            ))
            
            start += self.step_size
        
        logger.info(f"✓ Generated {len(splits)} walk-forward splits")
        return splits

# ============================================================
# MODEL TRAINER
# ============================================================

class HFTModelTrainer:
    """
    Trains and evaluates tree-based models for HFT
    """
    
    def __init__(self, model_type: str = 'xgboost'):
        self.model_type = model_type
        self.model = None
        self.results = []
    
    def create_model(self, **kwargs) -> object:
        """Create model with hyperparameters"""
        if self.model_type == 'xgboost' and HAS_XGBOOST:
            params = {
                'n_estimators': kwargs.get('n_estimators', 200),
                'max_depth': kwargs.get('max_depth', 6),
                'learning_rate': kwargs.get('learning_rate', 0.1),
                'subsample': kwargs.get('subsample', 0.8),
                'colsample_bytree': kwargs.get('colsample_bytree', 0.8),
                'min_child_weight': kwargs.get('min_child_weight', 3),
                'gamma': kwargs.get('gamma', 0.1),
                'reg_alpha': kwargs.get('reg_alpha', 0.1),
                'reg_lambda': kwargs.get('reg_lambda', 1.0),
                'eval_metric': 'mlogloss',
                'random_state': 42,
                'n_jobs': -1
            }
            # Add class weights if provided
            if 'scale_pos_weight' in kwargs:
                params['scale_pos_weight'] = kwargs['scale_pos_weight']
            return XGBClassifier(**{k: v for k, v in params.items() if v is not None})
        
        elif self.model_type == 'random_forest':
            params = {
                'n_estimators': kwargs.get('n_estimators', 200),
                'max_depth': kwargs.get('max_depth', 10),
                'min_samples_split': kwargs.get('min_samples_split', 10),
                'min_samples_leaf': kwargs.get('min_samples_leaf', 5),
                'max_features': kwargs.get('max_features', 'sqrt'),
                'class_weight': 'balanced',
                'random_state': 42,
                'n_jobs': -1
            }
            return RandomForestClassifier(**params)
        
        else:  # Gradient Boosting (sklearn)
            params = {
                'n_estimators': kwargs.get('n_estimators', 100),
                'max_depth': kwargs.get('max_depth', 5),
                'learning_rate': kwargs.get('learning_rate', 0.1),
                'subsample': kwargs.get('subsample', 0.8),
                'random_state': 42
            }
            return GradientBoostingClassifier(**params)
    
    def train_and_evaluate(self, 
                          X_train: np.ndarray, y_train: np.ndarray,
                          X_test: np.ndarray, y_test: np.ndarray,
                          feature_names: List[str],
                          **kwargs) -> Dict:
        """Train model and evaluate on test set"""
        
        # Compute class weights for imbalance
        classes, counts = np.unique(y_train, return_counts=True)
        class_weights = {c: len(y_train) / (len(classes) * count) for c, count in zip(classes, counts)}
        sample_weights = np.array([class_weights[y] for y in y_train])
        
        # Create and train model
        self.model = self.create_model(**kwargs)
        
        start_time = time.time()
        self.model.fit(X_train, y_train, sample_weight=sample_weights)
        train_time = time.time() - start_time
        
        # Predict
        start_time = time.time()
        y_pred = self.model.predict(X_test)
        inference_time = (time.time() - start_time) / len(X_test) * 1e6  # microseconds
        
        # Metrics
        acc = accuracy_score(y_test, y_pred)
        f1_macro = f1_score(y_test, y_pred, average='macro', zero_division=0)
        f1_up = f1_score(y_test, y_pred, labels=[2], average='micro', zero_division=0) if 2 in y_test else 0
        f1_down = f1_score(y_test, y_pred, labels=[0], average='micro', zero_division=0) if 0 in y_test else 0
        
        # Feature importance
        if hasattr(self.model, 'feature_importances_'):
            importances = dict(zip(feature_names, self.model.feature_importances_.tolist()))
            top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:10]
        else:
            top_features = []
        
        result = {
            'accuracy': acc,
            'f1_macro': f1_macro,
            'f1_up': f1_up,
            'f1_down': f1_down,
            'train_time': train_time,
            'inference_time_us': inference_time,
            'top_features': top_features,
            'confusion_matrix': [[int(x) for x in row] for row in confusion_matrix(y_test, y_pred).tolist()]
        }
        
        return result

# ============================================================
# MAIN ORCHESTRATOR
# ============================================================

class HFTXGBoostPipeline:
    """
    Complete XGBoost/RF training pipeline with walk-forward CV
    """
    
    def __init__(self, 
                 symbol: str,
                 data_dir: str = './data',
                 output_dir: str = './output',
                 model_type: str = 'xgboost',
                 horizon: int = 10,
                 n_splits: int = 5):
        
        self.symbol = symbol
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.model_type = model_type
        self.horizon = horizon
        self.n_splits = n_splits
        
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        self.feature_engineer = HFTFeatureEngineer()
        self.trainer = HFTModelTrainer(model_type)
    
    def run(self):
        """Run complete pipeline"""
        logger.info("="*60)
        logger.info(f"🚀 HFT {self.model_type.upper()} TRAINING PIPELINE")
        logger.info(f"   Symbol: {self.symbol}")
        logger.info(f"   Horizon: {self.horizon} ticks")
        logger.info("="*60)
        
        # 1. Load data
        filepath = os.path.join(self.data_dir, f'{self.symbol}.parquet')
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Data file not found: {filepath}")
        
        logger.info(f"\n📂 Loading data from {filepath}...")
        df = pd.read_parquet(filepath)
        logger.info(f"  ✓ Loaded {len(df):,} snapshots")
        
        # 2. Feature engineering
        logger.info(f"\n🔧 Engineering features...")
        features, feature_names = self.feature_engineer.engineer_features(df)
        
        # 3. Generate labels
        logger.info(f"\n🏷️ Generating labels (horizon={self.horizon})...")
        mid = (df['bid_price_1'] + df['ask_price_1']) / 2
        labels = self.feature_engineer.generate_labels(mid, horizon=self.horizon, balanced=True)
        
        # Align features and labels
        min_len = min(len(features), len(labels))
        X = features.iloc[:min_len].values
        y = labels[:min_len]
        
        logger.info(f"  ✓ Dataset: {X.shape[0]} samples, {X.shape[1]} features")
        logger.info(f"  ✓ Classes: Down={np.sum(y==0)}, Unchanged={np.sum(y==1)}, Up={np.sum(y==2)}")
        
        # 4. Walk-forward validation
        logger.info(f"\n🔄 Walk-forward validation ({self.n_splits} splits)...")
        validator = WalkForwardValidator(
            train_size=30000,
            test_size=5000,
            step_size=5000
        )
        splits = validator.generate_splits(len(X))
        
        all_results = []
        
        for i, (train_slice, test_slice) in enumerate(splits[:self.n_splits]):
            logger.info(f"\n{'─'*40}")
            logger.info(f"SPLIT {i+1}/{min(self.n_splits, len(splits))}")
            logger.info(f"{'─'*40}")
            
            X_train, y_train = X[train_slice], y[train_slice]
            X_test, y_test = X[test_slice], y[test_slice]
            
            result = self.trainer.train_and_evaluate(
                X_train, y_train, X_test, y_test,
                feature_names,
                n_estimators=200,
                max_depth=8,  # Deeper trees for better learning
                learning_rate=0.05,  # Slower learning
                min_child_weight=5  # Prevent overfitting
            )
            
            logger.info(f"  Accuracy: {result['accuracy']:.3f}")
            logger.info(f"  F1 Macro: {result['f1_macro']:.3f}")
            logger.info(f"  F1 Up:    {result['f1_up']:.3f}")
            logger.info(f"  F1 Down:  {result['f1_down']:.3f}")
            logger.info(f"  Train:    {result['train_time']:.2f}s")
            logger.info(f"  Infer:    {result['inference_time_us']:.1f}µs")
            
            all_results.append(result)
        
        # 5. Aggregate results
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 AGGREGATE RESULTS")
        logger.info(f"{'='*60}")
        
        avg_acc = np.mean([r['accuracy'] for r in all_results])
        avg_f1 = np.mean([r['f1_macro'] for r in all_results])
        avg_f1_up = np.mean([r['f1_up'] for r in all_results])
        avg_f1_down = np.mean([r['f1_down'] for r in all_results])
        avg_train_time = np.mean([r['train_time'] for r in all_results])
        avg_infer_time = np.mean([r['inference_time_us'] for r in all_results])
        
        logger.info(f"  Avg Accuracy: {avg_acc:.3f}")
        logger.info(f"  Avg F1 Macro: {avg_f1:.3f}")
        logger.info(f"  Avg F1 Up:    {avg_f1_up:.3f}")
        logger.info(f"  Avg F1 Down:  {avg_f1_down:.3f}")
        logger.info(f"  Avg Train:    {avg_train_time:.2f}s per split")
        logger.info(f"  Avg Infer:    {avg_infer_time:.1f}µs per sample")
        
        # 6. Feature importance
        if self.trainer.model is not None and hasattr(self.trainer.model, 'feature_importances_'):
            logger.info(f"\n📈 TOP 10 FEATURE IMPORTANCES:")
            importances = sorted(zip(feature_names, self.trainer.model.feature_importances_), 
                               key=lambda x: x[1], reverse=True)[:10]
            for rank, (feat, imp) in enumerate(importances, 1):
                bar = '█' * int(imp * 50)
                logger.info(f"  {rank:2d}. {feat:<20} {imp:.3f} {bar}")
        
        # 7. Final model (train on all data with class weights)
        logger.info(f"\n🎯 Training final model on full dataset...")
        final_classes, final_counts = np.unique(y, return_counts=True)
        final_weights = {c: len(y) / (len(final_classes) * count) for c, count in zip(final_classes, final_counts)}
        final_sample_weights = np.array([final_weights[yi] for yi in y])
        
        final_model = self.trainer.create_model(n_estimators=200, max_depth=8, learning_rate=0.05, min_child_weight=5)
        final_model.fit(X, y, sample_weight=final_sample_weights)
        
        # 8. Save model
        model_path = os.path.join(self.output_dir, f'{self.symbol}_{self.model_type}.joblib')
        joblib.dump({
            'model': final_model,
            'feature_names': feature_names,
            'symbol': self.symbol,
            'horizon': self.horizon,
            'model_type': self.model_type
        }, model_path)
        logger.info(f"  ✓ Model saved to {model_path}")
        
        # 9. Save report
        report = {
            'timestamp': datetime.now().isoformat(),
            'symbol': self.symbol,
            'model_type': self.model_type,
            'horizon': self.horizon,
            'n_features': len(feature_names),
            'feature_names': [str(f) for f in feature_names],
            'aggregate_results': {
                'accuracy': round(float(avg_acc), 4),
                'f1_macro': round(float(avg_f1), 4),
                'f1_up': round(float(avg_f1_up), 4),
                'f1_down': round(float(avg_f1_down), 4),
                'train_time_s': round(float(avg_train_time), 3),
                'inference_time_us': round(float(avg_infer_time), 2)
            },
            'per_split_results': all_results,
            'top_features': [(str(feat), round(float(imp), 4)) for feat, imp in importances[:10]] if 'importances' in dir() else []
        }
        
        report_path = os.path.join(self.output_dir, f'{self.symbol}_report.json')
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        logger.info(f"  ✓ Report saved to {report_path}")
        
        # 10. Performance targets
        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 PERFORMANCE TARGETS")
        logger.info(f"{'='*60}")
        targets = {
            'Accuracy > 55%': avg_acc > 0.55,
            'F1 Macro > 0.5': avg_f1 > 0.5,
            'Inference < 100µs': avg_infer_time < 100,
            'Train time < 60s': avg_train_time < 60
        }
        
        for target, passed in targets.items():
            status = '✅ PASS' if passed else '❌ FAIL'
            logger.info(f"  {status}: {target}")
        
        passed_count = sum(1 for v in targets.values() if v)
        logger.info(f"\n  Passed: {passed_count}/{len(targets)} ({passed_count/len(targets)*100:.0f}%)")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ PIPELINE COMPLETE")
        logger.info(f"{'='*60}")
        
        return report

# ============================================================
# MAIN
# ============================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='HFT XGBoost Training Pipeline')
    parser.add_argument('--symbol', type=str, default='HNGSNGBEES', help='Symbol to train')
    parser.add_argument('--data-dir', type=str, default='./data', help='Data directory')
    parser.add_argument('--output-dir', type=str, default='./output', help='Output directory')
    parser.add_argument('--model', type=str, default='xgboost', choices=['xgboost', 'random_forest', 'gradient_boosting'], help='Model type')
    parser.add_argument('--horizon', type=int, default=10, help='Prediction horizon (ticks)')
    parser.add_argument('--splits', type=int, default=5, help='Number of walk-forward splits')
    
    args = parser.parse_args()
    
    pipeline = HFTXGBoostPipeline(
        symbol=args.symbol,
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        model_type=args.model,
        horizon=args.horizon,
        n_splits=args.splits
    )
    
    report = pipeline.run()
    return report

if __name__ == '__main__':
    main()
