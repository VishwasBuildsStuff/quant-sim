"""
Quick test script for HFT Simulation Platform
Tests core functionality without external dependencies
"""

import sys
import os

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'hft-simulation'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'hft-strategies'))

print("="*70)
print("HFT Simulation Platform - Quick Test")
print("="*70)

# Test 1: Import modules
print("\n[Test 1] Importing modules...")
try:
    from stochastic_processes import (
        GBMParams, JumpDiffusionParams, GARCHParams,
        GeometricBrownianMotion, MertonJumpDiffusion, GARCHProcess
    )
    print("  ✓ Stochastic processes imported successfully")
except Exception as e:
    print(f"  ✗ Import failed: {e}")
    sys.exit(1)

try:
    from historical_scenarios import HistoricalScenarioLibrary
    print("  ✓ Historical scenarios imported successfully")
except Exception as e:
    print(f"  ✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Run stochastic processes
print("\n[Test 2] Generating price paths...")
try:
    import numpy as np
    np.random.seed(42)
    
    # GBM
    gbm_params = GBMParams(initial_price=100.0, mu=0.05, sigma=0.20, seed=42)
    gbm = GeometricBrownianMotion(gbm_params)
    gbm_prices = gbm.generate(100)
    print(f"  ✓ GBM: Generated {len(gbm_prices)} prices, final=${gbm_prices[-1]:.2f}")
    
    # Jump Diffusion
    jd_params = JumpDiffusionParams(
        initial_price=100.0, mu=0.05, sigma=0.20,
        jump_intensity=10.0, jump_mean=-0.02, jump_std=0.05, seed=42
    )
    jd = MertonJumpDiffusion(jd_params)
    jd_prices = jd.generate(100)
    print(f"  ✓ Jump Diffusion: Generated {len(jd_prices)} prices, final=${jd_prices[-1]:.2f}")
    
    # GARCH
    garch_params = GARCHParams(initial_price=100.0, mu=0.05, seed=42)
    garch = GARCHProcess(garch_params)
    garch_prices, garch_vars = garch.generate(100)
    print(f"  ✓ GARCH: Generated {len(garch_prices)} prices, final vol={np.sqrt(garch_vars[-1]):.4f}")
    
except Exception as e:
    print(f"  ✗ Price generation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Historical scenarios
print("\n[Test 3] Loading historical scenarios...")
try:
    scenarios = HistoricalScenarioLibrary.get_all_scenarios()
    print(f"  ✓ Loaded {len(scenarios)} scenarios:")
    for name, scenario in scenarios.items():
        print(f"    - {scenario.name}: Max DD={scenario.max_drawdown*100:.1f}%, Recovery={scenario.recovery_days} days")
except Exception as e:
    print(f"  ✗ Scenario loading failed: {e}")
    sys.exit(1)

# Test 4: Market regimes
print("\n[Test 4] Creating market regimes...")
try:
    from stochastic_processes import MarketRegimeSimulator
    
    regimes = MarketRegimeSimulator.get_regime_names()
    print(f"  ✓ Available regimes: {', '.join(regimes)}")
    
    # Create bull market process
    bull_process = MarketRegimeSimulator.create_regime_process('bull', initial_price=100.0)
    bull_prices = bull_process.generate(50)
    print(f"  ✓ Bull market: Generated {len(bull_prices)} prices")
    
except Exception as e:
    print(f"  ✗ Regime creation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Macro events
print("\n[Test 5] Macro event scheduling...")
try:
    from datetime import datetime
    from macro_events import MacroEventScheduler
    
    scheduler = MacroEventScheduler()
    events = scheduler.generate_scheduled_events(
        datetime(2024, 1, 1),
        datetime(2024, 3, 31),
        seed=42
    )
    print(f"  ✓ Generated {len(events)} scheduled events for Q1 2024")
    for event in events[:3]:
        print(f"    - {event.name} on {event.date.date()} (impact: {event.magnitude:.2f})")
    if len(events) > 3:
        print(f"    ... and {len(events)-3} more events")
        
except Exception as e:
    print(f"  ✗ Event scheduling failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*70)
print("✅ All tests passed successfully!")
print("="*70)
print("\nNext steps:")
print("  1. Install full dependencies: pip install numpy scipy matplotlib")
print("  2. Run complete demo: python hft-simulation/examples/demo_simulation.py")
print("  3. Build Rust engine: cd hft-matching-engine && cargo build --release")
print("  4. Read documentation: docs/QUICK_START.md")
