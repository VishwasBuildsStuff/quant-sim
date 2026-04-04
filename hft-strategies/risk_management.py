"""
Risk Management System
Pre-trade and post-trade risk controls

Features:
- Pre-trade risk checks (position limits, capital adequacy)
- Post-trade analysis (VaR, stress testing)
- Real-time PnL monitoring
- Drawdown controls
- Fat-finger error prevention
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from scipy import stats
import logging

logger = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    """Risk limits for a trader/portfolio"""
    max_position_size: float = 1_000_000.0  # Maximum position value
    max_order_size: float = 100_000.0  # Maximum single order value
    max_daily_loss: float = 50_000.0  # Maximum daily loss
    max_drawdown: float = 0.10  # Maximum drawdown (10%)
    max_leverage: float = 2.0  # Maximum leverage ratio
    max_var_95: float = 100_000.0  # Maximum 95% VaR
    max_concentration: float = 0.20  # Maximum single asset concentration (20%)
    max_sector_exposure: float = 0.40  # Maximum sector exposure
    max_turnover: float = 10.0  # Maximum daily turnover multiple


@dataclass
class RiskMetrics:
    """Current risk metrics"""
    current_pnl: float = 0.0
    daily_pnl: float = 0.0
    total_exposure: float = 0.0
    leverage: float = 1.0
    var_95: float = 0.0
    var_99: float = 0.0
    expected_shortfall: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    concentration: Dict[str, float] = field(default_factory=dict)


class PreTradeRiskEngine:
    """
    Pre-trade risk checks before order submission
    
    Checks:
    - Order size limits
    - Position limits
    - Capital adequacy
    - Fat-finger detection
    - Price reasonability
    - Regulatory constraints
    """
    
    def __init__(self, limits: RiskLimits):
        self.limits = limits
        
        # Current state
        self.positions: Dict[str, float] = {}  # instrument -> value
        self.daily_pnl: float = 0.0
        self.daily_turnover: float = 0.0
        self.orders_today: int = 0
        
        # Fat-finger detection thresholds
        self.price_deviation_threshold = 0.05  # 5% from market
        self.quantity_spike_threshold = 10.0  # 10x average
        
        # Order tracking
        self.recent_orders: List[Dict] = []
    
    def check_order(self, 
                   instrument: str,
                   side: str,
                   quantity: float,
                   price: float,
                   order_type: str,
                   current_market_price: float,
                   available_capital: float,
                   avg_order_size: float = 1000.0) -> Tuple[bool, str]:
        """
        Pre-trade risk check
        
        Returns:
            (passed: bool, reason: str)
        """
        order_value = quantity * price
        
        # 1. Order size check
        if order_value > self.limits.max_order_size:
            return False, f"Order size {order_value:.2f} exceeds limit {self.limits.max_order_size:.2f}"
        
        # 2. Fat-finger detection - price
        if order_type in ['limit', 'stop_limit']:
            price_deviation = abs(price - current_market_price) / current_market_price
            if price_deviation > self.price_deviation_threshold:
                return False, f"Price deviation {price_deviation*100:.2f}% exceeds threshold"
        
        # 3. Fat-finger detection - quantity
        if avg_order_size > 0 and quantity > avg_order_size * self.quantity_spike_threshold:
            return False, f"Quantity {quantity} is {quantity/avg_order_size:.1f}x average"
        
        # 4. Position limit check
        current_position = self.positions.get(instrument, 0.0)
        new_position_value = abs(current_position + (order_value if side == 'buy' else -order_value))
        
        if new_position_value > self.limits.max_position_size:
            return False, f"Position would exceed limit"
        
        # 5. Capital adequacy
        if order_value > available_capital * self.limits.max_leverage:
            return False, f"Insufficient capital for order"
        
        # 6. Daily loss limit
        if self.daily_pnl < -self.limits.max_daily_loss:
            return False, f"Daily loss limit exceeded"
        
        # 7. Order rate limit (prevent runaway algorithms)
        self.orders_today += 1
        if self.orders_today > 10000:  # Reasonable daily limit
            return False, f"Daily order limit exceeded"
        
        # 8. Check for wash trading (self-trading)
        if self._detect_wash_trade_pattern(instrument, side, quantity, price):
            return False, f"Potential wash trading detected"
        
        # All checks passed
        return True, "Order approved"
    
    def _detect_wash_trade_pattern(self, 
                                   instrument: str, 
                                   side: str, 
                                   quantity: float, 
                                   price: float) -> bool:
        """Detect potential wash trading (buying and selling to yourself)"""
        if len(self.recent_orders) < 5:
            return False
        
        # Check recent orders for opposite side at similar price
        recent_same_instrument = [
            o for o in self.recent_orders[-20:]
            if o['instrument'] == instrument and o['side'] != side
        ]
        
        for order in recent_same_instrument:
            price_diff = abs(order['price'] - price) / price
            if price_diff < 0.001 and order['quantity'] == quantity:  # Very similar
                return True
        
        return False
    
    def update_position(self, instrument: str, value: float):
        """Update position after fill"""
        self.positions[instrument] = value
        self.daily_turnover += abs(value)
        self.recent_orders.append({
            'instrument': instrument,
            'value': value,
            'timestamp': datetime.now()
        })
    
    def update_pnl(self, pnl: float):
        """Update daily PnL"""
        self.daily_pnl += pnl
    
    def reset_daily_limits(self):
        """Reset daily counters"""
        self.daily_pnl = 0.0
        self.daily_turnover = 0.0
        self.orders_today = 0
        self.recent_orders.clear()


class PostTradeRiskAnalyzer:
    """
    Post-trade risk analysis
    
    Calculates:
    - Value at Risk (VaR)
    - Expected Shortfall (CVaR)
    - Stress test results
    - Drawdown analysis
    - Risk attribution
    """
    
    def __init__(self, confidence_levels: List[float] = None):
        if confidence_levels is None:
            confidence_levels = [0.95, 0.99]
        self.confidence_levels = confidence_levels
        
        # PnL history
        self.pnl_history: List[float] = []
        self.position_history: List[Dict[str, float]] = []
    
    def calculate_var_historical(self, 
                               confidence: float = 0.95,
                               lookback: int = 252) -> float:
        """
        Calculate Value at Risk using historical simulation
        
        VaR: Maximum loss at given confidence level
        """
        if len(self.pnl_history) < lookback:
            return 0.0
        
        returns = self.pnl_history[-lookback:]
        var = np.percentile(returns, (1 - confidence) * 100)
        
        return abs(var)
    
    def calculate_var_parametric(self, 
                                confidence: float = 0.95,
                                lookback: int = 252) -> float:
        """
        Calculate VaR using parametric method (assumes normal distribution)
        """
        if len(self.pnl_history) < lookback:
            return 0.0
        
        returns = self.pnl_history[-lookback:]
        mean = np.mean(returns)
        std = np.std(returns)
        
        # Z-score for confidence level
        z_score = stats.norm.ppf(1 - confidence)
        
        var = abs(mean + z_score * std)
        return var
    
    def calculate_var_monte_carlo(self, 
                                 confidence: float = 0.95,
                                 n_simulations: int = 10000,
                                 lookback: int = 252) -> float:
        """
        Calculate VaR using Monte Carlo simulation
        """
        if len(self.pnl_history) < lookback:
            return 0.0
        
        returns = self.pnl_history[-lookback:]
        mean = np.mean(returns)
        std = np.std(returns)
        
        # Simulate future returns
        simulated_returns = np.random.normal(mean, std, n_simulations)
        
        var = np.percentile(simulated_returns, (1 - confidence) * 100)
        return abs(var)
    
    def calculate_expected_shortfall(self, 
                                    confidence: float = 0.95,
                                    lookback: int = 252) -> float:
        """
        Calculate Expected Shortfall (CVaR)
        Average loss beyond VaR
        """
        if len(self.pnl_history) < lookback:
            return 0.0
        
        returns = self.pnl_history[-lookback:]
        var = np.percentile(returns, (1 - confidence) * 100)
        
        # Average of losses beyond VaR
        tail_returns = [r for r in returns if r <= var]
        if not tail_returns:
            return abs(var)
        
        es = abs(np.mean(tail_returns))
        return es
    
    def calculate_max_drawdown(self, 
                              portfolio_values: List[float]) -> Tuple[float, int, int]:
        """
        Calculate maximum drawdown
        
        Returns:
            (max_drawdown, peak_index, trough_index)
        """
        if not portfolio_values:
            return 0.0, 0, 0
        
        peak = portfolio_values[0]
        max_dd = 0.0
        peak_idx = 0
        trough_idx = 0
        
        for i, value in enumerate(portfolio_values):
            if value > peak:
                peak = value
                peak_idx = i
            
            dd = (peak - value) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                trough_idx = i
        
        return max_dd, peak_idx, trough_idx
    
    def stress_test(self, 
                   portfolio_returns: np.ndarray,
                   scenarios: Dict[str, float]) -> Dict[str, float]:
        """
        Stress test portfolio against historical scenarios
        
        Args:
            portfolio_returns: Array of portfolio returns
            scenarios: Dict of scenario name -> shock multiplier
            
        Returns:
            Dict of scenario -> stressed loss
        """
        results = {}
        
        for scenario_name, shock in scenarios.items():
            stressed_returns = portfolio_returns * shock
            loss = np.percentile(stressed_returns, 5)  # 5th percentile loss
            results[scenario_name] = loss
        
        return results
    
    def calculate_risk_attribution(self, 
                                  positions: Dict[str, float],
                                  covariance_matrix: np.ndarray,
                                  portfolio_variance: float) -> Dict[str, float]:
        """
        Calculate marginal contribution to risk for each position
        """
        if portfolio_variance == 0:
            return {asset: 0.0 for asset in positions}
        
        weights = np.array(list(positions.values()))
        total_value = sum(positions.values())
        
        if total_value == 0:
            return {asset: 0.0 for asset in positions}
        
        weight_vector = weights / total_value
        
        # Marginal contribution to risk
        marginal_risk = covariance_matrix @ weight_vector
        
        # Component risk
        component_risk = weight_vector * marginal_risk
        total_risk = np.sqrt(portfolio_variance)
        
        # Risk contribution as percentage
        risk_contributions = component_risk / total_risk if total_risk > 0 else component_risk
        
        return dict(zip(positions.keys(), risk_contributions))
    
    def add_pnl_observation(self, pnl: float):
        """Add PnL observation to history"""
        self.pnl_history.append(pnl)
    
    def get_risk_metrics(self, portfolio_value: float) -> RiskMetrics:
        """Get comprehensive risk metrics"""
        metrics = RiskMetrics()
        
        if len(self.pnl_history) > 0:
            metrics.daily_pnl = self.pnl_history[-1]
            metrics.var_95 = self.calculate_var_historical(0.95)
            metrics.var_99 = self.calculate_var_historical(0.99)
            metrics.expected_shortfall = self.calculate_expected_shortfall(0.95)
        
        return metrics


class CircuitBreaker:
    """
    Circuit breaker implementation
    
    Halts trading when certain thresholds are breached
    Based on SEC Rule 11 (Limit Up-Limit Down)
    """
    
    def __init__(self, 
                 level1_pct: float = 0.05,  # 5% move
                 level2_pct: float = 0.10,  # 10% move
                 level3_pct: float = 0.20,  # 20% move
                 cooldown_seconds: int = 300):
        self.level1_threshold = level1_pct
        self.level2_threshold = level2_pct
        self.level3_threshold = level3_pct
        self.cooldown_seconds = cooldown_seconds
        
        self.trading_halted = False
        self.halt_level = 0
        self.halt_start_time: Optional[datetime] = None
        
        # Price tracking
        self.reference_price: Optional[float] = None
        self.price_history: List[float] = []
    
    def check_price_move(self, current_price: float) -> Tuple[bool, str]:
        """
        Check if price movement triggers circuit breaker
        
        Returns:
            (halt_trading: bool, reason: str)
        """
        self.price_history.append(current_price)
        
        if self.reference_price is None:
            self.reference_price = current_price
            return False, ""
        
        # Calculate price move
        price_move = abs(current_price - self.reference_price) / self.reference_price
        
        # Check halt levels
        if self.trading_halted:
            # Check if cooldown has passed
            if self.halt_start_time:
                elapsed = (datetime.now() - self.halt_start_time).total_seconds()
                if elapsed >= self.cooldown_seconds:
                    self.trading_halted = False
                    self.halt_level = 0
                    self.reference_price = current_price
                    return False, "Trading resumed after cooldown"
            return True, f"Trading halted (Level {self.halt_level})"
        
        # Level 3 halt (most severe)
        if price_move >= self.level3_threshold:
            self._trigger_halt(3)
            return True, f"LEVEL 3 CIRCUIT BREAKER: {price_move*100:.1f}% move"
        
        # Level 2 halt
        if price_move >= self.level2_threshold:
            self._trigger_halt(2)
            return True, f"LEVEL 2 CIRCUIT BREAKER: {price_move*100:.1f}% move"
        
        # Level 1 halt
        if price_move >= self.level1_threshold:
            self._trigger_halt(1)
            return True, f"LEVEL 1 CIRCUIT BREAKER: {price_move*100:.1f}% move"
        
        return False, ""
    
    def _trigger_halt(self, level: int):
        """Trigger trading halt"""
        self.trading_halted = True
        self.halt_level = level
        self.halt_start_time = datetime.now()
        
        logger.warning(f"Circuit breaker triggered: Level {level}")
    
    def reset(self):
        """Reset circuit breaker"""
        self.trading_halted = False
        self.halt_level = 0
        self.halt_start_time = None
        self.reference_price = None
        self.price_history.clear()
