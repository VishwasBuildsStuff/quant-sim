"""
Semi-Professional Trader Agent
More sophisticated than retail, less than institutional

Characteristics:
- Uses standard technical indicators systematically
- Basic risk management (stop-loss, take-profit)
- Moderate reaction time
- Less emotional bias
- Some fundamental analysis awareness
- Position sizing based on volatility
"""

import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

from base_agent import BaseAgent, AgentConfig, AgentType, OrderRequest, Fill, AgentState
from indicators import (
    TechnicalAnalysis, 
    MomentumIndicators, 
    VolatilityIndicators,
    MovingAverage
)

logger = logging.getLogger(__name__)


@dataclass
class SemiProConfig(AgentConfig):
    """Semi-professional trader configuration"""
    agent_type: AgentType = AgentType.SEMI_PROFESSIONAL
    
    # Strategy parameters
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    
    # Risk management
    stop_loss_pct: float = 0.02  # 2% stop loss
    take_profit_pct: float = 0.04  # 4% take profit
    max_positions: int = 5
    risk_per_trade: float = 0.02  # Risk 2% per trade
    
    # Signal thresholds
    entry_threshold: float = 0.4
    exit_threshold: float = 0.2
    
    # Information delay (less than retail)
    information_delay_seconds: float = 1.0


