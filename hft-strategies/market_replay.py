"""
Market Replay Engine
Replays historical tick data through HFT tactic logic at configurable speeds.

Supports parquet files or synthetic tick data. Simulates DOM updates, computes
V_t (velocity), IR (imbalance ratio), DS (depth slope), checks tactic triggers,
and simulates fills. Prints per-tactic PnL, win rate, and total PnL summary.

Usage:
    python market_replay.py --symbol SBIN --date 2026-04-10 --speed 100
    python market_replay.py --symbol SBIN --parquet data/SBIN_ticks.parquet --speed 10
"""

import os
import sys
import argparse
import time
import json
import csv
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


# ========================================================================
# Constants
# ========================================================================
LOT_SIZE = 75  # NSE lot size
TICK_VALUE = 0.05  # SBIN tick size
TACTIC_NAMES = ["LES", "MP", "DPFL", "RCP", "SESO", "VTDL", "EODPL", "VRS"]

# ========================================================================
# Data models
# ========================================================================

@dataclass
class Tick:
    timestamp: datetime
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    trade_price: float
    trade_size: int
    trade_side: str  # "B", "A", "M"
    volume: int
    dom_levels: Optional[List[Tuple[float, int, float, int]]] = None
    # dom_levels: [(bid_price_l0, bid_size_l0, ask_price_l0, ask_size_l0), ...]


@dataclass
class Fill:
    tactic: str
    side: str
    price: float
    lots: int
    timestamp: datetime
    commission: float = 0.0
    pnl: float = 0.0


@dataclass
class TacticState:
    name: str
    active: bool = False
    position: int = 0  # lots, positive=long, negative=short
    avg_entry: float = 0.0
    entry_tick: int = 0  # track tick index for hold time calculation
    orders: List[dict] = field(default_factory=list)
    fills: List[Fill] = field(default_factory=list)
    realized_pnl: float = 0.0
    win_count: int = 0
    loss_count: int = 0
    total_trades: int = 0


# ========================================================================
# Synthetic Tick Data Generator
# ========================================================================

def generate_synthetic_ticks(
    symbol: str = "SBIN",
    date_str: str = "2026-04-10",
    n_ticks: int = 20000,
    seed: int = 42,
) -> List[Tick]:
    """Generate realistic synthetic tick data for one trading day."""
    np.random.seed(seed)

    base_price = 580.0 + np.random.uniform(-2, 2)
    vwap = base_price + np.random.uniform(-0.5, 0.5)

    start = datetime.strptime(f"{date_str} 09:15:00", "%Y-%m-%d %H:%M:%S")
    # 375 minutes of trading, spread over n_ticks
    interval_ms = int(375 * 60 * 1000 / n_ticks)

    # Price path: mean-reverting with momentum bursts
    returns = np.random.randn(n_ticks) * 0.008
    price_path = np.cumsum(returns)
    price_path = price_path - np.mean(price_path)  # center
    # Mean reversion
    for i in range(1, n_ticks):
        price_path[i] += 0.002 * (-price_path[i - 1])

    prices = base_price + price_path
    prices = np.clip(prices, base_price - 3, base_price + 3)

    # Spread varies with distance from vwap
    spreads = np.clip(
        0.03 + np.abs(prices - vwap) * 0.02 + np.random.exponential(0.005, n_ticks),
        0.01, 0.10,
    )

    half_spread = spreads / 2
    bids = np.round(prices - half_spread, 2)
    asks = np.round(prices + half_spread, 2)

    # DOM levels at each tick
    dom_levels_all = []
    for i in range(n_ticks):
        levels = []
        for l in range(5):
            bp = np.round(bids[i] - l * TICK_VALUE, 2)
            ap = np.round(asks[i] + l * TICK_VALUE, 2)
            bs = int(np.clip(np.random.poisson(200 + 100 * (5 - l)), 20, 2000))
            als = int(np.clip(np.random.poisson(200 + 100 * (5 - l)), 20, 2000))
            levels.append((bp, bs, ap, als))
        dom_levels_all.append(levels)

    ticks = []
    for i in range(n_ticks):
        ts = start + timedelta(milliseconds=i * interval_ms)
        side = np.random.choice(["B", "A", "M"], p=[0.45, 0.45, 0.10])
        tp = np.round(prices[i] + np.random.randn() * 0.003, 2)
        ts_ = int(np.clip(np.random.exponential(30), 1, 500))
        vol = int(np.random.poisson(2000))

        ticks.append(Tick(
            timestamp=ts,
            bid=bids[i],
            ask=asks[i],
            bid_size=int(np.clip(np.random.poisson(400), 50, 3000)),
            ask_size=int(np.clip(np.random.poisson(400), 50, 3000)),
            trade_price=tp,
            trade_size=ts_,
            trade_side=side,
            volume=vol,
            dom_levels=dom_levels_all[i],
        ))

    return ticks


