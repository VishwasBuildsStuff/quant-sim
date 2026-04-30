"""
Regime-Adaptive Model Architecture
HMM for regime detection + attention-based gating for model blending
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Dict, Tuple, Optional

try:
    from hmmlearn import hmm
    HMMLEARN_AVAILABLE = True
except ImportError:
    HMMLEARN_AVAILABLE = False
    hmm = None


class RegimeDetectorHMM(nn.Module):
    """
    Hidden Markov Model for market regime detection
    Regimes: Low Vol, High Vol, Trending, Mean-Reverting
    """
    
    def __init__(self, 
                 n_regimes: int = 4,
                 n_features: int = 10,
                 covariance_type: str = 'full'):
        super().__init__()
        
        if not HMMLEARN_AVAILABLE:
            raise ImportError(
                "hmmlearn is required for RegimeDetectorHMM. "
                "Install it with: pip install hmmlearn"
            )
        
        self.n_regimes = n_regimes
        self.n_features = n_features
        
        # sklearn HMM (not differentiable, used for inference)
        self.hmm_model = hmm.GaussianHMM(
            n_components=n_regimes,
            covariance_type=covariance_type,
            n_iter=100,
            random_state=42
        )
        
        self.is_fitted = False
        
        # Regime names for interpretation
        self.regime_names = ['low_vol', 'high_vol', 'trending', 'mean_reverting']
    
    def fit(self, features: np.ndarray) -> 'RegimeDetectorHMM':
        """
        Fit HMM to historical features
        
        Args:
            features: (n_samples, n_features) - volatility, returns, OFI, etc.
        
        Returns:
            self
        """
        if features.ndim != 2:
            raise ValueError(f"Expected 2D array, got {features.ndim}D")
        if features.shape[1] != self.n_features:
            raise ValueError(
                f"Expected {self.n_features} features, got {features.shape[1]}"
            )
        
        self.hmm_model.fit(features)
        self.is_fitted = True
        return self
    
    def predict_regime(self, features: np.ndarray) -> int:
        """
        Predict current regime
        
        Args:
            features: (1, n_features) or (n_samples, n_features)
        
        Returns:
            regime index (0 to n_regimes-1)
        """
        if not self.is_fitted:
            raise RuntimeError("HMM not fitted. Call fit() first.")
        
        if features.ndim == 1:
            features = features.reshape(1, -1)
        
        return self.hmm_model.predict(features)[-1]
    
    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """
        Get regime probabilities
        
        Args:
            features: (n_samples, n_features)
        
        Returns:
            (n_regimes,) probability vector for last sample
        """
        if not self.is_fitted:
            return np.ones(self.n_regimes) / self.n_regimes
        
        if features.ndim == 1:
            features = features.reshape(1, -1)
        
        return self.hmm_model.predict_proba(features)[-1]
    
    def get_regime_stats(self) -> Dict:
        """Get statistics for each regime"""
        if not self.is_fitted:
            return {}
        
        stats = {}
        for i in range(self.n_regimes):
            # Handle different covariance shapes
            if len(self.hmm_model.covars_.shape) == 2:
                variance = self.hmm_model.covars_[i].diagonal().tolist()
            else:
                variance = self.hmm_model.covars_[i][i].diagonal().tolist()
            
            stats[self.regime_names[i]] = {
                'mean': self.hmm_model.means_[i].tolist(),
                'variance': variance,
                'transition_probs': self.hmm_model.transmat_[i].tolist()
            }
        
        return stats


class RegimeGatingNetwork(nn.Module):
    """
    Attention-based gating network that blends predictions
    from multiple sub-models based on detected regime
    """
    
    def __init__(self,
                 n_regimes: int = 4,
                 n_sub_models: int = 3,
                 input_dim: int = 20,
                 hidden_dim: int = 64):
        super().__init__()
        
        self.n_regimes = n_regimes
        self.n_sub_models = n_sub_models
        
        # Regime classifier (small neural network)
        self.regime_classifier = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, n_regimes),
            nn.Softmax(dim=-1)
        )
        
        # Gating network (outputs weights for sub-models)
        self.gate_generator = nn.Sequential(
            nn.Linear(n_regimes + input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_sub_models),
            nn.Softmax(dim=-1)  # Weights sum to 1
        )
    
    def forward(self, 
                features: torch.Tensor,
                sub_model_outputs: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Blend sub-model outputs based on regime
        
        Args:
            features: (batch, input_dim) - market features
            sub_model_outputs: (batch, n_sub_models, output_dim) - predictions from each model
        
        Returns:
            Dict with blended_output, regime_probs, and gate_weights
        """
        batch_size = features.shape[0]
        
        # Predict regime probabilities
        regime_probs = self.regime_classifier(features)  # (batch, n_regimes)
        
        # Generate gating weights
        gate_input = torch.cat([features, regime_probs], dim=-1)
        gate_weights = self.gate_generator(gate_input)  # (batch, n_sub_models)
        
        # Blend sub-model outputs
        # gate_weights: (batch, n_sub_models)
        # sub_model_outputs: (batch, n_sub_models, output_dim)
        gate_weights_expanded = gate_weights.unsqueeze(-1)  # (batch, n_sub_models, 1)
        
        blended_output = (gate_weights_expanded * sub_model_outputs).sum(dim=1)  # (batch, output_dim)
        
        return {
            'blended_output': blended_output,
            'regime_probs': regime_probs,
            'gate_weights': gate_weights
        }


