"""
Ensemble Model for HFT Prediction
Stacking: XGBoost + Random Forest + Gradient Boosting + Meta-learner
"""

import sys
sys.path.insert(0, r'V:\pylibs')

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, StackingClassifier
from sklearn.model_selection import cross_val_predict
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.linear_model import LogisticRegression
import joblib
import time
from typing import Dict, List, Tuple

try:
    from xgboost import XGBClassifier
    HAS_XGBOOST = True
except:
    HAS_XGBOOST = False
    print("⚠️ XGBoost not available")

class HFTEnsemble:
    """
    Stacking ensemble for HFT prediction
    
    Level 1 (Base models):
      - XGBoost
      - Random Forest
      - Gradient Boosting
    
    Level 2 (Meta-learner):
      - Logistic Regression (blends base model predictions)
    """
    
    def __init__(self, n_classes: int = 3):
        self.n_classes = n_classes
        self.models = {}
        self.meta_model = None
        self.feature_names = []
        self.class_weights = None
    
    def create_base_models(self) -> Dict:
        """Create base models with diverse hyperparameters"""
        models = {}
        
        if HAS_XGBOOST:
            models['xgboost'] = XGBClassifier(
                n_estimators=200,
                max_depth=8,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=5,
                gamma=0.1,
                reg_alpha=0.1,
                reg_lambda=1.0,
                eval_metric='mlogloss',
                random_state=42,
                n_jobs=-1
            )
        
        models['random_forest'] = RandomForestClassifier(
            n_estimators=200,
            max_depth=12,
            min_samples_split=10,
            min_samples_leaf=5,
            max_features='sqrt',
            class_weight='balanced',
            random_state=42,
            n_jobs=-1
        )
        
        models['gradient_boosting'] = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42
        )
        
        return models
    
    def create_meta_model(self):
        """Create meta-learner (logistic regression)"""
        return LogisticRegression(
            C=1.0,
            max_iter=1000,
            random_state=42,
            class_weight='balanced'
        )
    
    def fit(self, X_train: np.ndarray, y_train: np.ndarray, 
            feature_names: List[str] = None, use_stacking: bool = True):
        """
        Train ensemble with optional stacking
        
        Args:
            X_train: Training features
            y_train: Training labels
            feature_names: List of feature names
            use_stacking: If True, use stacking. Else, simple voting.
        """
        self.feature_names = feature_names or [f'f{i}' for i in range(X_train.shape[1])]
        
        # Compute class weights
        classes, counts = np.unique(y_train, return_counts=True)
        self.class_weights = {c: len(y_train) / (len(classes) * count) for c, count in zip(classes, counts)}
        sample_weights = np.array([self.class_weights[y] for y in y_train])
        
        print("\n" + "="*60)
        print("🔥 TRAINING ENSEMBLE MODEL")
        print("="*60)
        
        if use_stacking and HAS_XGBOOST:
            # Stacking with cross-validated base predictions
            print("\n📊 Using STACKING ensemble")
            self._train_stacking(X_train, y_train, sample_weights)
        else:
            # Simple voting ensemble
            print("\n📊 Using VOTING ensemble")
            self._train_voting(X_train, y_train, sample_weights)
        
        # Evaluate each model
        self._evaluate_models(X_train, y_train)
    
    def _train_stacking(self, X_train, y_train, sample_weights):
        """Train stacking ensemble"""
        base_models = []
        
        # Train each base model
        for name, model in self.create_base_models().items():
            print(f"\n  Training {name}...")
            start = time.time()
            
            # Handle sample weights for models that support it
            if name == 'xgboost':
                model.fit(X_train, y_train, sample_weight=sample_weights)
            elif hasattr(model, 'feature_importances_') and 'random_forest' in name:
                model.fit(X_train, y_train)  # RF uses class_weight
            else:
                model.fit(X_train, y_train)
            
            train_time = time.time() - start
            self.models[name] = model
            
            # Quick train accuracy
            train_acc = accuracy_score(y_train, model.predict(X_train))
            print(f"    ✓ {name}: {train_time:.2f}s, Train Acc: {train_acc:.3f}")
        
        # Generate meta-features (cross-validated predictions)
        print("\n  Generating meta-features (cross-validation)...")
        meta_features = self._generate_meta_features_cv(X_train, y_train, sample_weights)
        
        # Train meta-learner
        print("  Training meta-learner...")
        self.meta_model = self.create_meta_model()
        self.meta_model.fit(meta_features, y_train)
        
        # Meta-learner accuracy
        meta_preds = self.meta_model.predict(meta_features)
        meta_acc = accuracy_score(y_train, meta_preds)
        print(f"    ✓ Meta-learner train accuracy: {meta_acc:.3f}")
    
    def _generate_meta_features_cv(self, X, y, sample_weights, n_folds=5):
        """Generate meta-features using cross-validation"""
        from sklearn.model_selection import KFold
        
        kf = KFold(n_splits=n_folds, shuffle=False)
        meta_features = np.zeros((len(X), len(self.models) * self.n_classes))
        
        for fold, (train_idx, val_idx) in enumerate(kf.split(X)):
            X_tr, X_val = X[train_idx], X[val_idx]
            y_tr, y_val = y[train_idx], y[val_idx]
            sw_tr = sample_weights[train_idx]
            
            for i, (name, model_template) in enumerate(self.create_base_models().items()):
                # Quick train on fold
                if name == 'xgboost':
                    model_template.fit(X_tr, y_tr, sample_weight=sw_tr)
                else:
                    model_template.fit(X_tr, y_tr)
                
                # Predict probabilities
                probs = model_template.predict_proba(X_val)
                
                # Store in meta-features
                start_col = i * self.n_classes
                meta_features[val_idx, start_col:start_col + probs.shape[1]] = probs
        
        return meta_features
    
    def _train_voting(self, X_train, y_train, sample_weights):
        """Train voting ensemble (fallback)"""
        for name, model in self.create_base_models().items():
            print(f"\n  Training {name}...")
            start = time.time()
            
            if name == 'xgboost':
                model.fit(X_train, y_train, sample_weight=sample_weights)
            else:
                model.fit(X_train, y_train)
            
            train_time = time.time() - start
            self.models[name] = model
            
            train_acc = accuracy_score(y_train, model.predict(X_train))
            print(f"    ✓ {name}: {train_time:.2f}s, Train Acc: {train_acc:.3f}")
    
    def _evaluate_models(self, X, y):
        """Evaluate all models on training data"""
        print("\n" + "="*60)
        print("📊 MODEL EVALUATION")
        print("="*60)
        
        results = {}
        
        for name, model in self.models.items():
            preds = model.predict(X)
            acc = accuracy_score(y, preds)
            f1 = f1_score(y, preds, average='macro', zero_division=0)
            
            results[name] = {'accuracy': acc, 'f1_macro': f1}
            
            print(f"\n  {name.upper()}:")
            print(f"    Accuracy: {acc:.3f}")
            print(f"    F1 Macro: {f1:.3f}")
        
        # Evaluate ensemble
        ensemble_preds = self.predict(X)
        ens_acc = accuracy_score(y, ensemble_preds)
        ens_f1 = f1_score(y, ensemble_preds, average='macro', zero_division=0)
        
        results['ensemble'] = {'accuracy': ens_acc, 'f1_macro': ens_f1}
        
        print(f"\n  ENSEMBLE:")
        print(f"    Accuracy: {ens_acc:.3f}")
        print(f"    F1 Macro: {ens_f1:.3f}")
        
        return results
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict class labels"""
        if self.meta_model is not None:
            # Stacking: use meta-learner
            meta_features = self._generate_meta_features(X)
            return self.meta_model.predict(meta_features)
        else:
            # Voting: average probabilities
            return self._predict_voting(X)
    
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities"""
        if self.meta_model is not None:
            meta_features = self._generate_meta_features(X)
            return self.meta_model.predict_proba(meta_features)
        else:
            return self._predict_proba_voting(X)
    
    def _generate_meta_features(self, X):
        """Generate meta-features from base model predictions"""
        meta_features = np.zeros((len(X), len(self.models) * self.n_classes))
        
        for i, (name, model) in enumerate(self.models.items()):
            probs = model.predict_proba(X)
            start_col = i * self.n_classes
            meta_features[:, start_col:start_col + probs.shape[1]] = probs
        
        return meta_features
    
    def _predict_voting(self, X):
        """Voting prediction"""
        all_preds = np.array([model.predict(X) for model in self.models.values()])
        # Majority vote
        from scipy import stats
        return stats.mode(all_preds, axis=0)[0].flatten()
    
    def _predict_proba_voting(self, X):
        """Voting probability prediction"""
        all_probs = np.array([model.predict_proba(X) for model in self.models.values()])
        return np.mean(all_probs, axis=0)
    
    def get_feature_importance(self) -> Dict[str, float]:
        """Get averaged feature importance across tree-based models"""
        importances = {}
        
        for name, model in self.models.items():
            if hasattr(model, 'feature_importances_'):
                importances[name] = dict(zip(self.feature_names, model.feature_importances_.tolist()))
        
        # Average across models
        if importances:
            avg_importance = {feat: 0 for feat in self.feature_names}
            for model_imp in importances.values():
                for feat, imp in model_imp.items():
                    avg_importance[feat] += imp
            
            for feat in avg_importance:
                avg_importance[feat] /= len(importances)
            
            return avg_importance
        
        return {}
    
    def save(self, filepath: str):
        """Save ensemble to file"""
        joblib.dump({
            'models': self.models,
            'meta_model': self.meta_model,
            'feature_names': self.feature_names,
            'class_weights': self.class_weights,
            'n_classes': self.n_classes
        }, filepath)
        print(f"💾 Ensemble saved to {filepath}")
    
    @classmethod
    def load(cls, filepath: str) -> 'HFTEnsemble':
        """Load ensemble from file"""
        ensemble = cls()
        data = joblib.load(filepath)
        ensemble.models = data['models']
        ensemble.meta_model = data['meta_model']
        ensemble.feature_names = data['feature_names']
        ensemble.class_weights = data['class_weights']
        ensemble.n_classes = data['n_classes']
        return ensemble
