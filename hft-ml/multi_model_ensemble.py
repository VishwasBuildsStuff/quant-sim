"""
Multi-Model Ensemble for HFT Trading
Combines XGBoost, LightGBM, and Random Forest with voting
"""

import sys
sys.path.insert(0, r'V:\pylibs')

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
import logging

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MultiModelEnsemble:
    """
    Professional multi-model ensemble for HFT prediction
    
    Features:
    - XGBoost gradient boosting
    - LightGBM (if available)
    - Random Forest
    - Soft voting for final prediction
    - Per-model confidence scoring
    """
    
    def __init__(self, n_classes: int = 3):
        self.n_classes = n_classes
        self.models = {}
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_names = None
        self.model_weights = {}  # Performance-based weights
        
    def build_models(self):
        """Initialize all models"""
        
        # XGBoost
        self.models['xgboost'] = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=3,
            objective='multi:softprob',
            num_class=self.n_classes,
            eval_metric='mlogloss',
            use_label_encoder=False,
            n_jobs=-1
        )
        
        # LightGBM (if available)
        if HAS_LIGHTGBM:
            self.models['lightgbm'] = lgb.LGBMClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_samples=10,
                num_class=self.n_classes,
                objective='multiclass',
                n_jobs=-1,
                verbose=-1
            )
            logger.info("✓ LightGBM model enabled")
        else:
            logger.warning("⚠ LightGBM not available, install with: pip install lightgbm")
        
        # Random Forest
        self.models['random_forest'] = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            n_jobs=-1,
            random_state=42
        )
        
        # Initialize equal weights
        for name in self.models.keys():
            self.model_weights[name] = 1.0 / len(self.models)
        
        logger.info(f"✓ Initialized {len(self.models)} models")
    
    def train(self, X_train: np.ndarray, y_train: np.ndarray, 
              X_val: np.ndarray = None, y_val: np.ndarray = None):
        """
        Train all models
        
        Args:
            X_train: Training features
            y_train: Training labels
            X_val: Validation features (optional)
            y_val: Validation labels (optional)
        """
        logger.info("\n" + "="*60)
        logger.info("🎯 TRAINING MULTI-MODEL ENSEMBLE")
        logger.info("="*60)
        
        # Fit scaler
        X_train_scaled = self.scaler.fit_transform(X_train)
        
        if X_val is not None:
            X_val_scaled = self.scaler.transform(X_val)
        
        # Train each model
        model_accuracies = {}
        
        for name, model in self.models.items():
            logger.info(f"\n📊 Training {name}...")
            
            if name == 'xgboost' and X_val is not None:
                model.fit(
                    X_train_scaled, y_train,
                    eval_set=[(X_val_scaled, y_val)],
                    verbose=False
                )
            else:
                model.fit(X_train_scaled, y_train)
            
            # Calculate accuracy
            if X_val is not None and y_val is not None:
                train_acc = model.score(X_train_scaled, y_train)
                val_acc = model.score(X_val_scaled, y_val)
                model_accuracies[name] = val_acc
                logger.info(f"  ✓ {name}: Train={train_acc:.1%}, Val={val_acc:.1%}")
            else:
                train_acc = model.score(X_train_scaled, y_train)
                model_accuracies[name] = train_acc
                logger.info(f"  ✓ {name}: Train={train_acc:.1%}")
        
        # Update weights based on validation accuracy
        if model_accuracies:
            total_acc = sum(model_accuracies.values())
            for name in self.model_weights:
                self.model_weights[name] = model_accuracies.get(name, 0.01) / total_acc
            
            logger.info(f"\n📊 Model Weights:")
            for name, weight in self.model_weights.items():
                logger.info(f"  {name}: {weight:.1%}")
        
        self.is_trained = True
        logger.info("\n✅ All models trained successfully!")
        
        return model_accuracies
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict with ensemble voting
        
        Returns:
            Array of predictions (0=DOWN, 1=UNCH, 2=UP)
        """
        if not self.is_trained:
            raise RuntimeError("Models not trained yet!")
        
        X_scaled = self.scaler.transform(X)
        
        # Get probability predictions from all models
        all_probas = []
        
        for name, model in self.models.items():
            proba = model.predict_proba(X_scaled)
            weight = self.model_weights[name]
            all_probas.append(proba * weight)
        
        # Weighted average of probabilities
        ensemble_proba = np.sum(all_probas, axis=0)
        
        # Return class with highest probability
        predictions = np.argmax(ensemble_proba, axis=1)
        
        return predictions
    
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Get ensemble probabilities
        
        Returns:
            Array of shape (n_samples, n_classes)
        """
        if not self.is_trained:
            raise RuntimeError("Models not trained yet!")
        
        X_scaled = self.scaler.transform(X)
        
        all_probas = []
        
        for name, model in self.models.items():
            proba = model.predict_proba(X_scaled)
            weight = self.model_weights[name]
            all_probas.append(proba * weight)
        
        ensemble_proba = np.sum(all_probas, axis=0)
        
        # Normalize
        ensemble_proba = ensemble_proba / ensemble_proba.sum(axis=1, keepdims=True)
        
        return ensemble_proba
    
    def get_model_agreement(self, X: np.ndarray) -> np.ndarray:
        """
        Calculate how much models agree (0-1)
        High agreement = more confident prediction
        """
        if not self.is_trained:
            raise RuntimeError("Models not trained yet!")
        
        X_scaled = self.scaler.transform(X)
        
        # Get predictions from each model
        all_preds = []
        for name, model in self.models.items():
            preds = model.predict(X_scaled)
            all_preds.append(preds)
        
        all_preds = np.array(all_preds)  # Shape: (n_models, n_samples)
        
        # Calculate agreement (fraction of models predicting same class)
        agreements = np.zeros(X.shape[0])
        
        for i in range(X.shape[0]):
            predictions = all_preds[:, i]
            # Most common prediction
            counts = np.bincount(predictions, minlength=self.n_classes)
            max_count = counts.max()
            agreements[i] = max_count / len(predictions)
        
        return agreements
    
    def save(self, filepath: str):
        """Save ensemble to file"""
        import joblib
        
        model_data = {
            'models': self.models,
            'scaler': self.scaler,
            'model_weights': self.model_weights,
            'n_classes': self.n_classes,
            'is_trained': self.is_trained
        }
        
        import os
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        joblib.dump(model_data, filepath)
        logger.info(f"💾 Ensemble saved to {filepath}")
    
    @classmethod
    def load(cls, filepath: str) -> 'MultiModelEnsemble':
        """Load ensemble from file"""
        import joblib
        
        model_data = joblib.load(filepath)
        
        ensemble = cls(n_classes=model_data['n_classes'])
        ensemble.models = model_data['models']
        ensemble.scaler = model_data['scaler']
        ensemble.model_weights = model_data['model_weights']
        ensemble.is_trained = model_data['is_trained']
        
        logger.info(f"✅ Ensemble loaded from {filepath}")
        logger.info(f"   Models: {list(ensemble.models.keys())}")
        logger.info(f"   Weights: {ensemble.model_weights}")
        
        return ensemble


