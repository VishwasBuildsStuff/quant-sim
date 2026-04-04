"""
Event-Driven Backtesting Engine
Walk-forward analysis, strategy plug-in system, historical replay

Architecture:
- Event queue (Market, Signal, Order, Fill)
- Strategy plug-in interface
- Portfolio manager
- Performance analyzer
- Walk-forward optimizer
"""

import numpy as np
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from abc import ABC, abstractmethod
import logging
from collections import deque

logger = logging.getLogger(__name__)


class EventType(Enum):
    MARKET = "market"
    SIGNAL = "signal"
    ORDER = "order"
    FILL = "fill"
    TIMER = "timer"


@dataclass
class Event:
    """Base event for backtesting"""
    timestamp: datetime
    event_type: EventType = EventType.MARKET
    data: Dict = field(default_factory=dict)


@dataclass
class MarketEvent(Event):
    """New market data event"""
    instrument: str = ""
    price: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: float = 0.0
    bid: float = 0.0
    ask: float = 0.0


@dataclass
class SignalEvent(Event):
    """Trading signal from strategy"""
    instrument: str = ""
    signal_type: str = "LONG"  # LONG, SHORT, EXIT
    strength: float = 1.0  # 0-1 confidence


@dataclass
class OrderEvent(Event):
    """Order to be executed"""
    instrument: str = ""
    order_type: str = "MARKET"  # MARKET, LIMIT
    side: str = "BUY"  # BUY, SELL
    quantity: float = 0.0
    price: Optional[float] = None
    commission: float = 0.0


@dataclass
class FillEvent(Event):
    """Order execution report"""
    instrument: str = ""
    side: str = "BUY"
    quantity: float = 0.0
    fill_price: float = 0.0
    commission: float = 0.0


class Strategy(ABC):
    """
    Abstract base class for trading strategies
    
    Plug-in interface - users implement on_data() and generate_signals()
    """
    
    def __init__(self, name: str, params: Dict = None):
        self.name = name
        self.params = params or {}
        self.signals: List[SignalEvent] = []
    
    @abstractmethod
    def on_data(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        """
        Process market data and optionally return trading signal
        
        Args:
            market_event: New market data
            
        Returns:
            SignalEvent or None
        """
        pass
    
    def on_start(self):
        """Called at strategy initialization"""
        pass
    
    def on_end(self):
        """Called at strategy termination"""
        pass


class MovingAverageCrossoverStrategy(Strategy):
    """
    Example strategy: Moving Average Crossover
    
    Buy when short MA crosses above long MA
    Sell when short MA crosses below long MA
    """
    
    def __init__(self, params: Dict = None):
        super().__init__("MA Crossover", params)
        self.short_window = self.params.get('short_window', 20)
        self.long_window = self.params.get('long_window', 50)
        
        self.price_history = []
        self.short_ma = 0.0
        self.long_ma = 0.0
        self.prev_short_ma = 0.0
        self.prev_long_ma = 0.0
    
    def on_data(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        self.price_history.append(market_event.price)
        
        if len(self.price_history) < self.long_window:
            return None
        
        # Calculate moving averages
        recent_prices = self.price_history[-self.long_window:]
        self.prev_short_ma = self.short_ma
        self.prev_long_ma = self.long_ma
        
        self.short_ma = np.mean(recent_prices[-self.short_window:])
        self.long_ma = np.mean(recent_prices)
        
        # Check for crossover
        signal = None
        
        if self.prev_short_ma <= self.prev_long_ma and self.short_ma > self.long_ma:
            # Bullish crossover
            signal = SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="LONG",
                strength=1.0
            )
        elif self.prev_short_ma >= self.prev_long_ma and self.short_ma < self.long_ma:
            # Bearish crossover
            signal = SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="SHORT",
                strength=1.0
            )
        
        return signal


class MeanReversionStrategy(Strategy):
    """
    Mean reversion strategy using Bollinger Bands
    
    Buy when price touches lower band
    Sell when price touches upper band
    """
    
    def __init__(self, params: Dict = None):
        super().__init__("Mean Reversion", params)
        self.window = self.params.get('window', 20)
        self.num_std = self.params.get('num_std', 2.0)
        
        self.price_history = []
    
    def on_data(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        self.price_history.append(market_event.price)
        
        if len(self.price_history) < self.window:
            return None
        
        recent = self.price_history[-self.window:]
        mean = np.mean(recent)
        std = np.std(recent)
        
        upper_band = mean + self.num_std * std
        lower_band = mean - self.num_std * std
        
        signal = None
        
        if market_event.price <= lower_band:
            signal = SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="LONG",
                strength=0.8
            )
        elif market_event.price >= upper_band:
            signal = SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="SHORT",
                strength=0.8
            )
        
        return signal


