"""
Compare 2008 Financial Crisis vs 2020 Pandemic Crash
Wrapper script to run from hft-simulation directory
"""

import sys
import os

# Ensure current directory is in path
sys.path.insert(0, os.getcwd())

from examples.compare_crises import run_scenario_comparison

if __name__ == "__main__":
    run_scenario_comparison()
