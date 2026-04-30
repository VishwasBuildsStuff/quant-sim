"""
HFT Paper Trading Engine
Real-time paper trading for all 8 HFT tactics using synthetic DOM data.

Uses synthetic DOM derived from 1-second bid/ask data.
Implements triggers for: LES, MP, DPFL, RCP, SESO, VTDL, EODPL, VRS.
Logs to paper_trading_hft_log.csv, prints running PnL every 30 seconds.

Usage:
    python paper_trader_hft.py
    python paper_trader_hft.py --symbol SBIN --capital 1000000
"""

import os
import sys
import time
import csv
import argparse
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

LOG_FILE = os.path.join(SCRIPT_DIR, "paper_trading_hft_log.csv")

# ========================================================================
# Constants
# ========================================================================
LOT_SIZE = 75
TICK_VALUE = 0.05
TACTIC_NAMES = ["LES", "MP", "DPFL", "RCP", "SESO", "VTDL", "EODPL", "VRS"]

# ========================================================================
# Data Models
# ========================================================================

@dataclass
class DOMSnapshot:
    timestamp: datetime
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    levels: List[Tuple[float, int, float, int]] = field(default_factory=list)
    # (bid_price, bid_size, ask_price, ask_size) per level


@dataclass
class PaperFill:
    tactic: str
    side: str
    price: float
    lots: int
    timestamp: datetime
    commission: float = 0.0
    pnl: float = 0.0


@dataclass
class TacticPaperState:
    name: str
    active: bool = False
    position: int = 0
    avg_entry: float = 0.0
    fills: List[PaperFill] = field(default_factory=list)
    realized_pnl: float = 0.0
    win_count: int = 0
    loss_count: int = 0
    total_trades: int = 0
    peak_pnl: float = 0.0
    max_drawdown: float = 0.0


# ========================================================================
# Synthetic DOM Generator
# ========================================================================

class SyntheticDOMGenerator:
    """Generates realistic synthetic DOM ticks at 1-second intervals."""

    def __init__(self, symbol: str = "SBIN", base_price: float = 580.0, seed: int = 42):
        self.symbol = symbol
        self.base_price = base_price
        self.current_price = base_price
        self.vwap = base_price
        self.rng = np.random.RandomState(seed)
        self.tick_count = 0

    def next_tick(self) -> DOMSnapshot:
        """Generate next DOM snapshot."""
        self.tick_count += 1

        # Mean-reverting price with momentum
        momentum = 0.001 * (self.vwap - self.current_price)
        noise = self.rng.randn() * 0.01
        self.current_price += momentum + noise

        spread = np.clip(
            0.03 + abs(self.current_price - self.vwap) * 0.03 + self.rng.exponential(0.005),
            0.01, 0.10,
        )

        bid = round(self.current_price - spread / 2, 2)
        ask = round(self.current_price + spread / 2, 2)

        levels = []
        for l in range(5):
            bp = round(bid - l * TICK_VALUE, 2)
            ap = round(ask + l * TICK_VALUE, 2)
            bs = int(np.clip(self.rng.poisson(200 + 100 * (5 - l)), 20, 2000))
            als = int(np.clip(self.rng.poisson(200 + 100 * (5 - l)), 20, 2000))
            levels.append((bp, bs, ap, als))

        return DOMSnapshot(
            timestamp=datetime.now(),
            bid=bid,
            ask=ask,
            bid_size=int(np.clip(self.rng.poisson(400), 50, 3000)),
            ask_size=int(np.clip(self.rng.poisson(400), 50, 3000)),
            levels=levels,
        )


# ========================================================================
# Indicator Computer
# ========================================================================