def train_and_save_ensemble(
    data_path: str,
    output_path: str,
    prediction_horizon: int = 10
):
    """Helper function to train and save ensemble"""
    from advanced_features import AdvancedFeatureEngineer
    
    logger.info(f"\n📥 Loading data from {data_path}")
    df = pd.read_parquet(data_path)
    logger.info(f"✅ Loaded {len(df)} snapshots")
    
    # Engineer features
    logger.info("\n🔧 Engineering features...")
    feature_engineer = AdvancedFeatureEngineer()
    features_df, feature_names = feature_engineer.engineer_features(df)
    
    features_df = features_df.fillna(0).replace([np.inf, -np.inf], 0)
    
    # Generate labels
    mid_prices = (df['bid_price_1'].values + df['ask_price_1'].values) / 2.0
    
    future_returns = np.zeros(len(mid_prices))
    for i in range(len(mid_prices) - prediction_horizon):
        future_returns[i] = (mid_prices[i + prediction_horizon] - mid_prices[i]) / mid_prices[i]
    
    labels = np.ones(len(mid_prices), dtype=int)
    labels[future_returns > 0.0001] = 2
    labels[future_returns < -0.0001] = 0
    
    # Prepare data
    n_samples = len(features_df)
    features = features_df.values[:n_samples]
    y = labels[:n_samples]
    features = features[:-prediction_horizon]
    y = y[:-prediction_horizon]
    
    # Split (time-series)
    split_idx = int(len(features) * 0.8)
    X_train = features[:split_idx]
    y_train = y[:split_idx]
    X_val = features[split_idx:]
    y_val = y[split_idx:]
    
    logger.info(f"\n📊 Train: {len(X_train)}, Val: {len(X_val)}")
    
    # Train ensemble
    ensemble = MultiModelEnsemble(n_classes=3)
    ensemble.build_models()
    
    accuracies = ensemble.train(X_train, y_train, X_val, y_val)
    
    # Save
    ensemble.save(output_path)
    
    return ensemble


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Train Multi-Model Ensemble')
    parser.add_argument('--data', type=str, default='data/RELIANCE_live.parquet', help='Data path')
    parser.add_argument('--output', type=str, default='output/RELIANCE_multi_ensemble.joblib', help='Output path')
    parser.add_argument('--horizon', type=int, default=10, help='Prediction horizon')
    
    args = parser.parse_args()
    
    train_and_save_ensemble(args.data, args.output, args.horizon)
