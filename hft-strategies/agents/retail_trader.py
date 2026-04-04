"""
Retail Trader Agent
Implements behavioral finance principles and psychological biases

Features:
- Prospect Theory (Kahneman & Tversky)
- Loss aversion
- Herd mentality
- Confirmation bias
- Recency bias
- Overconfidence
- Emotional decision making
- Delayed/incomplete information processing
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging

from base_agent import BaseAgent, AgentConfig, AgentType, OrderRequest, Fill, Position, AgentState
from indicators import TechnicalAnalysis, MomentumIndicators, MovingAverage

logger = logging.getLogger(__name__)


@dataclass
class PsychologicalState:
    """Track psychological state of retail trader"""
    fear_level: float = 0.5  # 0-1, higher = more fearful
    greed_level: float = 0.5  # 0-1, higher = more greedy
    confidence: float = 0.5  # 0-1, higher = more confident
    regret: float = 0.0  # 0-1, regret from missed opportunities
    anxiety: float = 0.0  # 0-1, anxiety about current positions
    herd_tendency: float = 0.5  # 0-1, tendency to follow crowd
    
    # Recent emotional history
    emotional_history: List[float] = field(default_factory=list)
    
    def update_emotions(self, 
                       pnl_change: float, 
                       market_volatility: float,
                       missed_opportunity: float = 0.0):
        """Update emotional state based on recent events"""
        # PnL impact on emotions
        if pnl_change > 0:
            self.greed_level = min(1.0, self.greed_level + 0.1)
            self.fear_level = max(0.0, self.fear_level - 0.15)
            self.confidence = min(1.0, self.confidence + 0.1)
            self.anxiety = max(0.0, self.anxiety - 0.1)
        elif pnl_change < 0:
            self.fear_level = min(1.0, self.fear_level + 0.15)
            self.greed_level = max(0.0, self.greed_level - 0.1)
            self.confidence = max(0.0, self.confidence - 0.15)
            self.anxiety = min(1.0, self.anxiety + 0.2)
        
        # Market volatility increases fear
        self.fear_level = min(1.0, self.fear_level + market_volatility * 0.1)
        
        # Regret from missed opportunities
        self.regret = min(1.0, self.regret + missed_opportunity * 0.1)
        
        # Store emotional history
        self.emotional_history.append(self.fear_level)
        if len(self.emotional_history) > 50:
            self.emotional_history.pop(0)
    
    def get_emotional_bias(self) -> float:
        """Get overall emotional bias (-1 to 1, positive = bullish)"""
        # Greed pushes bullish, fear pushes bearish
        return self.greed_level - self.fear_level


@dataclass
class RetailConfig(AgentConfig):
    """Retail trader specific configuration"""
    agent_type: AgentType = AgentType.RETAIL
    
    # Behavioral parameters
    loss_aversion_coefficient: float = 2.0  # Typically 1.5-2.5 (Kahneman & Tversky)
    prospect_power: float = 0.88  # Value function curvature (typically < 1)
    probability_weighting: float = 0.61  # Tendency to overweight small probabilities
    
    # Information processing
    information_delay_seconds: float = 5.0  # Delayed data feed
    attention_span_bars: int = 20  # How far back they look
    news_sensitivity: float = 0.5  # How much news affects decisions
    
    # Trading behavior
    average_trades_per_day: int = 5  # Typical trading frequency
    position_sizing_randomness: float = 0.3  # Randomness in position sizing
    tendency_to_chase: float = 0.4  # Tendency to chase momentum
    tendency_to_panic_sell: float = 0.3  # Tendency to panic sell
    
    # Technical analysis usage
    uses_technical_analysis: bool = True
    preferred_indicators: List[str] = None  # ['RSI', 'MACD', 'Moving Averages']
    
    def __post_init__(self):
        if self.preferred_indicators is None:
            self.preferred_indicators = ['RSI', 'MACD', 'SMA']


class RetailTraderAgent(BaseAgent):
    """
    Retail trader agent with behavioral biases
    
    Characteristics:
    - Delayed and incomplete information
    - Emotional decision making (fear/greed)
    - Prospect Theory value function
    - Loss aversion (losses hurt 2x more than gains)
    - Herd behavior
    - Tendency to chase momentum
    - Panic selling during crashes
    - Uses basic technical analysis
    """
    
    def __init__(self, config: RetailConfig):
        super().__init__(config)
        self.retail_config = config
        
        # Psychological state
        self.psychology = PsychologicalState()
        
        # Technical analysis (simplified)
        self.ta = TechnicalAnalysis(lookback=config.attention_span_bars)
        
        # Market data with delay
        self.delayed_market_data: Dict[str, Dict] = {}
        self.market_data_buffer: List[Tuple[str, Dict]] = []
        
        # Performance tracking for emotions
        self.recent_pnl_changes: List[float] = []
        self.missed_opportunities: List[float] = []
        
        # Decision history
        self.decision_history: List[Dict] = []
        
        logger.info(f"Retail trader {self.agent_id} initialized with behavioral biases")
    
    def on_market_data(self, instrument: str, data: Dict):
        """
        Process market data with delay and imperfections
        Retail traders don't see real-time data
        """
        # Buffer data for delayed processing
        self.market_data_buffer.append((instrument, data))
        
        # Process with delay (simulate delayed feed)
        if len(self.market_data_buffer) > 5:  # Arbitrary delay
            delayed_instrument, delayed_data = self.market_data_buffer.pop(0)
            self.delayed_market_data[delayed_instrument] = delayed_data
            
            # Update technical analysis
            if 'price' in delayed_data:
                price = delayed_data['price']
                high = delayed_data.get('high', price)
                low = delayed_data.get('low', price)
                volume = delayed_data.get('volume', 1000000)
                
                self.ta.update(price, high, low, volume)
    
    def on_fill(self, fill: Fill):
        """Handle order fill with emotional response"""
        super().on_fill(fill)
        
        # Update position
        self.update_position(fill.instrument, fill.quantity, fill.price, fill.side)
        
        # Emotional response to fill
        pnl_impact = 0.01 if fill.side == 'buy' else -0.01  # Simplified
        self.recent_pnl_changes.append(pnl_impact)
        
        # Update psychology
        self.psychology.update_emotions(
            pnl_change=pnl_impact,
            market_volatility=0.02
        )
        
        logger.info(f"Retail {self.agent_id} filled: {fill.side} {fill.quantity} @ {fill.price}")
    
    def generate_orders(self) -> List[OrderRequest]:
        """
        Generate orders based on biased decision making
        
        Decision process:
        1. Technical analysis (basic)
        2. Emotional overlay (fear/greed)
        3. Behavioral biases (loss aversion, herd, etc.)
        4. Risk check
        """
        orders = []
        
        if self.state != AgentState.ACTIVE:
            return orders
        
        # Get technical signals
        ta_signals = self._analyze_technicals()
        
        # Apply behavioral biases
        biased_signals = self._apply_behavioral_biases(ta_signals)
        
        # Generate orders based on biased signals
        for instrument, signal in biased_signals.items():
            if abs(signal) > 0.3:  # Threshold for action
                order = self._create_order(instrument, signal)
                if order and self.check_risk_limits(order):
                    orders.append(order)
        
        # Occasionally panic sell or FOMO buy
        if np.random.random() < self._get_panic_probability():
            panic_order = self._generate_panic_sell()
            if panic_order:
                orders.append(panic_order)
        
        if np.random.random() < self._get_fomo_probability():
            fomo_order = self._generate_fomo_buy()
            if fomo_order:
                orders.append(fomo_order)
        
        return orders
    
    def _analyze_technicals(self) -> Dict[str, float]:
        """
        Analyze technical indicators (simplified view)
        Returns: Dict of instrument -> signal (-1 to 1)
        """
        signals = {}
        
        ta_data = self.ta.calculate_all()
        if not ta_data:
            return signals
        
        signal = 0.0
        
        # RSI signal
        if 'rsi_14' in ta_data:
            rsi = ta_data['rsi_14']
            if rsi < 30:  # Oversold
                signal += 0.5
            elif rsi > 70:  # Overbought
                signal -= 0.5
        
        # MACD signal
        if 'macd' in ta_data and 'macd_signal' in ta_data:
            if ta_data['macd'] > ta_data['macd_signal']:
                signal += 0.3
            else:
                signal -= 0.3
        
        # Moving average crossover
        if 'sma_20' in ta_data and 'sma_50' in ta_data:
            if ta_data['sma_20'] > ta_data['sma_50']:
                signal += 0.3
            else:
                signal -= 0.3
        
        # Trend
        if 'trend' in ta_data:
            signal += ta_data['trend'] * 0.5
        
        # Clamp signal
        signal = np.clip(signal, -1.0, 1.0)
        
        signals["ASSET_0"] = signal
        return signals
    
    def _apply_behavioral_biases(self, signals: Dict[str, float]) -> Dict[str, float]:
        """
        Apply behavioral finance biases to signals
        
        Implements:
        - Prospect Theory value function
        - Loss aversion
        - Herd behavior
        - Recency bias
        - Confirmation bias
        """
        biased_signals = {}
        
        for instrument, signal in signals.items():
            biased_signal = signal
            
            # 1. Prospect Theory: Asymmetric treatment of gains/losses
            # Losses loom larger than gains
            if signal < 0:  # Potential loss
                biased_signal *= self.retail_config.loss_aversion_coefficient
            
            # 2. Recency bias: Overweight recent performance
            if self.recent_pnl_changes:
                recent_pnl = np.mean(self.recent_pnl_changes[-5:])
                biased_signal += recent_pnl * 2  # Overweight recent PnL
            
            # 3. Herd behavior: Follow the crowd
            herd_bias = (self.psychology.herd_tendency - 0.5) * 0.5
            biased_signal += herd_bias
            
            # 4. Emotional overlay
            emotional_bias = self.psychology.get_emotional_bias() * 0.3
            biased_signal += emotional_bias
            
            # 5. Chase momentum (if configured)
            if self.retail_config.tendency_to_chase > 0.5:
                if signal > 0:  # Chasing upward momentum
                    biased_signal *= (1 + self.retail_config.tendency_to_chase)
            
            # 6. Overconfidence in bull markets
            if self.psychology.confidence > 0.7:
                biased_signal *= 1.2  # Overconfident amplification
            
            # Clamp final signal
            biased_signals[instrument] = np.clip(biased_signal, -1.0, 1.0)
        
        return biased_signals
    
    def _create_order(self, instrument: str, signal: float) -> Optional[OrderRequest]:
        """Create order from signal"""
        side = 'buy' if signal > 0 else 'sell'
        
        # Position sizing with randomness (retail traders are inconsistent)
        base_size = self.get_available_capital() * 0.1  # 10% of available
        randomness = np.random.uniform(
            1 - self.retail_config.position_sizing_randomness,
            1 + self.retail_config.position_sizing_randomness
        )
        quantity = base_size * randomness / self._get_current_price(instrument)
        
        # Round to lot size
        quantity = round(quantity / 100) * 100
        
        if quantity <= 0:
            return None
        
        # Get price (with delay)
        price = self._get_current_price(instrument)
        
        # Add slippage (retail gets worse fills)
        slippage = price * 0.001  # 0.1% slippage
        if side == 'buy':
            price += slippage
        else:
            price -= slippage
        
        order = OrderRequest(
            order_id="",
            agent_id=self.agent_id,
            instrument=instrument,
            side=side,
            order_type='market',
            quantity=quantity,
            price=price
        )
        
        return order
    
    def _get_current_price(self, instrument: str) -> float:
        """Get current price (may be delayed)"""
        if instrument in self.delayed_market_data:
            return self.delayed_market_data[instrument].get('price', 100.0)
        return 100.0  # Default
    
    def _get_panic_probability(self) -> float:
        """Calculate probability of panic selling"""
        base_prob = self.retail_config.tendency_to_panic_sell
        
        # Increase with fear and recent losses
        fear_multiplier = 1 + self.psychology.fear_level * 2
        loss_multiplier = 1.0
        
        if self.recent_pnl_changes:
            recent_losses = sum(1 for pnl in self.recent_pnl_changes[-5:] if pnl < 0)
            loss_multiplier = 1 + recent_losses * 0.3
        
        return min(1.0, base_prob * fear_multiplier * loss_multiplier)
    
    def _get_fomo_probability(self) -> float:
        """Calculate probability of FOMO (Fear Of Missing Out) buying"""
        base_prob = self.retail_config.tendency_to_chase * 0.3
        
        # Increase with greed and regret
        greed_multiplier = 1 + self.psychology.greed_level * 2
        regret_multiplier = 1 + self.psychology.regret * 1.5
        
        return min(1.0, base_prob * greed_multiplier * regret_multiplier)
    
    def _generate_panic_sell(self) -> Optional[OrderRequest]:
        """Generate panic sell order"""
        if not self.positions:
            return None
        
        # Sell largest position
        largest_pos = max(self.positions.values(), key=lambda p: abs(p.quantity))
        
        if largest_pos.quantity <= 0:
            return None
        
        # Panic sell 50-100% of position
        sell_pct = np.random.uniform(0.5, 1.0)
        quantity = largest_pos.quantity * sell_pct
        
        price = self._get_current_price(largest_pos.instrument)
        price *= 0.995  # Accept worse price in panic
        
        order = OrderRequest(
            order_id="",
            agent_id=self.agent_id,
            instrument=largest_pos.instrument,
            side='sell',
            order_type='market',
            quantity=quantity,
            price=price
        )
        
        logger.warning(f"PANIC SELL: {largest_pos.instrument} {quantity} @ {price}")
        return order
    
    def _generate_fomo_buy(self) -> Optional[OrderRequest]:
        """Generate FOMO buy order (chasing momentum)"""
        # Buy instrument that's gone up the most
        best_performer = None
        best_return = -999
        
        for instrument, data in self.delayed_market_data.items():
            if 'price' in data and 'open' in data:
                ret = (data['price'] - data['open']) / data['open']
                if ret > best_return:
                    best_return = ret
                    best_performer = instrument
        
        if best_performer is None:
            return None
        
        # FOMO buy
        quantity = self.get_available_capital() * 0.15 / self._get_current_price(best_performer)
        quantity = round(quantity / 100) * 100
        
        if quantity <= 0:
            return None
        
        price = self._get_current_price(best_performer)
        price *= 1.002  # Pay premium in FOMO
        
        order = OrderRequest(
            order_id="",
            agent_id=self.agent_id,
            instrument=best_performer,
            side='buy',
            order_type='market',
            quantity=quantity,
            price=price
        )
        
        logger.warning(f"FOMO BUY: {best_performer} {quantity} @ {price}")
        return order
    
    def calculate_prospect_value(self, outcomes: List[float], probabilities: List[float]) -> float:
        """
        Calculate prospect theory value
        
        V = Σ w(p_i) * v(x_i)
        
        Where:
        - v(x) = x^α for gains, -λ*(-x)^β for losses
        - w(p) = p^γ / (p^γ + (1-p)^γ)^(1/γ)
        """
        alpha = self.retail_config.prospect_power
        beta = self.retail_config.prospect_power
        lam = self.retail_config.loss_aversion_coefficient
        gamma = self.retail_config.probability_weighting
        
        total_value = 0.0
        
        for outcome, prob in zip(outcomes, probabilities):
            # Weight probability
            weighted_prob = prob**gamma / (prob**gamma + (1 - prob)**gamma)**(1/gamma)
            
            # Value function
            if outcome >= 0:
                value = outcome**alpha
            else:
                value = -lam * (-outcome)**beta
            
            total_value += weighted_prob * value
        
        return total_value
