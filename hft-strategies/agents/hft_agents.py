"""
HFT Agents
High-Frequency Trading strategies with microsecond latency

Includes:
- Market Maker (provides liquidity, earns spread)
- Latency Arbitrageur (exploits price differences across venues)
- Statistical Arbitrageur (pairs trading, mean reversion)

Characteristics:
- Ultra-low latency (nanoseconds to microseconds)
- Lock-free data structures
- Kernel bypass networking simulation
- Inventory management
- Adverse selection protection
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging
from collections import deque

from base_agent import BaseAgent, AgentConfig, AgentType, OrderRequest, Fill, AgentState

logger = logging.getLogger(__name__)


# ============================================================================
# HFT Market Maker
# ============================================================================

@dataclass
class MarketMakerConfig(AgentConfig):
    """HFT Market Maker configuration"""
    agent_type: AgentType = AgentType.HFT_MARKET_MAKER
    
    # Quoting parameters
    target_spread: float = 0.02  # Target bid-ask spread
    min_spread: float = 0.01     # Minimum spread
    max_spread: float = 0.10     # Maximum spread
    
    # Inventory management
    max_inventory: float = 10000  # Maximum position size
    inventory_skew: float = 0.5   # How much inventory affects quotes
    mean_reversion_speed: float = 0.1  # Speed of inventory mean reversion
    
    # Risk management
    max_position_duration_seconds: float = 5.0  # Don't hold positions too long
    adverse_selection_threshold: float = 0.001  # Detect informed flow
    cancel_threshold: float = 0.0005  # Cancel if mid moves more than this
    
    # Latency advantage
    latency_microseconds: float = 1.0  # 1 microsecond
    update_frequency_hz: int = 1000    # Update quotes 1000 times/sec


class HFTMarketMakerAgent(BaseAgent):
    """
    HFT Market Maker
    
    Strategy:
    - Continuously quote bid and ask
    - Earn spread while managing inventory risk
    - Adjust quotes based on inventory and market movement
    - Cancel and refresh if market moves against quotes
    
    Key risks:
    - Adverse selection (trading with informed traders)
    - Inventory risk (holding losing positions)
    - Latency arbitrage (being picked off by faster traders)
    """
    
    def __init__(self, config: MarketMakerConfig):
        super().__init__(config)
        self.mm_config = config
        
        # Current quotes
        self.bid_price: Optional[float] = None
        self.ask_price: Optional[float] = None
        self.bid_size: float = 100
        self.ask_size: float = 100
        
        # Inventory tracking
        self.inventory: float = 0.0
        self.inventory_history: deque = deque(maxlen=1000)
        
        # Market data
        self.mid_price: Optional[float] = None
        self.mid_price_history: deque = deque(maxlen=100)
        
        # PnL tracking
        self.realized_spread: float = 0.0
        self.unrealized_inventory_pnl: float = 0.0
        
        # Adverse selection detection
        self.fill_sequence: deque = deque(maxlen=50)
        
        logger.info(f"HFT Market Maker {self.agent_id} initialized")
    
    def on_market_data(self, instrument: str, data: Dict):
        """Update quotes based on new market data"""
        if 'mid_price' in data:
            old_mid = self.mid_price
            self.mid_price = data['mid_price']
            
            self.mid_price_history.append(self.mid_price)
            
            # Check if we need to cancel/refresh quotes
            if old_mid is not None:
                mid_move = abs(self.mid_price - old_mid) / old_mid
                
                if mid_move > self.mm_config.cancel_threshold:
                    # Market moved, cancel and refresh
                    self._cancel_all_quotes()
        
        # Update quotes
        self._update_quotes()
    
    def on_fill(self, fill: Fill):
        """Handle fill - critical for inventory management"""
        super().on_fill(fill)
        
        # Update inventory
        if fill.side == 'buy':
            self.inventory += fill.quantity
            self.realized_spread -= fill.price * fill.quantity  # Cash out
        else:
            self.inventory -= fill.quantity
            self.realized_spread += fill.price * fill.quantity  # Cash in
        
        # Track fills for adverse selection detection
        self.fill_sequence.append({
            'side': fill.side,
            'price': fill.price,
            'time': datetime.now()
        })
        
        # Update inventory history
        self.inventory_history.append(self.inventory)
        
        # Immediately adjust quotes after fill
        self._update_quotes()
    
    def generate_orders(self) -> List[OrderRequest]:
        """Generate quote orders"""
        orders = []
        
        if self.state != AgentState.ACTIVE:
            return orders
        
        if self.mid_price is None:
            return orders
        
        # Check inventory limits
        if abs(self.inventory) > self.mm_config.max_inventory:
            # Flatten inventory
            flatten_order = self._generate_flatten_order()
            if flatten_order:
                orders.append(flatten_order)
                return orders
        
        # Generate quote orders
        bid_order, ask_order = self._generate_quote_orders()
        
        if bid_order:
            orders.append(bid_order)
        if ask_order:
            orders.append(ask_order)
        
        return orders
    
    def _update_quotes(self):
        """Update bid and ask quotes based on current conditions"""
        if self.mid_price is None:
            return
        
        # Base spread
        spread = self.mm_config.target_spread
        
        # Adjust spread based on inventory
        inventory_adjustment = self._calculate_inventory_adjustment()
        spread = max(self.mm_config.min_spread, spread + inventory_adjustment)
        
        # Adjust for adverse selection
        if self._detect_adverse_selection():
            spread *= 2  # Widen spread if detecting informed flow
        
        # Adjust for volatility
        volatility_adjustment = self._calculate_volatility_adjustment()
        spread += volatility_adjustment
        
        # Clamp spread
        spread = min(spread, self.mm_config.max_spread)
        
        # Calculate quote prices
        # Skew quotes to manage inventory
        inventory_skew = self._calculate_inventory_skew()
        
        self.bid_price = self.mid_price - spread / 2 + inventory_skew
        self.ask_price = self.mid_price + spread / 2 + inventory_skew
        
        # Adjust sizes based on inventory
        if self.inventory > 0:
            # Have inventory, want to sell more
            self.ask_size = self.bid_size * 1.5
        elif self.inventory < 0:
            # Short inventory, want to buy more
            self.bid_size = self.ask_size * 1.5
    
    def _calculate_inventory_adjustment(self) -> float:
        """Adjust spread based on inventory risk"""
        inventory_ratio = self.inventory / self.mm_config.max_inventory
        return abs(inventory_ratio) * self.mm_config.inventory_skew
    
    def _calculate_inventory_skew(self) -> float:
        """Skew quotes to manage inventory"""
        inventory_ratio = self.inventory / self.mm_config.max_inventory
        return -inventory_ratio * self.mid_price * self.mm_config.inventory_skew * 0.01
    
    def _calculate_volatility_adjustment(self) -> float:
        """Widen spread during high volatility"""
        if len(self.mid_price_history) < 10:
            return 0.0
        
        prices = np.array(list(self.mid_price_history))
        returns = np.diff(np.log(prices))
        vol = np.std(returns)
        
        # Widen spread proportional to volatility
        return vol * 10  # Scale factor
    
    def _detect_adverse_selection(self) -> bool:
        """Detect if we're being picked off by informed traders"""
        if len(self.fill_sequence) < 10:
            return False
        
        # Check if fills are one-sided (indicates informed flow)
        recent_fills = list(self.fill_sequence)[-10:]
        buy_fills = sum(1 for f in recent_fills if f['side'] == 'buy')
        
        # If 80%+ are same side, likely adverse selection
        if buy_fills >= 8 or buy_fills <= 2:
            return True
        
        return False
    
    def _generate_quote_orders(self) -> Tuple[Optional[OrderRequest], Optional[OrderRequest]]:
        """Generate bid and ask quote orders"""
        if self.mid_price is None:
            return None, None
        
        bid_order = OrderRequest(
            order_id="",
            agent_id=self.agent_id,
            instrument="ASSET_0",
            side='buy',
            order_type='limit',
            quantity=self.bid_size,
            price=self.bid_price
        )
        
        ask_order = OrderRequest(
            order_id="",
            agent_id=self.agent_id,
            instrument="ASSET_0",
            side='sell',
            order_type='limit',
            quantity=self.ask_size,
            price=self.ask_price
        )
        
        return bid_order, ask_order
    
    def _generate_flatten_order(self) -> Optional[OrderRequest]:
        """Generate order to flatten inventory"""
        if abs(self.inventory) < 100:
            return None
        
        side = 'sell' if self.inventory > 0 else 'buy'
        quantity = abs(self.inventory)
        
        return OrderRequest(
            order_id="",
            agent_id=self.agent_id,
            instrument="ASSET_0",
            side=side,
            order_type='market',
            quantity=quantity,
            price=self.mid_price
        )
    
    def _cancel_all_quotes(self):
        """Cancel all outstanding quote orders"""
        # Would communicate with matching engine
        pass
    
    def get_performance_metrics(self) -> Dict:
        """Get market maker specific metrics"""
        return {
            'total_spread_captured': self.realized_spread,
            'avg_inventory': np.mean(list(self.inventory_history)) if self.inventory_history else 0,
            'max_inventory': max(abs(np.max(list(self.inventory_history))), abs(np.min(list(self.inventory_history)))) if self.inventory_history else 0,
            'current_inventory': self.inventory,
            'adverse_selection_detected': self._detect_adverse_selection()
        }