# ========================================================================
# Market Replay Engine
# ========================================================================

class MarketReplayEngine:
    """
    Replays tick data through tactic logic, simulating fills and tracking PnL.
    """

    def __init__(
        self,
        symbol: str = "SBIN",
        capital: float = 1_000_000.0,
        tick_data: Optional[List[Tick]] = None,
        tactics: Optional[List[str]] = None,
        commission_per_lot: float = 4.0,
        slippage_ticks: float = 0.5,
    ):
        self.symbol = symbol
        self.capital = capital
        self.initial_capital = capital
        self.tick_data = tick_data or []
        self.commission_per_lot = commission_per_lot
        self.slippage_ticks = slippage_ticks

        self.tactics = {name: TacticState(name=name) for name in (tactics or TACTIC_NAMES)}
        self.positions: Dict[str, int] = {}  # symbol -> net lots
        self.all_fills: List[Fill] = []

        # Market state
        self.dom: deque = deque(maxlen=1000)  # last 1000 ticks for DOM analysis
        self.price_history: deque = deque(maxlen=5000)
        self.volume_history: deque = deque(maxlen=1200)  # ~60s of 50ms ticks
        self.current_tick_idx = 0

        # Computed indicators
        self.vt = 0.0  # velocity
        self.ir = 0.0  # imbalance ratio
        self.ds = 0.0  # depth slope
        self.cvi = 1.0  # composite volatility index
        self.vwap: Optional[float] = None  # session VWAP
        self.pin_level: Optional[float] = None  # EOD pin level

        # History for tactics (needed for IR/VT confirmation)
        self.ir_history: deque = deque(maxlen=10)
        self.vt_history: deque = deque(maxlen=20)

        # Timing
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Indicator computation
    # ------------------------------------------------------------------

    def _compute_vt(self) -> float:
        """Velocity: trades per second weighted by size."""
        if len(self.dom) < 10:
            return 50.0
        recent = list(self.volume_history)[-60:]  # last ~3s
        if not recent:
            return 50.0
        return float(np.mean(recent)) / 3.0  # volume per second

    def _compute_ir(self) -> float:
        """Imbalance Ratio: bid_volume / ask_volume at top of book."""
        if len(self.dom) < 2:
            return 1.0
        tick = self.dom[-1]
        if tick.ask_size == 0:
            return 10.0
        return tick.bid_size / tick.ask_size

    def _compute_ds(self) -> float:
        """Depth Slope: ratio of depth at L0 vs L2."""
        if len(self.dom) < 1 or self.dom[-1].dom_levels is None:
            return 1.0
        levels = self.dom[-1].dom_levels
        if len(levels) < 3:
            return 1.0
        bid_l0 = levels[0][1]
        bid_l2 = levels[2][1] if len(levels) > 2 else bid_l0
        ask_l0 = levels[0][2]
        ask_l2 = levels[2][3] if len(levels) > 2 else ask_l0
        denom = (bid_l2 + ask_l2)
        if denom == 0:
            return 1.0
        return (bid_l0 + ask_l0) / denom

    def _compute_indicators(self, tick: Tick):
        self.dom.append(tick)
        self.price_history.append(tick.trade_price)
        self.volume_history.append(tick.volume)

        # VWAP tracking (use trade_price as proxy)
        if self.vwap is None:
            self.vwap = tick.trade_price
        else:
            # Rolling VWAP approximation
            self.vwap = self.vwap * 0.99 + tick.trade_price * 0.01

        # V_t: use trade_size directly (matches standalone backtests)
        self.vt_history.append(tick.trade_size)
        self.vt = sum(list(self.vt_history)[-4:])  # sum of last 4 trade sizes

        # IR
        self.ir = self._compute_ir()
        self.ir_history.append(self.ir)

        self.ds = self._compute_ds()
        # CVI: normalized rolling std
        if len(self.price_history) > 60:
            prices = list(self.price_history)[-60:]
            self.cvi = float(np.std(prices)) / max(np.mean(prices) * 0.001, 0.0001)
        else:
            self.cvi = 1.0

        # EOD pin level detection (set once, in last 18% of session)
        if self.pin_level is None:
            if len(self.price_history) >= 500:
                prices = np.array(list(self.price_history)[-500:])
                hist, bin_edges = np.histogram(prices, bins=100)
                mode_idx = np.argmax(hist)
                self.pin_level = (bin_edges[mode_idx] + bin_edges[mode_idx + 1]) / 2

    # ------------------------------------------------------------------
    # Tactic trigger logic — Aligned with standalone backtests
    # All thresholds scaled for 5-second real data (V_t ~4000-12000)
    # ------------------------------------------------------------------

    def _check_les(self, ts: TacticState, tick: Tick) -> bool:
        """Ladder Entry Scalp: IR >= 1.15 for 3 ticks (mean reversion)"""
        if ts.active or ts.position > 0:
            return False
        if len(self.ir_history) < 3:
            return False
        return all(v >= 1.15 for v in list(self.ir_history)[-3:])

    def _check_mp(self, ts: TacticState, tick: Tick) -> bool:
        """Momentum Pyramid: V_t > 9000 AND IR >= 1.14"""
        if ts.active or ts.position > 0:
            return False
        return self.vt > 9000 and self.ir >= 1.14

    def _check_dpfl(self, ts: TacticState, tick: Tick) -> bool:
        """Dark Pool Footprint: large trade size >= 15000"""
        if ts.active:
            return False
        return tick.trade_size >= 15000

    def _check_rcp(self, ts: TacticState, tick: Tick) -> bool:
        """Range Capture: price oscillation in recent 80 ticks, width 5-18 ticks"""
        if ts.active or len(self.price_history) < 80:
            return False
        prices = list(self.price_history)[-80:]
        high = max(prices)
        low = min(prices)
        width_ticks = round((high - low) / 0.05)
        return 5 <= width_ticks <= 18

    def _check_seso(self, ts: TacticState, tick: Tick) -> bool:
        """Sweep Exhaustion: V_t drops to <= 50% of recent peak >= 10000"""
        if ts.active or ts.position > 0:
            return False
        if len(self.vt_history) < 15:
            return False
        recent = list(self.vt_history)[-15:]
        peak = max(recent[:10])
        current = recent[-1]
        if peak < 10000:
            return False
        return current / peak <= 0.50 and self.ir >= 1.25

    def _check_vtdl(self, ts: TacticState, tick: Tick) -> bool:
        """VWAP Divergence: price below VWAP, V_t in range, IR elevated"""
        if ts.active or ts.position > 0:
            return False
        if self.vwap is None:
            return False
        dev_bps = (self.vwap - tick.trade_price) / self.vwap * 10000
        return 5 <= dev_bps <= 25 and 4000 <= self.vt <= 30000 and self.ir >= 1.10

    def _check_eodpl(self, ts: TacticState, tick: Tick) -> bool:
        """End-of-Day Pin: last 18% of session, price within 18 bps of pin, V_t >= 6000"""
        if ts.active:
            return False
        if self.pin_level is None:
            return False
        hour = tick.timestamp.hour
        minute = tick.timestamp.minute
        # Only trigger in last 18% of session (approx 14:40 onwards for 15:30 close)
        if hour < 14 or (hour == 14 and minute < 40):
            return False
        dist_bps = (self.pin_level - tick.bid) / self.pin_level * 10000
        return 0 < dist_bps < 18 and self.vt >= 6000

    def _check_vrs(self, ts: TacticState, tick: Tick) -> bool:
        """Volatility Regime Sizing: DISABLED — meta-tactic, use individual tactics instead."""
        return False

    # ------------------------------------------------------------------
    # Fill simulation
    # ------------------------------------------------------------------

    def _simulate_fill(
        self,
        tactic: str,
        side: str,
        tick: Tick,
        lots: int,
    ) -> Fill:
        slippage = self.slippage_ticks * TICK_VALUE
        if side == "BUY":
            price = tick.ask + slippage
        else:
            price = tick.bid - slippage
        comm = lots * self.commission_per_lot
        return Fill(
            tactic=tactic,
            side=side,
            price=round(price, 2),
            lots=lots,
            timestamp=tick.timestamp,
            commission=comm,
        )

    def _execute_tactic(self, tactic: str, tick: Tick):
        ts = self.tactics[tactic]

        # ---- EXIT logic for active positions ----
        if ts.active and ts.position > 0:
            should_exit = False
            exit_reason = None

            if tactic == "LES":
                # Profit: +5 ticks, Stop: -5 ticks, Max hold: 18 ticks
                pnl_ticks = (tick.bid - ts.avg_entry) / 0.05
                hold_ticks = self.current_tick_idx - ts.entry_tick
                if pnl_ticks >= 5:
                    should_exit, exit_reason = True, "PROFIT"
                elif pnl_ticks <= -5:
                    should_exit, exit_reason = True, "STOP"
                elif hold_ticks >= 18:
                    should_exit, exit_reason = True, "TIMEOUT"

            elif tactic == "MP":
                # Profit: +4 ticks, Stop: -3 ticks, Max hold: 40 ticks
                pnl_ticks = (tick.bid - ts.avg_entry) / 0.05
                hold_ticks = self.current_tick_idx - ts.entry_tick
                if pnl_ticks >= 4:
                    should_exit, exit_reason = True, "PROFIT"
                elif pnl_ticks <= -3:
                    should_exit, exit_reason = True, "STOP"
                elif hold_ticks >= 40:
                    should_exit, exit_reason = True, "TIMEOUT"

            elif tactic == "RCP":
                # Range capture: exit at range high (buy) or low (sell)
                # Simple: take profit at 8 ticks, stop at -6 ticks
                pnl_ticks = (tick.bid - ts.avg_entry) / 0.05
                hold_ticks = self.current_tick_idx - ts.entry_tick
                if pnl_ticks >= 8:
                    should_exit, exit_reason = True, "TARGET"
                elif pnl_ticks <= -6:
                    should_exit, exit_reason = True, "STOP"
                elif hold_ticks >= 140:
                    should_exit, exit_reason = True, "TIMEOUT"

            elif tactic == "VTDL":
                # Profit: +6 ticks, Stop: -4 ticks, Max hold: 40 ticks
                pnl_ticks = (tick.bid - ts.avg_entry) / 0.05
                hold_ticks = self.current_tick_idx - ts.entry_tick
                if pnl_ticks >= 6:
                    should_exit, exit_reason = True, "PROFIT"
                elif pnl_ticks <= -4:
                    should_exit, exit_reason = True, "STOP"
                elif hold_ticks >= 40:
                    should_exit, exit_reason = True, "TIMEOUT"

            elif tactic == "EODPL":
                # Convergence exit: within 10 bps of pin, or timeout 50 ticks
                if self.pin_level is not None:
                    dist_bps = (self.pin_level - tick.bid) / self.pin_level * 10000
                    hold_ticks = self.current_tick_idx - ts.entry_tick
                    if abs(dist_bps) <= 10:
                        should_exit, exit_reason = True, "CONVERGENCE"
                    elif hold_ticks >= 50:
                        should_exit, exit_reason = True, "TIMEOUT"

            elif tactic == "DPFL":
                # Target: +5 ticks, Stop: -3 ticks, Max hold: 30 ticks
                pnl_ticks = (tick.bid - ts.avg_entry) / 0.05
                hold_ticks = self.current_tick_idx - ts.entry_tick
                if pnl_ticks >= 5:
                    should_exit, exit_reason = True, "TARGET"
                elif pnl_ticks <= -3:
                    should_exit, exit_reason = True, "STOP"
                elif hold_ticks >= 30:
                    should_exit, exit_reason = True, "TIMEOUT"

            elif tactic == "SESO":
                # Profit: +4 ticks, Stop: -5 ticks, Max hold: 10 ticks
                pnl_ticks = (tick.bid - ts.avg_entry) / 0.05
                hold_ticks = self.current_tick_idx - ts.entry_tick
                if pnl_ticks >= 4:
                    should_exit, exit_reason = True, "PROFIT"
                elif pnl_ticks <= -5:
                    should_exit, exit_reason = True, "STOP"
                elif hold_ticks >= 10:
                    should_exit, exit_reason = True, "TIMEOUT"

            # Execute exit
            if should_exit:
                fill = self._simulate_fill(tactic, "SELL", tick, ts.position)
                pnl = (fill.price - ts.avg_entry) * fill.lots * LOT_SIZE - fill.commission
                fill.pnl = pnl
                ts.realized_pnl += pnl
                ts.fills.append(fill)
                self.all_fills.append(fill)
                self.capital += (fill.price * fill.lots * LOT_SIZE) - fill.commission
                ts.total_trades += 1
                if pnl > 0:
                    ts.win_count += 1
                else:
                    ts.loss_count += 1
                ts.position = 0
                ts.active = False
                ts.avg_entry = 0.0
                ts.entry_tick = 0
                return

        # ---- ENTRY logic ----
        checkers = {
            "LES": self._check_les,
            "MP": self._check_mp,
            "DPFL": self._check_dpfl,
            "RCP": self._check_rcp,
            "VTDL": self._check_vtdl,
            "EODPL": self._check_eodpl,
            "SESO": self._check_seso,
            "VRS": self._check_vrs,
        }

        if tactic in checkers and checkers[tactic](ts, tick):
            # Lot sizes scaled for replay engine (LOT_SIZE=75, so use small multipliers)
            # Each "lot" in replay = 75 shares, so 1 lot costs ~₹75,000
            lot_map = {"LES": 2, "MP": 3, "DPFL": 2, "RCP": 2,
                       "VTDL": 2, "EODPL": 2, "SESO": 1, "VRS": 1}
            lots = lot_map.get(tactic, 1)

            fill = self._simulate_fill(tactic, "BUY", tick, lots)
            cost = fill.price * fill.lots * LOT_SIZE + fill.commission
            if cost > self.capital:
                return  # insufficient capital
            self.capital -= cost
            ts.active = True
            ts.position = fill.lots
            ts.avg_entry = fill.price
            ts.entry_tick = self.current_tick_idx  # Track entry tick for hold time
            ts.fills.append(fill)
            self.all_fills.append(fill)

    def _check_all_tactics(self, tick: Tick):
        for name in self.tactics:
            self._execute_tactic(name, tick)

    # ------------------------------------------------------------------
    # Replay loop
    # ------------------------------------------------------------------

    def replay(self, speed: float = 1.0):
        """Replay tick data at given speed multiplier. speed=1 is real-time."""
        if not self.tick_data:
            print("[WARN] No tick data loaded; generating synthetic data...")
            self.tick_data = generate_synthetic_ticks(self.symbol)

        self.start_time = self.tick_data[0].timestamp
        self.end_time = self.tick_data[-1].timestamp

        total = len(self.tick_data)
        print(f"{'='*70}")
        print(f"  MARKET REPLAY ENGINE  |  {self.symbol}  |  {total:,} ticks")
        print(f"  Period: {self.start_time.strftime('%H:%M:%S')} -> {self.end_time.strftime('%H:%M:%S')}")
        print(f"  Speed: {speed}x  |  Capital: Rs {self.initial_capital:,.0f}")
        print(f"{'='*70}")

        t0 = time.time()
        last_print = 0

        for i, tick in enumerate(self.tick_data):
            self.current_tick_idx = i
            self._compute_indicators(tick)
            self._check_all_tactics(tick)

            # Progress every 5%
            pct = (i + 1) / total * 100
            if pct - last_print >= 5:
                last_print = pct
                elapsed = time.time() - t0
                eta = elapsed / (i + 1) * (total - i - 1) if i > 0 else 0
                pos_pnl = sum(t.realized_pnl for t in self.tactics.values())
                print(f"  [{pct:5.1f}%] tick {i+1:,}/{total:,}  |  Vt={self.vt:6.1f}  "
                      f"IR={self.ir:5.2f}  |  PnL=Rs {pos_pnl:,.0f}  |  "
                      f"cap=Rs {self.capital:,.0f}  |  eta={eta:.0f}s")

            if speed == 1.0:
                # Real-time: sleep to match tick interval
                if i > 0:
                    dt = (tick.timestamp - self.tick_data[i - 1].timestamp).total_seconds()
                    if dt > 0:
                        time.sleep(dt)

        elapsed = time.time() - t0
        self._print_summary(elapsed)

    def replay_with_hotkey_simulation(self, speed: float = 100.0):
        """100x speed replay, logging simulated hotkey presses."""
        if not self.tick_data:
            self.tick_data = generate_synthetic_ticks(self.symbol)

        self.start_time = self.tick_data[0].timestamp
        self.end_time = self.tick_data[-1].timestamp

        total = len(self.tick_data)
        print(f"{'='*70}")
        print(f"  MARKET REPLAY + HOTKEY SIMULATION  |  {self.symbol}")
        print(f"  Speed: {speed}x (hotkey log enabled)")
        print(f"{'='*70}")

        hotkey_log: List[dict] = []
        t0 = time.time()

        # Simulated hotkey press patterns
        hotkey_map = {
            "CTRL+B": "LES_BUY",
            "CTRL+E1": "SCALE_OUT",
            "CTRL+D1": "DPFL_FLATTEN",
            "F12": "EMERGENCY_FLATTEN",
        }

        for i, tick in enumerate(self.tick_data):
            self.current_tick_idx = i
            self._compute_indicators(tick)
            self._check_all_tactics(tick)

            # Simulate random hotkey presses every ~500 ticks
            if i > 0 and i % 500 == 0:
                import random
                hk = random.choice(list(hotkey_map.keys()))
                reaction_ms = random.gauss(350, 100)
                hotkey_log.append({
                    "tick": i,
                    "time": tick.timestamp.isoformat(),
                    "hotkey": hk,
                    "action": hotkey_map[hk],
                    "reaction_ms": round(reaction_ms, 1),
                    "vt": round(self.vt, 1),
                    "ir": round(self.ir, 2),
                })
                print(f"  [HOTKEY] tick {i:,}  {hk} -> {hotkey_map[hk]}  "
                      f"reaction={reaction_ms:.0f}ms  Vt={self.vt:.0f}")

            if speed < 1000:
                # At moderate speed, add tiny sleep
                time.sleep(0.00001)

        elapsed = time.time() - t0

        # Save hotkey log
        log_file = os.path.join(SCRIPT_DIR, f"hotkey_log_{self.symbol}.json")
        with open(log_file, "w") as f:
            json.dump(hotkey_log, f, indent=2)
        print(f"\n  Hotkey log saved to {log_file}")

        self._print_summary(elapsed)
        print(f"\n  Simulated {len(hotkey_log)} hotkey presses logged")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _print_summary(self, elapsed: float):
        print(f"\n{'='*70}")
        print(f"  REPLAY SUMMARY  |  {self.symbol}")
        print(f"  Duration: {elapsed:.1f}s  |  Ticks: {len(self.tick_data):,}")
        print(f"  Capital: Rs {self.initial_capital:,.0f} -> Rs {self.capital:,.0f}")
        print(f"{'='*70}")

        total_pnl = 0.0
        total_trades = 0
        total_wins = 0

        print(f"\n  {'Tactic':<8} {'Trades':>7} {'Wins':>6} {'Losses':>7} "
              f"{'Win%':>6} {'Realized PnL':>14} {'Position':>9}")
        print(f"  {'-'*70}")

        for name in TACTIC_NAMES:
            ts = self.tactics[name]
            total_pnl += ts.realized_pnl
            total_trades += ts.total_trades
            total_wins += ts.win_count
            wr = ts.win_count / ts.total_trades * 100 if ts.total_trades > 0 else 0.0
            pos_str = f"{ts.position}L" if ts.position > 0 else "flat"
            print(f"  {name:<8} {ts.total_trades:>7} {ts.win_count:>6} "
                  f"{ts.loss_count:>7} {wr:>5.1f}% "
                  f"Rs {ts.realized_pnl:>11,.0f}  {pos_str:>9}")

        print(f"  {'-'*70}")
        overall_wr = total_wins / total_trades * 100 if total_trades > 0 else 0.0
        print(f"  {'TOTAL':<8} {total_trades:>7} {total_wins:>6} "
              f"{total_trades - total_wins:>7} {overall_wr:>5.1f}% "
              f"Rs {total_pnl:>11,.0f}")
        print(f"{'='*70}")

        # Export fill log
        fill_file = os.path.join(SCRIPT_DIR, f"replay_fills_{self.symbol}.csv")
        with open(fill_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["tactic", "side", "price", "lots", "timestamp", "commission", "pnl"])
            for fill in self.all_fills:
                writer.writerow([
                    fill.tactic, fill.side, fill.price, fill.lots,
                    fill.timestamp.isoformat(), fill.commission, fill.pnl,
                ])
        print(f"\n  Fill log exported to {fill_file}")