class Portfolio:
    """
    Portfolio manager
    Tracks positions, cash, and equity
    """
    
    def __init__(self, initial_capital: float = 1_000_000.0):
        self.initial_capital = initial_capital
        self.current_cash = initial_capital
        self.positions: Dict[str, float] = {}  # instrument -> quantity
        self.position_prices: Dict[str, float] = {}  # instrument -> avg entry price
        
        # Performance tracking
        self.equity_curve: List[Dict] = []
        self.trades: List[Dict] = []
        self.current_equity = initial_capital
    
    def update_position(self, instrument: str, quantity: float, price: float, side: str):
        """Update position after fill"""
        if side == "BUY":
            if instrument in self.positions:
                # Average up/down
                old_qty = self.positions[instrument]
                old_price = self.position_prices[instrument]
                new_qty = old_qty + quantity
                new_avg_price = (old_qty * old_price + quantity * price) / new_qty if new_qty > 0 else price
                
                self.positions[instrument] = new_qty
                self.position_prices[instrument] = new_avg_price
            else:
                self.positions[instrument] = quantity
                self.position_prices[instrument] = price
            
            self.current_cash -= quantity * price
        else:  # SELL
            if instrument in self.positions:
                self.positions[instrument] -= quantity
                self.current_cash += quantity * price
                
                if self.positions[instrument] <= 0:
                    del self.positions[instrument]
                    del self.position_prices[instrument]
    
    def calculate_equity(self, current_prices: Dict[str, float]) -> float:
        """Calculate total portfolio equity"""
        equity = self.current_cash
        
        for instrument, quantity in self.positions.items():
            if instrument in current_prices:
                equity += quantity * current_prices[instrument]
        
        self.current_equity = equity
        return equity
    
    def record_snapshot(self, timestamp: datetime, current_prices: Dict[str, float]):
        """Record portfolio state"""
        equity = self.calculate_equity(current_prices)
        
        self.equity_curve.append({
            'timestamp': timestamp,
            'equity': equity,
            'cash': self.current_cash,
            'positions': dict(self.positions),
            'return': (equity / self.initial_capital - 1) if self.initial_capital > 0 else 0
        })


class CommissionModel(ABC):
    """Abstract commission model"""
    
    @abstractmethod
    def calculate_commission(self, quantity: float, price: float) -> float:
        pass


class FixedCommission(CommissionModel):
    """Fixed commission per share"""
    
    def __init__(self, commission_per_share: float = 0.005):
        self.commission_per_share = commission_per_share
    
    def calculate_commission(self, quantity: float, price: float) -> float:
        return quantity * self.commission_per_share


class PercentageCommission(CommissionModel):
    """Percentage of trade value"""
    
    def __init__(self, pct: float = 0.001):  # 10 bps
        self.pct = pct
    
    def calculate_commission(self, quantity: float, price: float) -> float:
        return quantity * price * self.pct


class SlippageModel(ABC):
    """Abstract slippage model"""
    
    @abstractmethod
    def calculate_slippage(self, price: float, quantity: float) -> float:
        pass


class FixedSlippage(SlippageModel):
    """Fixed slippage in price units"""
    
    def __init__(self, slippage: float = 0.01):
        self.slippage = slippage
    
    def calculate_slippage(self, price: float, quantity: float) -> float:
        return self.slippage


class PercentageSlippage(SlippageModel):
    """Percentage slippage"""
    
    def __init__(self, pct: float = 0.0005):  # 5 bps
        self.pct = pct
    
    def calculate_slippage(self, price: float, quantity: float) -> float:
        return price * self.pct


class ExecutionHandler:
    """
    Simulates order execution with slippage and commission
    """
    
    def __init__(self, 
                 commission_model: CommissionModel = None,
                 slippage_model: SlippageModel = None):
        self.commission_model = commission_model or PercentageCommission(0.001)
        self.slippage_model = slippage_model or PercentageSlippage(0.0005)
    
    def execute_order(self, order: OrderEvent, market_price: float) -> FillEvent:
        """
        Execute order with realistic fills
        
        Args:
            order: Order to execute
            market_price: Current market price
            
        Returns:
            FillEvent with execution details
        """
        # Calculate slippage
        slippage = self.slippage_model.calculate_slippage(market_price, order.quantity)
        
        if order.side == "BUY":
            fill_price = market_price + slippage
        else:
            fill_price = market_price - slippage
        
        # Calculate commission
        commission = self.commission_model.calculate_commission(order.quantity, fill_price)
        
        return FillEvent(
            timestamp=order.timestamp,
            instrument=order.instrument,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=commission
        )


