"""
EODPL (End-of-Day Pin Ladder) Backtest — Redesigned for 5-second data.

Key insights:
- Data is 5-second intervals, not tick-level HFT
- EOD pin effect is subtle at this frequency
- Use price clustering (not VWAP) to detect pin level
- Tighter tier deviations (max pain acts like magnet)
- Faster exits (pin should happen quickly or not at all)

Usage:
    python test_eodpl_backtest.py
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


class EODPLBacktester:
    """End-of-Day Pin Ladder backtest - Redesigned."""

    TIERS = 3
    TIER_SIZES = [10, 15, 20]  # reduced (45 total, less risk)
    TIER_DEVIATIONS_BPS = [-5, -10, -15]  # tighter to pin
    PIN_CONVERGENCE_BPS = 10  # back to 10 (selective exit)
    TIMEOUT_TICKS = 45
    PIN_WINDOW_PCT = 0.18
    VT_CONFIRM_MIN = 6000  # back to 6000 (more selective)
    ENTRY_ZONE_BPS = 15  # narrowed (more selective entry)

    def __init__(self, data):
        self.data = data
        self.ladders = []
        self.active = None
        self.counter = 0
        self.pin_level = None
        self.running_pnl = 0.0
        self.peak_pnl = 0.0
        self.max_drawdown = 0.0
        self.price_buffer = deque(maxlen=100)
        self.vt_history = deque(maxlen=20)

    def _detect_pin_level(self, prices):
        """Detect pin level using improved price clustering."""
        if len(prices) < 50:
            return None
        price_array = np.array(prices)
        hist, bin_edges = np.histogram(price_array, bins=100)
        mode_idx = np.argmax(hist)
        return (bin_edges[mode_idx] + bin_edges[mode_idx + 1]) / 2

    def compute_vt(self):
        """Compute V_t as sum of last 4 trade sizes."""
        if not self.vt_history:
            return 0
        return sum(list(self.vt_history)[-4:])

    def run(self, verbose=False):
        print("=" * 80)
        print("  EODPL (End-of-Day Pin Ladder) Backtest — Optimized")
        print("=" * 80)
        print(f"  Data points     : {len(self.data)}")
        print(f"  Pin window      : last {self.PIN_WINDOW_PCT*100:.0f}% of session")
        print(f"  Tier deviations : {self.TIER_DEVIATIONS_BPS} bps")
        print(f"  Tier sizes      : {self.TIER_SIZES}")
        print(f"  Convergence exit: within {self.PIN_CONVERGENCE_BPS} bps of pin")
        print(f"  Entry zone      : within {self.ENTRY_ZONE_BPS} bps below pin")
        print(f"  Volume confirm  : V_t >= {self.VT_CONFIRM_MIN:,}")
        print(f"  Timeout exit    : {self.TIMEOUT_TICKS} ticks (~{self.TIMEOUT_TICKS*5:.0f}s)")
        print("=" * 80)

        n = len(self.data)
        pin_start = int(n * (1 - self.PIN_WINDOW_PCT))

        # First pass: detect pin level
        for idx, row in self.data.iterrows():
            if idx >= pin_start:
                self.price_buffer.append(row["bid"])

        if len(self.price_buffer) >= 50:
            try:
                self.pin_level = self._detect_pin_level(list(self.price_buffer))
            except:
                self.pin_level = np.median(list(self.price_buffer))
            print(f"\n  Detected pin level: Rs {self.pin_level:.2f}")
        else:
            self.pin_level = np.median(self.data.loc[pin_start:, "bid"])

        self.price_buffer.clear()

        # Second pass: run strategy
        for idx, row in self.data.iterrows():
            ts = row["timestamp"]
            bid = row["bid"]
            ask = row["ask"]
            trade_size = int(row["trade_size"])

            self.vt_history.append(trade_size)
            v_t = self.compute_vt()

            # ---- Outside pin window: no ladders ----
            if idx < pin_start:
                if self.active is not None:
                    self._exit(idx, ts, bid, ask, "OUTSIDE_WINDOW")
                continue

            # ---- No active ladder → try to arm ----
            if self.active is None and self.pin_level is not None:
                dist_bps = (self.pin_level - bid) / self.pin_level * 10000
                if 0 < dist_bps < self.ENTRY_ZONE_BPS and v_t >= self.VT_CONFIRM_MIN:
                    self._arm(idx, ts, bid)
                    for tier in self.active["tiers"]:
                        if bid <= tier["price"]:
                            tier["filled"] = tier["size"]
                            tier["fill_price"] = bid
                            self.active["total_filled"] += tier["size"]
                            self.active["total_cost"] += tier["size"] * bid
                    if verbose:
                        filled_n = sum(1 for t in self.active["tiers"] if t["filled"] > 0)
                        print(f"  [{ts}] ARMED  pin={self.pin_level:.2f} bid={bid:.2f} dist={dist_bps:.1f}bps V_t={v_t:,} {filled_n}/{self.TIERS} filled")
                    continue

            # ---- Active ladder: manage exits ----
            if self.active is not None:
                p = self.active
                for tier in p["tiers"]:
                    if tier["filled"] == 0 and bid <= tier["price"]:
                        tier["filled"] = tier["size"]
                        tier["fill_price"] = bid
                        p["total_filled"] += tier["size"]
                        p["total_cost"] += tier["size"] * bid

                if p["total_filled"] > 0:
                    dist_to_pin_bps = (self.pin_level - bid) / self.pin_level * 10000
                    if abs(dist_to_pin_bps) <= self.PIN_CONVERGENCE_BPS:
                        self._exit(idx, ts, bid, ask, "CONVERGENCE")
                        if verbose:
                            print(f"  [{ts}] EXIT CONVERGENCE  dist={dist_to_pin_bps:.1f}bps")
                        continue
                    hold_ticks = idx - p["arm_idx"]
                    if hold_ticks > self.TIMEOUT_TICKS:
                        self._exit(idx, ts, bid, ask, "TIMEOUT")
                        if verbose:
                            print(f"  [{ts}] EXIT TIMEOUT  hold={hold_ticks}t dist={dist_to_pin_bps:.1f}bps")
                        continue

        if self.active is not None and self.active["total_filled"] > 0:
            last = self.data.iloc[-1]
            self._exit(n - 1, last["timestamp"], last["bid"], last["ask"], "END_OF_DATA")

        self._print_summary()

    def _arm(self, idx, ts, bid):
        self.counter += 1
        tiers = []
        for i in range(self.TIERS):
            dev_bps = self.TIER_DEVIATIONS_BPS[i]
            price = round(self.pin_level * (1 + dev_bps / 10000), 2)
            tiers.append({"price": price, "size": self.TIER_SIZES[i], "filled": 0, "fill_price": 0})
        self.active = {
            "id": f"EOD_{self.counter:04d}",
            "arm_idx": idx,
            "arm_ts": ts,
            "tiers": tiers,
            "total_filled": 0,
            "total_cost": 0.0,
            "exit_reason": None,
            "pin_level": self.pin_level,
        }

    def _exit(self, idx, ts, bid, ask, reason):
        p = self.active
        if p is None or p["total_filled"] == 0:
            self.active = None
            return
        avg = p["total_cost"] / p["total_filled"]
        pnl_ticks = (bid - avg) / TICK_SIZE
        gross = pnl_ticks * p["total_filled"] * TICK_VALUE
        comm = p["total_filled"] * COMMISSION
        slip = p["total_filled"] * bid * SLIPPAGE_BPS / 10000
        net = gross - comm - slip
        self.running_pnl += net
        self.peak_pnl = max(self.peak_pnl, self.running_pnl)
        drawdown = self.peak_pnl - self.running_pnl
        self.max_drawdown = max(self.max_drawdown, drawdown)
        tiers_filled_count = sum(1 for t in p["tiers"] if t["filled"] > 0)
        dist_to_pin = (p["pin_level"] - avg) / p["pin_level"] * 10000 if p["pin_level"] else 0
        self.ladders.append({
            "id": p["id"], "entry_avg": round(avg, 4), "exit_price": round(bid, 4),
            "size": p["total_filled"], "tiers_filled": tiers_filled_count,
            "dist_to_pin_bps": round(dist_to_pin, 1), "gross_pnl": round(gross, 0),
            "net_pnl": round(net, 0), "exit_reason": reason, "hold_ticks": idx - p["arm_idx"],
        })
        self.active = None

    def _print_summary(self):
        if not self.ladders:
            print("\n  No EODPL ladders triggered.")
            return
        n = len(self.ladders)
        winners = [l for l in self.ladders if l["net_pnl"] > 0]
        losers = [l for l in self.ladders if l["net_pnl"] <= 0]
        total_pnl = sum(l["net_pnl"] for l in self.ladders)
        avg_pnl = total_pnl / n if n > 0 else 0
        by_reason = {}
        for l in self.ladders:
            r = l["exit_reason"]
            by_reason.setdefault(r, {"count": 0, "pnl": 0})
            by_reason[r]["count"] += 1
            by_reason[r]["pnl"] += l["net_pnl"]
        print("\n" + "=" * 80)
        print("  EODPL BACKTEST SUMMARY")
        print("=" * 80)
        print(f"  Ladders Triggered : {n}")
        print(f"  Winners           : {len(winners)}")
        print(f"  Losers            : {len(losers)}")
        print(f"  Win Rate          : {len(winners)/n*100:.1f}%")
        print(f"  Avg Dist to Pin   : {np.mean([l['dist_to_pin_bps'] for l in self.ladders]):.1f} bps")
        print(f"  Total Net P&L     : Rs {total_pnl:,.0f}")
        print(f"  Avg P&L / Ladder  : Rs {avg_pnl:,.0f}")
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
    print(f"  Data: {len(data)} ticks from {data['timestamp'].iloc[0]} to {data['timestamp'].iloc[-1]}")
    bt = EODPLBacktester(data)
    bt.run(verbose=False)

if __name__ == "__main__":
    main()
