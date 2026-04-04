"""
Institutional Algorithmic Trader
Sophisticated execution algorithms to minimize market impact

Strategies:
- TWAP (Time-Weighted Average Price)
- VWAP (Volume-Weighted Average Price)  
- Implementation Shortfall
- POV (Percentage of Volume)

Characteristics:
- Large order sizes
- Careful market impact management
- Sophisticated risk management
- Low urgency to complete orders
- Uses benchmarks and analytics
"""

import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

from base_agent import BaseAgent, AgentConfig, AgentType, OrderRequest, Fill, AgentState

logger = logging.getLogger(__name__)


@dataclass
class ExecutionBenchmark:
    """Track execution quality"""
    arrival_price: float
    target_quantity: float
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def get_participation_rate(self) -> float:
        """Get fill participation rate"""
        if self.target_quantity > 0:
            return self.filled_quantity / self.target_quantity
        return 0.0
    
    def get_slippage(self) -> float:
        """Calculate slippage from arrival price"""
        if self.avg_fill_price > 0 and self.arrival_price > 0:
            return (self.avg_fill_price - self.arrival_price) / self.arrival_price
        return 0.0


@dataclass
class InstitutionalConfig(AgentConfig):
    """Institutional trader configuration"""
    agent_type: AgentType = AgentType.INSTITUTIONAL
    
    # Execution strategy
    execution_strategy: str = "vwap"  # 'twap', 'vwap', 'is', 'pov'
    
    # TWAP parameters
    twap_duration_minutes: int = 60
    twap_num_slices: int = 12
    
    # VWAP parameters
    volume_profile: List[float] = None  # Expected volume distribution
    target_participation_rate: float = 0.10  # 10% of market volume
    
    # Implementation Shortfall parameters
    is_risk_aversion: float = 0.5  # Trade-off between timing and market impact
    max_participation_rate: float = 0.15
    
    # POV parameters
    pov_percentage: float = 0.10  # Participate at 10% of market volume
    
    # Risk management
    max_tracking_error: float = 0.05  # 5% max deviation from benchmark
    urgency_factor: float = 0.5  # How aggressively to trade
    
    def __post_init__(self):
        if self.volume_profile is None:
            # U-shaped volume profile (typical intraday pattern)
            self.volume_profile = [
                0.15, 0.12, 0.10, 0.08, 0.07, 0.06, 0.06, 0.07, 0.08, 0.10, 0.12, 0.15
            ]


