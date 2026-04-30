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
        self.min_crossover_pct = self.params.get('min_crossover_pct', 0.002)
        self.confirmation_bars = self.params.get('confirmation_bars', 2)
        
        self.price_history = []
        self.short_ma = 0.0
        self.long_ma = 0.0
        self.prev_short_ma = 0.0
        self.prev_long_ma = 0.0
        self.spread_sign_history: deque = deque(maxlen=max(1, self.confirmation_bars))
        self.position_state = "FLAT"
    
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
        
        if self.long_ma == 0:
            return None
        
        spread_pct = (self.short_ma - self.long_ma) / self.long_ma
        if spread_pct > self.min_crossover_pct:
            self.spread_sign_history.append(1)
        elif spread_pct < -self.min_crossover_pct:
            self.spread_sign_history.append(-1)
        else:
            self.spread_sign_history.append(0)
        
        if len(self.spread_sign_history) < self.confirmation_bars:
            return None
        
        # Check for crossover with confirmation
        signal = None
        bullish_confirmed = all(x == 1 for x in self.spread_sign_history)
        bearish_confirmed = all(x == -1 for x in self.spread_sign_history)
        
        if bullish_confirmed and self.position_state != "LONG":
            signal = SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="LONG",
                strength=1.0
            )
            self.position_state = "LONG"
        elif bearish_confirmed and self.position_state == "LONG":
            signal = SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="SHORT",
                strength=1.0
            )
            self.position_state = "FLAT"
        
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
        self.closed_trade_pnls: List[float] = []
    
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
        bar_count = 0
        last_timestamp = datetime.now()
        self.closed_trade_pnls = []
        
        while self.events:
            event = self.events.popleft()
            
            if event.event_type == EventType.MARKET:
                bar_count += 1
                last_timestamp = event.timestamp
                # Update current prices
                current_prices[event.instrument] = event.price
                
                # Record portfolio snapshot every 10 bars
                if bar_count % 10 == 0:
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
                            
                            # Estimate realized PnL for closed long slices
                            if fill.side == "SELL" and fill.instrument in self.portfolio.position_prices:
                                entry_price = self.portfolio.position_prices[fill.instrument]
                                realized_pnl = (fill.fill_price - entry_price) * fill.quantity - fill.commission
                                self.closed_trade_pnls.append(realized_pnl)
                            
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
        
        # Force-close remaining open long positions for clean end-of-backtest accounting
        for instrument, quantity in list(self.portfolio.positions.items()):
            if quantity > 0 and instrument in current_prices:
                final_price = current_prices[instrument]
                close_order = OrderEvent(
                    timestamp=last_timestamp,
                    instrument=instrument,
                    order_type="MARKET",
                    side="SELL",
                    quantity=quantity
                )
                close_fill = self.execution_handler.execute_order(close_order, final_price)
                if instrument in self.portfolio.position_prices:
                    entry_price = self.portfolio.position_prices[instrument]
                    close_pnl = (close_fill.fill_price - entry_price) * close_fill.quantity - close_fill.commission
                    self.closed_trade_pnls.append(close_pnl)
                self.portfolio.update_position(
                    close_fill.instrument,
                    close_fill.quantity,
                    close_fill.fill_price,
                    close_fill.side
                )
                trades_count += 1
                self.portfolio.trades.append({
                    'timestamp': close_fill.timestamp,
                    'instrument': close_fill.instrument,
                    'side': close_fill.side,
                    'quantity': close_fill.quantity,
                    'price': close_fill.fill_price,
                    'commission': close_fill.commission
                })
        
        # Final equity calculation
        final_equity = self.portfolio.calculate_equity(current_prices)
        self.portfolio.record_snapshot(
            last_timestamp,
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
        
        # Win rate from realized trade PnL if available
        if self.closed_trade_pnls:
            wins = sum(1 for p in self.closed_trade_pnls if p > 0)
            losses = sum(1 for p in self.closed_trade_pnls if p < 0)
            total = wins + losses
            win_rate = wins / total if total > 0 else 0.0
        else:
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


# ========================================================================
# MULTI-LOT BACKTESTER EXTENSION
# Extends event-driven backtester for ladder/pyramid/parallel tactics.
# Tracks multiple simultaneous orders per tactic, queue position estimation,
# partial fill simulation, and aggregate P&L.
# ========================================================================

@dataclass
class LadderOrder:
    """Represents a single order within a multi-level ladder."""
    tactic: str
    level: int
    price: float
    size: int
    filled: int = 0
    status: str = "PENDING"  # PENDING, WORKING, PARTIAL, FILLED, CANCELLED
    queue_position: float = 0.0  # 0.0 = front, 1.0 = back
    queue_decay_rate: float = 0.0
    timestamp_armed: Optional[datetime] = None
    timestamp_filled: Optional[datetime] = None
    fill_price: float = 0.0
    cancel_reason: str = ""


class MultiLotBacktester:
    """
    Extends the event-driven backtester for multi-lot HFT tactics.

    Supports:
    - Ladder entries (LES, VTDL, EODPL): multiple limit orders at different levels
    - Pyramid adds (MP): sequential orders gated on momentum confirmation
    - Parallel positions (RCP): simultaneous buy/sell at range boundaries
    - Scale-outs (SESO): partial exits with runner management
    - VRS sizing: dynamic lot sizing based on volatility regime

    Queue fill model: FIFO-based with configurable decay rate.
    """

    def __init__(self, base_engine: 'BacktestEngine' = None,
                 queue_decay_model: str = "fifo",
                 tick_value: float = 15.0,
                 commission_per_share: float = 0.05,
                 slippage_bps: int = 5):
        self.engine = base_engine
        self.queue_decay_model = queue_decay_model
        self.tick_value = tick_value
        self.commission_per_share = commission_per_share
        self.slippage_bps = slippage_bps

        # Active ladders: tactic_id -> list of LadderOrder
        self.active_ladders: Dict[str, List[LadderOrder]] = {}

        # Filled positions: list of dicts with entry/exit info
        self.filled_positions: List[Dict] = []

        # P&L tracking
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.trade_log: List[Dict] = []

        # Current market state
        self.current_bid = 0.0
        self.current_ask = 0.0
        self.current_mid = 0.0
        self.current_price = 0.0
        self.dom_snapshot: Dict = {}  # level -> {bid_size, ask_size, bid_price, ask_price}
        self.tape_window: deque = deque(maxlen=1000)  # last 1000 trade prints
        self.vwAP = 0.0

        # Volatility regime tracking (for VRS)
        self.vol_window: deque = deque(maxlen=1200)  # 60s of 50ms snapshots
        self.cvi = 1.0
        self.vm = 1.0  # volatility multiplier

    def arm_ladder(self, tactic_id: str, tactic_name: str,
                   levels: int, sizes: List[int], prices: List[float],
                   side: str = "BUY") -> List[LadderOrder]:
        """
        Arm a multi-level ladder (LES, VTDL, EODPL, etc.)

        Args:
            tactic_id: Unique identifier (e.g., "LES_001")
            tactic_name: Type (LES, MP, DPFL, VTDL, EODPL)
            levels: Number of levels
            sizes: Lot size per level
            prices: Limit price per level
            side: BUY or SELL

        Returns:
            List of LadderOrder objects
        """
        now = datetime.now()
        orders = []
        for i in range(levels):
            order = LadderOrder(
                tactic=tactic_name,
                level=i,
                price=prices[i],
                size=sizes[i],
                queue_position=self.estimate_queue_position(prices[i], side),
                timestamp_armed=now,
            )
            orders.append(order)

        self.active_ladders[tactic_id] = orders
        return orders

    def estimate_queue_position(self, price: float, side: str) -> float:
        """
        Estimate where your limit order sits in queue (FIFO model).

        Returns 0.0 (front of queue) to 1.0 (back of queue).
        Uses DOM snapshot at the price level.
        """
        if side == "BUY":
            # Check bid side size at this price level
            level_key = "bid"
        else:
            level_key = "ask"

        # Find the DOM level closest to our price
        total_size_at_level = 0
        for lvl, data in self.dom_snapshot.items():
            if side == "BUY" and abs(data.get("bid_price", 0) - price) < 0.01:
                total_size_at_level = data.get("bid_size", 500)
                break
            elif side == "SELL" and abs(data.get("ask_price", 0) - price) < 0.01:
                total_size_at_level = data.get("ask_size", 500)
                break

        if total_size_at_level == 0:
            total_size_at_level = 500  # default estimate

        # Assume we're placed randomly within the queue (uniform distribution)
        # More sophisticated: use time-weighted placement
        import random
        queue_pos = random.uniform(0.1, 0.9)

        return queue_pos

    def update_market(self, bid: float, ask: float, dom: Dict = None,
                      trade_print: Dict = None, vwap: float = None):
        """
        Update internal market state from tick data.

        Args:
            bid: Current best bid
            ask: Current best ask
            dom: Optional dict of level -> {bid_price, bid_size, ask_price, ask_size}
            trade_print: Optional dict with {price, size, side, timestamp}
            vwap: Current session VWAP
        """
        self.current_bid = bid
        self.current_ask = ask
        self.current_mid = (bid + ask) / 2
        self.current_price = bid  # conservative

        if dom:
            self.dom_snapshot = dom
        if trade_print:
            self.tape_window.append(trade_print)
            self.vol_window.append(trade_print.get("size", 0))
        if vwap:
            self.vwap = vwap

    def compute_tape_velocity(self, window_ms: int = 200) -> tuple:
        """
        Compute tape velocity: total lots traded in last window_ms.

        Returns:
            (V_t_total, V_t_buy, V_t_sell)
        """
        if not self.tape_window:
            return (0, 0, 0)

        # Get recent prints (approximate by last N items)
        n_prints = max(1, len(self.tape_window) * window_ms // 1000)
        recent = list(self.tape_window)[-n_prints:]

        v_t_buy = sum(p.get("size", 0) for p in recent if p.get("side") == "A")  # ask lifts
        v_t_sell = sum(p.get("size", 0) for p in recent if p.get("side") == "B")  # bid hits
        v_t_total = v_t_buy + v_t_sell

        return (v_t_total, v_t_buy, v_t_sell)

    def compute_imbalance_ratio(self, levels: int = 3) -> float:
        """
        Compute bid/ask imbalance ratio across top N levels.

        IR = sum(bid_sizes) / sum(ask_sizes)
        IR > 1.0 = bid-heavy (bullish)
        IR < 1.0 = ask-heavy (bearish)
        """
        bid_sum = 0
        ask_sum = 0
        for lvl in range(min(levels, len(self.dom_snapshot))):
            if lvl in self.dom_snapshot:
                bid_sum += self.dom_snapshot[lvl].get("bid_size", 0)
                ask_sum += self.dom_snapshot[lvl].get("ask_size", 0)

        if ask_sum == 0:
            return 10.0
        return bid_sum / ask_sum

    def process_ladder_fills(self, current_time: datetime) -> List[Dict]:
        """
        Check all pending ladder orders against current market.
        Simulate fills based on price crossing + queue decay.

        Returns:
            List of fill events
        """
        fills = []

        for tactic_id, orders in list(self.active_ladders.items()):
            for order in orders:
                if order.status != "PENDING":
                    continue

                # Check if price has crossed our limit
                if order.price >= self.current_bid and order.price <= self.current_ask:
                    # Price is at our level — check queue position
                    fill_probability = self._compute_fill_probability(order)

                    if fill_probability > 0.3:  # threshold
                        # Simulate fill (partial or full)
                        fill_size = self._simulate_fill_size(order, fill_probability)

                        if fill_size > 0:
                            order.filled += fill_size
                            if order.filled >= order.size:
                                order.status = "FILLED"
                                order.timestamp_filled = current_time
                                order.fill_price = order.price  # limit price

                                fills.append({
                                    "tactic_id": tactic_id,
                                    "tactic": order.tactic,
                                    "level": order.level,
                                    "side": "BUY",
                                    "size": order.size,
                                    "price": order.price,
                                    "timestamp": current_time,
                                })
                            else:
                                order.status = "PARTIAL"
                                fills.append({
                                    "tactic_id": tactic_id,
                                    "tactic": order.tactic,
                                    "level": order.level,
                                    "side": "BUY",
                                    "size": fill_size,
                                    "price": order.price,
                                    "timestamp": current_time,
                                    "partial": True,
                                })

                # Time-based cancel: unfilled after 5 seconds
                if order.timestamp_armed and \
                   (current_time - order.timestamp_armed).total_seconds() > 5.0:
                    if order.status == "PENDING":
                        order.status = "CANCELLED"
                        order.cancel_reason = "TIME_EXPIRY"

        return fills

    def _compute_fill_probability(self, order: LadderOrder) -> float:
        """
        Compute probability that this order gets filled.

        Based on:
        - Queue position (closer to front = higher probability)
        - Queue decay rate (faster decay = higher probability)
        - Price aggressiveness (at NBBO = higher probability)
        """
        # Queue position factor: 1.0 at front, 0.0 at back
        queue_factor = 1.0 - order.queue_position

        # Queue decay: estimate based on recent tape velocity
        v_t, _, _ = self.compute_tape_velocity()
        decay_rate = v_t / 1000.0  # normalize
        decay_factor = min(1.0, decay_rate * 2)

        # Price factor: at NBBO = 1.0, 1 tick away = 0.5, 2+ ticks = 0.1
        price_distance = abs(order.price - self.current_mid)
        tick_size = self.current_ask - self.current_bid
        if tick_size == 0:
            tick_size = 0.01
        price_factor = max(0.1, 1.0 - price_distance / (tick_size * 3))

        # Combined probability
        prob = queue_factor * 0.4 + decay_factor * 0.3 + price_factor * 0.3

        return prob

    def _simulate_fill_size(self, order: LadderOrder, prob: float) -> int:
        """
        Simulate how many lots get filled from this order.

        Returns fill size (0 to remaining size).
        """
        remaining = order.size - order.filled
        import random
        fill_fraction = prob * random.uniform(0.5, 1.0)
        fill_size = max(1, int(remaining * fill_fraction))
        return min(fill_size, remaining)

    def compute_unrealized_pnl(self) -> float:
        """Compute unrealized P&L across all filled positions."""
        unrealized = 0.0
        for pos in self.filled_positions:
            if pos.get("exit_price") is None:
                # Still open
                entry = pos["entry_price"]
                qty = pos["size"]
                # Current exit price = current bid (for longs)
                unrealized += (self.current_bid - entry) * qty * self.tick_value
        self.unrealized_pnl = unrealized
        return unrealized

    def exit_position(self, tactic_id: str, level: int, exit_price: float,
                      current_time: datetime) -> Dict:
        """
        Exit a filled position (scale-out or flatten).

        Returns:
            Dict with exit details including realized P&L.
        """
        # Find the position
        for i, pos in enumerate(self.filled_positions):
            if pos["tactic_id"] == tactic_id and pos["level"] == level and pos.get("exit_price") is None:
                entry = pos["entry_price"]
                qty = pos["size"]
                pnl = (exit_price - entry) * qty * self.tick_value
                commission = qty * self.commission_per_share
                slippage = qty * exit_price * self.slippage_bps / 10000
                net_pnl = pnl - commission - slippage

                pos["exit_price"] = exit_price
                pos["exit_timestamp"] = current_time
                pos["realized_pnl"] = net_pnl

                self.realized_pnl += net_pnl

                result = {
                    "tactic_id": tactic_id,
                    "level": level,
                    "entry": entry,
                    "exit": exit_price,
                    "size": qty,
                    "gross_pnl": pnl,
                    "commission": commission,
                    "slippage": slippage,
                    "net_pnl": net_pnl,
                    "timestamp": current_time,
                }
                self.trade_log.append(result)
                return result

        return {"error": "Position not found", "tactic_id": tactic_id, "level": level}

    def compute_aggregate_pnl(self) -> Dict:
        """
        Compute aggregate P&L across all tactics.

        Returns summary dict.
        """
        total_realized = self.realized_pnl
        total_unrealized = self.compute_unrealized_pnl()

        winning_trades = [t for t in self.trade_log if t.get("net_pnl", 0) > 0]
        losing_trades = [t for t in self.trade_log if t.get("net_pnl", 0) <= 0]

        return {
            "realized_pnl": total_realized,
            "unrealized_pnl": total_unrealized,
            "total_pnl": total_realized + total_unrealized,
            "total_trades": len(self.trade_log),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": len(winning_trades) / max(1, len(self.trade_log)) * 100,
            "avg_win": np.mean([t["net_pnl"] for t in winning_trades]) if winning_trades else 0,
            "avg_loss": np.mean([t["net_pnl"] for t in losing_trades]) if losing_trades else 0,
            "max_drawdown": self._compute_max_drawdown(),
            "trade_log": self.trade_log,
        }

    def _compute_max_drawdown(self) -> float:
        """Compute maximum drawdown from trade log."""
        if not self.trade_log:
            return 0.0

        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0

        for trade in self.trade_log:
            cumulative += trade.get("net_pnl", 0)
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        return max_dd

    def flatten_all(self, current_time: datetime, exit_price: float = None) -> List[Dict]:
        """
        Emergency flatten: exit ALL open positions at market.

        Args:
            exit_price: If None, uses current_bid
        """
        price = exit_price or self.current_bid
        results = []

        for tactic_id, orders in self.active_ladders.items():
            for order in orders:
                if order.status in ("FILLED", "PARTIAL"):
                    pos = {
                        "tactic_id": tactic_id,
                        "level": order.level,
                        "entry_price": order.fill_price or order.price,
                        "size": order.filled,
                        "exit_price": None,
                    }
                    # Add to filled positions if not already there
                    existing = [p for p in self.filled_positions
                               if p["tactic_id"] == tactic_id and p["level"] == order.level]
                    if not existing:
                        self.filled_positions.append(pos)
                        idx = len(self.filled_positions) - 1
                    else:
                        idx = self.filled_positions.index(existing[0])

                    if self.filled_positions[idx].get("exit_price") is None:
                        result = self.exit_position(tactic_id, order.level, price, current_time)
                        results.append(result)

            # Cancel all pending orders
            for order in orders:
                if order.status == "PENDING":
                    order.status = "CANCELLED"
                    order.cancel_reason = "EMERGENCY_FLATTEN"

        return results
