"""
DPFL (Dark Pool Footprint Laddering) — Rewritten with pullback entry.

The old version entered AT block price which was already the top.
New version: detect block print → wait for pullback → enter at block price.
This captures the institutional footprint without buying the top.

Usage:
    python test_dpfl_backtest.py
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


class DPFLBacktester:
    """Dark Pool Footprint Laddering with pullback entry - Optimized."""

    # Block detection: trade_size >= threshold in a single tick
    BLOCK_THRESHOLD = 15000    # raised significantly (only largest blocks)
    FSS_MIN = 0.60             # raised from 0.55 (much more selective)

    # Pullback entry
    PULLBACK_WINDOW = 20       # reduced from 25
    PULLBACK_TICKS = 1         # reduced from 2 (tighter entry)

    # Ladder tiers
    TIER1_SIZE = 25            # back to original
    TIER2_SIZE = 15            # back to original

    # Exit: target 5 ticks, stop 3 ticks (original worked well)
    TARGET_TICKS = 5
    STOP_LOSS_TICKS = 3

    def __init__(self, data):
        self.data = data
        self.trades = []
        self.counter = 0
        self.active = None  # Active ladder state
        self.running_pnl = 0.0
        self.peak_pnl = 0.0
        self.max_drawdown = 0.0

        # Pending block state
        self.pending_block = None  # {idx, ts, block_price, fss, trade_side}

    def _compute_fss(self, block_size, ir, absorption):
        """Footprint Strength Score."""
        avg_block = 8000
        score = (min(block_size / avg_block, 2.0) / 2.0) * 0.30
        score += (min(ir, 3.0) / 3.0) * 0.25
        score += absorption * 0.25
        score += 0.20  # base score (block detected = signal)
        return score

    def _arm(self, idx, ts, block_price, fss, trade_side):
        """Arm ladder at block price after pullback confirmed."""
        self.counter += 1
        # T1 at block price, T2 1 tick below (averaging in on pullback)
        t1_price = round(block_price, 2)
        t2_price = round(block_price - TICK_SIZE, 2)

        self.active = {
            "id": f"DPFL_{self.counter:04d}",
            "arm_idx": idx,
            "arm_ts": ts,
            "block_price": block_price,
            "fss": fss,
            "trade_side": trade_side,
            "tiers": [
                {"price": t1_price, "size": self.TIER1_SIZE, "filled": 0, "fill_price": 0},
                {"price": t2_price, "size": self.TIER2_SIZE, "filled": 0, "fill_price": 0},
            ],
            "total_filled": 0,
            "total_cost": 0.0,
        }

    def _exit(self, idx, ts, bid, ask, reason):
        """Exit the active DPFL ladder."""
        p = self.active
        if p is None or p["total_filled"] == 0:
            self.active = None
            return

        avg = p["total_cost"] / p["total_filled"]
        # Always exit at BID (we're long, so BID is the sellable price)
        exit_price = bid

        pnl_ticks = (exit_price - avg) / TICK_SIZE
        gross = pnl_ticks * p["total_filled"] * TICK_VALUE
        comm = p["total_filled"] * COMMISSION
        slip = p["total_filled"] * exit_price * SLIPPAGE_BPS / 10000
        net = gross - comm - slip

        # Update running P&L and track max drawdown
        self.running_pnl += net
        self.peak_pnl = max(self.peak_pnl, self.running_pnl)
        drawdown = self.peak_pnl - self.running_pnl
        self.max_drawdown = max(self.max_drawdown, drawdown)

        tiers_filled = sum(1 for t in p["tiers"] if t["filled"] > 0)
        self.trades.append({
            "id": p["id"],
            "entry_avg": round(avg, 4),
            "exit_price": round(exit_price, 4),
            "size": p["total_filled"],
            "tiers_filled": tiers_filled,
            "block_price": round(p["block_price"], 4),
            "fss": round(p["fss"], 2),
            "gross_pnl": round(gross, 0),
            "net_pnl": round(net, 0),
            "exit_reason": reason,
            "hold_ticks": idx - p["arm_idx"],
        })
        self.active = None

    def run(self, verbose=False):
        print("=" * 80)
        print("  DPFL (Dark Pool Footprint Laddering) — Pullback Entry")
        print("=" * 80)
        print(f"  Data points       : {len(self.data)}")
        print(f"  Block threshold   : >= {self.BLOCK_THRESHOLD:,} lots")
        print(f"  FSS min           : >= {self.FSS_MIN}")
        print(f"  Pullback window   : <= {self.PULLBACK_WINDOW} ticks")
        print(f"  Ladder tiers      : T1={self.TIER1_SIZE} @ block, T2={self.TIER2_SIZE} @ block-1")
        print(f"  Target            : {self.TARGET_TICKS} ticks above avg entry")
        print(f"  Stop loss         : {self.STOP_LOSS_TICKS} ticks below avg entry")
        print("=" * 80)

        absorption_window = deque(maxlen=4)

        for idx, row in self.data.iterrows():
            ts = row["timestamp"]
            bid = row["bid"]
            ask = row["ask"]
            trade_size = int(row["trade_size"])
            trade_side = row["trade_side"]

            # Absorption: fraction of prints at ask (buying pressure)
            is_ask_lift = (trade_side == "A")
            absorption_window.append(1.0 if is_ask_lift else 0.0)
            absorption = sum(list(absorption_window)[-4:]) / 4 if len(absorption_window) >= 4 else 0.5

            # ---- Check pending block for pullback ----
            if self.pending_block is not None and self.active is None:
                pb = self.pending_block
                ticks_since = idx - pb["idx"]

                # Check if price pulled back to block price
                if pb["trade_side"] == "A":
                    # Ask lift (bullish block) → wait for price to come DOWN to block
                    dist_to_block = abs(bid - pb["block_price"]) / TICK_SIZE
                else:
                    # Bid hit (bearish block) → wait for price to come UP to block
                    dist_to_block = abs(ask - pb["block_price"]) / TICK_SIZE

                if dist_to_block <= self.PULLBACK_TICKS:
                    # Pullback confirmed! Arm the ladder
                    self._arm(idx, ts, pb["block_price"], pb["fss"], pb["trade_side"])
                    # Fill T1 immediately at block price
                    self.active["tiers"][0]["filled"] = self.active["tiers"][0]["size"]
                    self.active["tiers"][0]["fill_price"] = pb["block_price"]
                    self.active["total_filled"] = self.active["tiers"][0]["size"]
                    self.active["total_cost"] = self.active["tiers"][0]["size"] * pb["block_price"]
                    self.pending_block = None
                    if verbose:
                        print(f"  [{ts}] PULLBACK CONFIRMED + ARMED  dist={dist_to_block:.1f}t @ {pb['block_price']:.2f}")
                    continue
                elif ticks_since > self.PULLBACK_WINDOW:
                    # No pullback within window → discard
                    self.pending_block = None

            # ---- No active ladder → look for new block prints ----
            if self.active is None and self.pending_block is None:
                if trade_size >= self.BLOCK_THRESHOLD:
                    # Compute IR
                    bid_sum = row.get("bid_size_l0", 500) + row.get("bid_size_l1", 300)
                    ask_sum = row.get("ask_size_l0", 500) + row.get("ask_size_l1", 300)
                    ir = bid_sum / ask_sum if ask_sum > 0 else 1.0

                    fss = self._compute_fss(trade_size, ir, absorption)

                    if fss >= self.FSS_MIN:
                        self.pending_block = {
                            "idx": idx,
                            "ts": ts,
                            "block_price": bid,
                            "fss": fss,
                            "trade_side": trade_side,
                        }
                        if verbose:
                            print(f"  [{ts}] BLOCK DETECTED  {trade_size:,} lots, FSS={fss:.2f}, side={trade_side}")
                        continue

            # ---- Active ladder: manage exits ----
            if self.active is not None:
                p = self.active

                # Fill T2 if price drops to T2 level
                if p["tiers"][1]["filled"] == 0 and bid <= p["tiers"][1]["price"]:
                    p["tiers"][1]["filled"] = p["tiers"][1]["size"]
                    p["tiers"][1]["fill_price"] = p["tiers"][1]["price"]
                    p["total_filled"] += p["tiers"][1]["size"]
                    p["total_cost"] += p["tiers"][1]["size"] * p["tiers"][1]["price"]

                if p["total_filled"] > 0:
                    avg = p["total_cost"] / p["total_filled"]
                    pnl_ticks = (bid - avg) / TICK_SIZE  # exit at BID

                    # Take profit: price advanced TARGET_TICKS above avg
                    if pnl_ticks >= self.TARGET_TICKS:
                        self._exit(idx, ts, bid, ask, "TARGET_REACHED")
                        if verbose:
                            print(f"  [{ts}] EXIT TARGET  +{pnl_ticks:.0f} ticks")
                        continue

                    # Stop loss: price dropped below avg
                    if pnl_ticks <= -self.STOP_LOSS_TICKS:
                        self._exit(idx, ts, bid, ask, "STOP_LOSS")
                        if verbose:
                            print(f"  [{ts}] EXIT STOP  {pnl_ticks:.0f} ticks")
                        continue

        # Force exit remaining
        if self.active is not None and self.active["total_filled"] > 0:
            last = self.data.iloc[-1]
            self._exit(len(self.data) - 1, last["timestamp"], last["bid"], last["ask"], "END_OF_DATA")

        self._print_summary()

    def _print_summary(self):
        if not self.trades:
            print("\n  No DPFL trades.")
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

        avg_fss = np.mean([t["fss"] for t in self.trades])
        avg_size = np.mean([t["size"] for t in self.trades])

        print("\n" + "=" * 80)
        print("  DPFL BACKTEST SUMMARY")
        print("=" * 80)
        print(f"  Block Prints Found  : {n}")
        print(f"  Winners             : {len(winners)}")
        print(f"  Losers              : {len(losers)}")
        print(f"  Win Rate            : {len(winners)/n*100:.1f}%")
        print(f"  Avg FSS             : {avg_fss:.2f}")
        print(f"  Avg Size Filled     : {avg_size:.0f} lots")
        print(f"  Total Net P&L       : Rs {total_pnl:,.0f}")
        print(f"  Avg P&L / Trade     : Rs {avg_pnl:,.0f}")
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
        data = generate_realistic_lob_data(n_ticks=35000, seed=77)

    bt = DPFLBacktester(data)
    bt.run(verbose=False)

if __name__ == "__main__":
    main()
