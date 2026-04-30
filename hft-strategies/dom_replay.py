"""
DOM Replay Tool for Practicing Live DOM Reading
Replays tick data as a live DOM display in the terminal.
Renders 20-level DOM, accepts keyboard input for hotkey presses,
simulates fills, tracks PnL.

Usage:
    python dom_replay.py --symbol SBIN --speed 1x
    python dom_replay.py --parquet data/SBIN_ticks.parquet --speed 0.5x
"""

import os
import sys
import argparse
import time
import csv
import platform
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# ========================================================================
# Constants
# ========================================================================
LOT_SIZE = 75
TICK_VALUE = 0.05
FILL_LOG = os.path.join(SCRIPT_DIR, "dom_replay_fills.csv")

# Hotkey definitions
HOTKEYS = {
    "\x02": ("CTRL+B", "LES_BUY"),         # 0x02 = Ctrl+B
    "\x05": ("CTRL+E1", "SCALE_OUT"),       # We map this conceptually
    "\x04": ("CTRL+D1", "DPFL_FLATTEN"),    # 0x04 = Ctrl+D
    "\x1b": ("ESC", "EMERGENCY"),           # Escape key
}


# ========================================================================
# Tick data models
# ========================================================================

@dataclass
class DOMTick:
    timestamp: datetime
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    trade_price: float
    trade_size: int
    trade_side: str
    volume: int
    dom_levels: Optional[List[Tuple[float, int, float, int]]] = None


# ========================================================================
# Terminal Renderer
# ========================================================================

class TerminalRenderer:
    """Handles terminal DOM display with ANSI escape codes."""

    DOM_DEPTH = 20  # 20 levels
    HEADER_LINES = 6

    def __init__(self):
        self.is_windows = platform.system() == "Windows"

    def clear_screen(self):
        if self.is_windows:
            os.system("cls")
        else:
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

    def move_cursor(self, row, col=0):
        sys.stdout.write(f"\033[{row};{col}H")

    def render_dom(
        self,
        dom_levels: List[Tuple[float, int, float, int]],
        mid_price: float,
        vt: float,
        ir: float,
        ds: float,
        cvi: float,
        position: int,
        pnl: float,
        hotkey_pressed: Optional[str] = None,
        speed: str = "1x",
    ):
        """Render 20-level DOM to terminal."""
        self.clear_screen()

        # Header
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"{'='*72}")
        print(f"  DOM REPLAY TOOL  |  {now}  |  Speed: {speed}")
        print(f"  Vt={vt:7.1f}  IR={ir:5.2f}  DS={ds:4.2f}  CVI={cvi:.2f}  |  "
              f"Position: {position}L  |  PnL: Rs {pnl:,.0f}")
        if hotkey_pressed:
            print(f"  >>> HOTKEY: {hotkey_pressed} <<<")
        else:
            print(f"  Hotkeys: CTRL+B=Buy  CTRL+D=DPFL  ESC=Flatten")
        print(f"{'='*72}")

        # Column headers
        print(f"  {'Level':>5}  {'Bid Price':>10}  {'Bid Size':>10}  |  "
              f"{'Ask Size':>10}  {'Ask Price':>10}  {'Level':>5}")
        print(f"  {'-'*72}")

        max_size = 2000  # For bar scaling
        depth = min(self.DOM_DEPTH, len(dom_levels))

        for i in range(depth):
            bp, bs, ap, als = dom_levels[i]

            # Bar visualization
            bid_bar = "#" * min(int(bs / max_size * 30), 30)
            ask_bar = "#" * min(int(als / max_size * 30), 30)

            bid_str = f"{bp:10.2f}  {bs:6d} {bid_bar:<30}"
            ask_str = f"{als:6d}  {ap:10.2f}"

            print(f"  L{i:<3}  {bid_str}  |  {ask_str}  L{i:<3}")

        print(f"  {'-'*72}")
        print(f"  Mid: {mid_price:.2f}  |  Spread: {(dom_levels[0][2] - dom_levels[0][0]):.2f}"
              if dom_levels else "")
        print(f"{'='*72}")

    def render_summary(self, stats: dict):
        """Print final trading summary."""
        self.clear_screen()
        print(f"\n{'='*72}")
        print(f"  DOM REPLAY SUMMARY")
        print(f"{'='*72}")
        for key, val in stats.items():
            print(f"  {key}: {val}")
        print(f"{'='*72}")


# ========================================================================
# Keyboard Listener (cross-platform)
# ========================================================================