# ========================================================================
# Parquet / Data loading
# ========================================================================

def load_tick_data_from_parquet(path: str) -> List[Tick]:
    """Load tick data from a parquet file."""
    try:
        import pandas as pd
    except ImportError:
        print("[ERROR] pandas required to load parquet. Install: pip install pandas pyarrow")
        return []

    df = pd.read_parquet(path)
    ticks = []
    for _, row in df.iterrows():
        dom_levels = None
        # If DOM columns exist, reconstruct
        cols = df.columns.tolist()
        if "bid_price_l0" in cols:
            levels = []
            for l in range(5):
                bp = row.get(f"bid_price_l{l}")
                bs = row.get(f"bid_size_l{l}")
                ap = row.get(f"ask_price_l{l}")
                als = row.get(f"ask_size_l{l}")
                if bp is not None and ap is not None:
                    levels.append((float(bp), int(bs), float(ap), int(als)))
            dom_levels = levels if levels else None

        ts = row.get("timestamp", row.get("time", None))
        if isinstance(ts, str):
            ts = pd.to_datetime(ts)

        ticks.append(Tick(
            timestamp=ts,
            bid=float(row.get("bid", 0)),
            ask=float(row.get("ask", 0)),
            bid_size=int(row.get("bid_size", row.get("bid_size_l0", 0))),
            ask_size=int(row.get("ask_size", row.get("ask_size_l0", 0))),
            trade_price=float(row.get("trade_price", row.get("close", 0))),
            trade_size=int(row.get("trade_size", 0)),
            trade_side=str(row.get("trade_side", "M")),
            volume=int(row.get("volume", 0)),
            dom_levels=dom_levels,
        ))

    print(f"  Loaded {len(ticks):,} ticks from parquet: {path}")
    return ticks


