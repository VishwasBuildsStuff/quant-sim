"""
HFT Paper Trade Optimizer v2.0
Realistic pricing with CORRECT slippage direction, R:R-aware targets,
trailing stops, Kelly position sizing, and regime-gated risk controls.
"""

from datetime import datetime
from typing import Dict, List, Optional
import numpy as np
import json

class TradeOptimizer:
    """
    Realistic constraints and EDGE-AWARE risk management for paper trading.
    Key fix: slippage is a COST already baked into price — we need edge > cost.
    """

    def __init__(self, slippage_bps: float = 3.0, commission_bps: float = 2.0):
        # NSE realistic costs: STT + exchange + brokerage ≈ 5-7 bps round-trip
        self.slippage_bps = slippage_bps        # 3 bps per leg
        self.commission_bps = commission_bps    # 2 bps per leg (NSE discount broker)
        self.total_cost_rt_bps = (slippage_bps + commission_bps) * 2  # ~10 bps round-trip

        # Risk limits — CONSERVATIVE defaults
        self.max_position_pct = 0.08    # 8% of capital per position
        self.daily_loss_limit = 0.015   # 1.5% daily hard stop
        self.stop_loss_pct = 0.015      # 1.5% per-trade stop
        self.take_profit_pct = 0.030    # 3.0% take-profit → 2:1 R:R minimum
        self.trailing_stop_pct = 0.010  # 1% trailing once +1% in profit

        # Position sizing: Kelly fraction (conservative ¼-Kelly)
        self.kelly_fraction = 0.25

        # Strategy-specific R:R targets (min reward:risk ratios required)
        self.strategy_min_rr = {
            'F1':  2.0,   # Scalp: tight, fast
            'F2':  2.5,   # Momentum: 2.5:1 minimum
            'F3':  2.0,   # Wall Fade
            'F4':  1.5,   # Rebate: mostly rebate, lower bar
            'F5':  3.0,   # Stop Hunt reversal: high conviction needed
            'F6':  2.0,   # Dark Pool follow
            'F7':  2.5,   # Sweep momentum
            'F8':  2.0,   # Auction Fade
            'F9':  2.5,   # News Fade: volatile, needs wider target
            'F10': 2.0,   # Iceberg Break
            'F11': 2.0,   # Queue Arb
            'F12': 2.5,   # VWAP Reversion
        }

        # Strategy-specific stop distances in bps
        # Calibration: sigma=0.00012 per tick
        # E[ticks to stop] = (stop_bps / 12)^2
        # F1 @ 50bps  →  (50/12)^2 = 17 min   F2 @ 60bps → 25 min
        self.strategy_stop_bps = {
            'F1':  50,   # Scalp: 50bps — survives ~17 min of noise
            'F2':  60,   # Momentum: slightly wider for continuation room
            'F3':  55,   # Wall Fade Short
            'F4':  50,   # Rebate
            'F5':  70,   # Stop Hunt: wide — counter-trend, needs room
            'F6':  55,   # Dark Pool
            'F7':  60,   # Sweep Momentum
            'F8':  55,   # Auction Fade
            'F9':  70,   # News Fade: volatile, widest stop
            'F10': 50,   # Iceberg Break
            'F11': 50,   # Queue Arb
            'F12': 60,   # VWAP Reversion
        }

        # Minimum momentum ticks required to confirm entry signal
        # (how many consecutive same-direction ticks in history before entry is valid)
        self.signal_confirm_ticks = {
            'F1':  2,   # Scalp: 2 ticks same direction
            'F2':  4,   # Momentum: stronger confirmation needed
            'F3':  3,   # Wall Fade
            'F4':  2,   # Rebate
            'F5':  3,   # Stop Hunt (reversal — check AGAINST direction)
            'F6':  3,   # Dark Pool
            'F7':  4,   # Sweep: needs strong momentum signal
            'F8':  2,   # Auction
            'F9':  3,   # News
            'F10': 3,   # Iceberg
            'F11': 2,   # Queue Arb
            'F12': 3,   # VWAP Rev (reversal — check AGAINST direction)
        }

        # Reversal strategies (enter AGAINST recent momentum — fade the move)
        self.reversal_strategies = {'F3', 'F5', 'F8', 'F9', 'F12'}

        # Performance tracking
        self.trade_journal: List[Dict] = []
        self.daily_pnl = 0.0
        self.peak_equity = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0

        # Trailing stop tracking: {symbol: highest_price_since_entry}
        self.trailing_highs: Dict[str, float] = {}
        self.trailing_lows: Dict[str, float] = {}

        # Strategy win-rate history for Kelly sizing (seeded with neutral 50%)
        self.strategy_stats: Dict[str, Dict] = {
            k: {'wins': 1, 'losses': 1} for k in self.strategy_min_rr
        }

    # ------------------------------------------------------------------
    # SIGNAL VALIDATION
    # ------------------------------------------------------------------

    def validate_entry(self, strategy_key: str, side: str,
                       price_history: list) -> tuple:
        """
        Check that recent price momentum CONFIRMS the entry direction.

        - Momentum strategies (F1,F2,F4,F6,F7,F10,F11): need N up-ticks for BUY.
        - Reversal strategies (F3,F5,F8,F9,F12): need N down-ticks before BUY
          (you're fading the drop), or N up-ticks before SELL (fading the rally).

        Returns: (is_valid: bool, message: str)
        """
        n = self.signal_confirm_ticks.get(strategy_key, 2)
        if len(price_history) < n + 1:
            return True, ""  # Not enough history — allow trade

        recent = [p['price'] for p in list(price_history)[-(n + 1):]]
        # Count consecutive direction
        is_uptrend = all(recent[i] <= recent[i+1] for i in range(len(recent)-1))
        is_downtrend = all(recent[i] >= recent[i+1] for i in range(len(recent)-1))

        is_reversal = strategy_key in self.reversal_strategies

        if not is_reversal:
            # Momentum strategy: price must be moving WITH the trade direction
            if side == 'BUY' and not is_uptrend:
                pct = (recent[-1] - recent[0]) / recent[0] * 100
                return False, (
                    f"[yellow]⚠ No momentum — price moved {pct:+.3f}% over last {n} ticks. "
                    f"Wait for {n} consecutive up-ticks before entering {strategy_key} BUY.[/yellow]"
                )
            if side == 'SELL' and not is_downtrend:
                pct = (recent[-1] - recent[0]) / recent[0] * 100
                return False, (
                    f"[yellow]⚠ No momentum — price moved {pct:+.3f}% over last {n} ticks. "
                    f"Wait for {n} consecutive down-ticks before entering {strategy_key} SELL.[/yellow]"
                )
        else:
            # Reversal strategy: price must have MOVED AGAINST trade direction first
            if side == 'BUY' and not is_downtrend:
                pct = (recent[-1] - recent[0]) / recent[0] * 100
                return False, (
                    f"[yellow]⚠ Reversal not ready — need {n} down-ticks to fade. "
                    f"Price moved {pct:+.3f}%. Wait for a sharp drop then fade it.[/yellow]"
                )
            if side == 'SELL' and not is_uptrend:
                pct = (recent[-1] - recent[0]) / recent[0] * 100
                return False, (
                    f"[yellow]⚠ Reversal not ready — need {n} up-ticks to fade. "
                    f"Price moved {pct:+.3f}%. Wait for a sharp rally then fade it.[/yellow]"
                )

        return True, ""


    # ------------------------------------------------------------------
    # PRICE & COST
    # ------------------------------------------------------------------

    def calculate_realistic_price(self, base_price: float, side: str,
                                   qty: int = 100) -> float:
        """
        Realistic fill price including:
        - Bid-ask spread crossing (always a cost)
        - Random slippage (uniform 0-slippage_bps)
        - Market impact (sqrt model, scaled by qty)
        """
        # Bid-ask half-spread: ~1 bps for liquid NSE large-caps
        half_spread = base_price * 0.0001

        # Random slippage component
        rand_slip = base_price * np.random.uniform(0, self.slippage_bps / 10000)

        # Square-root market impact: impact ∝ √(qty/ADV)
        # Approximate ADV for RELIANCE/TCS = 2M shares; scale accordingly
        adv_approx = 2_000_000
        impact = base_price * 0.002 * np.sqrt(qty / adv_approx)

        cost = half_spread + rand_slip + impact

        if side == 'BUY':
            return round(base_price + cost, 2)
        else:
            return round(base_price - cost, 2)

    def calculate_commission(self, notional: float) -> float:
        """
        NSE realistic charges per leg:
        STT (0.025%) + exchange (0.00345%) + brokerage (≈0.01%) + GST ≈ 0.04% per leg
        """
        return round(notional * (self.commission_bps / 10000), 2)

    def get_strategy_targets(self, entry_price: float, side: str,
                              strategy_key: str = 'F1') -> Dict:
        """
        Calculate entry, stop, and take-profit levels for a strategy.
        Returns all levels pre-computed so the trader sees exact levels.
        """
        stop_bps = self.strategy_stop_bps.get(strategy_key, 20)
        min_rr = self.strategy_min_rr.get(strategy_key, 2.0)

        stop_distance = entry_price * (stop_bps / 10000)
        target_distance = stop_distance * min_rr

        # Minimum edge: target must exceed round-trip cost
        min_edge_bps = self.total_cost_rt_bps * 1.5  # 50% buffer over cost
        min_target_distance = entry_price * (min_edge_bps / 10000)
        target_distance = max(target_distance, min_target_distance)

        if side == 'BUY':
            stop_price = round(entry_price - stop_distance, 2)
            target_price = round(entry_price + target_distance, 2)
        else:
            stop_price = round(entry_price + stop_distance, 2)
            target_price = round(entry_price - target_distance, 2)

        return {
            'entry': entry_price,
            'stop': stop_price,
            'target': target_price,
            'stop_bps': stop_bps,
            'rr_ratio': min_rr,
            'risk_per_share': stop_distance,
            'reward_per_share': target_distance,
        }

    # ------------------------------------------------------------------
    # POSITION SIZING
    # ------------------------------------------------------------------

    def calculate_position_size(self, capital: float, entry_price: float,
                                 stop_price: float, strategy_key: str = 'F1') -> int:
        """
        Kelly-fraction position sizing based on strategy win-rate history.
        Quantity = (Kelly% × capital) / risk_per_share
        Capped at max_position_pct of capital.
        """
        stats = self.strategy_stats.get(strategy_key, {'wins': 1, 'losses': 1})
        wins = stats['wins']
        losses = stats['losses']
        total = wins + losses
        win_rate = wins / total

        rr = self.strategy_min_rr.get(strategy_key, 2.0)
        # Full Kelly = win_rate - (1-win_rate)/rr
        full_kelly = win_rate - (1 - win_rate) / rr
        kelly_pct = max(0.01, full_kelly * self.kelly_fraction)  # floor at 1%

        risk_per_share = abs(entry_price - stop_price)
        if risk_per_share < 0.01:
            risk_per_share = entry_price * 0.002  # fallback: 0.2%

        # Capital at risk this trade
        capital_at_risk = capital * kelly_pct
        # Cap by max position size
        max_notional = capital * self.max_position_pct
        qty = int(min(capital_at_risk / risk_per_share,
                      max_notional / entry_price))
        return max(1, qty)

    # ------------------------------------------------------------------
    # RISK CONTROLS
    # ------------------------------------------------------------------

    def check_risk_limits(self, position_value: float, total_equity: float,
                          daily_pnl: float) -> Dict:
        """Check if trade violates risk limits."""
        alerts = []
        allowed = True

        if position_value > total_equity * self.max_position_pct:
            alerts.append(f"Position > {self.max_position_pct*100:.0f}% of equity — size down")
            allowed = False

        if daily_pnl < -total_equity * self.daily_loss_limit:
            alerts.append(f"Daily loss limit hit ({self.daily_loss_limit*100:.1f}%) — no new trades")
            allowed = False

        return {'allowed': allowed, 'alerts': alerts}

    def check_stop_loss(self, entry_price: float, current_price: float,
                         side: str, stop_price: Optional[float] = None) -> bool:
        """Check if stop loss triggered. Uses explicit stop_price if provided."""
        if stop_price is not None:
            if side == 'BUY':
                return current_price <= stop_price
            else:
                return current_price >= stop_price

        # Fallback to fixed % stop
        if side == 'BUY':
            return current_price <= entry_price * (1 - self.stop_loss_pct)
        else:
            return current_price >= entry_price * (1 + self.stop_loss_pct)

    def check_take_profit(self, entry_price: float, current_price: float,
                           side: str, target_price: Optional[float] = None) -> bool:
        """Check if take-profit level reached."""
        if target_price is not None:
            if side == 'BUY':
                return current_price >= target_price
            else:
                return current_price <= target_price

        if side == 'BUY':
            return current_price >= entry_price * (1 + self.take_profit_pct)
        else:
            return current_price <= entry_price * (1 - self.take_profit_pct)

    def update_trailing_stop(self, symbol: str, current_price: float,
                              side: str, entry_price: float) -> Optional[float]:
        """
        Trailing stop: activates once position is +1% in profit.
        Trails 1% behind the highest/lowest price reached.
        Returns updated stop price, or None if trailing not yet active.
        """
        if side == 'BUY':
            profit_pct = (current_price - entry_price) / entry_price
            if profit_pct >= 0.01:  # Activate trailing at +1%
                prev_high = self.trailing_highs.get(symbol, entry_price)
                new_high = max(prev_high, current_price)
                self.trailing_highs[symbol] = new_high
                trailing_stop = new_high * (1 - self.trailing_stop_pct)
                return round(trailing_stop, 2)
        else:
            profit_pct = (entry_price - current_price) / entry_price
            if profit_pct >= 0.01:
                prev_low = self.trailing_lows.get(symbol, entry_price)
                new_low = min(prev_low, current_price)
                self.trailing_lows[symbol] = new_low
                trailing_stop = new_low * (1 + self.trailing_stop_pct)
                return round(trailing_stop, 2)
        return None

    def clear_trailing(self, symbol: str):
        """Clear trailing stop state when position is closed."""
        self.trailing_highs.pop(symbol, None)
        self.trailing_lows.pop(symbol, None)

    # ------------------------------------------------------------------
    # TRADE JOURNAL & ANALYTICS
    # ------------------------------------------------------------------

    def log_trade(self, trade: Dict):
        """Add trade to journal; update strategy-specific win/loss stats."""
        self.trade_journal.append(trade)
        self.total_trades += 1

        pnl = trade.get('pnl', 0)
        strategy = trade.get('strategy', '')

        if pnl > 0:
            self.winning_trades += 1
            if strategy in self.strategy_stats:
                self.strategy_stats[strategy]['wins'] += 1
        elif pnl < 0:
            self.losing_trades += 1
            if strategy in self.strategy_stats:
                self.strategy_stats[strategy]['losses'] += 1

    def get_strategy_edge_report(self) -> str:
        """Human-readable edge report per strategy for dashboard."""
        lines = []
        for key, stats in self.strategy_stats.items():
            total = stats['wins'] + stats['losses']
            if total <= 2:
                continue
            wr = stats['wins'] / total
            rr = self.strategy_min_rr.get(key, 2.0)
            edge = wr * rr - (1 - wr)
            lines.append(f"  {key}: WR={wr:.0%}  Edge={edge:+.2f}")
        return "\n".join(lines) if lines else "  No strategy data yet"

    def get_performance_report(self) -> Dict:
        """Comprehensive performance report."""
        if not self.trade_journal:
            return {'message': 'No trades yet'}

        pnls = [t.get('pnl', 0) for t in self.trade_journal if 'pnl' in t]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        report = {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0,
            'total_pnl': sum(pnls),
            'avg_win': np.mean(wins) if wins else 0,
            'avg_loss': np.mean(losses) if losses else 0,
            'profit_factor': abs(sum(wins) / sum(losses)) if losses else float('inf'),
            'max_drawdown': min([0] + list(np.cumsum(pnls))),
            'sharpe_ratio': (np.mean(pnls) / np.std(pnls) * np.sqrt(252))
                            if len(pnls) > 1 and np.std(pnls) > 0 else 0,
            'recent_trades': self.trade_journal[-5:]
        }
        return report

    def save_journal(self, filepath: str = 'trade_journal.json'):
        """Save trade journal to file."""
        serializable = []
        for trade in self.trade_journal:
            t = trade.copy()
            if isinstance(t.get('time'), datetime):
                t['time'] = t['time'].strftime('%Y-%m-%d %H:%M:%S')
            serializable.append(t)
        with open(filepath, 'w') as f:
            json.dump(serializable, f, indent=2, default=str)