class KeyboardListener:
    """
    Non-blocking keyboard listener for hotkey detection.
    Falls back to polling if keyboard library is unavailable.
    """

    def __init__(self):
        self.last_hotkey: Optional[str] = None
        self.available = False
        self._hotkey_map = {}
        self._setup_hotkeys()

        # Try to import keyboard library for raw key detection
        try:
            import keyboard
            self.keyboard_lib = keyboard
            self.available = True
        except ImportError:
            self.keyboard_lib = None
            self.available = False

    def _setup_hotkeys(self):
        """Register hotkey callbacks."""
        if not self.available or not self.keyboard_lib:
            return
        try:
            self._hotkey_map = {
                "ctrl+b": "CTRL+B",
                "ctrl+e": "CTRL+E1",
                "ctrl+d": "CTRL+D1",
                "f12": "F12",
                "esc": "ESC",
            }
            for key, label in self._hotkey_map.items():
                self.keyboard_lib.add_hotkey(key, self._on_hotkey, args=(label,))
        except Exception:
            self.available = False

    def _on_hotkey(self, label: str):
        self.last_hotkey = label

    def get_hotkey(self) -> Optional[str]:
        """Return last hotkey pressed (cleared after read)."""
        hk = self.last_hotkey
        self.last_hotkey = None
        return hk

    def cleanup(self):
        if self.available and self.keyboard_lib:
            try:
                self.keyboard_lib.unhook_all()
            except Exception:
                pass


# ========================================================================
# Synthetic Data Generator
# ========================================================================

def generate_dom_ticks(
    symbol: str = "SBIN",
    n_ticks: int = 5000,
    seed: int = 42,
) -> List[DOMTick]:
    """Generate synthetic tick data for DOM replay."""
    np.random.seed(seed)

    base_price = 580.0 + np.random.uniform(-2, 2)
    vwap = base_price

    start = datetime.now().replace(hour=9, minute=15, second=0)
    interval_ms = int(375 * 60 * 1000 / n_ticks)

    returns = np.random.randn(n_ticks) * 0.008
    price_path = np.cumsum(returns)
    price_path = price_path - np.mean(price_path)
    for i in range(1, n_ticks):
        price_path[i] += 0.002 * (-price_path[i - 1])

    prices = base_price + price_path
    prices = np.clip(prices, base_price - 3, base_price + 3)

    spreads = np.clip(
        0.03 + np.abs(prices - vwap) * 0.02 + np.random.exponential(0.005, n_ticks),
        0.01, 0.10,
    )

    ticks = []
    for i in range(n_ticks):
        ts = start + int(interval_ms * 1000)
        spread = spreads[i]
        bid = round(prices[i] - spread / 2, 2)
        ask = round(prices[i] + spread / 2, 2)

        levels = []
        for l in range(20):
            bp = round(bid - l * TICK_VALUE, 2)
            ap = round(ask + l * TICK_VALUE, 2)
            bs = int(np.clip(np.random.poisson(200 + 100 * (20 - l)), 20, 3000))
            als = int(np.clip(np.random.poisson(200 + 100 * (20 - l)), 20, 3000))
            levels.append((bp, bs, ap, als))

        ticks.append(DOMTick(
            timestamp=ts,
            bid=bid,
            ask=ask,
            bid_size=int(np.clip(np.random.poisson(400), 50, 3000)),
            ask_size=int(np.clip(np.random.poisson(400), 50, 3000)),
            trade_price=round(prices[i] + np.random.randn() * 0.003, 2),
            trade_size=int(np.clip(np.random.exponential(30), 1, 500)),
            trade_side=np.random.choice(["B", "A", "M"], p=[0.45, 0.45, 0.10]),
            volume=int(np.random.poisson(2000)),
            dom_levels=levels,
        ))

    return ticks


# ========================================================================
# DOM Replayer
# ========================================================================

