"""
Portfolio Manager for Automated HFT Trading
Manages capital allocation, position sizing, and risk across multiple stocks
"""

import sys
sys.path.insert(0, r'V:\pylibs')

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Single stock position"""
    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    entry_time: datetime
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    
    def update_price(self, price: float):
        """Update current price"""
        self.current_price = price
        self.unrealized_pnl = (price - self.entry_price) * self.quantity
        self.max_profit = max(self.max_profit, self.unrealized_pnl)
        self.max_loss = min(self.max_loss, self.unrealized_pnl)
    
    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price
    
    @property
    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price


@dataclass
class TradeRecord:
    """Single trade record"""
    timestamp: datetime
    symbol: str
    action: str  # BUY, SELL, HOLD
    quantity: int
    price: float
    pnl: float = 0.0
    confidence: float = 0.0
    model_votes: str = ""


class PortfolioManager:
    """
    Professional portfolio management for HFT
    
    Features:
    - Multi-stock position tracking
    - Dynamic capital allocation
    - Risk management (stop loss, max drawdown)
    - Position sizing based on confidence
    - Performance tracking
    """
    
    def __init__(self,
                 initial_capital: float = 1_000_000,
                 max_positions: int = 5,
                 risk_per_trade: float = 0.02,
                 max_position_pct: float = 0.20,
                 stop_loss_pct: float = 0.02,
                 max_drawdown_pct: float = 0.05,
                 max_daily_trades: int = 100):
        
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.peak_capital = initial_capital
        
        # Position limits
        self.max_positions = max_positions
        self.max_position_pct = max_position_pct
        self.risk_per_trade = risk_per_trade
        
        # Risk limits
        self.stop_loss_pct = stop_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_daily_trades = max_daily_trades
        
        # State
        self.positions: Dict[str, Position] = {}
        self.trade_log: List[TradeRecord] = []
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.last_reset_date = datetime.now().date()
        
        # Performance tracking
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
    
    def calculate_position_size(self, price: float, confidence: float, volatility: float = 0.01) -> int:
        """
        Calculate optimal position size based on:
        - Available capital
        - Risk per trade
        - Prediction confidence
        - Stock volatility
        """
        # Base position size (Kelly-like formula)
        risk_amount = self.current_capital * self.risk_per_trade
        
        # Adjust by confidence (higher confidence = larger position)
        confidence_multiplier = (confidence - 0.5) * 2  # Scale 0.5-1.0 to 0-1
        confidence_multiplier = max(0.1, min(1.0, confidence_multiplier))
        
        risk_amount *= confidence_multiplier
        
        # Adjust by volatility (lower vol = larger position)
        vol_adjustment = 0.01 / max(volatility, 0.001)
        vol_adjustment = max(0.5, min(2.0, vol_adjustment))
        
        risk_amount *= vol_adjustment
        
        # Convert to shares
        position_size = int(risk_amount / price)
        
        # Cap at max position percentage
        max_shares = int((self.current_capital * self.max_position_pct) / price)
        position_size = min(position_size, max_shares)
        
        # Ensure minimum 1 share, if we can afford it
        if position_size < 1 and self.current_capital >= price:
            position_size = 1
        
        return max(0, position_size)
    
    def should_trade(self, symbol: str) -> Tuple[bool, str]:
        """Check if we should trade this symbol"""
        # Reset daily counter if new day
        if datetime.now().date() > self.last_reset_date:
            self.daily_trades = 0
            self.daily_pnl = 0.0
            self.last_reset_date = datetime.now().date()
        
        # Check daily trade limit
        if self.daily_trades >= self.max_daily_trades:
            return False, "Daily trade limit reached"
        
        # Check drawdown
        drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
        if drawdown >= self.max_drawdown_pct:
            return False, f"Max drawdown reached ({drawdown:.1%})"
        
        # Check max positions
        if len(self.positions) >= self.max_positions and symbol not in self.positions:
            return False, f"Max positions ({self.max_positions}) reached"
        
        return True, "OK"
    
    def execute_trade(self,
                     symbol: str,
                     action: str,
                     quantity: int,
                     price: float,
                     confidence: float = 0.0,
                     model_votes: str = "") -> TradeRecord:
        """
        Execute a trade and update portfolio
        """
        timestamp = datetime.now()
        pnl = 0.0
        
        if action == "BUY":
            # Open or add to long position
            cost = quantity * price
            
            if symbol in self.positions:
                pos = self.positions[symbol]
                # Average into existing position
                total_qty = pos.quantity + quantity
                avg_price = ((pos.quantity * pos.entry_price) + (quantity * price)) / total_qty
                pos.entry_price = avg_price
                pos.quantity = total_qty
            else:
                self.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=quantity,
                    entry_price=price,
                    current_price=price,
                    entry_time=timestamp
                )
            
            self.current_capital -= cost
            self.daily_trades += 1
            
        elif action == "SELL":
            # Close or reduce long position
            if symbol in self.positions:
                pos = self.positions[symbol]
                
                if quantity >= pos.quantity:
                    # Close entire position
                    pnl = (price - pos.entry_price) * pos.quantity
                    self.current_capital += pos.quantity * price
                    del self.positions[symbol]
                else:
                    # Partial close
                    pnl = (price - pos.entry_price) * quantity
                    pos.quantity -= quantity
                    self.current_capital += quantity * price
                
                self.current_capital += pnl
                self.daily_pnl += pnl
                self.total_trades += 1
                
                if pnl > 0:
                    self.winning_trades += 1
                else:
                    self.losing_trades += 1
        
        elif action == "SHORT":
            # Open short position
            if symbol in self.positions:
                pos = self.positions[symbol]
                pos.quantity -= quantity  # Negative for short
            else:
                self.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=-quantity,
                    entry_price=price,
                    current_price=price,
                    entry_time=timestamp
                )
            
            self.daily_trades += 1
            
        elif action == "COVER":
            # Close short position
            if symbol in self.positions:
                pos = self.positions[symbol]
                
                if pos.quantity < 0:
                    pnl = (pos.entry_price - price) * abs(pos.quantity)
                    self.current_capital += pnl
                    del self.positions[symbol]
                    
                    self.daily_pnl += pnl
                    self.total_trades += 1
                    
                    if pnl > 0:
                        self.winning_trades += 1
                    else:
                        self.losing_trades += 1
        
        # Check stop losses
        self._check_stop_losses()
        
        # Update peak capital
        self.peak_capital = max(self.peak_capital, self.current_capital)
        
        # Record trade
        trade = TradeRecord(
            timestamp=timestamp,
            symbol=symbol,
            action=action,
            quantity=quantity,
            price=price,
            pnl=pnl,
            confidence=confidence,
            model_votes=model_votes
        )
        self.trade_log.append(trade)
        
        # Update equity curve
        total_equity = self.current_capital + sum(p.market_value for p in self.positions.values())
        self.equity_curve.append((timestamp, total_equity))
        
        return trade
    
    def _check_stop_losses(self):
        """Check and execute stop losses for all positions"""
        symbols_to_close = []
        
        for symbol, pos in self.positions.items():
            if pos.quantity == 0:
                continue
            
            # Calculate stop loss level
            if pos.quantity > 0:  # Long position
                stop_price = pos.entry_price * (1 - self.stop_loss_pct)
                if pos.current_price <= stop_price:
                    symbols_to_close.append((symbol, 'SELL'))
            else:  # Short position
                stop_price = pos.entry_price * (1 + self.stop_loss_pct)
                if pos.current_price >= stop_price:
                    symbols_to_close.append((symbol, 'COVER'))
        
        # Execute stop losses
        for symbol, action in symbols_to_close:
            pos = self.positions[symbol]
            quantity = abs(pos.quantity)
            logger.warning(f"🛑 STOP LOSS: {symbol} {action} {quantity} @ {pos.current_price:.2f}")
            self.execute_trade(symbol, action, quantity, pos.current_price)
    
    def update_prices(self, price_data: Dict[str, float]):
        """Update current prices for all positions"""
        for symbol, price in price_data.items():
            if symbol in self.positions:
                self.positions[symbol].update_price(price)
    
    def get_portfolio_summary(self) -> Dict:
        """Get complete portfolio summary"""
        total_position_value = sum(p.market_value for p in self.positions.values())
        total_equity = self.current_capital + total_position_value
        total_pnl = total_equity - self.initial_capital
        return_pct = (total_pnl / self.initial_capital) * 100
        
        win_rate = self.winning_trades / max(self.total_trades, 1)
        drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
        
        return {
            'initial_capital': self.initial_capital,
            'current_capital': self.current_capital,
            'total_equity': total_equity,
            'total_pnl': total_pnl,
            'return_pct': return_pct,
            'open_positions': len(self.positions),
            'max_positions': self.max_positions,
            'daily_trades': self.daily_trades,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'daily_pnl': self.daily_pnl,
            'peak_capital': self.peak_capital,
            'drawdown': drawdown,
            'positions': {
                symbol: {
                    'quantity': pos.quantity,
                    'entry_price': pos.entry_price,
                    'current_price': pos.current_price,
                    'unrealized_pnl': pos.unrealized_pnl,
                    'pnl_pct': pos.pnl_pct
                }
                for symbol, pos in self.positions.items()
            }
        }
    
    def get_recommendations(self, signals: Dict[str, Dict]) -> List[Dict]:
        """
        Convert model signals to trade recommendations
        
        Args:
            signals: Dict of {symbol: {prediction, confidence, price, votes}}
        
        Returns:
            List of trade recommendations
        """
        recommendations = []
        
        for symbol, signal in signals.items():
            prediction = signal.get('prediction', 1)  # 0=DOWN, 1=UNCH, 2=UP
            confidence = signal.get('confidence', 0.0)
            price = signal.get('price', 0)
            votes = signal.get('votes', '')
            
            # Check if we should trade
            can_trade, reason = self.should_trade(symbol)
            
            if not can_trade:
                recommendations.append({
                    'symbol': symbol,
                    'action': 'HOLD',
                    'reason': reason,
                    'confidence': confidence
                })
                continue
            
            # Determine action based on prediction
            if prediction == 2 and confidence > 0.6:  # Strong UP
                quantity = self.calculate_position_size(price, confidence)
                
                if quantity > 0:
                    # If we have short position, cover it
                    if symbol in self.positions and self.positions[symbol].quantity < 0:
                        recommendations.append({
                            'symbol': symbol,
                            'action': 'COVER',
                            'quantity': abs(self.positions[symbol].quantity),
                            'price': price,
                            'confidence': confidence,
                            'votes': votes,
                            'reason': f'Strong UP signal ({confidence:.1%})'
                        })
                    
                    recommendations.append({
                        'symbol': symbol,
                        'action': 'BUY',
                        'quantity': quantity,
                        'price': price,
                        'confidence': confidence,
                        'votes': votes,
                        'reason': f'UP signal ({confidence:.1%})'
                    })
            
            elif prediction == 0 and confidence > 0.6:  # Strong DOWN
                if symbol in self.positions and self.positions[symbol].quantity > 0:
                    recommendations.append({
                        'symbol': symbol,
                        'action': 'SELL',
                        'quantity': self.positions[symbol].quantity,
                        'price': price,
                        'confidence': confidence,
                        'votes': votes,
                        'reason': f'DOWN signal ({confidence:.1%})'
                    })
                else:
                    # Consider shorting
                    quantity = self.calculate_position_size(price, confidence)
                    if quantity > 0 and len(self.positions) < self.max_positions:
                        recommendations.append({
                            'symbol': symbol,
                            'action': 'SHORT',
                            'quantity': quantity,
                            'price': price,
                            'confidence': confidence,
                            'votes': votes,
                            'reason': f'Strong DOWN signal ({confidence:.1%})'
                        })
            
            else:
                recommendations.append({
                    'symbol': symbol,
                    'action': 'HOLD',
                    'reason': f'Low confidence ({confidence:.1%}) or UNCH signal',
                    'confidence': confidence
                })
        
        return recommendations
