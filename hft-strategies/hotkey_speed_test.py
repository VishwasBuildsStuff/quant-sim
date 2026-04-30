"""
Hotkey Reaction Time Tester
Shows trading signals on screen, measures time until correct hotkey pressed.
Tests: LES BUY (CTRL+B), SCALE OUT (CTRL+E1), DPFL (CTRL+D1), FLATTEN (F12)
Uses keyboard library for detection.

Results: PASS (<500ms), SLOW (500-1000ms), FAIL (>1000ms)
Runs 10 rounds per hotkey, reports average.

Usage:
    python hotkey_speed_test.py
    python hotkey_speed_test.py --rounds 20
"""

import os
import sys
import time
import random
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

# Color support
try:
    import colorama
    colorama.init()
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False

# Keyboard library for hotkey detection
try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False
    print("[WARNING] 'keyboard' library not installed.")
    print("  Install: pip install keyboard")
    print("  Running in fallback mode (will prompt for Enter).")

# ========================================================================
# Constants
# ========================================================================

HOTKEY_TESTS = [
    {"hotkey": "ctrl+b",  "label": "CTRL+B",  "action": "LES_BUY",       "signal": "BUY SIGNAL - Press CTRL+B"},
    {"hotkey": "ctrl+e",  "label": "CTRL+E1", "action": "SCALE_OUT",     "signal": "SCALE OUT - Press CTRL+E"},
    {"hotkey": "ctrl+d",  "label": "CTRL+D1", "action": "DPFL_FLATTEN",  "signal": "DP FLATTEN - Press CTRL+D"},
    {"hotkey": "f12",     "label": "F12",     "action": "EMERGENCY_FLAT", "signal": "EMERGENCY FLATTEN - Press F12"},
]

PASS_THRESHOLD_MS = 500
SLOW_THRESHOLD_MS = 1000


# ========================================================================
# Color helpers
# ========================================================================

def color_text(text: str, color: str) -> str:
    """Return colored text string."""
    if not HAS_COLORAMA:
        return text
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "bold": "\033[1m",
        "reset": "\033[0m",
    }
    c = colors.get(color, "")
    reset = colors["reset"]
    return f"{c}{text}{reset}"


# ========================================================================
# Hotkey Tester
# ========================================================================

@dataclass
class TestResult:
    hotkey: str
    action: str
    reaction_ms: float
    verdict: str  # PASS, SLOW, FAIL


@dataclass
class TestRound:
    round_num: int
    hotkey: str
    label: str
    action: str
    reaction_ms: float
    verdict: str