class IndicatorComputer:
    """Computes real-time indicators from DOM stream."""

    def __init__(self, window_size: int = 1200):
        self.price_history: deque = deque(maxlen=window_size)
        self.volume_history: deque = deque(maxlen=window_size)
        self.dom_history: deque = deque(maxlen=1000)

    def update(self, dom: DOMSnapshot):
        self.price_history.append((dom.bid + dom.ask) / 2)
        self.volume_history.append(dom.bid_size + dom.ask_size)
        self.dom_history.append(dom)

    @property
    def vt(self) -> float:
        """Velocity: average volume per second."""
        if len(self.volume_history) < 10:
            return 50.0
        recent = list(self.volume_history)[-60:]
        return float(np.mean(recent))

    @property
    def ir(self) -> float:
        """Imbalance Ratio."""
        if len(self.dom_history) < 2:
            return 1.0
        dom = self.dom_history[-1]
        if dom.ask_size == 0:
            return 10.0
        return dom.bid_size / dom.ask_size

    @property
    def ds(self) -> float:
        """Depth Slope."""
        if len(self.dom_history) < 1:
            return 1.0
        dom = self.dom_history[-1]
        if not dom.levels or len(dom.levels) < 3:
            return 1.0
        bid_l0 = dom.levels[0][1]
        bid_l2 = dom.levels[2][1] if len(dom.levels) > 2 else bid_l0
        ask_l0 = dom.levels[0][2]
        ask_l2 = dom.levels[2][3] if len(dom.levels) > 2 else ask_l0
        denom = bid_l2 + ask_l2
        return (bid_l0 + ask_l0) / denom if denom > 0 else 1.0

    @property
    def cvi(self) -> float:
        """Composite Volatility Index."""
        if len(self.price_history) < 60:
            return 1.0
        prices = list(self.price_history)[-60:]
        return float(np.std(prices)) / max(np.mean(prices) * 0.001, 0.0001)

    @property
    def mid_price(self) -> float:
        if not self.price_history:
            return 0.0
        return self.price_history[-1]


# ========================================================================
# Tactic Trigger Engine
# ========================================================================

class TacticTriggerEngine:
    """Evaluates all 8 tactic triggers given current indicators."""

    @staticmethod
    def check_les(ic: IndicatorComputer, ts: TacticPaperState) -> bool:
        if ts.active or ts.position > 0:
            return False
        return ic.vt < 120 and ic.ir >= 1.2

    @staticmethod
    def check_mp(ic: IndicatorComputer, ts: TacticPaperState) -> bool:
        if ts.active or len(ic.price_history) < 20:
            return False
        prices = list(ic.price_history)[-20:]
        direction = prices[-1] - prices[0]
        return abs(direction) > 0.15 and ic.vt > 80

    @staticmethod
    def check_dpfl(ic: IndicatorComputer, ts: TacticPaperState) -> bool:
        if ts.active:
            return False
        if len(ic.dom_history) < 1:
            return False
        dom = ic.dom_history[-1]
        spread = dom.ask - dom.bid
        return spread > 0.06 and ic.vt < 60

    @staticmethod
    def check_rcp(ic: IndicatorComputer, ts: TacticPaperState) -> bool:
        if ts.active or len(ic.price_history) < 50:
            return False
        prices = list(ic.price_history)[-50:]
        rng = max(prices) - min(prices)
        return rng < 0.3 and ic.vt > 40 and ic.ir < 1.5

    @staticmethod
    def check_seso(ic: IndicatorComputer, ts: TacticPaperState) -> bool:
        if not ts.active or ts.position <= 0:
            return False
        pnl_per_lot = ic.mid_price - ts.avg_entry
        return pnl_per_lot >= 0.10 or pnl_per_lot <= -0.05

    @staticmethod
    def check_vtdl(ic: IndicatorComputer, ts: TacticPaperState) -> bool:
        if ts.active or ts.position > 0:
            return False
        return ic.vt > 150 and ic.ir > 2.0

    @staticmethod
    def check_eodpl(ic: IndicatorComputer, ts: TacticPaperState) -> bool:
        if ts.active:
            return False
        now = datetime.now()
        return (now.hour == 15 and now.minute >= 20) or now.hour >= 15

    @staticmethod
    def check_vrs(ic: IndicatorComputer, ts: TacticPaperState) -> bool:
        if ts.active or ts.position > 0:
            return False
        return ic.cvi > 2.0 and ic.vt > 100


# ========================================================================
# HFT Paper Trader
# ========================================================================