# ========================================================================
# CLI
# ========================================================================

def main():
    parser = argparse.ArgumentParser(description="HFT Market Replay Engine")
    parser.add_argument("--symbol", default="SBIN", help="Symbol to replay")
    parser.add_argument("--date", default="2026-04-10", help="Trading date (YYYY-MM-DD)")
    parser.add_argument("--parquet", default=None, help="Path to parquet tick data file")
    parser.add_argument("--speed", type=float, default=100.0, help="Replay speed multiplier")
    parser.add_argument("--hotkey", action="store_true", help="Enable hotkey simulation logging")
    parser.add_argument("--capital", type=float, default=1_000_000.0, help="Starting capital")
    parser.add_argument("--tactics", nargs="*", default=None, help="Tactics to enable (default: all 8)")
    args = parser.parse_args()

    # Load tick data
    tick_data: Optional[List[Tick]] = None
    if args.parquet:
        tick_data = load_tick_data_from_parquet(args.parquet)
        if not tick_data:
            print("[WARN] Parquet load failed; falling back to synthetic data")
            tick_data = None

    if tick_data is None:
        tick_data = generate_synthetic_ticks(symbol=args.symbol, date_str=args.date)

    engine = MarketReplayEngine(
        symbol=args.symbol,
        capital=args.capital,
        tick_data=tick_data,
        tactics=args.tactics,
    )

    if args.hotkey:
        engine.replay_with_hotkey_simulation(speed=args.speed)
    else:
        engine.replay(speed=args.speed)


if __name__ == "__main__":
    main()