class HotkeySpeedTester:
    """
    Measures hotkey reaction times for HFT trading hotkeys.
    Runs N rounds per hotkey, reports statistics.
    """

    def __init__(self, rounds_per_hotkey: int = 10, delay_range: Tuple[float, float] = (1.0, 3.0)):
        self.rounds_per_hotkey = rounds_per_hotkey
        self.delay_range = delay_range
        self.all_results: List[TestRound] = []
        self.current_hotkey: Optional[str] = None
        self.signal_time: float = 0.0
        self.response_received: bool = False

    def _setup_listener(self):
        """Set up keyboard listeners for all test hotkeys."""
        if not HAS_KEYBOARD:
            return

        def make_callback(hk_label):
            def callback():
                if hk_label == self.current_hotkey and not self.response_received:
                    elapsed = (time.time() - self.signal_time) * 1000
                    self.last_reaction_ms = elapsed
                    self.response_received = True
            return callback

        for test in HOTKEY_TESTS:
            keyboard.add_hotkey(test["hotkey"], make_callback(test["label"]))

    def _cleanup_listeners(self):
        """Remove all keyboard listeners."""
        if HAS_KEYBOARD:
            try:
                keyboard.unhook_all()
            except Exception:
                pass

    def _classify(self, reaction_ms: float) -> str:
        if reaction_ms < PASS_THRESHOLD_MS:
            return "PASS"
        elif reaction_ms < SLOW_THRESHOLD_MS:
            return "SLOW"
        else:
            return "FAIL"

    def _print_signal(self, signal_text: str, label: str):
        """Display the signal on screen."""
        print(f"\n{'='*60}")
        print(f"  {color_text(signal_text, 'bold')}")
        print(f"  Target: {color_text(label, 'yellow')}")
        print(f"  Waiting for response...")
        print(f"{'='*60}")

    def _print_result(self, reaction_ms: float, verdict: str, round_num: int, total_rounds: int):
        """Print result for a single round."""
        if verdict == "PASS":
            v_color = "green"
        elif verdict == "SLOW":
            v_color = "yellow"
        else:
            v_color = "red"

        print(f"  Round {round_num}/{total_rounds}: "
              f"{reaction_ms:6.0f}ms  ->  {color_text(verdict, v_color)}")

    def run_single_round(self, test: dict, round_num: int) -> TestRound:
        """Run a single reaction time test round."""
        self.current_hotkey = test["label"]
        self.last_reaction_ms = None
        self.response_received = False

        # Random delay before signal
        delay = random.uniform(*self.delay_range)
        print(f"\n  [Get Ready] Next signal in {delay:.1f}s...")
        time.sleep(delay)

        # Show signal
        self._print_signal(test["signal"], test["label"])
        self.signal_time = time.time()

        # Wait for response (max 3 seconds)
        timeout = 3.0
        start = time.time()

        if HAS_KEYBOARD:
            while time.time() - start < timeout:
                if self.response_received and self.last_reaction_ms is not None:
                    break
                time.sleep(0.005)
        else:
            # Fallback: user presses Enter as proxy
            print("  [FALLBACK] Press ENTER to simulate hotkey press")
            try:
                input()
                self.last_reaction_ms = (time.time() - self.signal_time) * 1000
                self.response_received = True
            except (KeyboardInterrupt, EOFError):
                pass

        if self.response_received and self.last_reaction_ms is not None:
            reaction = self.last_reaction_ms
        else:
            reaction = timeout * 1000  # timeout

        verdict = self._classify(reaction)
        self._print_result(reaction, verdict, round_num, self.rounds_per_hotkey)

        return TestRound(
            round_num=round_num,
            hotkey=test["hotkey"],
            label=test["label"],
            action=test["action"],
            reaction_ms=reaction,
            verdict=verdict,
        )

    def run(self):
        """Run all test rounds and report results."""
        print(f"\n{'#'*60}")
        print(f"#  HFT HOTKEY REACTION TIME TEST")
        print(f"#  Rounds per hotkey: {self.rounds_per_hotkey}")
        print(f"#  PASS: <{PASS_THRESHOLD_MS}ms  |  SLOW: {PASS_THRESHOLD_MS}-{SLOW_THRESHOLD_MS}ms  |  FAIL: >{SLOW_THRESHOLD_MS}ms")
        print(f"{'#'*60}")

        if HAS_KEYBOARD:
            print("\n  [INFO] Using 'keyboard' library for hotkey detection")
            print("  [NOTE] Run as Administrator on Windows for full key detection")
        else:
            print("\n  [FALLBACK MODE] Press ENTER when you see the signal")

        self._setup_listener()

        try:
            for test in HOTKEY_TESTS:
                print(f"\n{'='*60}")
                print(f"  Testing: {color_text(test['label'], 'bold')} -> {test['action']}")
                print(f"{'='*60}")

                for r in range(1, self.rounds_per_hotkey + 1):
                    result = self.run_single_round(test, r)
                    self.all_results.append(result)

                    # Small pause between rounds
                    time.sleep(0.5)

        except KeyboardInterrupt:
            print("\n\n  [STOP] Test interrupted by user")
        finally:
            self._cleanup_listeners()

        self._print_summary()

    def _print_summary(self):
        """Print comprehensive results summary."""
        print(f"\n\n{'#'*60}")
        print(f"#  HOTKEY SPEED TEST RESULTS")
        print(f"#  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*60}")

        # Per-hotkey stats
        print(f"\n  {'Hotkey':<10} {'Avg(ms)':>8} {'Min(ms)':>8} {'Max(ms)':>8} "
              f"{'PASS':>5} {'SLOW':>5} {'FAIL':>5} {'Verdict':>8}")
        print(f"  {'-'*65}")

        for test in HOTKEY_TESTS:
            results = [r for r in self.all_results if r.label == test["label"]]
            if not results:
                continue

            reactions = [r.reaction_ms for r in results]
            avg_ms = sum(reactions) / len(reactions)
            min_ms = min(reactions)
            max_ms = max(reactions)
            passes = sum(1 for r in results if r.verdict == "PASS")
            slows = sum(1 for r in results if r.verdict == "SLOW")
            fails = sum(1 for r in results if r.verdict == "FAIL")

            overall = "PASS" if passes > len(results) * 0.5 else ("SLOW" if slows > fails else "FAIL")
            v_color = "green" if overall == "PASS" else ("yellow" if overall == "SLOW" else "red")

            print(f"  {test['label']:<10} {avg_ms:>8.0f} {min_ms:>8.0f} {max_ms:>8.0f} "
                  f"{passes:>5} {slows:>5} {fails:>5} "
                  f"{color_text(overall, v_color):>8}")

        print(f"  {'-'*65}")

        # Overall
        all_reactions = [r.reaction_ms for r in self.all_results]
        if all_reactions:
            overall_avg = sum(all_reactions) / len(all_reactions)
            total_passes = sum(1 for r in self.all_results if r.verdict == "PASS")
            pass_rate = total_passes / len(self.all_results) * 100

            print(f"\n  Overall Average: {overall_avg:.0f}ms")
            print(f"  Pass Rate: {pass_rate:.0f}% ({total_passes}/{len(self.all_results)})")

            # Recommendation
            print(f"\n  {'='*60}")
            if overall_avg < PASS_THRESHOLD_MS:
                print(f"  {color_text('EXCELLENT', 'green')} - Your reaction time is HFT-grade!")
            elif overall_avg < SLOW_THRESHOLD_MS:
                print(f"  {color_text('NEEDS IMPROVEMENT', 'yellow')} - Practice more for sub-500ms targets.")
            else:
                print(f"  {color_text('TOO SLOW', 'red')} - Consider drills to improve reaction speed.")
            print(f"{'='*60}")

        # Save results to file
        result_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            f"hotkey_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        with open(result_file, "w", newline="") as f:
            import csv
            writer = csv.writer(f)
            writer.writerow(["hotkey", "label", "action", "round", "reaction_ms", "verdict"])
            for r in self.all_results:
                writer.writerow([r.hotkey, r.label, r.action, r.round_num,
                                 round(r.reaction_ms, 1), r.verdict])

        print(f"\n  Results saved to: {result_file}")


# ========================================================================
# CLI
# ========================================================================

def main():
    parser = argparse.ArgumentParser(description="HFT Hotkey Reaction Time Tester")
    parser.add_argument("--rounds", type=int, default=10, help="Rounds per hotkey (default: 10)")
    parser.add_argument("--min-delay", type=float, default=1.0, help="Min signal delay (seconds)")
    parser.add_argument("--max-delay", type=float, default=3.0, help="Max signal delay (seconds)")
    args = parser.parse_args()

    tester = HotkeySpeedTester(
        rounds_per_hotkey=args.rounds,
        delay_range=(args.min_delay, args.max_delay),
    )

    try:
        tester.run()
    except KeyboardInterrupt:
        print("\n  Test cancelled.")


if __name__ == "__main__":
    main()
