"""
Market Simulation Engine
Stochastic processes, price formation, and market dynamics

Implements:
- Geometric Brownian Motion (GBM)
- Jump Diffusion models
- GARCH volatility clustering
- Ornstein-Uhlenbeck (mean reversion)
- Heston stochastic volatility
- Market microstructure noise
"""

import numpy as np
from scipy import stats
from typing import Tuple, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ProcessType(Enum):
    """Types of stochastic processes"""
    GBM = "geometric_brownian_motion"
    JUMP_DIFFUSION = "jump_diffusion"
    GARCH = "garch"
    ORNSTEIN_UHLENBECK = "ornstein_uhlenbeck"
    HESTON = "heston"
    CEV = "constant_elasticity_variance"
    SABR = "stochastic_alpha_beta_rho"


@dataclass
class ProcessParameters:
    """Base parameters for stochastic processes"""
    initial_price: float = 100.0
    dt: float = 1.0 / 252.0  # Daily time step
    seed: Optional[int] = None


@dataclass
class GBMParams(ProcessParameters):
    """Geometric Brownian Motion parameters"""
    mu: float = 0.05          # Drift (expected return)
    sigma: float = 0.2        # Volatility
    dividend_yield: float = 0.0


@dataclass
class JumpDiffusionParams(ProcessParameters):
    """Merton Jump Diffusion parameters"""
    mu: float = 0.05          # Drift
    sigma: float = 0.2        # Diffusion volatility
    jump_intensity: float = 10.0    # Lambda: average jumps per year
    jump_mean: float = -0.02        # Mean jump size (negative for crashes)
    jump_std: float = 0.05          # Jump size volatility


@dataclass
class GARCHParams(ProcessParameters):
    """GARCH(1,1) parameters"""
    mu: float = 0.05          # Drift
    omega: float = 0.000002   # Long-run variance
    alpha: float = 0.1        # ARCH term (shock sensitivity)
    beta: float = 0.85        # GARCH term (persistence)
    initial_variance: Optional[float] = None


@dataclass
class OUParams(ProcessParameters):
    """Ornstein-Uhlenbeck parameters"""
    theta: float = 0.3        # Mean reversion speed
    mu: float = 100.0         # Long-term mean
    sigma: float = 0.2        # Volatility


@dataclass
class HestonParams(ProcessParameters):
    """Heston Stochastic Volatility parameters"""
    mu: float = 0.05          # Drift
    kappa: float = 2.0        # Mean reversion speed of variance
    theta: float = 0.04       # Long-term variance
    sigma: float = 0.3        # Volatility of variance
    rho: float = -0.7         # Correlation between price and variance
    v0: float = 0.04          # Initial variance


class StochasticProcess:
    """Base class for stochastic price processes"""

    def __init__(self, params: ProcessParameters):
        self.params = params
        if params.seed is not None:
            np.random.seed(params.seed)

    def generate(self, n_steps: int) -> np.ndarray:
        """Generate price path"""
        raise NotImplementedError

    def get_variance(self) -> Optional[float]:
        """Get current variance (for stochastic vol models)"""
        return None


class GeometricBrownianMotion(StochasticProcess):
    """
    Standard GBM: dS = μS dt + σS dW
    
    Used as baseline price movement model for liquid assets
    """

    def __init__(self, params: GBMParams):
        super().__init__(params)
        self.params = params

    def generate(self, n_steps: int) -> np.ndarray:
        """Generate GBM price path using exact solution"""
        prices = np.zeros(n_steps)
        prices[0] = self.params.initial_price

        dt = self.params.dt
        mu = self.params.mu - self.params.dividend_yield
        sigma = self.params.sigma

        # Exact solution: S_t = S_0 * exp((μ - σ²/2)t + σW_t)
        increments = np.random.normal(0, np.sqrt(dt), n_steps - 1)
        log_returns = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * increments

        prices[1:] = prices[0] * np.exp(np.cumsum(log_returns))

        logger.debug(f"Generated GBM path: {n_steps} steps, final price: {prices[-1]:.2f}")
        return prices

    def generate_paths(self, n_steps: int, n_paths: int) -> np.ndarray:
        """Generate multiple GBM paths for Monte Carlo"""
        dt = self.params.dt
        mu = self.params.mu - self.params.dividend_yield
        sigma = self.params.sigma

        # Shape: (n_paths, n_steps)
        increments = np.random.normal(0, np.sqrt(dt), (n_paths, n_steps - 1))
        log_returns = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * increments

        # Cumulative sum and exponentiate
        log_prices = np.cumsum(log_returns, axis=1)
        log_prices = np.hstack([np.zeros((n_paths, 1)), log_prices])

        prices = self.params.initial_price * np.exp(log_prices)
        return prices


