"""
Base Agent Framework
Common interfaces and base classes for all trading agents

Defines:
- BaseAgent abstract class
- Agent types and configurations
- Order submission interface
- Performance tracking
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)


class AgentType(Enum):
    """Types of trading agents"""
    RETAIL = "retail"
    SEMI_PROFESSIONAL = "semi_professional"
    INSTITUTIONAL = "institutional"
    HFT_MARKET_MAKER = "hft_market_maker"
    HFT_ARBITRAGEUR = "hft_arbitrageur"
    HFT_STAT_ARB = "hft_statistical_arbitrage"


class AgentState(Enum):
    """Agent operational states"""
    ACTIVE = "active"
    PAUSED = "paused"
    RISK_LIMITED = "risk_limited"
    ERROR = "error"
    TERMINATED = "terminated"


@dataclass
class AgentConfig:
    """Configuration for a trading agent"""
    agent_id: str
    agent_type: AgentType
    initial_capital: float = 1_000_000.0
    max_position_size: float = 100_000.0
    max_drawdown: float = 0.10  # 10%
    risk_tolerance: float = 0.5  # 0-1 scale
    latency_profile: str = "default"  # Maps to latency simulation
    trading_universe: List[str] = None
    enabled: bool = True


@dataclass
class Position:
    """Current position in an instrument"""
    instrument: str
    quantity: float  # Positive = long, Negative = short
    avg_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    entry_time: Optional[datetime] = None
    last_update: Optional[datetime] = None
    
    def update_pnl(self, current_price: float):
        """Update PnL with current market price"""
        self.realized_pnl = (current_price - self.avg_price) * self.quantity
        self.current_price = current_price
        self.unrealized_pnl = (current_price - self.avg_price) * abs(self.quantity)


@dataclass
class OrderRequest:
    """Order request from agent to matching engine"""
    order_id: str
    agent_id: str
    instrument: str
    side: str  # 'buy' or 'sell'
    order_type: str  # 'market', 'limit', etc.
    quantity: float
    price: Optional[float] = None
    time_in_force: str = "GTC"
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if not self.order_id:
            self.order_id = str(uuid.uuid4())


@dataclass
class Fill:
    """Order execution report"""
    order_id: str
    agent_id: str
    instrument: str
    side: str
    quantity: float
    price: float
    commission: float = 0.0
    timestamp: Optional[datetime] = None


@dataclass
class AgentPerformance:
    """Track agent performance metrics"""
    agent_id: str
    initial_capital: float
    current_capital: float
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    max_drawdown: float = 0.0
    peak_capital: float = 0.0
    sharpe_ratio: float = 0.0
    returns_history: List[float] = field(default_factory=list)
    
    def update_from_fill(self, fill: Fill):
        """Update performance from a fill"""
        self.total_trades += 1
        pnl = (fill.price - fill.price) * fill.quantity - fill.commission  # Simplified
        
        if pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        
        self.realized_pnl += pnl
        self.total_pnl = self.realized_pnl + self.unrealized_pnl
        self.current_capital = self.initial_capital + self.total_pnl
        
        # Update peak and drawdown
        self.peak_capital = max(self.peak_capital, self.current_capital)
        if self.peak_capital > 0:
            current_dd = (self.peak_capital - self.current_capital) / self.peak_capital
            self.max_drawdown = max(self.max_drawdown, current_dd)
    
    def calculate_metrics(self):
        """Calculate performance metrics"""
        if len(self.returns_history) < 2:
            return
        
        returns = np.array(self.returns_history)
        
        # Sharpe ratio
        if np.std(returns) > 0:
            self.sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252)
        
        # Win rate
        if self.total_trades > 0:
            win_rate = self.winning_trades / self.total_trades
        else:
            win_rate = 0.0


class BaseAgent(ABC):
    """
    Abstract base class for all trading agents
    
    All agent types must implement:
    - on_market_data: React to new market data
    - on_fill: Handle order execution
    - generate_orders: Create order requests
    """
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.agent_id = config.agent_id
        self.agent_type = config.agent_type
        self.state = AgentState.ACTIVE
        
        # Capital and positions
        self.capital = config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.pending_orders: Dict[str, OrderRequest] = {}
        self.order_history: List[Fill] = []
        
        # Performance tracking
        self.performance = AgentPerformance(
            agent_id=self.agent_id,
            initial_capital=config.initial_capital,
            current_capital=config.initial_capital,
            peak_capital=config.initial_capital
        )
        
        # Market data cache
        self.market_data: Dict[str, Dict] = {}
        
        # Risk limits
        self.max_position_size = config.max_position_size
        self.max_drawdown = config.max_drawdown
        
        logger.info(f"Agent {self.agent_id} ({self.agent_type.value}) initialized")
    
    @abstractmethod
    def on_market_data(self, instrument: str, data: Dict):
        """
        Called when new market data arrives
        
        Args:
            instrument: Instrument symbol
            data: Market data dictionary (bids, asks, trades, etc.)
        """
        pass
    
    @abstractmethod
    def on_fill(self, fill: Fill):
        """
        Called when an order is filled
        
        Args:
            fill: Fill information
        """
        pass
    
    @abstractmethod
    def generate_orders(self) -> List[OrderRequest]:
        """
        Generate orders based on current state and market view
        
        Returns:
            List of order requests to submit to matching engine
        """
        pass
    
    def on_timer(self, current_time: datetime):
        """
        Called periodically for time-based logic
        Override in subclasses if needed
        """
        pass
    
    def get_position(self, instrument: str) -> Optional[Position]:
        """Get current position for an instrument"""
        return self.positions.get(instrument)
    
    def get_total_exposure(self) -> float:
        """Get total market exposure across all positions"""
        total = 0.0
        for pos in self.positions.values():
            total += abs(pos.quantity * pos.current_price)
        return total
    
    def get_available_capital(self) -> float:
        """Get available capital for trading"""
        exposure = self.get_total_exposure()
        return max(0, self.capital - exposure)
    
    def check_risk_limits(self, order: OrderRequest) -> bool:
        """
        Pre-trade risk check
        
        Returns:
            True if order passes risk checks
        """
        # Check position size limit
        if order.quantity * (order.price or 0) > self.max_position_size:
            logger.warning(f"Agent {self.agent_id}: Order exceeds position size limit")
            return False
        
        # Check available capital
        required_capital = order.quantity * (order.price or 0)
        if required_capital > self.get_available_capital():
            logger.warning(f"Agent {self.agent_id}: Insufficient capital")
            return False
        
        # Check drawdown limit
        if self.performance.max_drawdown > self.max_drawdown:
            logger.warning(f"Agent {self.agent_id}: Drawdown limit exceeded")
            self.state = AgentState.RISK_LIMITED
            return False
        
        return True
    
    def update_position(self, instrument: str, quantity: float, price: float, side: str):
        """Update position after fill"""
        if instrument not in self.positions:
            self.positions[instrument] = Position(
                instrument=instrument,
                quantity=0,
                avg_price=price,
                current_price=price
            )
        
        pos = self.positions[instrument]
        
        if side == 'buy':
            # Adding to position
            total_cost = pos.avg_price * pos.quantity + price * quantity
            pos.quantity += quantity
            if pos.quantity != 0:
                pos.avg_price = total_cost / pos.quantity
        else:
            # Reducing position
            pos.quantity -= quantity
        
        pos.update_pnl(price)
    
    def reset(self):
        """Reset agent state"""
        self.capital = self.config.initial_capital
        self.positions.clear()
        self.pending_orders.clear()
        self.order_history.clear()
        self.state = AgentState.ACTIVE
        self.performance = AgentPerformance(
            agent_id=self.agent_id,
            initial_capital=self.config.initial_capital,
            current_capital=self.config.initial_capital,
            peak_capital=self.config.initial_capital
        )
    
    def get_state_dict(self) -> Dict:
        """Get agent state as dictionary (for serialization)"""
        return {
            'agent_id': self.agent_id,
            'agent_type': self.agent_type.value,
            'state': self.state.value,
            'capital': self.capital,
            'positions': {
                inst: {
                    'quantity': pos.quantity,
                    'avg_price': pos.avg_price,
                    'current_price': pos.current_price,
                    'unrealized_pnl': pos.unrealized_pnl
                }
                for inst, pos in self.positions.items()
            },
            'performance': {
                'total_trades': self.performance.total_trades,
                'total_pnl': self.performance.total_pnl,
                'sharpe_ratio': self.performance.sharpe_ratio,
                'max_drawdown': self.performance.max_drawdown
            }
        }