class SemiProfessionalTraderAgent(BaseAgent):
    """
    Semi-professional trader agent
    
    More disciplined than retail traders but not as sophisticated as institutions.
    Uses technical analysis systematically with basic risk management.
    """
    
    def __init__(self, config: SemiProConfig):
        super().__init__(config)
        self.semi_pro_config = config
        
        # Technical analysis
        self.ta = TechnicalAnalysis(lookback=100)
        
        # Active signals
        self.current_signals: Dict[str, float] = {}
        
        # Stop losses and take profits
        self.stop_losses: Dict[str, float] = {}
        self.take_profits: Dict[str, float] = {}
        
        logger.info(f"Semi-pro trader {self.agent_id} initialized")
    
    def on_market_data(self, instrument: str, data: Dict):
        """Process market data"""
        # Update delayed market data
        if 'price' in data:
            price = data['price']
            high = data.get('high', price)
            low = data.get('low', price)
            volume = data.get('volume', 1000000)
            
            self.ta.update(price, high, low, volume)
    
    def on_fill(self, fill: Fill):
        """Handle order fill"""
        super().on_fill(fill)
        self.update_position(fill.instrument, fill.quantity, fill.price, fill.side)
        
        # Set stop loss and take profit
        if fill.side == 'buy':
            self.stop_losses[fill.instrument] = fill.price * (1 - self.semi_pro_config.stop_loss_pct)
            self.take_profits[fill.instrument] = fill.price * (1 + self.semi_pro_config.take_profit_pct)
        elif fill.instrument in self.stop_losses:
            del self.stop_losses[fill.instrument]
            del self.take_profits[fill.instrument]
    
    def generate_orders(self) -> List[OrderRequest]:
        """Generate orders based on technical analysis"""
        orders = []
        
        if self.state != AgentState.ACTIVE:
            return orders
        
        # Check existing positions for exits
        exit_orders = self._check_exits()
        orders.extend(exit_orders)
        
        # Look for new entry opportunities
        if len(self.positions) < self.semi_pro_config.max_positions:
            entry_orders = self._find_entries()
            orders.extend(entry_orders)
        
        return orders
    
    def _check_exits(self) -> List[OrderRequest]:
        """Check if any positions should be exited"""
        orders = []
        
        for instrument, position in self.positions.items():
            if position.quantity <= 0:
                continue
            
            current_price = position.current_price
            
            # Check stop loss
            if instrument in self.stop_losses:
                if current_price <= self.stop_losses[instrument]:
                    order = OrderRequest(
                        order_id="",
                        agent_id=self.agent_id,
                        instrument=instrument,
                        side='sell',
                        order_type='stop_loss',
                        quantity=position.quantity,
                        price=current_price * 0.99
                    )
                    orders.append(order)
                    logger.info(f"Stop loss triggered: {instrument}")
                    continue
            
            # Check take profit
            if instrument in self.take_profits:
                if current_price >= self.take_profits[instrument]:
                    order = OrderRequest(
                        order_id="",
                        agent_id=self.agent_id,
                        instrument=instrument,
                        side='sell',
                        order_type='take_profit',
                        quantity=position.quantity,
                        price=current_price
                    )
                    orders.append(order)
                    logger.info(f"Take profit triggered: {instrument}")
                    continue
            
            # Check if signal has reversed
            if instrument in self.current_signals:
                if abs(self.current_signals[instrument]) < self.semi_pro_config.exit_threshold:
                    order = OrderRequest(
                        order_id="",
                        agent_id=self.agent_id,
                        instrument=instrument,
                        side='sell',
                        order_type='limit',
                        quantity=position.quantity,
                        price=current_price
                    )
                    orders.append(order)
        
        return orders
    
    def _find_entries(self) -> List[OrderRequest]:
        """Find new entry opportunities"""
        orders = []
        
        # Analyze technicals
        ta_data = self.ta.calculate_all()
        if not ta_data:
            return orders
        
        # Calculate composite signal
        signal = self._calculate_signal(ta_data)
        
        if abs(signal) > self.semi_pro_config.entry_threshold:
            # Calculate position size using volatility
            position_size = self._calculate_position_size(ta_data)
            
            if position_size > 0:
                side = 'buy' if signal > 0 else 'sell'
                price = ta_data.get('price', 100.0)
                
                order = OrderRequest(
                    order_id="",
                    agent_id=self.agent_id,
                    instrument="ASSET_0",
                    side=side,
                    order_type='limit',
                    quantity=position_size,
                    price=price
                )
                orders.append(order)
                
                self.current_signals["ASSET_0"] = signal
        
        return orders
    
    def _calculate_signal(self, ta_data: Dict) -> float:
        """Calculate composite technical signal"""
        signal = 0.0
        weight = 0.0
        
        # RSI (weight: 0.3)
        if 'rsi_14' in ta_data:
            rsi = ta_data['rsi_14']
            if rsi < 30:
                signal += 0.3 * (30 - rsi) / 30
            elif rsi > 70:
                signal -= 0.3 * (rsi - 70) / 30
            weight += 0.3
        
        # MACD (weight: 0.3)
        if 'macd' in ta_data and 'macd_histogram' in ta_data:
            hist = ta_data['macd_histogram']
            signal += 0.3 * np.clip(hist / ta_data['price'], -1, 1)
            weight += 0.3
        
        # Bollinger Bands (weight: 0.2)
        if 'bb_lower' in ta_data and 'bb_upper' in ta_data:
            price = ta_data['price']
            if price < ta_data['bb_lower']:
                signal += 0.2
            elif price > ta_data['bb_upper']:
                signal -= 0.2
            weight += 0.2
        
        # Trend (weight: 0.2)
        if 'trend' in ta_data:
            signal += 0.2 * ta_data['trend']
            weight += 0.2
        
        # Normalize
        if weight > 0:
            signal /= weight
        
        return np.clip(signal, -1.0, 1.0)
    
    def _calculate_position_size(self, ta_data: Dict) -> float:
        """Calculate position size based on risk"""
        if 'atr_14' not in ta_data:
            return 0.0
        
        atr = ta_data['atr_14']
        if atr <= 0:
            return 0.0
        
        # Risk-based position sizing
        risk_amount = self.capital * self.semi_pro_config.risk_per_trade
        position_size = risk_amount / (atr * 2)  # 2x ATR risk
        
        # Round to lot size
        position_size = round(position_size / 100) * 100
        
        return max(0, position_size)