class BacktestEngine:
    """
    Main backtesting engine
    
    Event-driven architecture:
    1. Load historical data
    2. Feed data as MarketEvents
    3. Strategy generates SignalEvents
    4. Risk management validates signals
    5. Orders created and sent to ExecutionHandler
    6. Fills processed and Portfolio updated
    7. Performance metrics calculated
    """
    
    def __init__(self, 
                 initial_capital: float = 1_000_000.0,
                 commission_model: CommissionModel = None,
                 slippage_model: SlippageModel = None):
        self.initial_capital = initial_capital
        self.portfolio = Portfolio(initial_capital)
        self.execution_handler = ExecutionHandler(commission_model, slippage_model)
        
        # Event queue
        self.events: deque = deque()
        
        # Strategies
        self.strategies: Dict[str, Strategy] = {}
        
        # Results
        self.results: Dict = {}
    
    def add_strategy(self, strategy: Strategy):
        """Add trading strategy"""
        self.strategies[strategy.name] = strategy
        strategy.on_start()
        logger.info(f"Added strategy: {strategy.name}")
    
    def load_price_data(self, 
                       instrument: str,
                       timestamps: List[datetime],
                       prices: np.ndarray,
                       highs: np.ndarray = None,
                       lows: np.ndarray = None,
                       volumes: np.ndarray = None):
        """
        Load historical price data and create market events
        """
        n = len(prices)
        if highs is None:
            highs = prices * 1.001
        if lows is None:
            lows = prices * 0.999
        if volumes is None:
            volumes = np.full(n, 1000000)
        
        for i in range(n):
            event = MarketEvent(
                timestamp=timestamps[i],
                instrument=instrument,
                price=prices[i],
                high=highs[i],
                low=lows[i],
                volume=volumes[i],
                bid=prices[i] * 0.999,
                ask=prices[i] * 1.001
            )
            self.events.append(event)
        
        logger.info(f"Loaded {n} bars for {instrument}")
    
    def run_backtest(self, verbose: bool = False) -> Dict:
        """
        Run complete backtest
        
        Returns:
            Dictionary with backtest results
        """
        logger.info(f"Starting backtest with {len(self.events)} events")
        
        current_prices = {}
        trades_count = 0
        
        while self.events:
            event = self.events.popleft()
            
            if event.event_type == EventType.MARKET:
                # Update current prices
                current_prices[event.instrument] = event.price
                
                # Record portfolio snapshot every 10 bars
                if len(self.portfolio.equity_curve) % 10 == 0:
                    self.portfolio.record_snapshot(event.timestamp, current_prices)
                
                # Feed to strategies
                for name, strategy in self.strategies.items():
                    signal = strategy.on_data(event)
                    
                    if signal:
                        # Create order from signal
                        order = self._signal_to_order(signal, event)
                        
                        if order:
                            # Execute order
                            fill = self.execution_handler.execute_order(order, event.price)
                            
                            # Update portfolio
                            self.portfolio.update_position(
                                fill.instrument,
                                fill.quantity,
                                fill.fill_price,
                                fill.side
                            )
                            
                            trades_count += 1
                            self.portfolio.trades.append({
                                'timestamp': fill.timestamp,
                                'instrument': fill.instrument,
                                'side': fill.side,
                                'quantity': fill.quantity,
                                'price': fill.fill_price,
                                'commission': fill.commission
                            })
                            
                            if verbose:
                                print(f"  {fill.timestamp}: {fill.side} {fill.quantity} {fill.instrument} @ {fill.fill_price:.2f}")
        
        # Final equity calculation
        final_equity = self.portfolio.calculate_equity(current_prices)
        self.portfolio.record_snapshot(
            self.events[-1].timestamp if self.events else datetime.now(),
            current_prices
        )
        
        # Calculate performance metrics
        self.results = self._calculate_performance_metrics()
        self.results['total_trades'] = trades_count
        
        logger.info(f"Backtest complete: {trades_count} trades, final equity: ${final_equity:.2f}")
        
        # Clean up strategies
        for strategy in self.strategies.values():
            strategy.on_end()
        
        return self.results
    
    def _signal_to_order(self, signal: SignalEvent, market_event: MarketEvent) -> Optional[OrderEvent]:
        """Convert trading signal to order"""
        # Simple position sizing: 10% of equity
        position_size = self.portfolio.current_equity * 0.10 / market_event.price
        position_size = max(100, round(position_size / 100) * 100)  # Round to 100s
        
        if signal.signal_type == "LONG":
            return OrderEvent(
                timestamp=signal.timestamp,
                instrument=signal.instrument,
                order_type="MARKET",
                side="BUY",
                quantity=position_size
            )
        elif signal.signal_type == "SHORT":
            if signal.instrument in self.portfolio.positions:
                quantity = min(self.portfolio.positions[signal.instrument], position_size)
                if quantity > 0:
                    return OrderEvent(
                        timestamp=signal.timestamp,
                        instrument=signal.instrument,
                        order_type="MARKET",
                        side="SELL",
                        quantity=quantity
                    )
        
        return None
    
    def _calculate_performance_metrics(self) -> Dict:
        """Calculate comprehensive performance metrics"""
        if not self.portfolio.equity_curve:
            return {}
        
        equity_curve = self.portfolio.equity_curve
        equities = [e['equity'] for e in equity_curve]
        returns = [e['return'] for e in equity_curve]
        
        if len(returns) < 2:
            return {}
        
        returns_array = np.array(returns)
        daily_returns = np.diff(returns_array)
        
        final_equity = equities[-1]
        total_return = (final_equity / self.initial_capital - 1) * 100
        
        # Sharpe ratio
        if np.std(daily_returns) > 0:
            sharpe = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
        else:
            sharpe = 0.0
        
        # Sortino ratio
        downside = daily_returns[daily_returns < 0]
        if len(downside) > 0 and np.std(downside) > 0:
            sortino = np.mean(daily_returns) / np.std(downside) * np.sqrt(252)
        else:
            sortino = 0.0
        
        # Maximum drawdown
        peak = equities[0]
        max_dd = 0.0
        for equity in equities:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd
        
        # Win rate (simplified)
        wins = sum(1 for r in daily_returns if r > 0)
        losses = sum(1 for r in daily_returns if r < 0)
        total = wins + losses
        win_rate = wins / total if total > 0 else 0.0
        
        return {
            'initial_capital': self.initial_capital,
            'final_equity': final_equity,
            'total_return_pct': total_return,
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'max_drawdown_pct': max_dd * 100,
            'win_rate_pct': win_rate * 100,
            'total_trades': len(self.portfolio.trades),
            'equity_curve': equity_curve
        }


