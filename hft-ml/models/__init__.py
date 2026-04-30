"""
HFT-ML Model Architectures

Available models:
  - GRUCNNModel: Hybrid GRU-CNN for LOB-based price prediction
  - SiameseLSTMAttention: Siamese LSTM with cross-attention for bid/ask processing
  - KalmanFilterPairs: Kalman filter for dynamic pairs trading
  - RegimeAdaptivePredictor: Regime-adaptive model with HMM detection
"""

from .gru_cnn import GRUCNNModel, FocalLoss, HuberLoss, MultiTaskLoss, count_parameters
from .siamese_lstm_attention import SiameseLSTMAttention
from .kalman_pairs import KalmanFilterPairs, KalmanState, PairsSignal
from .regime_adaptive import RegimeAdaptivePredictor, RegimeDetectorHMM, RegimeGatingNetwork

__all__ = [
    'GRUCNNModel',
    'FocalLoss',
    'HuberLoss',
    'MultiTaskLoss',
    'count_parameters',
    'SiameseLSTMAttention',
    'KalmanFilterPairs',
    'KalmanState',
    'PairsSignal',
    'RegimeAdaptivePredictor',
    'RegimeDetectorHMM',
    'RegimeGatingNetwork',
]
