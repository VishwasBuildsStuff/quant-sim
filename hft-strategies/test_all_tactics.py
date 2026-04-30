"""
TACTIC BACKTEST AGGREGATOR
Runs all 8 tactic backtests sequentially and produces a combined summary table.

Usage:
    python test_all_tactics.py [--tactics LES,MP,DPFL,RCP,SESO,VTDL,EODPL,VRS] [--quick]

Output:
    - Per-tactic summary
    - Combined comparison table
    - CSV export: backtest_results_TIMESTAMP.csv
"""
import sys
import os
import time
import argparse
import subprocess
from datetime import datetime

# Add project root to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

ALL_TACTICS = ["LES", "MP", "DPFL", "RCP", "SESO", "VTDL", "EODPL"]
# VRS removed: meta-tactic with synthetic-only thresholds (V_t < 60 vs real data V_t 5000-30000).
# Would require complete redesign to work with 5-second real data.
# Archive: test_vrs_backtest.py kept for reference.

SCRIPT_MAP = {
    "LES": "test_les_backtest.py",
    "MP": "test_mp_backtest.py",
    "DPFL": "test_dpfl_backtest.py",
    "RCP": "test_rcp_backtest.py",
    "SESO": "test_seso_backtest.py",
    "VTDL": "test_vtdl_backtest.py",
    "EODPL": "test_eodpl_backtest.py",
}


def run_single_backtest(tactic: str, quick: bool = False) -> dict:
    """
    Run a single tactic backtest via subprocess, capture and parse output.
    Returns summary dict.
    """
    script_name = SCRIPT_MAP.get(tactic)
    if not script_name:
        return {"error": f"Unknown tactic: {tactic}", "tactic": tactic}

    script_path = os.path.join(SCRIPT_DIR, script_name)
    if not os.path.exists(script_path):
        return {"error": f"Script not found: {script_path}", "tactic": tactic}

    print(f"\n{'='*60}")
    print(f"  RUNNING: {tactic} ({script_name})")
    print(f"{'='*60}")

    start_time = time.time()

    try:
        # Run as subprocess, capture stdout
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True, text=True, timeout=300,
            cwd=SCRIPT_DIR
        )
        output = result.stdout + result.stderr
        elapsed = time.time() - start_time

        # Parse summary table from output using regex
        import re
        summary = {"tactic": tactic, "elapsed_seconds": round(elapsed, 1)}

        # Extract key metrics from the output table
        # Look for patterns like "Ladders Triggered   : 142" or "Trades : 142"
        patterns = {
            "total_trades": [
                r'(?:Ladders Triggered|Pyramids Triggered|Block Prints Found|Ranges Captured|Sweeps Detected|Divergence Events|Pin Events|Pyramids Triggered)\s*[:=]\s*(\d+)',
                r'Total.*Trades.*[:=]\s*(\d+)',
            ],
            "win_rate": [
                r'Win Rate\s*[:=]\s*([\d.]+)%?',
            ],
            "total_pnl": [
                r'Total (?:Net |Gross )?P&L\s*[:=]\s*(?:Rs\s*|₹\s*)?([-\d,]+\.?\d*)',
            ],
            "avg_pnl": [
                r'Avg (?:Net )?P&L (?:per |/ )?(?:Ladder|Pyramid|Trade)\s*[:=]\s*(?:Rs\s*|₹\s*)?([-\d,]+\.?\d*)',
            ],
            "max_drawdown": [
                r'Max (?:Drawdown|DD)\s*[:=]\s*(?:Rs\s*|₹\s*)?([-\d,]+\.?\d*)',
            ],
            "avg_win": [
                r'Avg Win\s*[:=]\s*(?:Rs\s*|₹\s*)?([-\d,]+\.?\d*)',
            ],
            "avg_loss": [
                r'Avg Loss\s*[:=]\s*(?:Rs\s*|₹\s*)?([-\d,]+\.?\d*)',
            ],
        }

        for key, pattern_list in patterns.items():
            for pat in pattern_list:
                match = re.search(pat, output, re.IGNORECASE)
                if match:
                    val = match.group(1).replace(',', '')
                    try:
                        summary[key] = float(val)
                    except ValueError:
                        summary[key] = 0
                    break
            if key not in summary:
                summary[key] = 0

        # If script exited with error, capture it
        if result.returncode != 0:
            summary["error"] = f"Exit code {result.returncode}"

        return summary

    except subprocess.TimeoutExpired:
        return {
            "tactic": tactic, "error": "Timeout (>5 min)",
            "total_trades": 0, "win_rate": 0, "total_pnl": 0,
            "avg_pnl": 0, "max_drawdown": 0, "elapsed_seconds": 300,
        }
    except Exception as e:
        return {
            "tactic": tactic, "error": str(e),
            "total_trades": 0, "win_rate": 0, "total_pnl": 0,
            "avg_pnl": 0, "max_drawdown": 0, "elapsed_seconds": round(time.time() - start_time, 1),
        }


