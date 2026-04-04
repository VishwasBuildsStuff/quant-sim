"""
Multi-Backtest Runner
Wrapper to run from hft-strategies directory
"""

import sys
import os

# Ensure current directory is in path
sys.path.insert(0, os.getcwd())

from examples.multi_backtest import (
    run_multi_backtest,
    run_parameter_sweep,
    run_stress_test,
    run_ensemble_backtest
)

if __name__ == "__main__":
    print("HFT Multi-Backtest Runner")
    print("="*80)
    
    # Run all tests
    run_multi_backtest()
    run_parameter_sweep()
    run_stress_test()
    run_ensemble_backtest()
    
    print("\n" + "="*80)
    print("✅ All multi-backtests complete!")
    print("="*80)
