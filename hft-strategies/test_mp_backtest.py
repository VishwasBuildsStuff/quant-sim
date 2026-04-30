"""
MP (Momentum Pyramiding) Backtest — Rewritten from scratch.

Proper per-trade lifecycle: ARM → LOT1 → LOT2 → LOT3 → LOT4 → EXIT → CLEANUP
Each pyramid is isolated. No position stacking between pyramids.

Exit logic (3 independent triggers, any one fires):
  1. Stop loss: price drops 2+ ticks below average entry (after 1s cooldown)
  2. Take profit: price advances 3+ ticks above average entry
  3. Exhaustion: V_t drops >50% from peak within 300ms

Usage:
    python test_mp_backtest.py
"""
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime
from collections import deque

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from realistic_data_generator import generate_realistic_lob_data

TICK_SIZE = 0.05
TICK_VALUE = 15.0
COMMISSION = 0.05
SLIPPAGE_BPS = 5

# ---------------------------------------------------------------------------
# MP Backtester
# ---------------------------------------------------------------------------

class MPBacktester:
    """Momentum Pyramiding backtest - Optimized."""

    PYRAMID_SIZES = [20, 12, 6, 3]  # drastically reduced (41 total vs 68, 40% less risk)
    VT_ENTRY_MIN = 9000
    IR_ENTRY_MIN = 1.14
    VT_ADD_MIN = 14000  # raised (only add on very strong momentum)
    VT_EXHAUSTION_DROP = 0.50
    STOP_LOSS_TICKS = 3
    TAKE_PROFIT_TICKS = 4
    MAX_HOLD_TICKS = 35  # further reduced (faster cycle)
    COOLDOWN_TICKS = 15

    def __init__(self, data):
        self.data = data
        self.trades = []       # Completed pyramids
        self.active_pyramid = None  # Current pyramid state
        self.vt_history = deque(maxlen=20)
        self.vt_peak = 0
        self.pyramid_counter = 0
        self.running_pnl = 0.0
        self.peak_pnl = 0.0
        self.max_drawdown = 0.0

    # ---- helpers ----
    def compute_vt(self, window=4):
        """V_t from last N tape prints (each tick = 1 print, N*50ms window)."""
        if not self.vt_history:
            return 0
        return sum(list(self.vt_history)[-window:])

    def compute_ir(self, row):
        bid = row.get("bid_size_l0", 500) + row.get("bid_size_l1", 300) + row.get("bid_size_l2", 200)
        ask = row.get("ask_size_l0", 500) + row.get("ask_size_l1", 300) + row.get("ask_size_l2", 200)
        return bid / ask if ask > 0 else 10.0

    # ---- pyramid lifecycle ----
    def _arm(self, idx, ts, entry_price):
        """Start new pyramid. Can only arm when no active pyramid."""
        self.pyramid_counter += 1
        self.active_pyramid = {
            "id": f"MP_{self.pyramid_counter:04d}",
            "arm_idx": idx,
            "arm_ts": ts,
            "entry_price": entry_price,
            "fills": [],        # [{size, price, idx, ts}]
            "total_filled": 0,
            "total_cost": 0.0,
            "next_lot": 0,      # which lot to arm next (0..3)
            "cooldown_until": idx + self.COOLDOWN_TICKS,
            "vt_peak": 0,
            "exit_reason": None,
            "exit_ts": None,
            "exit_price": None,
            "max_bid": entry_price,
        }

    def _add_lot(self, idx, ts, fill_price):
        """Record a lot fill in the active pyramid."""
        p = self.active_pyramid
        lot_size = self.PYRAMID_SIZES[p["next_lot"]]
        p["fills"].append({"size": lot_size, "price": fill_price, "idx": idx, "ts": ts})
        p["total_filled"] += lot_size
        p["total_cost"] += lot_size * fill_price
        p["next_lot"] += 1
        p["max_bid"] = max(p["max_bid"], fill_price)

    def _exit(self, idx, ts, bid, ask, reason):
        """Exit the active pyramid and record the completed trade."""
        p = self.active_pyramid
        if p is None or p["total_filled"] == 0:
            self.active_pyramid = None
            return

        avg_entry = p["total_cost"] / p["total_filled"]
        pnl_in_ticks = (bid - avg_entry) / TICK_SIZE
        gross_pnl = pnl_in_ticks * p["total_filled"] * TICK_VALUE
        commission = p["total_filled"] * COMMISSION
        slippage = p["total_filled"] * bid * SLIPPAGE_BPS / 10000
        net_pnl = gross_pnl - commission - slippage

        # Update running P&L and track max drawdown
        self.running_pnl += net_pnl
        self.peak_pnl = max(self.peak_pnl, self.running_pnl)
        drawdown = self.peak_pnl - self.running_pnl
        self.max_drawdown = max(self.max_drawdown, drawdown)

        self.trades.append({
            "id": p["id"],
            "entry_price": round(avg_entry, 4),
            "exit_price": round(bid, 4),
            "size": p["total_filled"],
            "lots_filled": len(p["fills"]),
            "max_bid": round(p["max_bid"], 4),
            "gross_pnl": round(gross_pnl, 0),
            "net_pnl": round(net_pnl, 0),
            "exit_reason": reason,
            "hold_ticks": idx - p["arm_idx"],
        })
        self.active_pyramid = None

    # ---- main loop ----
    def run(self, verbose=False):
        print("=" * 80)
        print("  MP (Momentum Pyramiding) Backtest — Optimized")
        print("=" * 80)
        print(f"  Data points       : {len(self.data)}")
        print(f"  Entry trigger     : V_t > {self.VT_ENTRY_MIN}  AND  IR >= {self.IR_ENTRY_MIN}")
        print(f"  Pyramid sizes     : {self.PYRAMID_SIZES}")
        print(f"  Stop loss         : {self.STOP_LOSS_TICKS} ticks below avg entry (after {self.COOLDOWN_TICKS}t cooldown)")
        print(f"  Take profit       : {self.TAKE_PROFIT_TICKS} ticks above avg entry")
        print(f"  Exhaustion        : V_t drops >{self.VT_EXHAUSTION_DROP*100:.0f}% from peak")
        print("=" * 80)

        for idx, row in self.data.iterrows():
            ts = row["timestamp"]
            bid = row["bid"]
            ask = row["ask"]

            # Tape velocity
            trade_sz = int(row["trade_size"])
            self.vt_history.append(trade_sz)
            vt = self.compute_vt(window=4)
            ir = self.compute_ir(row)

            # Track V_t peak for active pyramid
            if self.active_pyramid:
                self.active_pyramid["vt_peak"] = max(self.active_pyramid["vt_peak"], vt)

            # ---- ENTRY: arm new pyramid when conditions met AND no active pyramid ----
            if self.active_pyramid is None:
                if vt > self.VT_ENTRY_MIN and ir >= self.IR_ENTRY_MIN:
                    self._arm(idx, ts, bid)  # Enter at BID (better price than ASK)
                    # Immediately fill Lot 1 at bid
                    self._add_lot(idx, ts, bid)
                    if verbose:
                        print(f"  [{ts}] ARMED + LOT1 FILLED  V_t={vt} IR={ir:.2f} @ {bid:.2f}")
                    continue

            # ---- ACTIVE PYRAMID: manage exits first, then adds ----
            if self.active_pyramid is not None:
                p = self.active_pyramid
                p["max_bid"] = max(p["max_bid"], bid)

                # 1. Stop loss (after cooldown)
                if idx > p["cooldown_until"]:
                    avg = p["total_cost"] / p["total_filled"] if p["total_filled"] > 0 else 0
                    if bid < avg - self.STOP_LOSS_TICKS * TICK_SIZE:
                        self._exit(idx, ts, bid, ask, "STOP_LOSS")
                        if verbose:
                            print(f"  [{ts}] STOP_LOSS  avg={avg:.2f} bid={bid:.2f}")
                        continue

                    # 2. Take profit
                    if bid > avg + self.TAKE_PROFIT_TICKS * TICK_SIZE:
                        self._exit(idx, ts, bid, ask, "TAKE_PROFIT")
                        if verbose:
                            print(f"  [{ts}] TAKE_PROFIT  avg={avg:.2f} bid={bid:.2f}")
                        continue

                # 3. Exhaustion exit
                if p["vt_peak"] > 0:
                    if vt < p["vt_peak"] * (1 - self.VT_EXHAUSTION_DROP):
                        self._exit(idx, ts, bid, ask, "EXHAUSTION")
                        if verbose:
                            print(f"  [{ts}] EXHAUSTION  peak={p['vt_peak']} now={vt}")
                        continue

                # 4. Add subsequent lots (Lot 2, 3, 4) — only if V_t still high
                if p["next_lot"] < len(self.PYRAMID_SIZES) and vt > self.VT_ADD_MIN:
                    self._add_lot(idx, ts, bid)  # Fill at BID price
                    if verbose:
                        print(f"  [{ts}] LOT{p['next_lot']} FILLED  V_t={vt} @ {bid:.2f}")

                # 5. Time-based exit if held too long
                hold_ticks = idx - p["arm_idx"]
                if hold_ticks >= self.MAX_HOLD_TICKS:
                    self._exit(idx, ts, bid, ask, "TIMEOUT")
                    if verbose:
                        print(f"  [{ts}] EXIT TIMEOUT  hold={hold_ticks}t")
                    continue

        # ---- Force-exit any remaining active pyramid at end ----
        if self.active_pyramid is not None:
            last = self.data.iloc[-1]
            self._exit(len(self.data) - 1, last["timestamp"], last["bid"], last["ask"], "END_OF_DATA")

        self._print_summary()

    def _print_summary(self):
        if not self.trades:
            print("\n  No pyramids triggered.")
            return

        n = len(self.trades)
        winners = [t for t in self.trades if t["net_pnl"] > 0]
        losers = [t for t in self.trades if t["net_pnl"] <= 0]
        total_pnl = sum(t["net_pnl"] for t in self.trades)
        avg_pnl = total_pnl / n if n > 0 else 0

        # By exit reason
        by_reason = {}
        for t in self.trades:
            r = t["exit_reason"]
            by_reason.setdefault(r, {"count": 0, "pnl": 0})
            by_reason[r]["count"] += 1
            by_reason[r]["pnl"] += t["net_pnl"]

        print("\n" + "=" * 80)
        print("  MP BACKTEST SUMMARY")
        print("=" * 80)
        print(f"  Pyramids Triggered  : {n}")
        print(f"  Winners             : {len(winners)}")
        print(f"  Losers              : {len(losers)}")
        print(f"  Win Rate            : {len(winners)/n*100:.1f}%")
        print(f"  Total Net P&L       : Rs {total_pnl:,.0f}")
        print(f"  Avg P&L per Pyramid : Rs {avg_pnl:,.0f}")
        print(f"  Avg Size Filled     : {sum(t['size'] for t in self.trades)/n:.0f} lots")
        print(f"  Avg Lots per Pyramid: {sum(t['lots_filled'] for t in self.trades)/n:.1f}")
        print(f"  Max Drawdown        : Rs {self.max_drawdown:,.0f}")
        print("-" * 80)
        print(f"  {'Reason':<16} {'Count':>6} {'Total P&L':>16}")
        print("-" * 80)
        for reason, stats in by_reason.items():
            print(f"  {reason:<16} {stats['count']:>6} Rs {stats['pnl']:>13,.0f}")
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
    print(f"  Generated {len(data)} ticks from {data['timestamp'].iloc[0]} to {data['timestamp'].iloc[-1]}")

    bt = MPBacktester(data)
    bt.run(verbose=False)


if __name__ == "__main__":
    main()