class HFTPaperTrader:
    """
    Paper trading engine for all 8 HFT tactics.
    Loops with 1-second updates, logs to CSV, prints PnL every 30 seconds.
    """

    TACTIC_SIZES = {
        "LES": 5, "MP": 5, "DPFL": 5, "RCP": 3,
        "VTDL": 5, "EODPL": 3, "VRS": 3, "SESO": 0,  # SESO is exit-only
    }

    def __init__(
        self,
        symbol: str = "SBIN",
        capital: float = 1_000_000.0,
        commission_per_lot: float = 4.0,
        slippage_ticks: float = 0.5,
        tactics: Optional[List[str]] = None,
    ):
        self.symbol = symbol
        self.capital = capital
        self.initial_capital = capital
        self.commission_per_lot = commission_per_lot
        self.slippage_ticks = slippage_ticks

        self.tactics: Dict[str, TacticPaperState] = {
            name: TacticPaperState(name=name)
            for name in (tactics or TACTIC_NAMES)
        }

        self.dom_gen = SyntheticDOMGenerator(symbol=symbol)
        self.indicators = IndicatorComputer()
        self.triggers = TacticTriggerEngine()

        self.all_fills: List[PaperFill] = []
        self.update_count = 0
        self.running = True

        # CSV log setup
        self._init_log()

    def _init_log(self):
        """Initialize CSV log file."""
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "tactic", "side", "price", "lots",
                    "commission", "pnl", "capital", "position", "avg_entry",
                    "vt", "ir", "ds", "cvi",
                ])
        print(f"  Log file: {LOG_FILE}")

    def _log_fill(self, fill: PaperFill, ts: TacticPaperState):
        """Append fill to CSV log."""
        with open(LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                fill.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                fill.tactic, fill.side, fill.price, fill.lots,
                fill.commission, fill.pnl,
                round(self.capital, 2), ts.position, ts.avg_entry,
                round(self.indicators.vt, 1),
                round(self.indicators.ir, 2),
                round(self.indicators.ds, 2),
                round(self.indicators.cvi, 2),
            ])

    def _simulate_fill(self, tactic: str, side: str, dom: DOMSnapshot, lots: int) -> PaperFill:
        slippage = self.slippage_ticks * TICK_VALUE
        if side == "BUY":
            price = dom.ask + slippage
        else:
            price = dom.bid - slippage
        comm = lots * self.commission_per_lot
        return PaperFill(
            tactic=tactic, side=side, price=round(price, 2),
            lots=lots, timestamp=dom.timestamp, commission=comm,
        )

    def _get_lot_size(self, tactic: str) -> int:
        if tactic == "VRS":
            return max(1, int(10 / self.indicators.cvi))
        return self.TACTIC_SIZES.get(tactic, 3)

    def _process_tactic(self, name: str, dom: DOMSnapshot):
        ts = self.tactics[name]

        # Exit check
        if ts.active and ts.position > 0:
            if self.triggers.check_seso(self.indicators, ts):
                lots = ts.position
                fill = self._simulate_fill(name, "SELL", dom, lots)
                pnl = (fill.price - ts.avg_entry) * fill.lots * LOT_SIZE - fill.commission
                fill.pnl = pnl
                ts.realized_pnl += pnl
                ts.fills.append(fill)
                self.all_fills.append(fill)
                self.capital += fill.price * fill.lots * LOT_SIZE - fill.commission
                ts.total_trades += 1
                if pnl > 0:
                    ts.win_count += 1
                else:
                    ts.loss_count += 1
                ts.position = 0
                ts.active = False
                ts.avg_entry = 0.0
                self._log_fill(fill, ts)
                return

        # Entry checks
        checkers = {
            "LES": self.triggers.check_les,
            "MP": self.triggers.check_mp,
            "DPFL": self.triggers.check_dpfl,
            "RCP": self.triggers.check_rcp,
            "VTDL": self.triggers.check_vtdl,
            "EODPL": self.triggers.check_eodpl,
            "VRS": self.triggers.check_vrs,
        }

        if name in checkers:
            checker = checkers[name]
            if checker(self.indicators, ts):
                lots = self._get_lot_size(name)
                fill = self._simulate_fill(name, "BUY", dom, lots)
                cost = fill.price * fill.lots * LOT_SIZE + fill.commission
                if cost > self.capital:
                    return
                self.capital -= cost
                ts.active = True
                ts.position = fill.lots
                ts.avg_entry = fill.price
                ts.fills.append(fill)
                self.all_fills.append(fill)
                self._log_fill(fill, ts)

    def _print_pnl(self):
        """Print running PnL summary."""
        total_pnl = sum(t.realized_pnl for t in self.tactics.values())
        total_trades = sum(t.total_trades for t in self.tactics.values())

        print(f"\n  {'='*60}")
        print(f"  PnL UPDATE  |  {self.symbol}  |  {datetime.now().strftime('%H:%M:%S')}")
        print(f"  Updates: {self.update_count:,}  |  Trades: {total_trades}")
        print(f"  Capital: Rs {self.capital:,.0f}  |  PnL: Rs {total_pnl:,.0f}")
        print(f"  {'Tactic':<8} {'Trades':>7} {'PnL':>14} {'Position':>9}")
        print(f"  {'-'*50}")

        for name in TACTIC_NAMES:
            ts = self.tactics[name]
            pos_str = f"{ts.position}L" if ts.position > 0 else "flat"
            print(f"  {name:<8} {ts.total_trades:>7} Rs {ts.realized_pnl:>11,.0f}  {pos_str:>9}")

        print(f"  {'='*60}")

    def run_session(self, max_updates: int = 10000, update_interval: float = 1.0):
        """
        Main session loop: 1-second updates, PnL every 30 seconds.

        Args:
            max_updates: Maximum number of loop iterations (0 = unlimited)
            update_interval: Seconds between updates (default 1.0 for 1-second)
        """
        print(f"{'='*60}")
        print(f"  HFT PAPER TRADING  |  {self.symbol}")
        print(f"  Capital: Rs {self.initial_capital:,.0f}")
        print(f"  Update interval: {update_interval}s")
        print(f"{'='*60}")
        print(f"  Press Ctrl+C to stop.\n")

        last_pnl_print = 0
        try:
            while self.running and (max_updates == 0 or self.update_count < max_updates):
                self.update_count += 1
                dom = self.dom_gen.next_tick()
                self.indicators.update(dom)

                # Process all tactics
                for name in TACTIC_NAMES:
                    if name in self.tactics:
                        self._process_tactic(name, dom)

                # PnL print every 30 seconds (30 updates at 1s interval)
                if self.update_count - last_pnl_print >= 30:
                    self._print_pnl()
                    last_pnl_print = self.update_count

                time.sleep(update_interval)

        except KeyboardInterrupt:
            print("\n  [STOP] Paper trading session ended by user")

        self._print_final_summary()

    def _print_final_summary(self):
        total_pnl = sum(t.realized_pnl for t in self.tactics.values())
        total_trades = sum(t.total_trades for t in self.tactics.values())
        total_wins = sum(t.win_count for t in self.tactics.values())
        wr = total_wins / total_trades * 100 if total_trades > 0 else 0

        print(f"\n{'='*60}")
        print(f"  FINAL SUMMARY  |  {self.symbol}")
        print(f"  Updates: {self.update_count:,}  |  Trades: {total_trades}")
        print(f"  Win Rate: {wr:.1f}%  |  Total PnL: Rs {total_pnl:,.0f}")
        print(f"  Capital: Rs {self.initial_capital:,.0f} -> Rs {self.capital:,.0f}")
        print(f"{'='*60}")

        print(f"\n  {'Tactic':<8} {'Trades':>7} {'Wins':>6} {'Losses':>7} "
              f"{'Win%':>6} {'Realized PnL':>14}")
        print(f"  {'-'*55}")
        for name in TACTIC_NAMES:
            ts = self.tactics[name]
            t_wr = ts.win_count / ts.total_trades * 100 if ts.total_trades > 0 else 0
            print(f"  {name:<8} {ts.total_trades:>7} {ts.win_count:>6} "
                  f"{ts.loss_count:>7} {t_wr:>5.1f}% Rs {ts.realized_pnl:>11,.0f}")
        print(f"  {'-'*55}")
        print(f"  Log file: {LOG_FILE}")
        print(f"{'='*60}")


# ========================================================================
# CLI
# ========================================================================

def main():
    parser = argparse.ArgumentParser(description="HFT Paper Trading Engine")
    parser.add_argument("--symbol", default="SBIN", help="Symbol to trade")
    parser.add_argument("--capital", type=float, default=1_000_000.0, help="Starting capital")
    parser.add_argument("--max-updates", type=int, default=10000, help="Max loop iterations (0=unlimited)")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between updates")
    parser.add_argument("--tactics", nargs="*", default=None, help="Tactics to enable (default: all 8)")
    args = parser.parse_args()

    trader = HFTPaperTrader(
        symbol=args.symbol,
        capital=args.capital,
        tactics=args.tactics,
    )

    try:
        trader.run_session(max_updates=args.max_updates, update_interval=args.interval)
    except KeyboardInterrupt:
        print("\n  Paper trader stopped.")


if __name__ == "__main__":
    main()