class MertonJumpDiffusion(StochasticProcess):
    """
    Merton Jump Diffusion: dS/S = (μ - λκ)dt + σdW + dJ
    
    Models sudden price discontinuities (earnings surprises, news shocks)
    κ = exp(jump_mean + jump_std²/2) - 1 (compensator)
    """

    def __init__(self, params: JumpDiffusionParams):
        super().__init__(params)
        self.params = params
        # Calculate compensator to maintain correct drift
        self.kappa = np.exp(params.jump_mean + 0.5 * params.jump_std**2) - 1

    def generate(self, n_steps: int) -> np.ndarray:
        """Generate jump diffusion price path"""
        prices = np.zeros(n_steps)
        prices[0] = self.params.initial_price

        dt = self.params.dt
        mu = self.params.mu
        sigma = self.params.sigma
        lam = self.params.jump_intensity

        # Adjusted drift to compensate for jumps
        mu_adj = mu - lam * self.kappa

        # Brownian motion component
        increments = np.random.normal(0, np.sqrt(dt), n_steps - 1)
        brownian = (mu_adj - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * increments

        # Jump component
        n_jumps = np.random.poisson(lam * dt, n_steps - 1)
        jump_sizes = np.random.normal(self.params.jump_mean, self.params.jump_std, n_steps - 1)
        jumps = n_jumps * jump_sizes

        # Combine
        total_returns = brownian + jumps
        prices[1:] = prices[0] * np.exp(np.cumsum(total_returns))

        n_total_jumps = np.sum(n_jumps)
        logger.debug(f"Generated jump diffusion path: {n_total_jumps} jumps")
        return prices


class GARCHProcess(StochasticProcess):
    """
    GARCH(1,1): σ²_t = ω + αε²_{t-1} + βσ²_{t-1}
    
    Models volatility clustering - periods of high/low volatility persist
    Essential for realistic market simulation
    """

    def __init__(self, params: GARCHParams):
        super().__init__(params)
        self.params = params
        self.current_variance = params.initial_variance or params.omega / (1 - params.alpha - params.beta)

    def generate(self, n_steps: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate GARCH price path and variance path
        Returns: (prices, variances)
        """
        prices = np.zeros(n_steps)
        variances = np.zeros(n_steps)

        prices[0] = self.params.initial_price
        variances[0] = self.current_variance

        omega = self.params.omega
        alpha = self.params.alpha
        beta = self.params.beta
        mu = self.params.mu

        for t in range(1, n_steps):
            # Generate return with current variance
            epsilon = np.random.normal(0, 1)
            return_t = mu + np.sqrt(variances[t-1]) * epsilon

            # Update variance for next period
            variances[t] = omega + alpha * (return_t - mu)**2 + beta * variances[t-1]

            # Update price
            prices[t] = prices[t-1] * np.exp(return_t - 0.5 * variances[t-1])

            self.current_variance = variances[t]

        logger.debug(f"Generated GARCH path: final vol = {np.sqrt(variances[-1]):.4f}")
        return prices, variances

    def forecast_variance(self, n_steps_ahead: int) -> np.ndarray:
        """Forecast future variance (mean-reverts to long-run level)"""
        long_run_var = self.params.omega / (1 - self.params.alpha - self.params.beta)
        forecasts = np.zeros(n_steps_ahead)
        current_var = self.current_variance

        for i in range(n_steps_ahead):
            forecasts[i] = current_var
            current_var = self.params.omega + self.params.alpha * (current_var - long_run_var) + self.params.beta * current_var

        return forecasts


class OrnsteinUhlenbeck(StochasticProcess):
    """
    Mean-reverting process: dX = θ(μ - X)dt + σdW
    
    Used for:
    - Spread trading (pairs trading)
    - Commodity prices
    - FX rates with purchasing power parity
    """

    def __init__(self, params: OUParams):
        super().__init__(params)
        self.params = params

    def generate(self, n_steps: int) -> np.ndarray:
        """Generate OU mean-reverting path"""
        values = np.zeros(n_steps)
        values[0] = self.params.initial_price

        dt = self.params.dt
        theta = self.params.theta
        mu = self.params.mu
        sigma = self.params.sigma

        # Exact discretization
        for t in range(1, n_steps):
            # Mean-reverting drift
            drift = theta * (mu - values[t-1]) * dt

            # Diffusion
            diffusion = sigma * np.sqrt(dt) * np.random.normal()

            values[t] = values[t-1] + drift + diffusion

        logger.debug(f"Generated OU path: mean = {np.mean(values):.2f}, target = {mu}")
        return values

    def half_life(self) -> float:
        """Calculate half-life of mean reversion"""
        return np.log(2) / self.params.theta


class HestonModel(StochasticProcess):
    """
    Heston Stochastic Volatility:
    dS = μS dt + √v S dW₁
    dv = κ(θ - v)dt + σ√v dW₂
    dW₁dW₂ = ρdt
    
    Most realistic model - captures volatility clustering, mean reversion,
    and leverage effect (negative correlation between price and vol)
    """

    def __init__(self, params: HestonParams):
        super().__init__(params)
        self.params = params

    def generate(self, n_steps: int) -> Tuple[np.ndarray, np.ndarray]:
        """Generate Heston price and variance paths using Euler-Maruyama"""
        prices = np.zeros(n_steps)
        variances = np.zeros(n_steps)

        prices[0] = self.params.initial_price
        variances[0] = self.params.v0

        dt = self.params.dt
        kappa = self.params.kappa
        theta = self.params.theta
        sigma = self.params.sigma
        rho = self.params.rho

        # Cholesky decomposition for correlation
        L = np.array([[1, 0], [rho, np.sqrt(1 - rho**2)]])

        for t in range(1, n_steps):
            # Generate correlated Brownian motions
            z = np.random.normal(0, 1, 2)
            corr_z = L @ z

            # Update variance (Feller condition: 2κθ > σ² ensures positivity)
            dv = kappa * (theta - variances[t-1]) * dt + \
                 sigma * np.sqrt(max(variances[t-1], 0)) * np.sqrt(dt) * corr_z[0]
            variances[t] = max(variances[t-1] + dv, 0)  # Floor at zero

            # Update price
            ds = self.params.mu * dt + \
                 np.sqrt(max(variances[t-1], 0)) * np.sqrt(dt) * corr_z[1]
            prices[t] = prices[t-1] * np.exp(ds - 0.5 * variances[t-1])

        logger.debug(f"Generated Heston path: final var = {variances[-1]:.4f}")
        return prices, variances


class MarketMicrostructureNoise:
    """
    Add realistic market microstructure effects to price series
    
    Models:
    - Bid-ask bounce
    - Discrete tick sizes
    - Volume effects
    - Order flow imbalance
    """

    def __init__(
        self,
        tick_size: float = 0.01,
        bid_ask_spread: float = 0.02,
        volume_impact: float = 0.1,
        noise_level: float = 0.001
    ):
        self.tick_size = tick_size
        self.bid_ask_spread = bid_ask_spread
        self.volume_impact = volume_impact
        self.noise_level = noise_level

    def add_noise(self, prices: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        """Add microstructure noise to efficient prices"""
        noisy_prices = prices.copy()

        # Add bid-ask bounce (alternating between bid and ask)
        bounce = np.random.choice([-1, 1], size=len(prices)) * self.bid_ask_spread / 2
        noisy_prices += bounce

        # Add volume impact if provided
        if volumes is not None:
            signed_volume = volumes * np.sign(np.diff(prices, prepend=prices[0]))
            impact = self.volume_impact * signed_volume / np.mean(volumes)
            noisy_prices += impact

        # Add random noise
        noisy_prices += np.random.normal(0, self.noise_level, len(prices))

        # Round to tick size
        noisy_prices = np.round(noisy_prices / self.tick_size) * self.tick_size

        return noisy_prices


class MultiAssetCorrelator:
    """
    Generate correlated price paths across multiple assets
    Uses Cholesky decomposition of correlation matrix
    """

    def __init__(self, correlation_matrix: np.ndarray):
        """
        Initialize with correlation matrix
        
        Args:
            correlation_matrix: NxN symmetric positive definite matrix
        """
        assert correlation_matrix.shape[0] == correlation_matrix.shape[1]
        assert np.allclose(correlation_matrix, correlation_matrix.T)

        self.n_assets = correlation_matrix.shape[0]
        self.correlation_matrix = correlation_matrix
        self.cholesky = np.linalg.cholesky(correlation_matrix)

    def generate_correlated_returns(
        self,
        processes: list,
        n_steps: int
    ) -> np.ndarray:
        """
        Generate correlated price paths
        
        Args:
            processes: List of StochasticProcess instances
            n_steps: Number of time steps
            
        Returns:
            Array of shape (n_assets, n_steps)
        """
        assert len(processes) == self.n_assets

        # Generate independent paths
        independent_paths = np.zeros((self.n_assets, n_steps))

        for i, process in enumerate(processes):
            path = process.generate(n_steps)
            # Convert to returns
            returns = np.diff(np.log(path), prepend=np.log(path[0]))
            independent_paths[i] = returns

        # Apply correlation structure
        correlated_returns = self.cholesky @ independent_paths

        # Convert back to prices
        prices = np.exp(np.cumsum(correlated_returns, axis=1))
        prices *= np.array([p.params.initial_price for p in processes]).reshape(-1, 1)

        return prices


@dataclass
class RegimeParameters:
    """Parameters defining a market regime"""
    name: str
    base_volatility: float
    drift: float
    jump_intensity: float
    mean_reversion: float  # 0 = none, 1 = strong
    liquidity: float  # 0 = illiquid, 1 = highly liquid
    correlation_stability: float  # How stable are cross-asset correlations


class MarketRegimeSimulator:
    """
    Simulate different market regimes with distinct characteristics
    """

    REGIMES = {
        'bull': RegimeParameters(
            name='Bull Market',
            base_volatility=0.15,
            drift=0.20,
            jump_intensity=2.0,
            mean_reversion=0.1,
            liquidity=0.9,
            correlation_stability=0.8
        ),
        'bear': RegimeParameters(
            name='Bear Market',
            base_volatility=0.35,
            drift=-0.15,
            jump_intensity=8.0,
            mean_reversion=0.5,
            liquidity=0.6,
            correlation_stability=0.6
        ),
        'sideways': RegimeParameters(
            name='Sideways/Range-bound',
            base_volatility=0.12,
            drift=0.02,
            jump_intensity=1.0,
            mean_reversion=0.8,
            liquidity=0.8,
            correlation_stability=0.9
        ),
        'high_freq_noise': RegimeParameters(
            name='High-Frequency Noise',
            base_volatility=0.25,
            drift=0.05,
            jump_intensity=5.0,
            mean_reversion=0.3,
            liquidity=0.7,
            correlation_stability=0.5
        ),
        'black_swan': RegimeParameters(
            name='Black Swan Event',
            base_volatility=0.60,
            drift=-0.30,
            jump_intensity=20.0,
            mean_reversion=0.2,
            liquidity=0.2,
            correlation_stability=0.3
        )
    }

    @classmethod
    def create_regime_process(cls, regime_name: str, initial_price: float = 100.0) -> StochasticProcess:
        """Create a stochastic process configured for a specific regime"""
        if regime_name not in cls.REGIMES:
            raise ValueError(f"Unknown regime: {regime_name}. Choose from {list(cls.REGIMES.keys())}")

        regime = cls.REGIMES[regime_name]

        # Use Jump Diffusion as base - can represent all regimes
        params = JumpDiffusionParams(
            initial_price=initial_price,
            mu=regime.drift,
            sigma=regime.base_volatility,
            jump_intensity=regime.jump_intensity,
            jump_mean=-0.03 if regime.drift < 0 else 0.01,
            jump_std=regime.base_volatility * 0.5
        )

        return MertonJumpDiffusion(params)

    @classmethod
    def get_regime_names(cls) -> list:
        return list(cls.REGIMES.keys())