class WalkForwardOptimizer:
    """
    Walk-forward optimization
    
    1. Split data into in-sample (optimization) and out-of-sample (testing)
    2. Optimize parameters on in-sample
    3. Test on out-of-sample
    4. Roll forward and repeat
    """
    
    def __init__(self, 
                 strategy_class,
                 param_grid: Dict,
                 train_pct: float = 0.7):
        self.strategy_class = strategy_class
        self.param_grid = param_grid
        self.train_pct = train_pct
    
    def optimize(self, 
                timestamps: List[datetime],
                prices: np.ndarray) -> Dict:
        """
        Run walk-forward optimization
        
        Returns:
            Dictionary with optimization results
        """
        n = len(prices)
        train_size = int(n * self.train_pct)
        
        best_params = None
        best_return = -999
        oos_returns = []
        
        # Generate parameter combinations
        param_combos = self._generate_param_combinations()
        
        # Train on first portion
        train_timestamps = timestamps[:train_size]
        train_prices = prices[:train_size]
        
        for params in param_combos:
            engine = BacktestEngine(initial_capital=1_000_000)
            strategy = self.strategy_class(params)
            engine.add_strategy(strategy)
            engine.load_price_data("TEST", train_timestamps, train_prices)
            
            results = engine.run_backtest()
            total_return = results.get('total_return_pct', -999)
            
            if total_return > best_return:
                best_return = total_return
                best_params = params
        
        # Test best params on out-of-sample
        oos_timestamps = timestamps[train_size:]
        oos_prices = prices[train_size:]
        
        if best_params and len(oos_prices) > 0:
            engine = BacktestEngine(initial_capital=1_000_000)
            strategy = self.strategy_class(best_params)
            engine.add_strategy(strategy)
            engine.load_price_data("TEST", oos_timestamps, oos_prices)
            
            oos_results = engine.run_backtest()
            oos_returns.append(oos_results)
        
        return {
            'best_params': best_params,
            'in_sample_return': best_return,
            'out_of_sample_results': oos_returns
        }
    
    def _generate_param_combinations(self) -> List[Dict]:
        """Generate all parameter combinations"""
        import itertools
        
        keys = list(self.param_grid.keys())
        values = [self.param_grid[k] for k in keys]
        
        combos = []
        for combo in itertools.product(*values):
            combos.append(dict(zip(keys, combo)))
        
        return combos