class DOMReplayer:
    """
    Replays tick data as a live DOM display.
    Accepts keyboard input for hotkey presses, simulates fills, tracks PnL.
    """

    def __init__(
        self,
        symbol: str = "SBIN",
        tick_data: Optional[List[DOMTick]] = None,
        capital: float = 1_000_000.0,
        commission_per_lot: float = 4.0,
        slippage_ticks: float = 0.5,
    ):
        self.symbol = symbol
        self.capital = capital
        self.initial_capital = capital
        self.tick_data = tick_data or generate_dom_ticks(symbol)
        self.commission_per_lot = commission_per_lot
        self.slippage_ticks = slippage_ticks

        self.renderer = TerminalRenderer()
        self.keyboard = KeyboardListener()

        # Market state
        self.price_history: deque = deque(maxlen=5000)
        self.volume_history: deque = deque(maxlen=1200)
        self.dom_history: deque = deque(maxlen=1000)

        # Trading state
        self.position: int = 0
        self.avg_entry: float = 0.0
        self.realized_pnl: float = 0.0
        self.unrealized_pnl: float = 0.0
        self.total_trades: int = 0
        self.wins: int = 0
        self.losses: int = 0

        # Indicator state
        self.vt = 50.0
        self.ir = 1.0
        self.ds = 1.0
        self.cvi = 1.0

        # Hotkey tracking
        self.hotkey_log: List[dict] = []
        self.last_hotkey: Optional[str] = None

        self.running = True

    def _compute_indicators(self, tick: DOMTick):
        self.price_history.append((tick.bid + tick.ask) / 2)
        self.volume_history.append(tick.volume)
        self.dom_history.append(tick)

        # Vt
        if len(self.volume_history) >= 10:
            recent = list(self.volume_history)[-60:]
            self.vt = float(np.mean(recent))

        # IR
        if tick.ask_size > 0:
            self.ir = tick.bid_size / tick.ask_size

        # DS
        if tick.dom_levels and len(tick.dom_levels) >= 3:
            l0 = tick.dom_levels[0]
            l2 = tick.dom_levels[2]
            denom = l2[1] + l2[3]
            self.ds = (l0[1] + l0[3]) / denom if denom > 0 else 1.0

        # CVI
        if len(self.price_history) >= 60:
            prices = list(self.price_history)[-60:]
            self.cvi = float(np.std(prices)) / max(np.mean(prices) * 0.001, 0.0001)

    def _simulate_fill(self, side: str, tick: DOMTick, lots: int):
        slippage = self.slippage_ticks * TICK_VALUE
        if side == "BUY":
            price = tick.ask + slippage
        else:
            price = tick.bid - slippage

        comm = lots * self.commission_per_lot

        if side == "BUY":
            cost = price * lots * LOT_SIZE + comm
            self.capital -= cost
            if self.position == 0:
                self.avg_entry = price
            else:
                total_cost = self.avg_entry * self.position * LOT_SIZE + price * lots * LOT_SIZE
                self.avg_entry = total_cost / ((self.position + lots) * LOT_SIZE)
            self.position += lots
        else:
            pnl = (price - self.avg_entry) * lots * LOT_SIZE - comm
            self.realized_pnl += pnl
            self.capital += price * lots * LOT_SIZE - comm
            self.position -= lots
            self.total_trades += 1
            if pnl > 0:
                self.wins += 1
            else:
                self.losses += 1

            if self.position == 0:
                self.avg_entry = 0.0

        # Log
        with open(FILL_LOG, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                tick.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                side, price, lots, comm,
                self.realized_pnl, self.position, self.capital,
            ])

        return pnl

    def _handle_hotkey(self, tick: DOMTick, hotkey: str):
        """Execute action based on hotkey press."""
        self.last_hotkey = hotkey
        self.hotkey_log.append({
            "time": tick.timestamp.isoformat(),
            "hotkey": hotkey,
            "price": tick.trade_price,
            "position": self.position,
            "pnl": self.realized_pnl,
        })

        if hotkey == "CTRL+B":
            # Buy 5 lots at market
            if self.position < 50:  # Max 50 lots
                self._simulate_fill("BUY", tick, 5)
        elif hotkey == "CTRL+E1":
            # Scale out: sell half
            if self.position > 0:
                lots = max(1, self.position // 2)
                self._simulate_fill("SELL", tick, lots)
        elif hotkey == "CTRL+D1":
            # DPFL flatten
            if self.position > 0:
                self._simulate_fill("SELL", tick, self.position)
        elif hotkey == "F12" or hotkey == "ESC":
            # Emergency flatten
            if self.position > 0:
                self._simulate_fill("SELL", tick, self.position)
                print(f"\n  [EMERGENCY FLATTEN] Position closed at {tick.bid:.2f}")

    def _check_auto_exit(self, tick: DOMTick):
        """Auto-exit if stop-loss hit."""
        if self.position > 0 and self.avg_entry > 0:
            pnl_per_lot = tick.bid - self.avg_entry
            if pnl_per_lot <= -0.15:  # 15 paisa stop loss
                self._simulate_fill("SELL", tick, self.position)

    def run(self, speed: str = "1x"):
        """
        Replay at 1x speed with keyboard input.

        Args:
            speed: "1x" (real-time), "0.5x" (half speed), "2x" (double), etc.
        """
        # Initialize fill log
        if not os.path.exists(FILL_LOG):
            with open(FILL_LOG, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "side", "price", "lots", "commission",
                                 "realized_pnl", "position", "capital"])

        total = len(self.tick_data)
        speed_map = {"0.5x": 0.5, "1x": 1.0, "2x": 2.0, "5x": 5.0, "10x": 10.0}
        speed_val = speed_map.get(speed, 1.0)

        print(f"{'='*72}")
        print(f"  DOM REPLAY  |  {self.symbol}  |  {total:,} ticks  |  Speed: {speed}")
        print(f"  Capital: Rs {self.initial_capital:,.0f}")
        print(f"  Press Ctrl+C to stop at any time")
        print(f"{'='*72}")
        time.sleep(2)

        base_delay = 0.05  # base inter-tick delay in seconds

        try:
            for i, tick in enumerate(self.tick_data):
                self._compute_indicators(tick)

                # Check for hotkey
                hk = self.keyboard.get_hotkey()
                if hk:
                    self._handle_hotkey(tick, hk)

                # Auto stop-loss check
                self._check_auto_exit(tick)

                # Render DOM every 10 ticks
                if i % 10 == 0 or hk:
                    mid = (tick.bid + tick.ask) / 2
                    self.unrealized_pnl = (mid - self.avg_entry) * self.position * LOT_SIZE if self.position > 0 else 0
                    self.renderer.render_dom(
                        dom_levels=tick.dom_levels or [],
                        mid_price=mid,
                        vt=self.vt,
                        ir=self.ir,
                        ds=self.ds,
                        cvi=self.cvi,
                        position=self.position,
                        pnl=self.realized_pnl + self.unrealized_pnl,
                        hotkey_pressed=hk,
                        speed=speed,
                    )

                # Progress
                if i % 500 == 0:
                    pct = (i + 1) / total * 100
                    print(f"\r  [{pct:5.1f}%] tick {i+1:,}/{total:,}  |  "
                          f"Pos: {self.position}L  |  PnL: Rs {self.realized_pnl:,.0f}", end="")

                delay = base_delay / speed_val
                if delay > 0:
                    time.sleep(delay)

        except KeyboardInterrupt:
            print("\n\n  [STOP] DOM replay ended by user")
        finally:
            self.keyboard.cleanup()
            self._print_summary()

    def _print_summary(self):
        total_pnl = self.realized_pnl
        wr = self.wins / self.total_trades * 100 if self.total_trades > 0 else 0

        self.renderer.render_summary({
            "Symbol": self.symbol,
            "Ticks Processed": len(self.tick_data),
            "Total Trades": self.total_trades,
            "Wins": self.wins,
            "Losses": self.losses,
            "Win Rate": f"{wr:.1f}%",
            "Realized PnL": f"Rs {total_pnl:,.0f}",
            "Capital": f"Rs {self.initial_capital:,.0f} -> Rs {self.capital:,.0f}",
            "Hotkey Presses": len(self.hotkey_log),
            "Fill Log": FILL_LOG,
        })