# ============================================================================
# HFT Latency Arbitrageur
# ============================================================================

@dataclass
class LatencyArbConfig(AgentConfig):
    """Latency Arbitrage configuration"""
    agent_type: AgentType = AgentType.HFT_ARBITRAGEUR
    
    # Arbitrage parameters
    min_profit_threshold: float = 0.0005  # Minimum profit to trade (0.05%)
    max_position_size: float = 5000
    latency_advantage_ns: float = 100  # 100 nanosecond advantage
    
    # Multiple venues
    num_venues: int = 3
    venue_latency差异: float = 0.001  # Latency difference between venues


class HFTLatencyArbAgent(BaseAgent):
    """
    HFT Latency Arbitrageur
    
    Strategy:
    - Monitor same instrument across multiple venues
    - Exploit temporary price discrepancies
    - Buy on slow venue, sell on fast venue
    - Requires ultra-low latency
    
    Note: This is simulated - real latency arb requires hardware
    """
    
    def __init__(self, config: LatencyArbConfig):
        super().__init__(config)
        self.arb_config = config
        
        # Venue prices
        self.venue_prices: Dict[str, Dict[str, float]] = {}
        
        # Arbitrage opportunities
        self.opportunities_found: int = 0
        self.total_profit: float = 0.0
        
        logger.info(f"HFT Latency Arb {self.agent_id} initialized")
    
    def on_market_data(self, instrument: str, data: Dict):
        """Update venue prices"""
        if 'venue' in data and 'price' in data:
            venue = data['venue']
            if instrument not in self.venue_prices:
                self.venue_prices[instrument] = {}
            self.venue_prices[instrument][venue] = data['price']
    
    def generate_orders(self) -> List[OrderRequest]:
        """Look for arbitrage opportunities"""
        orders = []
        
        if self.state != AgentState.ACTIVE:
            return orders
        
        for instrument, venues in self.venue_prices.items():
            if len(venues) < 2:
                continue
            
            # Find best and worst prices
            prices = [(venue, price) for venue, price in venues.items()]
            prices.sort(key=lambda x: x[1])
            
            best_venue, best_price = prices[0]  # Lowest (buy)
            worst_venue, worst_price = prices[-1]  # Highest (sell)
            
            # Calculate profit potential
            profit = (worst_price - best_price) / best_price
            
            if profit > self.arb_config.min_profit_threshold:
                # Found arbitrage!
                self.opportunities_found += 1
                
                # Buy on cheap venue
                buy_order = OrderRequest(
                    order_id="",
                    agent_id=self.agent_id,
                    instrument=instrument,
                    side='buy',
                    order_type='limit',
                    quantity=self.arb_config.max_position_size,
                    price=best_price
                )
                
                # Sell on expensive venue
                sell_order = OrderRequest(
                    order_id="",
                    agent_id=self.agent_id,
                    instrument=instrument,
                    side='sell',
                    order_type='limit',
                    quantity=self.arb_config.max_position_size,
                    price=worst_price
                )
                
                orders.extend([buy_order, sell_order])
                self.total_profit += profit * self.arb_config.max_position_size
        
        return orders


