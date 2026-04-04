"""
Backtesting Demo Runner
Wrapper to run from hft-strategies directory
"""

import sys
import os

# Ensure current directory is in path
sys.path.insert(0, os.getcwd())

from examples.demo_backtesting import (
    demo_simple_backtest,
    demo_strategy_comparison,
    demo_walk_forward_optimization,
    demo_stress_test
)

if __name__ == "__main__":
    print("HFT Backtesting Engine - Quick Demo")
    print("="*70)
    
    demo_simple_backtest()
    demo_strategy_comparison()
    demo_walk_forward_optimization()
    demo_stress_test()
    
    print("\n" + "="*70)
    print("✅ Demo complete!")
    print("="*70)
