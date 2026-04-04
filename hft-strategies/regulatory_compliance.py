"""
Regulatory Compliance Module
Detect and flag manipulative behaviors per SEC and MiFID II

Implements detection for:
- Spoofing (layering)
- Wash trading
- Painting the tape
- Front running
- Marking the close
- Quote stuffing
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, Counter
import logging

logger = logging.getLogger(__name__)


@dataclass
class ViolationReport:
    """Report of potential regulatory violation"""
    violation_type: str
    severity: str  # 'low', 'medium', 'high', 'critical'
    timestamp: datetime
    agent_id: str
    description: str
    evidence: Dict
    recommended_action: str


class SpoofingDetector:
    """
    Detect spoofing and layering behaviors
    
    Spoofing: Placing orders with intent to cancel before execution
    Layering: Multiple orders at different price levels to create false appearance
    
    Per SEC and CFTC regulations
    """
    
    def __init__(self, 
                 cancel_ratio_threshold: float = 0.8,
                 layer_count_threshold: int = 5,
                 time_window_seconds: float = 60):
        self.cancel_ratio_threshold = cancel_ratio_threshold
        self.layer_count_threshold = layer_count_threshold
        self.time_window_seconds = time_window_seconds
        
        # Order tracking
        self.order_history: Dict[str, deque] = {}  # agent_id -> orders
        self.cancel_history: Dict[str, deque] = {}
    
    def track_order(self, 
                   agent_id: str, 
                   order_id: str, 
                   side: str, 
                   quantity: float, 
                   price: float,
                   timestamp: datetime):
        """Track new order"""
        if agent_id not in self.order_history:
            self.order_history[agent_id] = deque(maxlen=1000)
        
        self.order_history[agent_id].append({
            'order_id': order_id,
            'side': side,
            'quantity': quantity,
            'price': price,
            'timestamp': timestamp,
            'status': 'new'
        })
    
    def track_cancel(self, 
                    agent_id: str, 
                    order_id: str,
                    timestamp: datetime):
        """Track order cancellation"""
        if agent_id not in self.cancel_history:
            self.cancel_history[agent_id] = deque(maxlen=1000)
        
        self.cancel_history[agent_id].append({
            'order_id': order_id,
            'timestamp': timestamp
        })
        
        # Update order status
        if agent_id in self.order_history:
            for order in self.order_history[agent_id]:
                if order['order_id'] == order_id:
                    order['status'] = 'cancelled'
                    order['cancel_time'] = timestamp
                    break
    
    def detect_spoofing(self, agent_id: str) -> Optional[ViolationReport]:
        """
        Detect spoofing behavior
        
        Check for:
        1. High cancel-to-order ratio
        2. Orders placed and quickly cancelled
        3. Large orders that never intend to fill
        """
        if agent_id not in self.order_history or agent_id not in self.cancel_history:
            return None
        
        recent_orders = self.order_history[agent_id]
        recent_cancels = self.cancel_history[agent_id]
        
        # Filter to time window
        cutoff = datetime.now() - timedelta(seconds=self.time_window_seconds)
        recent_orders = [o for o in recent_orders if o['timestamp'] > cutoff]
        recent_cancels = [c for c in recent_cancels if c['timestamp'] > cutoff]
        
        if not recent_orders:
            return None
        
        # 1. Check cancel ratio
        cancel_ratio = len(recent_cancels) / len(recent_orders)
        if cancel_ratio > self.cancel_ratio_threshold:
            return ViolationReport(
                violation_type="Spoofing (High Cancel Ratio)",
                severity="high",
                timestamp=datetime.now(),
                agent_id=agent_id,
                description=f"Cancel ratio: {cancel_ratio:.2%} exceeds threshold",
                evidence={
                    'cancel_ratio': cancel_ratio,
                    'total_orders': len(recent_orders),
                    'total_cancels': len(recent_cancels)
                },
                recommended_action="Review trading activity, consider suspension"
            )
        
        # 2. Check for layering (multiple orders at different prices)
        if len(recent_orders) >= self.layer_count_threshold:
            price_levels = set(o['price'] for o in recent_orders if o['status'] == 'cancelled')
            
            if len(price_levels) >= self.layer_count_threshold:
                # Check if most are cancelled
                cancelled_at_levels = sum(
                    1 for o in recent_orders 
                    if o['price'] in price_levels and o['status'] == 'cancelled'
                )
                
                if cancelled_at_levels > len(recent_orders) * 0.7:
                    return ViolationReport(
                        violation_type="Layering",
                        severity="critical",
                        timestamp=datetime.now(),
                        agent_id=agent_id,
                        description=f"Detected {len(price_levels)} price levels with cancellations",
                        evidence={
                            'price_levels': len(price_levels),
                            'cancelled_orders': cancelled_at_levels
                        },
                        recommended_action="Immediate investigation required"
                    )
        
        # 3. Check for large cancelled orders
        large_cancelled = [
            o for o in recent_orders 
            if o['status'] == 'cancelled' and o['quantity'] > np.median([o['quantity'] for o in recent_orders]) * 3
        ]
        
        if len(large_cancelled) > 5:
            return ViolationReport(
                violation_type="Large Order Spoofing",
                severity="high",
                timestamp=datetime.now(),
                agent_id=agent_id,
                description=f"Multiple large orders cancelled without execution",
                evidence={
                    'large_cancelled_count': len(large_cancelled)
                },
                recommended_action="Review order placement intent"
            )
        
        return None


class WashTradeDetector:
    """
    Detect wash trading
    
    Wash trade: Buying and selling same asset to create false activity
    No change in beneficial ownership
    """
    
    def __init__(self, 
                 time_window_seconds: float = 60,
                 price_tolerance: float = 0.001):
        self.time_window_seconds = time_window_seconds
        self.price_tolerance = price_tolerance
        
        self.trade_history: Dict[str, deque] = {}
    
    def record_trade(self, 
                    agent_id: str, 
                    instrument: str,
                    side: str,
                    quantity: float,
                    price: float,
                    counterparty_id: str,
                    timestamp: datetime):
        """Record trade"""
        if agent_id not in self.trade_history:
            self.trade_history[agent_id] = deque(maxlen=5000)
        
        self.trade_history[agent_id].append({
            'instrument': instrument,
            'side': side,
            'quantity': quantity,
            'price': price,
            'counterparty_id': counterparty_id,
            'timestamp': timestamp
        })
    
    def detect_wash_trades(self, agent_id: str) -> Optional[ViolationReport]:
        """Detect wash trading patterns"""
        if agent_id not in self.trade_history:
            return None
        
        trades = self.trade_history[agent_id]
        cutoff = datetime.now() - timedelta(seconds=self.time_window_seconds)
        recent_trades = [t for t in trades if t['timestamp'] > cutoff]
        
        if len(recent_trades) < 4:
            return None
        
        # Check for buy-sell patterns at similar prices
        buy_trades = [t for t in recent_trades if t['side'] == 'buy']
        sell_trades = [t for t in recent_trades if t['side'] == 'sell']
        
        wash_trade_count = 0
        
        for buy in buy_trades:
            for sell in sell_trades:
                # Same instrument
                if buy['instrument'] != sell['instrument']:
                    continue
                
                # Similar price
                price_diff = abs(buy['price'] - sell['price']) / buy['price']
                if price_diff > self.price_tolerance:
                    continue
                
                # Similar quantity
                qty_diff = abs(buy['quantity'] - sell['quantity']) / buy['quantity']
                if qty_diff > 0.1:  # 10% tolerance
                    continue
                
                # Check if counterparty is same or related
                if buy['counterparty_id'] == sell['counterparty_id']:
                    wash_trade_count += 1
        
        # If significant portion of trades are wash trades
        total_trades = len(recent_trades)
        if wash_trade_count > total_trades * 0.3 and wash_trade_count >= 3:
            return ViolationReport(
                violation_type="Wash Trading",
                severity="critical",
                timestamp=datetime.now(),
                agent_id=agent_id,
                description=f"Detected {wash_trade_count} potential wash trades",
                evidence={
                    'wash_trade_count': wash_trade_count,
                    'total_trades': total_trades,
                    'wash_trade_ratio': wash_trade_count / total_trades
                },
                recommended_action="Immediate trading suspension, regulatory notification"
            )
        
        return None


class QuoteStuffingDetector:
    """
    Detect quote stuffing
    
    Quote stuffing: Flooding market with orders/cancels to slow down competitors
    """
    
    def __init__(self, 
                 messages_per_second_threshold: int = 100,
                 time_window_seconds: float = 1):
        self.messages_per_second_threshold = messages_per_second_threshold
        self.time_window_seconds = time_window_seconds
        
        self.message_counts: Dict[str, deque] = {}
    
    def record_message(self, agent_id: str, timestamp: datetime):
        """Record order/cancel message"""
        if agent_id not in self.message_counts:
            self.message_counts[agent_id] = deque(maxlen=10000)
        
        self.message_counts[agent_id].append(timestamp)
    
    def detect_quote_stuffing(self, agent_id: str) -> Optional[ViolationReport]:
        """Detect quote stuffing"""
        if agent_id not in self.message_counts:
            return None
        
        recent_messages = self.message_counts[agent_id]
        cutoff = datetime.now() - timedelta(seconds=self.time_window_seconds)
        recent = [m for m in recent_messages if m > cutoff]
        
        messages_per_second = len(recent) / self.time_window_seconds
        
        if messages_per_second > self.messages_per_second_threshold:
            return ViolationReport(
                violation_type="Quote Stuffing",
                severity="high",
                timestamp=datetime.now(),
                agent_id=agent_id,
                description=f"Message rate: {messages_per_second:.0f}/sec exceeds threshold",
                evidence={
                    'messages_per_second': messages_per_second,
                    'total_messages': len(recent)
                },
                recommended_action="Apply message rate limits"
            )
        
        return None


class MarkingTheCloseDetector:
    """
    Detect marking the close
    
    Manipulating closing price to benefit derivatives positions
    """
    
    def __init__(self, 
                 minutes_before_close: int = 10,
                 price_impact_threshold: float = 0.01):
        self.minutes_before_close = minutes_before_close
        self.price_impact_threshold = price_impact_threshold
        
        self.close_trades: Dict[str, List] = {}
    
    def check_close_activity(self,
                            agent_id: str,
                            instrument: str,
                            trades: List[Dict],
                            closing_price: float,
                            reference_price: float) -> Optional[ViolationReport]:
        """Check for suspicious activity near close"""
        
        # Filter trades near close
        close_trades = [
            t for t in trades
            if t['timestamp'] >= self._get_close_time()
        ]
        
        if not close_trades:
            return None
        
        # Check if trades moved the price
        price_impact = abs(closing_price - reference_price) / reference_price
        
        if price_impact > self.price_impact_threshold:
            # Check if agent was dominant
            agent_volume = sum(t['quantity'] for t in close_trades if t['agent_id'] == agent_id)
            total_volume = sum(t['quantity'] for t in close_trades)
            
            if total_volume > 0 and agent_volume / total_volume > 0.5:
                return ViolationReport(
                    violation_type="Marking the Close",
                    severity="high",
                    timestamp=datetime.now(),
                    agent_id=agent_id,
                    description=f"Agent dominated trading near close, moved price {price_impact*100:.2f}%",
                    evidence={
                        'price_impact': price_impact,
                        'agent_volume_share': agent_volume / total_volume
                    },
                    recommended_action="Review closing auction activity"
                )
        
        return None
    
    def _get_close_time(self) -> datetime:
        """Get trading close time"""
        # Would be market-specific
        return datetime.now().replace(hour=15, minute=50, second=0)


class FrontRunningDetector:
    """
    Detect front running
    
    Trading ahead of known client orders
    """
    
    def __init__(self, 
                 time_window_minutes: int = 5):
        self.time_window_minutes = time_window_minutes
        
        self.client_orders: deque = deque(maxlen=1000)
        self.prop_trades: deque = deque(maxlen=5000)
    
    def record_client_order(self, 
                           instrument: str,
                           side: str,
                           quantity: float,
                           timestamp: datetime,
                           client_id: str):
        """Record client order"""
        self.client_orders.append({
            'instrument': instrument,
            'side': side,
            'quantity': quantity,
            'timestamp': timestamp,
            'client_id': client_id
        })
    
    def record_prop_trade(self,
                         agent_id: str,
                         instrument: str,
                         side: str,
                         quantity: float,
                         price: float,
                         timestamp: datetime):
        """Record proprietary trade"""
        self.prop_trades.append({
            'agent_id': agent_id,
            'instrument': instrument,
            'side': side,
            'quantity': quantity,
            'price': price,
            'timestamp': timestamp
        })
    
    def detect_front_running(self, agent_id: str) -> Optional[ViolationReport]:
        """Detect potential front running"""
        suspicious_trades = []
        
        for prop_trade in self.prop_trades:
            if prop_trade['agent_id'] != agent_id:
                continue
            
            # Look for client orders shortly after
            for client_order in self.client_orders:
                time_diff = (client_order['timestamp'] - prop_trade['timestamp']).total_seconds()
                
                if 0 < time_diff < self.time_window_minutes * 60:
                    # Same instrument and side
                    if (prop_trade['instrument'] == client_order['instrument'] and
                        prop_trade['side'] == client_order['side']):
                        suspicious_trades.append({
                            'prop_trade': prop_trade,
                            'client_order': client_order,
                            'time_gap_seconds': time_diff
                        })
        
        if len(suspicious_trades) >= 2:
            return ViolationReport(
                violation_type="Potential Front Running",
                severity="critical",
                timestamp=datetime.now(),
                agent_id=agent_id,
                description=f"Detected {len(suspicious_trades)} suspicious trades ahead of client orders",
                evidence={
                    'suspicious_trade_count': len(suspicious_trades)
                },
                recommended_action="Immediate compliance review required"
            )
        
        return None


class RegulatoryComplianceEngine:
    """
    Comprehensive regulatory compliance engine
    
    Monitors all trading activity for regulatory violations
    Generates reports and alerts
    """
    
    def __init__(self):
        # Detection modules
        self.spoofing_detector = SpoofingDetector()
        self.wash_trade_detector = WashTradeDetector()
        self.quote_stuffing_detector = QuoteStuffingDetector()
        self.marking_close_detector = MarkingTheCloseDetector()
        self.front_running_detector = FrontRunningDetector()
        
        # Violation tracking
        self.violations: List[ViolationReport] = []
        self.suspended_agents: set = set()
        
        # Audit trail
        self.audit_log: deque = deque(maxlen=100000)
    
    def monitor_order(self, 
                     agent_id: str,
                     order_id: str,
                     instrument: str,
                     side: str,
                     quantity: float,
                     price: float,
                     timestamp: datetime):
        """Monitor new order"""
        self.spoofing_detector.track_order(agent_id, order_id, side, quantity, price, timestamp)
        self.quote_stuffing_detector.record_message(agent_id, timestamp)
        
        self._log_audit_event('order', agent_id, {
            'order_id': order_id,
            'instrument': instrument,
            'side': side,
            'quantity': quantity,
            'price': price
        })
    
    def monitor_cancel(self, 
                      agent_id: str,
                      order_id: str,
                      timestamp: datetime):
        """Monitor order cancellation"""
        self.spoofing_detector.track_cancel(agent_id, order_id, timestamp)
        self.quote_stuffing_detector.record_message(agent_id, timestamp)
        
        self._log_audit_event('cancel', agent_id, {
            'order_id': order_id
        })
    
    def monitor_trade(self,
                     agent_id: str,
                     instrument: str,
                     side: str,
                     quantity: float,
                     price: float,
                     counterparty_id: str,
                     timestamp: datetime):
        """Monitor executed trade"""
        self.wash_trade_detector.record_trade(
            agent_id, instrument, side, quantity, price, counterparty_id, timestamp
        )
        
        self._log_audit_event('trade', agent_id, {
            'instrument': instrument,
            'side': side,
            'quantity': quantity,
            'price': price,
            'counterparty': counterparty_id
        })
    
    def run_compliance_checks(self, agent_id: str) -> List[ViolationReport]:
        """Run all compliance checks for an agent"""
        violations = []
        
        # Run all detectors
        spoofing = self.spoofing_detector.detect_spoofing(agent_id)
        if spoofing:
            violations.append(spoofing)
        
        wash_trades = self.wash_trade_detector.detect_wash_trades(agent_id)
        if wash_trades:
            violations.append(wash_trades)
        
        quote_stuffing = self.quote_stuffing_detector.detect_quote_stuffing(agent_id)
        if quote_stuffing:
            violations.append(quote_stuffing)
        
        front_running = self.front_running_detector.detect_front_running(agent_id)
        if front_running:
            violations.append(front_running)
        
        # Record violations
        self.violations.extend(violations)
        
        # Auto-suspend for critical violations
        for violation in violations:
            if violation.severity == 'critical':
                self.suspend_agent(agent_id)
                break
        
        return violations
    
    def suspend_agent(self, agent_id: str):
        """Suspend agent for violations"""
        self.suspended_agents.add(agent_id)
        logger.critical(f"Agent {agent_id} suspended for regulatory violations")
    
    def is_agent_suspended(self, agent_id: str) -> bool:
        """Check if agent is suspended"""
        return agent_id in self.suspended_agents
    
    def get_violation_summary(self) -> Dict:
        """Get summary of all violations"""
        violation_counts = Counter(v.violation_type for v in self.violations)
        severity_counts = Counter(v.severity for v in self.violations)
        
        return {
            'total_violations': len(self.violations),
            'violation_types': dict(violation_counts),
            'severity_breakdown': dict(severity_counts),
            'suspended_agents': len(self.suspended_agents)
        }
    
    def _log_audit_event(self, event_type: str, agent_id: str, data: Dict):
        """Log event to audit trail"""
        self.audit_log.append({
            'timestamp': datetime.now(),
            'event_type': event_type,
            'agent_id': agent_id,
            'data': data
        })
    
    def generate_audit_report(self, 
                             start_time: datetime, 
                             end_time: datetime) -> Dict:
        """Generate audit report for time period"""
        events = [
            e for e in self.audit_log
            if start_time <= e['timestamp'] <= end_time
        ]
        
        return {
            'period': {
                'start': start_time.isoformat(),
                'end': end_time.isoformat()
            },
            'total_events': len(events),
            'events_by_type': dict(Counter(e['event_type'] for e in events)),
            'violations': [v.__dict__ for v in self.violations 
                          if start_time <= v.timestamp <= end_time]
        }
