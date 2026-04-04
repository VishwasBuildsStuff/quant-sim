"""
HFT Analytics Engine
Comprehensive performance measurement and attribution

Metrics:
- Profit & Loss (PnL) analysis
- Risk-adjusted returns (Sharpe, Sortino, Calmar)
- Drawdown analysis
- VaR and Expected Shortfall
- Execution quality (slippage, fill rates)
- Win/Loss analysis
- Performance attribution
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from scipy import stats
import logging

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Individual trade record"""
    trade_id: str
    agent_id: str
    instrument: str
    side: str  # 'buy' or 'sell'
    quantity: float
    price: float
    commission: float
    timestamp: datetime
    pnl: float = 0.0
    holding_period_seconds: float = 0.0


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics"""
    # Basic metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # PnL metrics
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    
    # Risk-adjusted returns
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    omega_ratio: float = 0.0
    information_ratio: float = 0.0
    
    # Risk metrics
    max_drawdown: float = 0.0
    max_drawdown_duration_days: int = 0
    current_drawdown: float = 0.0
    var_95: float = 0.0
    var_99: float = 0.0
    expected_shortfall: float = 0.0
    volatility: float = 0.0
    skewness: float = 0.0
    kurtosis: float = 0.0
    
    # Execution metrics
    total_commission: float = 0.0
    avg_slippage_bps: float = 0.0
    fill_rate: float = 0.0
    avg_holding_period_seconds: float = 0.0
    
    # Additional analytics
    profit_factor: float = 0.0
    recovery_factor: float = 0.0
    tail_ratio: float = 0.0
    common_sense_ratio: float = 0.0
    payoff_ratio: float = 0.0
    
    # Time series
    equity_curve: List[float] = field(default_factory=list)
    returns_series: List[float] = field(default_factory=list)
    drawdown_series: List[float] = field(default_factory=list)


class PerformanceAnalyzer:
    """
    Analyze trading performance
    
    Calculates comprehensive set of performance metrics
    """
    
    def __init__(self, risk_free_rate: float = 0.02):
        self.risk_free_rate = risk_free_rate
        
        # Trade history
        self.trades: List[TradeRecord] = []
        
        # Equity tracking
        self.equity_curve: List[float] = []
        self.returns_series: List[float] = []
    
    def add_trade(self, trade: TradeRecord):
        """Add trade to history"""
        self.trades.append(trade)
    
    def calculate_metrics(self, initial_capital: float) -> PerformanceMetrics:
        """Calculate all performance metrics"""
        metrics = PerformanceMetrics()
        
        if not self.trades:
            return metrics
        
        # Calculate PnL for each trade
        pnls = [t.pnl for t in self.trades]
        metrics.total_trades = len(pnls)
        metrics.winning_trades = sum(1 for p in pnls if p > 0)
        metrics.losing_trades = sum(1 for p in pnls if p < 0)
        metrics.win_rate = metrics.winning_trades / metrics.total_trades if metrics.total_trades > 0 else 0.0
        
        # PnL statistics
        metrics.total_pnl = sum(pnls)
        metrics.avg_pnl = np.mean(pnls)
        
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        
        metrics.avg_win = np.mean(wins) if wins else 0.0
        metrics.avg_loss = np.mean(losses) if losses else 0.0
        metrics.largest_win = max(pnls)
        metrics.largest_loss = min(pnls)
        
        # Profit factor
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 1.0
        metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Payoff ratio
        metrics.payoff_ratio = abs(metrics.avg_win / metrics.avg_loss) if metrics.avg_loss != 0 else 0.0
        
        # Commission
        metrics.total_commission = sum(t.commission for t in self.trades)
        
        # Build equity curve
        equity = initial_capital
        self.equity_curve = [initial_capital]
        
        for pnl in pnls:
            equity += pnl
            self.equity_curve.append(equity)
        
        # Calculate returns
        if len(self.equity_curve) > 1:
            self.returns_series = np.diff(self.equity_curve) / self.equity_curve[:-1]
        
        metrics.equity_curve = self.equity_curve
        metrics.returns_series = list(self.returns_series)
        
        # Risk-adjusted returns
        if len(self.returns_series) > 1:
            returns = np.array(self.returns_series)
            
            # Sharpe ratio
            excess_returns = returns - self.risk_free_rate / 252
            if np.std(excess_returns) > 0:
                metrics.sharpe_ratio = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)
            
            # Sortino ratio (downside deviation)
            downside_returns = returns[returns < 0]
            if len(downside_returns) > 0:
                downside_std = np.std(downside_returns)
                if downside_std > 0:
                    metrics.sortino_ratio = np.mean(returns) / downside_std * np.sqrt(252)
            
            # Volatility
            metrics.volatility = np.std(returns) * np.sqrt(252)
            
            # Skewness and kurtosis
            if len(returns) > 2:
                metrics.skewness = stats.skew(returns)
            if len(returns) > 3:
                metrics.kurtosis = stats.kurtosis(returns)
        
        # Drawdown analysis
        metrics.max_drawdown, metrics.max_drawdown_duration_days = self._calculate_max_drawdown()
        metrics.current_drawdown = self._calculate_current_drawdown()
        metrics.drawdown_series = self._calculate_drawdown_series()
        
        # Calmar ratio
        if metrics.max_drawdown > 0:
            annualized_return = (self.equity_curve[-1] / self.equity_curve[0] - 1)
            metrics.calmar_ratio = annualized_return / metrics.max_drawdown
        
        # Omega ratio
        if len(self.returns_series) > 0:
            metrics.omega_ratio = self._calculate_omega_ratio()
        
        # VaR
        if len(self.returns_series) > 0:
            returns = np.array(self.returns_series)
            metrics.var_95 = abs(np.percentile(returns, 5))
            metrics.var_99 = abs(np.percentile(returns, 1))
            
            # Expected Shortfall
            tail_returns = returns[returns <= -metrics.var_95]
            metrics.expected_shortfall = abs(np.mean(tail_returns)) if len(tail_returns) > 0 else metrics.var_95
        
        # Recovery factor
        if metrics.max_drawdown > 0:
            metrics.recovery_factor = metrics.total_pnl / (initial_capital * metrics.max_drawdown)
        
        # Tail ratio
        if len(self.returns_series) > 0:
            returns = np.array(self.returns_series)
            tail_95 = np.percentile(returns, 95)
            tail_5 = np.percentile(returns, 5)
            metrics.tail_ratio = abs(tail_95 / tail_5) if tail_5 != 0 else 0.0
        
        # Common Sense Ratio
        if len(self.returns_series) > 0:
            returns = np.array(self.returns_series)
            median_return = np.median(returns)
            metrics.common_sense_ratio = median_return / metrics.volatility if metrics.volatility > 0 else 0.0
        
        # Average holding period
        holding_periods = [t.holding_period_seconds for t in self.trades if t.holding_period_seconds > 0]
        if holding_periods:
            metrics.avg_holding_period_seconds = np.mean(holding_periods)
        
        return metrics
    
    def _calculate_max_drawdown(self) -> Tuple[float, int]:
        """Calculate maximum drawdown and duration"""
        if not self.equity_curve:
            return 0.0, 0
        
        peak = self.equity_curve[0]
        max_dd = 0.0
        peak_idx = 0
        trough_idx = 0
        max_duration = 0
        
        for i, value in enumerate(self.equity_curve):
            if value > peak:
                peak = value
                peak_idx = i
            
            dd = (peak - value) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                trough_idx = i
                max_duration = trough_idx - peak_idx
        
        return max_dd, max_duration
    
    def _calculate_current_drawdown(self) -> float:
        """Calculate current drawdown from peak"""
        if not self.equity_curve:
            return 0.0
        
        peak = max(self.equity_curve)
        current = self.equity_curve[-1]
        
        return (peak - current) / peak if peak > 0 else 0.0
    
    def _calculate_drawdown_series(self) -> List[float]:
        """Calculate drawdown at each point in time"""
        if not self.equity_curve:
            return []
        
        drawdowns = []
        peak = self.equity_curve[0]
        
        for value in self.equity_curve:
            peak = max(peak, value)
            dd = (peak - value) / peak if peak > 0 else 0
            drawdowns.append(dd)
        
        return drawdowns
    
    def _calculate_omega_ratio(self, threshold: float = 0.0) -> float:
        """
        Omega ratio: Probability-weighted ratio of gains to losses
        relative to a threshold
        """
        if not self.returns_series:
            return 1.0
        
        returns = np.array(self.returns_series)
        gains = returns[returns > threshold]
        losses = returns[returns <= threshold]
        
        if len(losses) == 0:
            return float('inf')
        
        return np.sum(gains) / abs(np.sum(losses))


class ExecutionQualityAnalyzer:
    """
    Analyze execution quality
    
    Metrics:
    - Slippage analysis
    - Fill rate
    - Market impact
    - Implementation shortfall
    """
    
    def __init__(self):
        self.orders: List[Dict] = []
        self.fills: List[Dict] = []
    
    def record_order(self, 
                    order_id: str,
                    agent_id: str,
                    instrument: str,
                    side: str,
                    quantity: float,
                    price: float,
                    timestamp: datetime,
                    market_price: float):
        """Record order submission"""
        self.orders.append({
            'order_id': order_id,
            'agent_id': agent_id,
            'instrument': instrument,
            'side': side,
            'quantity': quantity,
            'price': price,
            'timestamp': timestamp,
            'market_price': market_price
        })
    
    def record_fill(self,
                   order_id: str,
                   fill_price: float,
                   fill_quantity: float,
                   timestamp: datetime):
        """Record order fill"""
        self.fills.append({
            'order_id': order_id,
            'fill_price': fill_price,
            'fill_quantity': fill_quantity,
            'timestamp': timestamp
        })
    
    def calculate_slippage(self) -> Dict:
        """Calculate slippage statistics"""
        slippages = []
        
        for order in self.orders:
            # Find corresponding fill
            fill = next((f for f in self.fills if f['order_id'] == order['order_id']), None)
            
            if fill:
                if order['side'] == 'buy':
                    slippage = fill['fill_price'] - order['market_price']
                else:
                    slippage = order['market_price'] - fill['fill_price']
                
                slippage_bps = slippage / order['market_price'] * 10000
                slippages.append(slippage_bps)
        
        if not slippages:
            return {}
        
        return {
            'avg_slippage_bps': np.mean(slippages),
            'median_slippage_bps': np.median(slippages),
            'p95_slippage_bps': np.percentile(slippages, 95),
            'max_slippage_bps': max(slippages),
            'min_slippage_bps': min(slippages),
            'std_slippage_bps': np.std(slippages)
        }
    
    def calculate_fill_rate(self) -> float:
        """Calculate order fill rate"""
        if not self.orders:
            return 0.0
        
        filled_orders = set(f['order_id'] for f in self.fills)
        return len(filled_orders) / len(self.orders)
    
    def calculate_market_impact(self) -> Dict:
        """
        Calculate market impact of trades
        
        Measures how much the market moves after our trades
        """
        # Would require price data around trade times
        # Simplified version here
        return {
            'immediate_impact_bps': 0.0,
            'permanent_impact_bps': 0.0,
            'temporary_impact_bps': 0.0
        }


class AttributionAnalyzer:
    """
    Performance attribution analysis
    
    Decompose PnL into contributing factors:
    - Alpha (skill)
    - Beta (market exposure)
    - Sector/asset allocation
    - Execution quality
    """
    
    def __init__(self):
        self.portfolio_returns: List[float] = []
        self.benchmark_returns: List[float] = []
        self.factor_returns: Dict[str, List[float]] = {}
    
    def add_return_observation(self, 
                              portfolio_return: float,
                              benchmark_return: float,
                              factor_returns: Dict[str, float] = None):
        """Add return observation"""
        self.portfolio_returns.append(portfolio_return)
        self.benchmark_returns.append(benchmark_return)
        
        if factor_returns:
            for factor, value in factor_returns.items():
                if factor not in self.factor_returns:
                    self.factor_returns[factor] = []
                self.factor_returns[factor].append(value)
    
    def calculate_attribution(self) -> Dict:
        """Calculate performance attribution"""
        if len(self.portfolio_returns) < 10:
            return {}
        
        port_ret = np.array(self.portfolio_returns)
        bench_ret = np.array(self.benchmark_returns)
        
        # Active return
        active_return = port_ret - bench_ret
        
        # Total returns
        total_portfolio_return = np.sum(port_ret)
        total_benchmark_return = np.sum(bench_ret)
        total_active_return = np.sum(active_return)
        
        # Alpha (Jensen's alpha)
        # Regress portfolio returns on benchmark
        if np.std(bench_ret) > 0:
            beta, alpha, _, _, _ = stats.linregress(bench_ret, port_ret)
        else:
            beta = 0.0
            alpha = np.mean(port_ret)
        
        # Factor attribution
        factor_attribution = {}
        for factor, factor_returns in self.factor_returns.items():
            factor_array = np.array(factor_returns)
            if np.std(factor_array) > 0 and len(factor_array) == len(port_ret):
                beta_factor, _, _, _, _ = stats.linregress(factor_array, port_ret)
                factor_attribution[factor] = {
                    'beta': beta_factor,
                    'contribution': beta_factor * np.sum(factor_array)
                }
        
        return {
            'total_portfolio_return': total_portfolio_return,
            'total_benchmark_return': total_benchmark_return,
            'active_return': total_active_return,
            'alpha': alpha,
            'beta': beta,
            'information_ratio': np.mean(active_return) / np.std(active_return) * np.sqrt(252) if np.std(active_return) > 0 else 0,
            'tracking_error': np.std(active_return) * np.sqrt(252),
            'factor_attribution': factor_attribution
        }


class AnalyticsEngine:
    """
    Complete analytics engine
    
    Combines all analytics components
    """
    
    def __init__(self, initial_capital: float, risk_free_rate: float = 0.02):
        self.initial_capital = initial_capital
        self.performance_analyzer = PerformanceAnalyzer(risk_free_rate)
        self.execution_analyzer = ExecutionQualityAnalyzer()
        self.attribution_analyzer = AttributionAnalyzer()
    
    def record_trade(self, trade: TradeRecord):
        """Record trade for analysis"""
        self.performance_analyzer.add_trade(trade)
    
    def record_order(self, **kwargs):
        """Record order for execution quality analysis"""
        self.execution_analyzer.record_order(**kwargs)
    
    def record_fill(self, **kwargs):
        """Record fill for execution quality analysis"""
        self.execution_analyzer.record_fill(**kwargs)
    
    def generate_report(self) -> Dict:
        """Generate comprehensive analytics report"""
        report = {}
        
        # Performance metrics
        report['performance'] = self.performance_analyzer.calculate_metrics(self.initial_capital).__dict__
        
        # Execution quality
        report['execution'] = {
            'slippage': self.execution_analyzer.calculate_slippage(),
            'fill_rate': self.execution_analyzer.calculate_fill_rate(),
            'market_impact': self.execution_analyzer.calculate_market_impact()
        }
        
        # Attribution (if benchmark data available)
        if self.attribution_analyzer.portfolio_returns:
            report['attribution'] = self.attribution_analyzer.calculate_attribution()
        
        return report
    
    def get_equity_curve(self) -> List[float]:
        """Get equity curve"""
        return self.performance_analyzer.equity_curve
    
    def get_drawdown_chart(self) -> List[float]:
        """Get drawdown series"""
        return self.performance_analyzer.drawdown_series
