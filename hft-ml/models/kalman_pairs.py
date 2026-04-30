"""
Kalman Filter for Statistical Arbitrage (Pairs Trading)
Dynamic hedge ratio estimation with mean reversion detection
"""

import numpy as np
from typing import Tuple, Optional, Dict, List
from dataclasses import dataclass


@dataclass
class KalmanState:
    """Kalman filter state"""
    state_mean: np.ndarray  # [alpha, beta] - intercept and hedge ratio
    state_cov: np.ndarray   # 2x2 covariance matrix
    observation_noise: float  # R matrix
    process_noise: np.ndarray  # Q matrix


@dataclass
class PairsSignal:
    """Trading signal from pairs model"""
    timestamp: int
    spread: float
    z_score: float
    hedge_ratio: float
    alpha: float
    signal: int  # -1=short spread, 0=no trade, 1=long spread
    confidence: float
    entry_threshold: float = 2.0
    exit_threshold: float = 0.5


class KalmanFilterPairs:
    """
    Rolling Kalman Filter for dynamic pairs trading
    
    Estimates time-varying hedge ratio beta and intercept alpha
    Generates entry/exit signals based on z-score of spread residual
    """
    
    def __init__(self,
                 entry_threshold: float = 2.0,
                 exit_threshold: float = 0.5,
                 delta: float = 1e-4,
                 observation_noise_init: float = 1e-3,
                 process_noise_init: np.ndarray = None):
        
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        
        # Process noise (how fast hedge ratio can change)
        if process_noise_init is None:
            process_noise_init = np.diag([delta, delta])
        
        self.Q = process_noise_init
        self.R = observation_noise_init
        
        # Initial state
        self.state = KalmanState(
            state_mean=np.array([0.0, 1.0]),  # [alpha=0, beta=1]
            state_cov=np.eye(2) * 1.0,
            observation_noise=self.R,
            process_noise=self.Q
        )
        
        # History
        self.spread_history: List[float] = []
        self.z_score_history: List[float] = []
        self.hedge_ratio_history: List[float] = []
        
        # Position tracking
        self.position = 0  # -1, 0, 1
        self.entry_z_score: Optional[float] = None
    
    def update(self, 
               price_A: float, 
               price_B: float,
               timestamp: int) -> PairsSignal:
        """
        Process new prices and generate signal
        
        Args:
            price_A: Price of asset A (y variable)
            price_B: Price of asset B (x variable)
            timestamp: Current timestamp
        
        Returns:
            PairsSignal with trading recommendation
        """
        # === KALMAN FILTER UPDATE ===
        observation = price_A
        design_matrix = np.array([1.0, price_B])  # [1, x] for alpha + beta*x
        
        # Predict step
        predicted_state = self.state.state_mean
        predicted_cov = self.state.state_cov + self.state.process_noise
        
        # Innovation
        predicted_observation = design_matrix @ predicted_state
        innovation = observation - predicted_observation
        
        # Innovation covariance
        innovation_cov = design_matrix @ predicted_cov @ design_matrix.T + self.state.observation_noise
        
        # Kalman gain
        kalman_gain = (predicted_cov @ design_matrix.T) / innovation_cov
        
        # Update step
        self.state.state_mean = predicted_state + kalman_gain * innovation
        self.state.state_cov = (np.eye(2) - np.outer(kalman_gain, design_matrix)) @ predicted_cov
        
        # Extract parameters
        alpha = self.state.state_mean[0]
        beta = self.state.state_mean[1]
        
        # === COMPUTE SPREAD AND Z-SCORE ===
        spread = price_A - (alpha + beta * price_B)
        self.spread_history.append(spread)
        
        # Rolling z-score
        spread_array = np.array(self.spread_history[-100:])
        spread_mean = np.mean(spread_array)
        spread_std = np.std(spread_array) + 1e-10
        z_score = (spread - spread_mean) / spread_std
        
        self.z_score_history.append(z_score)
        self.hedge_ratio_history.append(beta)
        
        # === GENERATE SIGNAL ===
        signal = self._generate_signal(z_score, beta)
        
        return PairsSignal(
            timestamp=timestamp,
            spread=spread,
            z_score=z_score,
            hedge_ratio=beta,
            alpha=alpha,
            signal=signal,
            confidence=min(1.0, abs(z_score) / self.entry_threshold),
            entry_threshold=self.entry_threshold,
            exit_threshold=self.exit_threshold
        )
    
    def _generate_signal(self, z_score: float, hedge_ratio: float) -> int:
        """Generate trading signal based on z-score"""
        
        if self.position == 0:
            # No position - look for entry
            if z_score > self.entry_threshold:
                self.position = -1  # Short spread (sell A, buy B)
                self.entry_z_score = z_score
                return -1
            elif z_score < -self.entry_threshold:
                self.position = 1  # Long spread (buy A, sell B)
                self.entry_z_score = z_score
                return 1
        else:
            # Have position - look for exit
            if (self.position == 1 and z_score > -self.exit_threshold) or \
               (self.position == -1 and z_score < self.exit_threshold):
                self.position = 0
                self.entry_z_score = None
                return 0  # Exit signal
        
        return 0  # No action
    
    def compute_trade_sizes(self, 
                           capital: float,
                           price_A: float,
                           price_B: float,
                           risk_per_trade: float = 0.02) -> Tuple[int, int]:
        """
        Compute optimal trade sizes for both legs
        
        Args:
            capital: Available capital
            price_A: Current price of asset A
            price_B: Current price of asset B
            risk_per_trade: Risk as fraction of capital
        
        Returns:
            (size_A, size_B) - positive=long, negative=short
        """
        beta = self.state.state_mean[1]
        
        # Risk-based sizing
        risk_amount = capital * risk_per_trade
        spread_std = np.std(self.spread_history[-100:]) + 1e-10
        
        # Size based on z-score mean reversion expectation
        expected_reversion = abs(self.z_score_history[-1]) * spread_std
        if expected_reversion <= 0:
            return 0, 0
        
        # Notional value
        notional_A = risk_amount / (spread_std / price_A + 1e-10)
        notional_B = notional_A * beta
        
        # Convert to share counts
        size_A = int(notional_A / price_A)
        size_B = int(notional_B / price_B)
        
        # Apply sign based on position
        if self.position == -1:
            return -size_A, size_B  # Short A, Long B
        elif self.position == 1:
            return size_A, -size_B  # Long A, Short B
        
        return 0, 0
    
    def get_state(self) -> Dict:
        """Get current filter state"""
        return {
            'alpha': float(self.state.state_mean[0]),
            'beta': float(self.state.state_mean[1]),
            'alpha_std': float(np.sqrt(self.state.state_cov[0, 0])),
            'beta_std': float(np.sqrt(self.state.state_cov[1, 1])),
            'current_z_score': float(self.z_score_history[-1]) if self.z_score_history else 0.0,
            'position': self.position,
            'spread_history_len': len(self.spread_history)
        }
    
    def reset(self):
        """Reset filter to initial state"""
        self.state = KalmanState(
            state_mean=np.array([0.0, 1.0]),
            state_cov=np.eye(2) * 1.0,
            observation_noise=self.R,
            process_noise=self.Q
        )
        self.spread_history.clear()
        self.z_score_history.clear()
        self.hedge_ratio_history.clear()
        self.position = 0
        self.entry_z_score = None
