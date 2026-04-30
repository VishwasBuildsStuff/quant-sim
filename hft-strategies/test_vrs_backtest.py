"""
VRS (Volatility Regime Switch) Backtest Script

⚠️  DEPRECATED / EXCLUDED from test_all_tactics.py

Reason: VRS is a meta-tactic that orchestrates all 7 other tactics with
dynamic sizing based on a Composite Volatility Index (CVI). Its trigger
thresholds (V_t < 60, V_t > 80, IR >= 2.0, V_t >= 150) were designed
for synthetic 50ms tick data where V_t ranges ~40-200.

On REAL 5-second interval data, V_t ranges from 5,000-30,000, so NONE
of the trigger conditions ever fire → zero trades generated.

To fix VRS would require:
  1. Scaling all thresholds by ~100x for 5-second data
  2. Reimplementing all 7 sub-tactics inline (duplicating their logic)
  3. Adding proper position lifecycle management per tactic

Better approach: Run the 7 individual tactics directly (as test_all_tactics.py
already does) and apply volatility-based position sizing at the portfolio level
instead of trying to gate entries within a meta-tactic.

Archive kept for reference — do NOT include in live trading without redesign.

Usage:
    python test_vrs_backtest.py  # runs standalone (will produce zero trades on real data)
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import deque

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
try:
    from realistic_data_generator import generate_realistic_lob_data
except ImportError:
    generate_realistic_lob_data = None


try:
    from backtesting_engine import MultiLotBacktester
except ImportError:
    print("ERROR: Cannot import backtesting_engine.py")
    print(f"Expected location: {SCRIPT_DIR}/backtesting_engine.py")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Synthetic LOB data with multiple volatility regimes
# ---------------------------------------------------------------------------

def generate_synthetic_lob(n_ticks=60000, seed=121):
    """Generate LOB tick data with distinct volatility regimes."""
    np.random.seed(seed)
    vwap = 223.50
    timestamps = pd.date_range("2026-04-13 09:15:00", periods=n_ticks, freq="50ms")

    price = np.full(n_ticks, vwap)

    # Define regime boundaries
    # Low vol: 0-25%, Normal: 25-50%, High: 50-75%, Low: 75-100%
    regime_vol = np.zeros(n_ticks)
    regime_vol[:15000] = 0.003    # low
    regime_vol[15000:30000] = 0.008  # normal
    regime_vol[30000:45000] = 0.020  # high
    regime_vol[45000:] = 0.004     # low

    for i in range(1, n_ticks):
        vol = regime_vol[i]
        deviation = price[i - 1] - vwap
        mr = 0.001 * (vwap - price[i - 1])
        shock = np.random.randn() * vol
        price[i] = price[i - 1] + mr + shock

    spread = np.clip(0.02 + np.abs(price - vwap) * 0.1 + np.random.exponential(0.005, n_ticks),
                     0.01, 0.10)
    bid = np.round(price - spread / 2, 2)
    ask = np.round(price + spread / 2, 2)

    def gen_sizes(base, n):
        return np.clip(np.random.poisson(base, n) + np.random.randint(-100, 100, n), 50, 2000)

    # Trade sizes scale with volatility
    trade_sizes = np.clip(np.random.exponential(40, n_ticks).astype(int), 1, 400)
    trade_sizes[30000:45000] = np.clip(np.random.exponential(80, 15000).astype(int), 1, 800)

    return pd.DataFrame({
        "timestamp": timestamps,
        "bid": np.round(bid, 2),
        "ask": np.round(ask, 2),
        "bid_size_l0": gen_sizes(800, n_ticks),
        "bid_size_l1": gen_sizes(600, n_ticks),
        "bid_size_l2": gen_sizes(400, n_ticks),
        "ask_size_l0": gen_sizes(700, n_ticks),
        "ask_size_l1": gen_sizes(500, n_ticks),
        "ask_size_l2": gen_sizes(350, n_ticks),
        "trade_price": np.round(price + np.random.randn(n_ticks) * 0.003, 2),
        "trade_size": trade_sizes,
        "trade_side": np.random.choice(["B", "A", "M"], n_ticks, p=[0.45, 0.45, 0.10]),
        "volume": np.random.poisson(3000, n_ticks),
        "vwap": np.full(n_ticks, vwap),
        "regime_vol": regime_vol,
    })


# ---------------------------------------------------------------------------
# Tactic Definitions (simplified inline implementations)
# ---------------------------------------------------------------------------

class TacticDef:
    """Base class for tactic definitions used by VRS."""
    def __init__(self, name, base_lots, vm=1.0):
        self.name = name
        self.base_lots = base_lots
        self.vm = vm

    @property
    def adjusted_lots(self):
        return [max(1, int(l * self.vm)) for l in self.base_lots]


def make_tactics(vm=1.0):
    """Create all 7 tactic definitions with volatility multiplier."""
    return [
        TacticDef("LES",  [50, 50, 50], vm),
        TacticDef("MP",   [40, 30, 20, 10], vm),
        TacticDef("DPFL", [50, 35, 25, 15], vm),
        TacticDef("RCP",  [40], vm),
        TacticDef("SESO", [100], vm),
        TacticDef("VTDL", [30, 40, 50], vm),
        TacticDef("EODPL", [25, 35, 45, 55], vm),
    ]


# ---------------------------------------------------------------------------
# VRS Backtester
# ---------------------------------------------------------------------------

class VRSBacktester:
    """Volatility Regime Switch backtest harness."""

    TACTIC_NAME = "VRS"
    CVI_LOW_THRESHOLD = 50       # CVI < 50 = low vol
    CVI_HIGH_THRESHOLD = 150     # CVI > 150 = high vol
    VM_LOW = 1.30
    VM_NORMAL = 1.00
    VM_HIGH = 0.55
    CVI_WINDOW_MS = 5000         # 5s lookback for CVI
    TICK_VALUE = 15.0
    COMMISSION = 0.05

    def __init__(self, data: pd.DataFrame):
        self.data = data
        self.engine = MultiLotBacktester(
            tick_value=self.TICK_VALUE,
            commission_per_share=self.COMMISSION,
            slippage_bps=5,
        )

        # Tactic results tracking
        self.tactic_results = {name: [] for name in ["LES", "MP", "DPFL", "RCP", "SESO", "VTDL", "EODPL"]}
        self.regime_changes = 0
        self.current_regime = "NORMAL"
        self.current_vm = self.VM_NORMAL

        # Active positions per tactic
        self.active_positions = {}  # tactic_name -> position dict
        self.position_counter = {}  # tactic_name -> count

        # CVI / volatility tracking
        self.return_history = deque(maxlen=2000)
        self.vt_history = deque(maxlen=2000)
        self.cvi_history = []
        self.regime_log = []  # (timestamp, regime, vm, cvi)

        # Tape
        self.tape_window = deque(maxlen=500)

        # Previous price for returns
        self.prev_price = None

    def compute_vt(self, window_ms=200):
        if not self.tape_window:
            return 0
        n_recent = max(1, len(self.tape_window) * window_ms // 1000)
        recent = list(self.tape_window)[-n_recent:]
        return sum(t.get("size", 0) for t in recent)

    def compute_cvi(self):
        """
        Composite Volatility Index.
        Combines price return volatility and tape velocity.
        """
        if len(self.return_history) < 20:
            return 100.0  # default

        returns = list(self.return_history)
        vol = np.std(returns) * 10000  # scale to bps

        vt_values = list(self.vt_history)
        avg_vt = np.mean(vt_values[-100:]) if vt_values else 50

        # CVI = weighted combo
        cvi = vol * 500 + avg_vt * 0.3
        return max(0, min(300, cvi))

    def determine_regime(self, cvi):
        """Determine volatility regime from CVI."""
        if cvi < self.CVI_LOW_THRESHOLD:
            return "LOW"
        elif cvi > self.CVI_HIGH_THRESHOLD:
            return "HIGH"
        else:
            return "NORMAL"

    def get_vm(self, regime):
        """Get volatility multiplier for regime."""
        if regime == "LOW":
            return self.VM_LOW
        elif regime == "HIGH":
            return self.VM_HIGH
        return self.VM_NORMAL

    def _open_position(self, tactic, ts, bid, ask, entry_price, reason):
        """Open a position for a tactic."""
        tdef = make_tactics(vm=self.current_vm)
        tactic_def = next((t for t in tdef if t.name == tactic), None)
        if tactic_def is None:
            return

        lots = tactic_def.adjusted_lots
        total_lots = sum(lots)

        self.position_counter[tactic] = self.position_counter.get(tactic, 0) + 1
        pos_id = f"{tactic}_{self.position_counter[tactic]:04d}"

        self.active_positions[tactic] = {
            "pos_id": pos_id,
            "tactic": tactic,
            "entry_time": ts,
            "entry_price": entry_price,
            "lots": lots,
            "total_lots": total_lots,
            "vm": self.current_vm,
            "regime": self.current_regime,
            "exit_price": None,
            "exit_time": None,
            "exit_reason": None,
            "pnl": 0.0,
            "reason": reason,
        }

    def _close_position(self, tactic, ts, bid, ask, reason):
        """Close a position for a tactic."""
        pos = self.active_positions.get(tactic)
        if pos is None:
            return

        pos["exit_time"] = ts
        pos["exit_reason"] = reason

        if tactic in ["LES", "DPFL", "VTDL", "EODPL", "RCP"]:
            # Long tactics: exit at bid
            pos["exit_price"] = bid
            pnl = (bid - pos["entry_price"]) * pos["total_lots"] * self.TICK_VALUE
        elif tactic == "MP":
            pos["exit_price"] = bid
            pnl = (bid - pos["entry_price"]) * pos["total_lots"] * self.TICK_VALUE
        elif tactic == "SESO":
            pos["exit_price"] = bid
            pnl = (bid - pos["entry_price"]) * pos["total_lots"] * self.TICK_VALUE
        else:
            pos["exit_price"] = bid
            pnl = (bid - pos["entry_price"]) * pos["total_lots"] * self.TICK_VALUE

        pos["pnl"] = round(pnl, 2)

        self.tactic_results[tactic].append({
            "pos_id": pos["pos_id"],
            "entry_time": pos["entry_time"],
            "exit_time": ts,
            "entry_price": round(pos["entry_price"], 4),
            "exit_price": round(bid, 4),
            "lots": pos["total_lots"],
            "vm": round(pos["vm"], 2),
            "regime": pos["regime"],
            "pnl": pos["pnl"],
            "entry_reason": pos["reason"],
            "exit_reason": reason,
        })

        del self.active_positions[tactic]

    def _check_tactic_triggers(self, ts, bid, ask, v_t, ir):
        """Check if any tactic should trigger."""
        # LES: V_t < 60 AND IR >= 2.0
        if "LES" not in self.active_positions and v_t < 60 and ir >= 2.0:
            self._open_position("LES", ts, bid, ask, bid, "VT_LOW_IR_HIGH")

        # MP: V_t > 80 AND IR >= 1.5
        if "MP" not in self.active_positions and v_t > 80 and ir >= 1.5:
            self._open_position("MP", ts, bid, ask, ask, "MOMENTUM")

        # DPFL: Simulated -- trigger on large trade size
        if "DPFL" not in self.active_positions and v_t > 120:
            self._open_position("DPFL", ts, bid, ask, bid, "FOOTPRINT")

        # RCP: Trigger at range extremes
        if "RCP" not in self.active_positions and len(self.return_history) > 100:
            returns = list(self.return_history)
            if abs(np.mean(returns[-50:])) < 0.0001:  # range-bound
                self._open_position("RCP", ts, bid, ask, bid, "RANGE")

        # SESO: V_t >= 150
        if "SESO" not in self.active_positions and v_t >= 150:
            self._open_position("SESO", ts, bid, ask, ask, "SWEEP")

        # VTDL: Price below VWAP
        if "VTDL" not in self.active_positions:
            data_vwap = self.data.iloc[min(len(self.data) - 1, int(ts.second * 20))].get("vwap", 223.50)
            if bid < data_vwap * 0.998:
                self._open_position("VTDL", ts, bid, ask, bid, "VWAP_DEV")

        # EODPL: Simulated based on time (last portion of data)
        if "EODPL" not in self.active_positions:
            pct_done = self.data.index.get_loc(ts) / len(self.data) if ts in self.data.index else 0.9
            if pct_done > 0.85:
                max_pain = 223.80
                if bid < max_pain * 0.995:
                    self._open_position("EODPL", ts, bid, ask, bid, "PIN")

    def _check_tactic_exits(self, ts, bid, ask, v_t):
        """Check if any active position should exit."""
        exits_to_process = []
        for tactic, pos in self.active_positions.items():
            if tactic == "LES" and v_t > 80:
                exits_to_process.append((tactic, "TAPE_ACCEL"))
            elif tactic == "MP" and v_t < 40:
                exits_to_process.append((tactic, "EXHAUSTION"))
            elif tactic == "SESO" and v_t < 90:
                exits_to_process.append((tactic, "EXHAUSTION"))
            elif pos["entry_time"] and (ts - pos["entry_time"]).total_seconds() > 10:
                exits_to_process.append((tactic, "TIME_EXPIRY"))

        for tactic, reason in exits_to_process:
            if tactic in self.active_positions:
                self._close_position(tactic, ts, bid, ask, reason)

    def run(self, verbose=False):
        print("=" * 80)
        print("  VRS (Volatility Regime Switch) Backtest")
        print("=" * 80)
        print(f"  Data points        : {len(self.data)}")
        print(f"  CVI Low threshold  : < {self.CVI_LOW_THRESHOLD}")
        print(f"  CVI High threshold : > {self.CVI_HIGH_THRESHOLD}")
        print(f"  VM Low vol         : {self.VM_LOW}")
        print(f"  VM Normal          : {self.VM_NORMAL}")
        print(f"  VM High vol        : {self.VM_HIGH}")
        print(f"  Tactics            : LES, MP, DPFL, RCP, SESO, VTDL, EODPL")
        print("=" * 80)

        for idx, row in self.data.iterrows():
            ts = row["timestamp"]
            bid = row["bid"]
            ask = row["ask"]
            trade_price = row["trade_price"]
            trade_size = int(row["trade_size"])
            trade_side = row["trade_side"]

            trade_print = {"price": trade_price, "size": trade_size, "side": trade_side, "timestamp": ts}

            dom = {
                0: {"bid_price": bid, "bid_size": int(row["bid_size_l0"]),
                    "ask_price": ask, "ask_size": int(row["ask_size_l0"])},
                1: {"bid_price": bid - 0.01, "bid_size": int(row["bid_size_l1"]),
                    "ask_price": ask + 0.01, "ask_size": int(row["ask_size_l1"])},
                2: {"bid_price": bid - 0.02, "bid_size": int(row["bid_size_l2"]),
                    "ask_price": ask + 0.02, "ask_size": int(row["ask_size_l2"])},
            }
            self.engine.update_market(bid, ask, dom=dom, trade_print=trade_print, vwap=row["vwap"])
            self.tape_window.append(trade_print)

            # Track returns
            if self.prev_price is not None:
                ret = (trade_price - self.prev_price) / self.prev_price
                self.return_history.append(ret)
            self.prev_price = trade_price

            # Compute indicators
            v_t = self.compute_vt()
            ir = self.compute_ir()
            cvi = self.compute_cvi()

            self.vt_history.append(v_t)
            self.cvi_history.append(cvi)

            # Determine regime
            regime = self.determine_regime(cvi)
            vm = self.get_vm(regime)
            if regime != self.current_regime:
                self.regime_changes += 1
                if verbose:
                    print(f"  [{ts}] REGIME CHANGE  {self.current_regime} -> {regime}  CVI={cvi:.1f}  VM={vm:.2f}")
            self.current_regime = regime
            self.current_vm = vm
            self.regime_log.append((ts, regime, vm, cvi))

            # Process tactic triggers
            self._check_tactic_triggers(ts, bid, ask, v_t, ir)

            # Process tactic exits
            self._check_tactic_exits(ts, bid, ask, v_t)

            # Process engine ladder fills
            self.engine.process_ladder_fills(ts)

        # Force close remaining positions
        for tactic in list(self.active_positions.keys()):
            self._close_position(tactic, self.data.iloc[-1]["timestamp"],
                                 self.data.iloc[-1]["bid"], self.data.iloc[-1]["ask"],
                                 "END_OF_DATA")

        self._print_summary()

    def compute_ir(self):
        dom = self.engine.dom_snapshot
        bid_sum = sum(dom.get(lvl, {}).get("bid_size", 0) for lvl in range(3))
        ask_sum = sum(dom.get(lvl, {}).get("ask_size", 0) for lvl in range(3))
        return bid_sum / ask_sum if ask_sum > 0 else 10.0

    def _print_summary(self):
        print("\n" + "=" * 80)
        print("  VRS BACKTEST SUMMARY")
        print("=" * 80)

        print(f"  Regime Changes      : {self.regime_changes}")
        print(f"  Current Regime      : {self.current_regime}")
        print(f"  Final VM            : {self.current_vm:.2f}")

        # Per-tactic summary
        print("\n  Per-Tactic Results:")
        print("-" * 80)

        grand_total_pnl = 0.0
        grand_total_trades = 0
        for tactic_name in ["LES", "MP", "DPFL", "RCP", "SESO", "VTDL", "EODPL"]:
            results = self.tactic_results[tactic_name]
            n = len(results)
            if n == 0:
                print(f"  {tactic_name:<8} : No trades")
                continue

            winners = sum(1 for r in results if r["pnl"] > 0)
            total_pnl = sum(r["pnl"] for r in results)
            avg_pnl = total_pnl / n
            win_rate = winners / n * 100
            avg_vm = np.mean([r["vm"] for r in results])

            grand_total_pnl += total_pnl
            grand_total_trades += n

            print(f"  {tactic_name:<8} : {n:4d} trades  "
                  f"win_rate={win_rate:5.1f}%  "
                  f"total_pnl=${total_pnl:>10,.2f}  "
                  f"avg_pnl=${avg_pnl:>8,.2f}  "
                  f"avg_vm={avg_vm:.2f}")

        print("-" * 80)
        print(f"  {'TOTAL':<8} : {grand_total_trades:4d} trades  "
              f"total_pnl=${grand_total_pnl:>10,.2f}")

        # Regime distribution
        print("\n  Regime Distribution:")
        regime_counts = {}
        for _, regime, vm, cvi in self.regime_log:
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

        total_ticks = len(self.regime_log)
        for regime in ["LOW", "NORMAL", "HIGH"]:
            count = regime_counts.get(regime, 0)
            pct = count / total_ticks * 100 if total_ticks > 0 else 0
            vm = self.get_vm(regime)
            print(f"  {regime:<10} : {count:6d} ticks ({pct:5.1f}%)  VM={vm:.2f}")

        # Risk-normalized P&L
        if grand_total_trades > 0:
            risk_norm_pnl = grand_total_pnl / grand_total_trades
            print(f"\n  Risk-Normalized P&L   : ${risk_norm_pnl:,.2f} per trade")
            print(f"  Regime-Adjusted P&L   : ${grand_total_pnl:,.2f}")

        print("=" * 80)


def main():
    print("Generating synthetic LOB data with volatility regimes ...")
    data = generate_realistic_lob_data(n_ticks=60000, seed=121) if generate_realistic_lob_data else generate_synthetic_lob(n_ticks=60000, seed=121)
    print(f"  Generated {len(data)} ticks from {data['timestamp'].iloc[0]} to {data['timestamp'].iloc[-1]}")

    backtest = VRSBacktester(data)
    backtest.run(verbose=False)


if __name__ == "__main__":
    main()
