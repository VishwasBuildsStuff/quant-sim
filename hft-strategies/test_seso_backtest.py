"""
SESO (Sweep Exhaustion Scale-Out) Backtest Script

REDESIGNED for 5-second interval data:
- Detects volume exhaustion (high volume spike followed by sharp drop)
- Enter on exhaustion confirmation (mean reversion)
- Simple profit target and stop loss management

Usage:
    python test_seso_backtest.py
"""

import os, sys
import numpy as np
import pandas as pd
from collections import deque

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
try:
    from realistic_data_generator import generate_realistic_lob_data
except ImportError:
    generate_realistic_lob_data = None


class SESOBacktester:
    """Sweep Exhaustion Scale-Out backtest - Redesigned."""

    TACTIC_NAME = "SESO"
    VT_LOOKBACK = 15
    VT_EXHAUST_RATIO = 0.50
    VT_PEAK_MIN = 10000
    IR_LONG_MIN = 1.25
    LOT_SIZE = 15
    PROFIT_TARGET_TICKS = 4
    STOP_LOSS_TICKS = 5
    MAX_HOLD_TICKS = 10
    TICK_SIZE = 0.05
    TICK_VALUE = 15.0
    COMMISSION = 0.05
    SLIPPAGE_BPS = 5

    def __init__(self, data: pd.DataFrame):
        self.data = data
        self.trades = []
        self.active = None
        self.counter = 0
        self.running_pnl = 0.0
        self.peak_pnl = 0.0
        self.max_drawdown = 0.0
        self.vt_history = deque(maxlen=20)

    def compute_vt(self):
        if not self.vt_history:
            return 0
        return sum(list(self.vt_history)[-4:])

    def _detect_exhaustion(self):
        if len(self.vt_history) < self.VT_LOOKBACK:
            return False, 0, 0
        recent = list(self.vt_history)[-self.VT_LOOKBACK:]
        first_part = recent[:10]
        current = recent[-1]
        if not first_part:
            return False, 0, 0
        peak = max(first_part)
        if peak < self.VT_PEAK_MIN:
            return False, peak, current
        drop_ratio = current / peak if peak > 0 else 1.0
        return drop_ratio <= self.VT_EXHAUST_RATIO, peak, current

    def _arm(self, idx, ts, bid, ask, direction, entry_price):
        self.counter += 1
        self.active = {
            "id": f"SESO_{self.counter:04d}", "entry_idx": idx, "entry_ts": ts,
            "direction": direction, "entry_price": entry_price, "size": self.LOT_SIZE,
        }

    def _exit(self, idx, ts, bid, ask, reason):
        p = self.active
        if p is None:
            return
        entry = p["entry_price"]
        if p["direction"] == "B":
            exit_price = bid
            pnl_ticks = (bid - entry) / self.TICK_SIZE
        else:
            exit_price = ask
            pnl_ticks = (entry - ask) / self.TICK_SIZE
        gross = pnl_ticks * p["size"] * self.TICK_VALUE
        comm = p["size"] * self.COMMISSION
        slip = p["size"] * entry * self.SLIPPAGE_BPS / 10000
        net = gross - comm - slip
        self.running_pnl += net
        self.peak_pnl = max(self.peak_pnl, self.running_pnl)
        drawdown = self.peak_pnl - self.running_pnl
        self.max_drawdown = max(self.max_drawdown, drawdown)
        self.trades.append({
            "id": p["id"], "entry_time": p["entry_ts"], "exit_time": ts,
            "direction": p["direction"], "entry_price": round(entry, 4),
            "exit_price": round(exit_price, 4), "size": p["size"],
            "gross_pnl": round(gross, 2), "net_pnl": round(net, 2),
            "exit_reason": reason, "hold_ticks": idx - p["entry_idx"],
        })
        self.active = None

    def run(self, verbose=False):
        print("=" * 80)
        print("  SESO (Sweep Exhaustion Scale-Out) Backtest - Redesigned")
        print("=" * 80)
        print(f"  Data points        : {len(self.data)}")
        print(f"  Exhaustion detect  : V_t drops to <= {self.VT_EXHAUST_RATIO*100:.0f}% of peak >= {self.VT_PEAK_MIN:,}")
        print(f"  IR LONG filter     : >= {self.IR_LONG_MIN}")
        print(f"  Profit target      : +{self.PROFIT_TARGET_TICKS} ticks")
        print(f"  Stop loss          : -{self.STOP_LOSS_TICKS} ticks")
        print(f"  Max hold           : {self.MAX_HOLD_TICKS} ticks")
        print("=" * 80)

        for idx, row in self.data.iterrows():
            ts = row["timestamp"]
            bid = row["bid"]
            ask = row["ask"]
            trade_size = int(row["trade_size"])
            self.vt_history.append(trade_size)
            v_t = self.compute_vt()
            is_exhaust, peak, current = self._detect_exhaustion()

            if is_exhaust and self.active is None:
                ir = row.get("bid_size_l0", 500) + row.get("bid_size_l1", 300)
                ir_denom = row.get("ask_size_l0", 500) + row.get("ask_size_l1", 300)
                ir = ir / ir_denom if ir_denom > 0 else 10.0
                if ir >= self.IR_LONG_MIN:
                    entry = bid
                    direction = "B"
                    self._arm(idx, ts, bid, ask, direction, entry)
                    if verbose:
                        print(f"  [{ts}] ENTER {direction}  V_t {peak:,.0f}→{current:,.0f}  IR={ir:.2f}  entry={entry:.2f}")

            if self.active is not None:
                p = self.active
                entry = p["entry_price"]
                hold_ticks = idx - p["entry_idx"]
                current_price = bid if p["direction"] == "B" else ask
                profit_target = entry + self.PROFIT_TARGET_TICKS * self.TICK_SIZE if p["direction"] == "B" else entry - self.PROFIT_TARGET_TICKS * self.TICK_SIZE
                if (p["direction"] == "B" and current_price >= profit_target) or \
                   (p["direction"] == "A" and current_price <= profit_target):
                    self._exit(idx, ts, bid, ask, "PROFIT_TARGET")
                    if verbose:
                        print(f"  [{ts}] EXIT PROFIT  entry={entry:.2f} exit={current_price:.2f}")
                    continue
                stop_loss = entry - self.STOP_LOSS_TICKS * self.TICK_SIZE if p["direction"] == "B" else entry + self.STOP_LOSS_TICKS * self.TICK_SIZE
                if (p["direction"] == "B" and current_price <= stop_loss) or \
                   (p["direction"] == "A" and current_price >= stop_loss):
                    self._exit(idx, ts, bid, ask, "STOP_LOSS")
                    if verbose:
                        print(f"  [{ts}] EXIT STOP  entry={entry:.2f} exit={current_price:.2f}")
                    continue
                if hold_ticks >= self.MAX_HOLD_TICKS:
                    self._exit(idx, ts, bid, ask, "TIME_EXPIRY")
                    if verbose:
                        print(f"  [{ts}] EXIT TIMEOUT  hold={hold_ticks}t")
                    continue

        if self.active is not None:
            last = self.data.iloc[-1]
            self._exit(len(self.data) - 1, last["timestamp"], last["bid"], last["ask"], "END_OF_DATA")

        self._print_summary()

    def _print_summary(self):
        print("\n" + "=" * 80)
        print("  SESO BACKTEST SUMMARY")
        print("=" * 80)
        if not self.trades:
            print("  No trades completed.")
            print("=" * 80)
            return
        total = len(self.trades)
        winners = [t for t in self.trades if t["net_pnl"] > 0]
        losers = [t for t in self.trades if t["net_pnl"] <= 0]
        total_pnl = sum(t["net_pnl"] for t in self.trades)
        avg_pnl = total_pnl / total if total > 0 else 0
        by_reason = {}
        for t in self.trades:
            r = t["exit_reason"]
            by_reason.setdefault(r, {"count": 0, "pnl": 0})
            by_reason[r]["count"] += 1
            by_reason[r]["pnl"] += t["net_pnl"]
        print(f"  Total Trades        : {total}")
        print(f"  Winning Trades      : {len(winners)}")
        print(f"  Losing Trades       : {len(losers)}")
        print(f"  Win Rate            : {len(winners)/total*100:.1f}%")
        print(f"  Total Net P&L       : Rs {total_pnl:,.0f}")
        print(f"  Avg P&L per Trade   : Rs {avg_pnl:,.0f}")
        print(f"  Max Drawdown        : Rs {self.max_drawdown:,.0f}")
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
        data = generate_realistic_lob_data(n_ticks=40000, seed=42)
    backtest = SESOBacktester(data)
    backtest.run(verbose=False)

if __name__ == "__main__":
    main()
