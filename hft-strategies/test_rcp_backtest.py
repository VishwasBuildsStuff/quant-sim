"""
RCP (Range Capture Parallelism) Backtest — Rewritten from scratch.

Proper per-range lifecycle:
  1. Detect range: price oscillates between high_zone and low_zone
  2. Arm buy at low_zone + sell at high_zone simultaneously
  3. When buy fills → hold, target = high_zone
  4. When sell fills → hold, target = low_zone
  5. EXIT when opposite zone fills (captured spread) or timeout
  6. CLEANUP: reset all state

Usage:
    python test_rcp_backtest.py
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


class RCPBacktester:
    """Range Capture Parallelism backtest - Optimized."""

    RANGE_LOOKBACK = 80   # back to 80 (better quality ranges)
    RANGE_MIN_WIDTH_TICKS = 5  # back to 5
    RANGE_MAX_WIDTH_TICKS = 18  # raised from 16 (more ranges)
    ZONE_SIZE = 38  # between 35 and 40 (balanced)
    TIMEOUT_TICKS = 140  # raised from 120 (more time to capture)

    def __init__(self, data):
        self.data = data
        self.trades = []
        self.active = None
        self.counter = 0
        self.price_window = deque(maxlen=self.RANGE_LOOKBACK)
        self.vt_history = deque(maxlen=20)
        self.running_pnl = 0.0
        self.peak_pnl = 0.0
        self.max_drawdown = 0.0

    def compute_vt(self):
        if not self.vt_history:
            return 0
        return sum(list(self.vt_history)[-4:])

    def _detect_range(self):
        """Detect high/low zones from recent price window."""
        if len(self.price_window) < self.RANGE_LOOKBACK:
            return None

        prices = np.array(list(self.price_window))
        # Use 20th and 80th percentiles as zones (robust to outliers)
        low_zone = np.percentile(prices, 20)
        high_zone = np.percentile(prices, 80)
        width_ticks = round((high_zone - low_zone) / TICK_SIZE)

        if self.RANGE_MIN_WIDTH_TICKS <= width_ticks <= self.RANGE_MAX_WIDTH_TICKS:
            return {"low": round(low_zone, 2), "high": round(high_zone, 2), "width_ticks": width_ticks}

        return None

    def _arm(self, idx, ts, range_info):
        """Arm a new range capture with buy at low + sell at high."""
        self.counter += 1
        self.active = {
            "id": f"RCP_{self.counter:04d}",
            "arm_idx": idx,
            "arm_ts": ts,
            "low_zone": range_info["low"],
            "high_zone": range_info["high"],
            "width_ticks": range_info["width_ticks"],
            "buy_filled": False,
            "buy_price": 0,
            "buy_size": 0,
            "sell_filled": False,
            "sell_price": 0,
            "sell_size": 0,
            "exit_reason": None,
        }

    def _exit(self, idx, ts, bid, ask, reason):
        """Exit the active range capture and record."""
        p = self.active
        if p is None:
            return

        total_pnl = 0.0
        total_filled = 0

        # Buy P&L: exit at high zone target (range capture strategy)
        if p["buy_filled"]:
            buy_exit = p["high_zone"]
            pnl_ticks = (buy_exit - p["buy_price"]) / TICK_SIZE
            pnl = pnl_ticks * p["buy_size"] * TICK_VALUE
            total_pnl += pnl
            total_filled += p["buy_size"]

        # Sell P&L: exit at low zone target (range capture strategy)
        if p["sell_filled"]:
            sell_exit = p["low_zone"]
            pnl_ticks = (p["sell_price"] - sell_exit) / TICK_SIZE
            pnl = pnl_ticks * p["sell_size"] * TICK_VALUE
            total_pnl += pnl
            total_filled += p["sell_size"]

        if total_filled == 0:
            self.active = None
            return

        comm = total_filled * COMMISSION
        slip = total_filled * bid * SLIPPAGE_BPS / 10000
        net = total_pnl - comm - slip

        # Update running P&L and track max drawdown
        self.running_pnl += net
        self.peak_pnl = max(self.peak_pnl, self.running_pnl)
        drawdown = self.peak_pnl - self.running_pnl
        self.max_drawdown = max(self.max_drawdown, drawdown)

        self.trades.append({
            "id": p["id"],
            "low_zone": p["low_zone"],
            "high_zone": p["high_zone"],
            "width_ticks": p["width_ticks"],
            "buy_filled": p["buy_filled"],
            "sell_filled": p["sell_filled"],
            "total_filled": total_filled,
            "gross_pnl": round(total_pnl, 0),
            "net_pnl": round(net, 0),
            "exit_reason": reason,
            "hold_ticks": idx - p["arm_idx"],
        })
        self.active = None

    def run(self, verbose=False):
        print("=" * 80)
        print("  RCP (Range Capture Parallelism) Backtest — Optimized")
        print("=" * 80)
        print(f"  Data points       : {len(self.data)}")
        print(f"  Range lookback    : {self.RANGE_LOOKBACK} ticks")
        print(f"  Range width       : {self.RANGE_MIN_WIDTH_TICKS}-{self.RANGE_MAX_WIDTH_TICKS} ticks")
        print(f"  Zone size         : {self.ZONE_SIZE} lots per side")
        print(f"  Timeout           : {self.TIMEOUT_TICKS} ticks")
        print("=" * 80)

        for idx, row in self.data.iterrows():
            ts = row["timestamp"]
            bid = row["bid"]
            ask = row["ask"]
            mid = (bid + ask) / 2

            self.price_window.append(mid)
            self.vt_history.append(int(row["trade_size"]))

            # ---- No active range → detect and arm ----
            if self.active is None:
                rng = self._detect_range()
                if rng is not None:
                    self._arm(idx, ts, rng)
                    # Fill buy if price is at low zone
                    if bid <= rng["low"]:
                        self.active["buy_filled"] = True
                        self.active["buy_price"] = bid
                        self.active["buy_size"] = self.ZONE_SIZE
                    # Fill sell if price is at high zone
                    if ask >= rng["high"]:
                        self.active["sell_filled"] = True
                        self.active["sell_price"] = ask
                        self.active["sell_size"] = self.ZONE_SIZE
                    if verbose:
                        bf = "B FILLED" if self.active["buy_filled"] else "B pending"
                        sf = "S FILLED" if self.active["sell_filled"] else "S pending"
                        print(f"  [{ts}] RANGE ARMED  low={rng['low']:.2f} high={rng['high']:.2f} w={rng['width_ticks']}t  {bf}  {sf}")
                    continue

            # ---- Active range: manage ----
            if self.active is not None:
                p = self.active

                # Fill buy if price touches low zone
                if not p["buy_filled"] and bid <= p["low_zone"]:
                    p["buy_filled"] = True
                    p["buy_price"] = bid
                    p["buy_size"] = self.ZONE_SIZE

                # Fill sell if price touches high zone
                if not p["sell_filled"] and ask >= p["high_zone"]:
                    p["sell_filled"] = True
                    p["sell_price"] = ask
                    p["sell_size"] = self.ZONE_SIZE

                # Exit: both filled → captured the range (spread between zones)
                if p["buy_filled"] and p["sell_filled"]:
                    self._exit(idx, ts, bid, ask, "BOTH_FILLED")
                    if verbose:
                        print(f"  [{ts}] EXIT BOTH  buy@{p['buy_price']:.2f} sell@{p['sell_price']:.2f}")
                    continue

                # Exit: buy filled, price reached high zone → exit buy at high
                if p["buy_filled"] and not p["sell_filled"] and ask >= p["high_zone"]:
                    self._exit(idx, ts, bid, ask, "BUY_TARGET")
                    if verbose:
                        print(f"  [{ts}] EXIT BUY_TARGET  buy@{p['buy_price']:.2f} exit@{ask:.2f}")
                    continue

                # Exit: sell filled, price reached low zone → exit sell at low
                if p["sell_filled"] and not p["buy_filled"] and bid <= p["low_zone"]:
                    self._exit(idx, ts, bid, ask, "SELL_TARGET")
                    if verbose:
                        print(f"  [{ts}] EXIT SELL_TARGET  sell@{p['sell_price']:.2f} exit@{bid:.2f}")
                    continue

                # Timeout exit
                hold_ticks = idx - p["arm_idx"]
                if hold_ticks > self.TIMEOUT_TICKS:
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
            print("\n  No RCP ranges captured.")
            return

        n = len(self.trades)
        winners = [t for t in self.trades if t["net_pnl"] > 0]
        losers = [t for t in self.trades if t["net_pnl"] <= 0]
        total_pnl = sum(t["net_pnl"] for t in self.trades)
        avg_pnl = total_pnl / n if n > 0 else 0

        both_filled = sum(1 for t in self.trades if t["buy_filled"] and t["sell_filled"])
        buy_only = sum(1 for t in self.trades if t["buy_filled"] and not t["sell_filled"])
        sell_only = sum(1 for t in self.trades if t["sell_filled"] and not t["buy_filled"])

        by_reason = {}
        for t in self.trades:
            r = t["exit_reason"]
            by_reason.setdefault(r, {"count": 0, "pnl": 0})
            by_reason[r]["count"] += 1
            by_reason[r]["pnl"] += t["net_pnl"]

        avg_width = np.mean([t["width_ticks"] for t in self.trades])

        print("\n" + "=" * 80)
        print("  RCP BACKTEST SUMMARY")
        print("=" * 80)
        print(f"  Ranges Captured   : {n}")
        print(f"  Winners           : {len(winners)}")
        print(f"  Losers            : {len(losers)}")
        print(f"  Win Rate          : {len(winners)/n*100:.1f}%")
        print(f"  Both Sides Filled : {both_filled}")
        print(f"  Buy Only          : {buy_only}")
        print(f"  Sell Only         : {sell_only}")
        print(f"  Avg Range Width   : {avg_width:.1f} ticks")
        print(f"  Total Net P&L     : Rs {total_pnl:,.0f}")
        print(f"  Avg P&L / Range   : Rs {avg_pnl:,.0f}")
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
        data = generate_realistic_lob_data(n_ticks=40000, seed=42)
    print(f"  Generated {len(data)} ticks from {data['timestamp'].iloc[0]} to {data['timestamp'].iloc[-1]}")
    bt = RCPBacktester(data)
    bt.run(verbose=False)

if __name__ == "__main__":
    main()