class RegimeAdaptivePredictor(nn.Module):
    """
    Complete regime-adaptive prediction system
    Combines HMM regime detection with gated model blending
    """
    
    def __init__(self,
                 n_regimes: int = 4,
                 n_features: int = 45,
                 n_sub_models: int = 3,
                 sub_model_output_dim: int = 128):
        super().__init__()
        
        # Regime detector (trained separately)
        self.regime_detector = RegimeDetectorHMM(
            n_regimes=n_regimes,
            n_features=min(n_features, 20)  # Use subset for HMM
        )
        
        # Gating network
        self.gating = RegimeGatingNetwork(
            n_regimes=n_regimes,
            n_sub_models=n_sub_models,
            input_dim=n_features
        )
        
        # Sub-model specialization layers
        # Each regime gets specialized adapter
        self.regime_adapters = nn.ModuleList([
            nn.Sequential(
                nn.Linear(sub_model_output_dim, sub_model_output_dim),
                nn.ReLU(),
                nn.Dropout(0.1)
            ) for _ in range(n_regimes)
        ])
    
    def forward(self, 
                features: torch.Tensor,
                sub_model_outputs: torch.Tensor,
                hmm_features: Optional[torch.Tensor] = None) -> Dict:
        """
        Forward pass for regime-adaptive prediction
        
        Args:
            features: (batch, n_features)
            sub_model_outputs: (batch, n_sub_models, sub_model_output_dim)
            hmm_features: (batch, n_hmm_features) - features for HMM
        
        Returns:
            Dict with output, regime_probs, gate_weights, and adapted_outputs
        """
        batch_size = features.shape[0]
        
        # Adapt sub-model outputs per regime
        adapted_outputs = []
        for i in range(self.regime_detector.n_regimes):
            adapted = self.regime_adapters[i](sub_model_outputs)
            adapted_outputs.append(adapted)
        
        # Stack: (n_regimes, batch, n_sub_models, output_dim)
        adapted_tensor = torch.stack(adapted_outputs, dim=0)
        
        # Use HMM features if provided, else use main features
        hmm_feat = hmm_features if hmm_features is not None else features[:, :20]
        
        # Get regime probabilities (using numpy HMM)
        if self.regime_detector.is_fitted:
            regime_probs_np = self.regime_detector.predict_proba(hmm_feat.detach().cpu().numpy())
            regime_probs = torch.tensor(regime_probs_np, device=features.device, dtype=features.dtype)
            if regime_probs.ndim == 1:
                regime_probs = regime_probs.unsqueeze(0).expand(batch_size, -1)
        else:
            regime_probs = torch.ones(batch_size, self.regime_detector.n_regimes, device=features.device) / self.regime_detector.n_regimes
        
        # Gate and blend
        gate_input = torch.cat([features, regime_probs], dim=-1)
        gate_weights = self.gating.gate_generator(gate_input)
        
        # Final blending
        gate_expanded = gate_weights.unsqueeze(-1)  # (batch, n_sub_models, 1)
        blended = (gate_expanded * sub_model_outputs).sum(dim=1)
        
        return {
            'output': blended,
            'regime_probs': regime_probs,
            'gate_weights': gate_weights,
            'adapted_outputs': adapted_tensor
        }
