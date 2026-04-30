"""
LES (Ladder Entry Scalp) — Mean Reversion Strategy

Key insights from real data analysis:
- Data is at 5-second intervals (not 50ms HFT)
- Simple mean reversion with IR filter works best
- 1:1 R:R with moderate win rate is sustainable

Usage:
    python test_les_backtest.py
"""
import os, sys
import numpy as np
import pandas as pd
from collections import deque

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from realistic_data_generator import generate_realistic_lob_data

TICK_SIZE = 0.05
TICK_VALUE = 15.0
COMMISSION = 0.05
SLIPPAGE_BPS = 5


class LESBacktester:
    """Ladder Entry Scalp - Mean Reversion with IR filter."""

    LEVELS = 3
    LOT_SIZE = 15
    IR_ENTRY_MIN = 1.15
    IR_CONFIRM_TICKS = 3
    PROFIT_TARGET_TICKS = 7  # asymmetric 1.75:1 R:R
    STOP_LOSS_TICKS = 4      # tighter stop
    MAX_HOLD_TICKS = 14      # faster exits
    COOLDOWN_TICKS = 6       # avoid re-entry noise

    def __init__(self, data):
        self.data = data
        self.trades = []
        self.active = None
        self.counter = 0
        self.running_pnl = 0.0
        self.peak_pnl = 0.0
        self.max_drawdown = 0.0
        self.ir_history = deque(maxlen=10)
        self.last_exit_idx = -999

    def compute_ir(self, row):
        """Compute Imbalance Ratio."""
        bid_size = row.get("bid_size_l0", 500) + row.get("bid_size_l1", 300)
        ask_size = row.get("ask_size_l0", 500) + row.get("ask_size_l1", 300)
        if ask_size == 0:
            return 10.0
        return bid_size / ask_size

    def _arm(self, idx, ts, bid, ask):
        """Arm a new long position."""
        self.counter += 1
        self.active = {
            "id": f"LES_{self.counter:04d}",
            "entry_idx": idx,
            "entry_ts": ts,
            "entry_price": bid,
            "size": self.LOT_SIZE,
            "exit_reason": None,
        }

    def _exit(self, idx, ts, bid, ask, reason):
        """Exit the active position."""
        p = self.active
        if p is None:
            return

        entry = p["entry_price"]
        pnl_ticks = (bid - entry) / TICK_SIZE
        gross = pnl_ticks * p["size"] * TICK_VALUE
        comm = p["size"] * COMMISSION
        slip = p["size"] * bid * SLIPPAGE_BPS / 10000
        net = gross - comm - slip

        # Update running P&L and track max drawdown
        self.running_pnl += net
        self.peak_pnl = max(self.peak_pnl, self.running_pnl)
        drawdown = self.peak_pnl - self.running_pnl
        self.max_drawdown = max(self.max_drawdown, drawdown)

        self.trades.append({
            "id": p["id"],
            "entry_price": round(entry, 4),
            "exit_price": round(bid, 4),
            "size": p["size"],
            "gross_pnl": round(gross, 0),
            "net_pnl": round(net, 0),
            "exit_reason": reason,
            "hold_ticks": idx - p["entry_idx"],
        })
        self.active = None
        self.last_exit_idx = idx

    def run(self, verbose=False):
        print("=" * 80)
        print("  LES (Ladder Entry Scalp) — Mean Reversion with IR Filter")
        print("=" * 80)
        print(f"  Data points       : {len(self.data)}")
        print(f"  Entry trigger     : IR >= {self.IR_ENTRY_MIN} for {self.IR_CONFIRM_TICKS} ticks")
        print(f"  Profit target     : +{self.PROFIT_TARGET_TICKS} ticks")
        print(f"  Stop loss         : -{self.STOP_LOSS_TICKS} ticks")
        print(f"  Max hold          : {self.MAX_HOLD_TICKS} ticks")
        print("=" * 80)

        for idx, row in self.data.iterrows():
            ts = row["timestamp"]
            bid = row["bid"]
            ask = row["ask"]

            ir = self.compute_ir(row)
            self.ir_history.append(ir)

            # ---- No active position → try to enter on IR confirmation ----
            if self.active is None and idx > self.last_exit_idx + self.COOLDOWN_TICKS:
                # Check if IR has been elevated for last N ticks
                if len(self.ir_history) >= self.IR_CONFIRM_TICKS:
                    recent_ir = list(self.ir_history)[-self.IR_CONFIRM_TICKS:]
                    if all(ir_val >= self.IR_ENTRY_MIN for ir_val in recent_ir):
                        self._arm(idx, ts, bid, ask)
                        if verbose:
                            print(f"  [{ts}] ENTER  IR={ir:.2f} @ {bid:.2f}")
                        continue

            # ---- Active position → manage exits ----
            if self.active is not None:
                p = self.active
                entry = p["entry_price"]
                hold_ticks = idx - p["entry_idx"]

                # Profit target
                if bid >= entry + self.PROFIT_TARGET_TICKS * TICK_SIZE:
                    self._exit(idx, ts, bid, ask, "PROFIT_TARGET")
                    if verbose:
                        print(f"  [{ts}] EXIT PROFIT  entry={entry:.2f} bid={bid:.2f}")
                    continue

                # Stop loss
                if bid <= entry - self.STOP_LOSS_TICKS * TICK_SIZE:
                    self._exit(idx, ts, bid, ask, "STOP_LOSS")
                    if verbose:
                        print(f"  [{ts}] EXIT STOP  entry={entry:.2f} bid={bid:.2f}")
                    continue

                # Max hold time exit
                if hold_ticks >= self.MAX_HOLD_TICKS:
                    self._exit(idx, ts, bid, ask, "TIMEOUT")
                    if verbose:
                        print(f"  [{ts}] EXIT TIMEOUT  hold={hold_ticks}t")
                    continue

        # Force exit remaining
        if self.active is not None:
            last = self.data.iloc[-1]
            self._exit(len(self.data) - 1, last["timestamp"], last["bid"], last["ask"], "END_OF_DATA")

        self._print_summary()

    def _print_summary(self):
        if not self.trades:
            print("\n  No trades executed.")
            return

        n = len(self.trades)
        winners = [t for t in self.trades if t["net_pnl"] > 0]
        losers = [t for t in self.trades if t["net_pnl"] <= 0]
        total_pnl = sum(t["net_pnl"] for t in self.trades)
        avg_pnl = total_pnl / n if n > 0 else 0

        by_reason = {}
        for t in self.trades:
            r = t["exit_reason"]
            by_reason.setdefault(r, {"count": 0, "pnl": 0})
            by_reason[r]["count"] += 1
            by_reason[r]["pnl"] += t["net_pnl"]

        print("\n" + "=" * 80)
        print("  LES BACKTEST SUMMARY")
        print("=" * 80)
        print(f"  Total Trades      : {n}")
        print(f"  Winning Trades    : {len(winners)}")
        print(f"  Losing Trades     : {len(losers)}")
        print(f"  Win Rate          : {len(winners)/n*100:.1f}%")
        print(f"  Total Net P&L     : Rs {total_pnl:,.0f}")
        print(f"  Avg P&L / Trade   : Rs {avg_pnl:,.0f}")
        print(f"  Max Drawdown      : Rs {self.max_drawdown:,.0f}")
        print("-" * 80)
        print(f"  {'Reason':<18} {'Count':>6} {'Total P&L':>16}")
        print("-" * 80)
        for reason, stats in by_reason.items():
            print(f"  {reason:<18} {stats['count']:>6} Rs {stats['pnl']:>13,.0f}")
        print("=" * 80)


def main():
    import os
    real_data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'SBIN_real.parquet')
    if os.path.exists(real_data_path):
        print(f"Loading REAL SBIN data from {real_data_path}")
        data = pd.read_parquet(real_data_path)
        print(f"  Loaded {len(data):,} real ticks")
    else:
        print("Generating synthetic LOB data (real data not found)...")
        data = generate_realistic_lob_data(n_ticks=30000, seed=42)

    bt = LESBacktester(data)
    bt.run(verbose=False)

if __name__ == "__main__":
    main()