# ========================================================================
# Parquet Loader
# ========================================================================

def load_ticks_from_parquet(path: str) -> List[DOMTick]:
    """Load tick data from parquet for DOM replay."""
    try:
        import pandas as pd
    except ImportError:
        print("[ERROR] pandas required. Install: pip install pandas pyarrow")
        return []

    df = pd.read_parquet(path)
    ticks = []
    for _, row in df.iterrows():
        levels = []
        for l in range(20):
            bp = row.get(f"bid_price_l{l}")
            bs = row.get(f"bid_size_l{l}")
            ap = row.get(f"ask_price_l{l}")
            als = row.get(f"ask_size_l{l}")
            if bp is not None and ap is not None:
                levels.append((float(bp), int(bs), float(ap), int(als)))

        ts = row.get("timestamp", row.get("time"))
        if isinstance(ts, str):
            ts = pd.to_datetime(ts)

        ticks.append(DOMTick(
            timestamp=ts,
            bid=float(row.get("bid", 0)),
            ask=float(row.get("ask", 0)),
            bid_size=int(row.get("bid_size", 0)),
            ask_size=int(row.get("ask_size", 0)),
            trade_price=float(row.get("trade_price", row.get("close", 0))),
            trade_size=int(row.get("trade_size", 0)),
            trade_side=str(row.get("trade_side", "M")),
            volume=int(row.get("volume", 0)),
            dom_levels=levels if levels else None,
        ))

    print(f"  Loaded {len(ticks):,} ticks from parquet: {path}")
    return ticks


# ========================================================================
# CLI
# ========================================================================

def main():
    parser = argparse.ArgumentParser(description="DOM Replay Tool")
    parser.add_argument("--symbol", default="SBIN", help="Symbol to replay")
    parser.add_argument("--parquet", default=None, help="Path to parquet tick data")
    parser.add_argument("--speed", default="1x", choices=["0.5x", "1x", "2x", "5x", "10x"],
                        help="Replay speed")
    parser.add_argument("--capital", type=float, default=1_000_000.0, help="Starting capital")
    args = parser.parse_args()

    tick_data = None
    if args.parquet:
        tick_data = load_ticks_from_parquet(args.parquet)

    replayer = DOMReplayer(
        symbol=args.symbol,
        tick_data=tick_data,
        capital=args.capital,
    )

    replayer.run(speed=args.speed)


if __name__ == "__main__":
    main()