class InstitutionalTraderAgent(BaseAgent):
    """
    Institutional algorithmic trader
    
    Focuses on executing large orders with minimal market impact.
    Uses sophisticated execution algorithms rather than directional betting.
    """
    
    def __init__(self, config: InstitutionalConfig):
        super().__init__(config)
        self.institutional_config = config
        
        # Active execution orders
        self.active_orders: Dict[str, ExecutionBenchmark] = {}
        
        # Execution history
        self.execution_history: List[ExecutionBenchmark] = []
        
        # Volume tracking
        self.market_volume: Dict[str, float] = {}
        self.participated_volume: Dict[str, float] = {}
        
        logger.info(f"Institutional trader {self.agent_id} initialized with {config.execution_strategy} strategy")
    
    def on_market_data(self, instrument: str, data: Dict):
        """Process market data"""
        if 'volume' in data:
            self.market_volume[instrument] = data['volume']
    
    def on_fill(self, fill: Fill):
        """Handle order fill"""
        super().on_fill(fill)
        self.update_position(fill.instrument, fill.quantity, fill.price, fill.side)
        
        # Update execution benchmark
        if fill.instrument in self.active_orders:
            benchmark = self.active_orders[fill.instrument]
            benchmark.filled_quantity += fill.quantity
            
            # Update average fill price
            total_value = benchmark.avg_fill_price * (benchmark.filled_quantity - fill.quantity) + \
                         fill.price * fill.quantity
            benchmark.avg_fill_price = total_value / benchmark.filled_quantity
            
            # Check if complete
            if benchmark.filled_quantity >= benchmark.target_quantity:
                benchmark.end_time = datetime.now()
                self.execution_history.append(benchmark)
                del self.active_orders[fill.instrument]
                
                logger.info(
                    f"Execution complete: {fill.instrument}, "
                    f"Slippage: {benchmark.get_slippage()*100:.2f}bps"
                )
    
    def generate_orders(self) -> List[OrderRequest]:
        """Generate orders based on execution algorithm"""
        orders = []
        
        if self.state != AgentState.ACTIVE:
            return orders
        
        # Process each active execution order
        for instrument, benchmark in list(self.active_orders.items()):
            order = self._calculate_next_slice(instrument, benchmark)
            if order:
                orders.append(order)
        
        return orders
    
    def submit_execution_order(
        self, 
        instrument: str, 
        side: str, 
        quantity: float, 
        arrival_price: float
    ):
        """Submit a new execution order"""
        benchmark = ExecutionBenchmark(
            arrival_price=arrival_price,
            target_quantity=quantity,
            start_time=datetime.now()
        )
        
        self.active_orders[instrument] = benchmark
        
        logger.info(
            f"New execution order: {side} {quantity} {instrument} "
            f"@ arrival {arrival_price}"
        )
    
    def _calculate_next_slice(self, instrument: str, benchmark: ExecutionBenchmark) -> Optional[OrderRequest]:
        """Calculate next slice of execution order"""
        remaining_qty = benchmark.target_quantity - benchmark.filled_quantity
        
        if remaining_qty <= 0:
            return None
        
        strategy = self.institutional_config.execution_strategy
        
        if strategy == "twap":
            return self._twap_slice(instrument, benchmark, remaining_qty)
        elif strategy == "vwap":
            return self._vwap_slice(instrument, benchmark, remaining_qty)
        elif strategy == "is":
            return self._implementation_shortfall(instrument, benchmark, remaining_qty)
        elif strategy == "pov":
            return self._pov_slice(instrument, benchmark, remaining_qty)
        else:
            logger.warning(f"Unknown strategy: {strategy}")
            return None
    
    def _twap_slice(self, instrument: str, benchmark: ExecutionBenchmark, remaining_qty: float) -> Optional[OrderRequest]:
        """Time-Weighted Average Price execution"""
        config = self.institutional_config
        
        # Calculate slice size
        slice_size = benchmark.target_quantity / config.twap_num_slices
        
        # Don't trade more than remaining
        trade_qty = min(slice_size, remaining_qty)
        
        if trade_qty <= 0:
            return None
        
        # Get current price
        current_price = self._get_current_price(instrument)
        
        return OrderRequest(
            order_id="",
            agent_id=self.agent_id,
            instrument=instrument,
            side=benchmark.side if hasattr(benchmark, 'side') else 'buy',
            order_type='limit',
            quantity=trade_qty,
            price=current_price
        )
    
    def _vwap_slice(self, instrument: str, benchmark: ExecutionBenchmark, remaining_qty: float) -> Optional[OrderRequest]:
        """Volume-Weighted Average Price execution"""
        config = self.institutional_config
        
        # Get current time bucket
        elapsed = (datetime.now() - benchmark.start_time).total_seconds()
        total_duration = config.twap_duration_minutes * 60
        time_progress = min(elapsed / total_duration, 1.0)
        
        # Get target participation from volume profile
        bucket_idx = int(time_progress * len(config.volume_profile))
        bucket_idx = min(bucket_idx, len(config.volume_profile) - 1)
        
        target_pct = config.volume_profile[bucket_idx]
        target_qty = benchmark.target_quantity * target_pct
        
        # Calculate trade size
        current_participation = self.participated_volume.get(instrument, 0)
        trade_qty = max(0, target_qty - current_participation)
        trade_qty = min(trade_qty, remaining_qty)
        
        if trade_qty <= 0:
            return None
        
        current_price = self._get_current_price(instrument)
        
        return OrderRequest(
            order_id="",
            agent_id=self.agent_id,
            instrument=instrument,
            side=benchmark.side if hasattr(benchmark, 'side') else 'buy',
            order_type='limit',
            quantity=trade_qty,
            price=current_price
        )
    
    def _implementation_shortfall(self, instrument: str, benchmark: ExecutionBenchmark, remaining_qty: float) -> Optional[OrderRequest]:
        """
        Implementation Shortfall algorithm
        
        Balances market impact cost vs timing risk
        """
        config = self.institutional_config
        
        # Calculate urgency based on remaining quantity and risk aversion
        participation = benchmark.filled_quantity / benchmark.target_quantity
        urgency = (1 - participation) * config.urgency_factor
        
        # Adjust for risk aversion
        urgency *= (1 + config.is_risk_aversion)
        
        # Calculate trade rate
        trade_qty = remaining_qty * urgency / config.twap_num_slices
        trade_qty = min(trade_qty, remaining_qty)
        
        if trade_qty <= 0:
            return None
        
        current_price = self._get_current_price(instrument)
        
        # More aggressive if behind schedule
        if participation < 0.5:
            order_type = 'market'
        else:
            order_type = 'limit'
        
        return OrderRequest(
            order_id="",
            agent_id=self.agent_id,
            instrument=instrument,
            side=benchmark.side if hasattr(benchmark, 'side') else 'buy',
            order_type=order_type,
            quantity=trade_qty,
            price=current_price
        )
    
    def _pov_slice(self, instrument: str, benchmark: ExecutionBenchmark, remaining_qty: float) -> Optional[OrderRequest]:
        """Percentage of Volume execution"""
        config = self.institutional_config
        
        # Get market volume
        market_vol = self.market_volume.get(instrument, 1000000)
        
        # Calculate target participation
        target_qty = market_vol * config.pov_percentage
        
        # Don't exceed remaining
        trade_qty = min(target_qty, remaining_qty)
        
        if trade_qty <= 0:
            return None
        
        current_price = self._get_current_price(instrument)
        
        return OrderRequest(
            order_id="",
            agent_id=self.agent_id,
            instrument=instrument,
            side=benchmark.side if hasattr(benchmark, 'side') else 'buy',
            order_type='limit',
            quantity=trade_qty,
            price=current_price
        )
    
    def _get_current_price(self, instrument: str) -> float:
        """Get current market price"""
        # Would come from market data feed
        return 100.0
    
    def get_execution_quality(self) -> Dict:
        """Get summary of execution quality"""
        if not self.execution_history:
            return {}
        
        slippages = [e.get_slippage() for e in self.execution_history]
        
        return {
            'total_orders': len(self.execution_history),
            'avg_slippage_bps': np.mean(slippages) * 10000,
            'max_slippage_bps': np.max(slippages) * 10000,
            'min_slippage_bps': np.min(slippages) * 10000,
            'avg_participation_rate': np.mean([e.get_participation_rate() for e in self.execution_history])
        }