def print_summary_table(results: list):
    """
    Print a formatted comparison table of all tactic backtest results.
    """
    print("\n")
    print("=" * 90)
    print("  TACTIC BACKTEST SUMMARY — AGGREGATED RESULTS")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)

    # Header
    print(f"{'Tactic':<10} | {'Trades':>6} | {'Win%':>6} | {'Avg P&L':>10} | {'Total P&L':>12} | {'Max DD':>10} | {'Time':>5}")
    print("-" * 90)

    total_pnl = 0.0
    total_trades = 0
    total_wins = 0

    for r in results:
        if r.get("error"):
            print(f"{r.get('tactic', '???'):<10} | ERROR: {r['error']}")
            continue

        tactic = r.get("tactic", "?")
        trades = int(r.get("total_trades", 0) or 0)
        win_rate = float(r.get("win_rate", 0) or 0)
        avg_pnl = float(r.get("avg_pnl", 0) or 0)
        total = float(r.get("total_pnl", 0) or 0)
        max_dd = float(r.get("max_drawdown", 0) or 0)
        elapsed = float(r.get("elapsed_seconds", 0) or 0)

        total_pnl += total
        total_trades += trades
        total_wins += int(trades * win_rate / 100)

        print(f"{tactic:<10} | {trades:>6} | {win_rate:>5.1f}% | ₹{avg_pnl:>8.0f} | ₹{total:>10,.0f} | ₹{max_dd:>8,.0f} | {elapsed:>4.0f}s")

    print("-" * 90)

    # Combined row
    combined_win_rate = (total_wins / max(1, total_trades)) * 100
    combined_avg = total_pnl / max(1, total_trades)
    print(f"{'COMBINED':<10} | {total_trades:>6} | {combined_win_rate:>5.1f}% | ₹{combined_avg:>8.0f} | ₹{total_pnl:>10,.0f} | {'':>10} | {'':>5}")
    print("=" * 90)

    # Key insights
    print("\n  KEY INSIGHTS:")
    profitable = [r for r in results if r.get("total_pnl", 0) > 0 and not r.get("error")]
    unprofitable = [r for r in results if r.get("total_pnl", 0) <= 0 and not r.get("error")]

    if profitable:
        best = max(profitable, key=lambda x: x.get("total_pnl", 0))
        print(f"    ✅ Best: {best['tactic']} — ₹{best['total_pnl']:,.0f}")
    if unprofitable:
        worst = min(unprofitable, key=lambda x: x.get("total_pnl", 0))
        print(f"    ❌ Worst: {worst['tactic']} — ₹{worst['total_pnl']:,.0f}")
        print(f"    ⚠️  DO NOT proceed to live testing for: {', '.join(r['tactic'] for r in unprofitable)}")

    if total_pnl > 0:
        print(f"\n    📈 Combined P&L: ₹{total_pnl:,.0f} — POSITIVE EXPECTANCY")
        print(f"    ✅ PROCEED to Phase 2 (Market Replay)")
    else:
        print(f"\n    📉 Combined P&L: ₹{total_pnl:,.0f} — NEGATIVE EXPECTANCY")
        print(f"    ❌ DO NOT proceed. Fix unprofitable tactics first.")


def export_results_csv(results: list, output_dir: str = None):
    """
    Export results to CSV for further analysis.
    """
    if output_dir is None:
        output_dir = SCRIPT_DIR

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(output_dir, f"backtest_results_{timestamp}.csv")

    import csv
    with open(filepath, "w", newline="") as f:
        fieldnames = ["tactic", "total_trades", "win_rate", "avg_pnl", "total_pnl",
                      "max_drawdown", "avg_win", "avg_loss", "elapsed_seconds", "error"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in results:
            row = {
                "tactic": r.get("tactic", ""),
                "total_trades": r.get("total_trades", 0),
                "win_rate": r.get("win_rate", 0),
                "avg_pnl": r.get("avg_pnl", 0),
                "total_pnl": r.get("total_pnl", 0),
                "max_drawdown": r.get("max_drawdown", 0),
                "avg_win": r.get("avg_win", 0),
                "avg_loss": r.get("avg_loss", 0),
                "elapsed_seconds": r.get("elapsed_seconds", 0),
                "error": r.get("error", ""),
            }
            writer.writerow(row)

    print(f"\n  📄 Results exported to: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Run all tactic backtests and aggregate results")
    parser.add_argument("--tactics", type=str, default="all",
                        help="Comma-separated list of tactics to test (default: all)")
    parser.add_argument("--quick", action="store_true",
                        help="Quick mode: fewer ticks for faster results")
    parser.add_argument("--export", action="store_true",
                        help="Export results to CSV")
    args = parser.parse_args()

    # Parse tactics
    if args.tactics.lower() == "all":
        tactics_to_run = ALL_TACTICS
    else:
        tactics_to_run = [t.strip().upper() for t in args.tactics.split(",")]

    print(f"\n  HFT Multi-Lot Tactic Backtest Aggregator")
    print(f"  Tactics: {', '.join(tactics_to_run)}")
    print(f"  Quick mode: {'ON' if args.quick else 'OFF'}")

    # Run each tactic
    results = []
    for tactic in tactics_to_run:
        result = run_single_backtest(tactic, quick=args.quick)
        results.append(result)

    # Print summary
    print_summary_table(results)

    # Export if requested
    if args.export:
        export_results_csv(results)

    print(f"\n  Done. {len(results)} tactics tested.")


if __name__ == "__main__":
    main()
