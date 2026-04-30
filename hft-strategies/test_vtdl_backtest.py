"""
VTDL (VWAP/Tape Divergence Ladder) Backtest — Rewritten from scratch.

Proper per-ladder lifecycle:
  1. Track session VWAP
  2. When price deviates >= 0.15% below VWAP → arm buy ladder (3 tiers)
  3. Fill tiers as price drops through levels
  4. EXIT when price returns to VWAP (mean reversion)
  5. STOP LOSS if deviation widens beyond 0.50%
  6. CLEANUP: reset all state

Usage:
    python test_vtdl_backtest.py
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


class VTDLBacktester:
    """VWAP/Tape Divergence Ladder backtest - Optimized."""

    TIERS = 3
    TIER_SIZES = [8, 12, 18]  # reduced total from 55 to 38 (less risk)
    TIER_DEVIATIONS_BPS = [-12, -22, -35]  # bps below VWAP (deeper levels)
    DS_MIN = 0.45
    MAX_DEVIATION = 0.0035  # -0.35% stop loss (tighter)
    COOLDOWN_TICKS = 20  # faster cooldown
    PROFIT_TARGET_TICKS = 6  # take profit at +6 ticks

    def __init__(self, data):
        self.data = data
        self.trades = []
        self.active = None
        self.counter = 0
        self.vt_history = deque(maxlen=20)
        self.last_exit_idx = -999
        self.running_pnl = 0.0
        self.peak_pnl = 0.0
        self.max_drawdown = 0.0

    def compute_vt(self):
        if not self.vt_history:
            return 0
        return sum(list(self.vt_history)[-4:])

    def _compute_ds(self, dev_bps, v_t, ir):
        """Divergence Score."""
        dev_score = min(dev_bps / 35, 1.0) * 0.25
        vt_score = max(0, 1 - v_t / 100) * 0.25
        ir_score = min(ir / 3, 1.0) * 0.25
        dev_score_2 = dev_score  # reuse
        return dev_score_2 + vt_score + ir_score + 0.25  # max 1.0

    def _arm(self, idx, ts, vwap, bid):
        """Arm a new VWAP divergence ladder."""
        self.counter += 1
        tiers = []
        for i in range(self.TIERS):
            dev_bps = self.TIER_DEVIATIONS_BPS[i]
            price = round(vwap * (1 + dev_bps / 10000), 2)
            tiers.append({"price": price, "size": self.TIER_SIZES[i], "filled": 0, "fill_price": 0})

        self.active = {
            "id": f"VTDL_{self.counter:04d}",
            "arm_idx": idx,
            "arm_ts": ts,
            "vwap": vwap,
            "tiers": tiers,
            "total_filled": 0,
            "total_cost": 0.0,
            "exit_reason": None,
        }

    def _exit(self, idx, ts, bid, ask, reason):
        """Exit the active VWAP ladder and record."""
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

        # Update running P&L and track max drawdown
        self.running_pnl += net
        self.peak_pnl = max(self.peak_pnl, self.running_pnl)
        drawdown = self.peak_pnl - self.running_pnl
        self.max_drawdown = max(self.max_drawdown, drawdown)

        tiers_filled = sum(1 for t in p["tiers"] if t["filled"] > 0)
        dev_bps = (p["vwap"] - bid) / p["vwap"] * 10000

        self.trades.append({
            "id": p["id"],
            "entry_avg": round(avg, 4),
            "exit_price": round(bid, 4),
            "vwap": round(p["vwap"], 4),
            "size": p["total_filled"],
            "tiers_filled": tiers_filled,
            "dev_bps": round(dev_bps, 1),
            "gross_pnl": round(gross, 0),
            "net_pnl": round(net, 0),
            "exit_reason": reason,
            "hold_ticks": idx - p["arm_idx"],
        })
        self.active = None

    def run(self, verbose=False):
        print("=" * 80)
        print("  VTDL (VWAP/Tape Divergence Ladder) Backtest — Optimized")
        print("=" * 80)
        print(f"  Data points       : {len(self.data)}")
        print(f"  Tier deviations   : {self.TIER_DEVIATIONS_BPS} bps")
        print(f"  Tier sizes        : {self.TIER_SIZES}")
        print(f"  Exit on VWAP return: yes (within 10 bps)")
        print(f"  Profit target     : +{self.PROFIT_TARGET_TICKS} ticks")
        print(f"  Stop loss         : deviation > {self.MAX_DEVIATION*100:.2f}%")
        print("=" * 80)

        rolling_vwap_window = deque(maxlen=500)

        for idx, row in self.data.iterrows():
            ts = row["timestamp"]
            bid = row["bid"]
            ask = row["ask"]
            trade_size = int(row["trade_size"])
            trade_price = row["trade_price"]

            self.vt_history.append(trade_size)
            vt = self.compute_vt()

            # Rolling VWAP: median of trade prices in window (robust to outliers)
            rolling_vwap_window.append(trade_price)
            if len(rolling_vwap_window) >= 100:
                vwap = float(np.median(list(rolling_vwap_window)))
            else:
                continue  # warmup

            # ---- No active ladder → look for divergence ----
            if self.active is None and idx > self.last_exit_idx + self.COOLDOWN_TICKS:
                dev_bps = (vwap - bid) / vwap * 10000
                
                # Buy ladder: price below rolling VWAP (5-25 bps range)
                if 5 <= dev_bps <= 25:
                    # Compute IR
                    bid_sum = row.get("bid_size_l0", 500) + row.get("bid_size_l1", 300) + row.get("bid_size_l2", 200)
                    ask_sum = row.get("ask_size_l0", 500) + row.get("ask_size_l1", 300) + row.get("ask_size_l2", 200)
                    ir = bid_sum / ask_sum if ask_sum > 0 else 1.0

                    ds = self._compute_ds(dev_bps, vt, ir)
                    if ds >= self.DS_MIN:
                        self._arm(idx, ts, vwap, bid)
                        # Fill tier 1 if price is at or below T1
                        t1_price = self.active["tiers"][0]["price"]
                        if bid <= t1_price:
                            self.active["tiers"][0]["filled"] = self.active["tiers"][0]["size"]
                            self.active["tiers"][0]["fill_price"] = bid
                            self.active["total_filled"] = self.active["tiers"][0]["size"]
                            self.active["total_cost"] = self.active["tiers"][0]["size"] * bid
                        if verbose:
                            filled_n = sum(1 for t in self.active["tiers"] if t["filled"] > 0)
                            print(f"  [{ts}] ARMED  dev={dev_bps:.1f}bps DS={ds:.2f} {filled_n} filled")
                        continue

            # ---- Active ladder: manage ----
            if self.active is not None:
                p = self.active

                # Fill remaining tiers
                for tier in p["tiers"]:
                    if tier["filled"] == 0 and bid <= tier["price"]:
                        tier["filled"] = tier["size"]
                        tier["fill_price"] = tier["price"]
                        p["total_filled"] += tier["size"]
                        p["total_cost"] += tier["size"] * tier["price"]

                if p["total_filled"] > 0:
                    avg = p["total_cost"] / p["total_filled"]
                    dev_from_vwap = (p["vwap"] - bid) / p["vwap"] * 10000
                    ticks_profit = (bid - avg) / TICK_SIZE

                    # Exit: price returned to VWAP (within 10 bps)
                    if abs(dev_from_vwap) <= 10:
                        self._exit(idx, ts, bid, ask, "VWAP_RETURN")
                        self.last_exit_idx = idx
                        if verbose:
                            print(f"  [{ts}] EXIT VWAP_RETURN  avg={avg:.2f} vwap={p['vwap']:.2f}")
                        continue

                    # Take profit: in profit by 6+ ticks
                    if ticks_profit >= self.PROFIT_TARGET_TICKS:
                        self._exit(idx, ts, bid, ask, "PARTIAL_PROFIT")
                        self.last_exit_idx = idx
                        if verbose:
                            print(f"  [{ts}] EXIT PROFIT  +{ticks_profit:.0f} ticks")
                        continue

                    # Stop loss: deviation too wide
                    if dev_from_vwap > self.MAX_DEVIATION * 10000:
                        self._exit(idx, ts, bid, ask, "STOP_LOSS")
                        self.last_exit_idx = idx
                        if verbose:
                            print(f"  [{ts}] EXIT STOP  dev={dev_from_vwap:.1f}bps")
                        continue

        # Force exit remaining
        if self.active is not None and self.active["total_filled"] > 0:
            last = self.data.iloc[-1]
            self._exit(len(self.data) - 1, last["timestamp"], last["bid"], last["ask"], "END_OF_DATA")

        self._print_summary()

    def _print_summary(self):
        if not self.trades:
            print("\n  No VTDL ladders triggered.")
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

        avg_dev = np.mean([t["dev_bps"] for t in self.trades])
        convergence = sum(1 for t in self.trades if t["exit_reason"] == "VWAP_RETURN")

        print("\n" + "=" * 80)
        print("  VTDL BACKTEST SUMMARY")
        print("=" * 80)
        print(f"  Divergence Events : {n}")
        print(f"  VWAP Convergences : {convergence}")
        print(f"  Winners           : {len(winners)}")
        print(f"  Losers            : {len(losers)}")
        print(f"  Win Rate          : {len(winners)/n*100:.1f}%")
        print(f"  Avg Deviation     : {avg_dev:.1f} bps")
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
        data = generate_realistic_lob_data(n_ticks=40000, seed=42)
    print(f"  Generated {len(data)} ticks from {data['timestamp'].iloc[0]} to {data['timestamp'].iloc[-1]}")
    bt = VTDLBacktester(data)
    bt.run(verbose=False)

if __name__ == "__main__":
    main()