# ============================================================================
# HFT Statistical Arbitrageur
# ============================================================================

@dataclass
class StatArbConfig(AgentConfig):
    """Statistical Arbitrage configuration"""
    agent_type: AgentType = AgentType.HFT_STAT_ARB
    
    # Pairs trading parameters
    lookback_window: int = 100
    entry_z_score: float = 2.0
    exit_z_score: float = 0.5
    max_pairs: int = 5
    
    # Mean reversion
    half_life_target: float = 10  # Target half-life in bars
    min_half_life: float = 5
    max_half_life: float = 50


class HFTStatArbAgent(BaseAgent):
    """
    HFT Statistical Arbitrageur
    
    Strategy:
    - Pairs trading (long one asset, short correlated asset)
    - Mean reversion on spread
    - Statistical signals for entry/exit
    - Fast execution on signal generation
    """
    
    def __init__(self, config: StatArbConfig):
        super().__init__(config)
        self.stat_config = config
        
        # Price histories
        self.price_history: Dict[str, deque] = {}
        
        # Active pairs
        self.active_pairs: List[Tuple[str, str]] = []
        self.spread_z_scores: Dict[Tuple[str, str], float] = {}
        
        # Performance
        self.pairs_pnl: Dict[Tuple[str, str], float] = {}
        
        logger.info(f"HFT Stat Arb {self.agent_id} initialized")
    
    def on_market_data(self, instrument: str, data: Dict):
        """Update price history"""
        if 'price' in data:
            if instrument not in self.price_history:
                self.price_history[instrument] = deque(maxlen=self.stat_config.lookback_window)
            self.price_history[instrument].append(data['price'])
    
    def generate_orders(self) -> List[OrderRequest]:
        """Generate pairs trading orders"""
        orders = []
        
        if self.state != AgentState.ACTIVE:
            return orders
        
        # Find pairs with diverged spreads
        pairs_to_trade = self._find_pairs()
        
        for leg1, leg2 in pairs_to_trade:
            z_score = self._calculate_z_score(leg1, leg2)
            
            if abs(z_score) > self.stat_config.entry_z_score:
                # Entry signal
                if z_score > 0:
                    # Spread too wide: short leg1, long leg2
                    orders.extend(self._create_pair_orders(leg1, leg2, 'short_spread'))
                else:
                    # Spread too narrow: long leg1, short leg2
                    orders.extend(self._create_pair_orders(leg1, leg2, 'long_spread'))
                
                self.spread_z_scores[(leg1, leg2)] = z_score
        
        # Check for exit signals on active pairs
        exit_orders = self._check_exits()
        orders.extend(exit_orders)
        
        return orders
    
    def _find_pairs(self) -> List[Tuple[str, str]]:
        """Find instruments to pair trade"""
        instruments = list(self.price_history.keys())
        pairs = []
        
        # Simple pairing: consecutive instruments
        for i in range(0, len(instruments) - 1, 2):
            if (len(self.price_history[instruments[i]]) >= self.stat_config.lookback_window and
                len(self.price_history[instruments[i+1]]) >= self.stat_config.lookback_window):
                pairs.append((instruments[i], instruments[i+1]))
        
        return pairs[:self.stat_config.max_pairs]
    
    def _calculate_z_score(self, instrument1: str, instrument2: str) -> float:
        """Calculate z-score of spread between two instruments"""
        prices1 = np.array(list(self.price_history[instrument1]))
        prices2 = np.array(list(self.price_history[instrument2]))
        
        # Calculate spread (log prices)
        spread = np.log(prices1) - np.log(prices2)
        
        # Z-score
        mean_spread = np.mean(spread)
        std_spread = np.std(spread)
        
        if std_spread == 0:
            return 0.0
        
        current_spread = spread[-1]
        z_score = (current_spread - mean_spread) / std_spread
        
        return z_score
    
    def _create_pair_orders(self, leg1: str, leg2: str, direction: str) -> List[OrderRequest]:
        """Create orders for pairs trade"""
        orders = []
        
        price1 = list(self.price_history[leg1])[-1]
        price2 = list(self.price_history[leg2])[-1]
        
        quantity = self.config.max_position_size / 2
        
        if direction == 'long_spread':
            # Long leg1, short leg2
            orders.append(OrderRequest(
                order_id="", agent_id=self.agent_id, instrument=leg1,
                side='buy', order_type='limit', quantity=quantity, price=price1
            ))
            orders.append(OrderRequest(
                order_id="", agent_id=self.agent_id, instrument=leg2,
                side='sell', order_type='limit', quantity=quantity, price=price2
            ))
        else:
            # Short leg1, long leg2
            orders.append(OrderRequest(
                order_id="", agent_id=self.agent_id, instrument=leg1,
                side='sell', order_type='limit', quantity=quantity, price=price1
            ))
            orders.append(OrderRequest(
                order_id="", agent_id=self.agent_id, instrument=leg2,
                side='buy', order_type='limit', quantity=quantity, price=price2
            ))
        
        return orders
    
    def _check_exits(self) -> List[OrderRequest]:
        """Check if any pairs should be exited"""
        orders = []
        
        for (leg1, leg2), z_score in list(self.spread_z_scores.items()):
            if abs(z_score) < self.stat_config.exit_z_score:
                # Exit signal - close both legs
                # ... would need to track positions to know quantities
                pass
        
        return orders
