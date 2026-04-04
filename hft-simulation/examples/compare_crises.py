"""
Compare 2008 Financial Crisis vs 2020 Pandemic Crash
Demonstrates key differences in crash dynamics and recovery
"""

import sys
import os
from pathlib import Path

# Add parent directory to path BEFORE importing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from stochastic_processes import JumpDiffusionParams, MertonJumpDiffusion
from historical_scenarios import HistoricalScenarioLibrary
from macro_events import SimulationConfig, MarketSimulationEngine

def run_scenario_comparison():
    """Run and compare 2008 GFC vs 2020 Pandemic scenarios"""
    
    print("="*70)
    print("Scenario Comparison: 2008 Financial Crisis vs 2020 Pandemic")
    print("="*70)
    
    # Get scenario details
    scenarios = {
        "financial_crisis_2008": HistoricalScenarioLibrary.get_scenario("financial_crisis_2008"),
        "pandemic_2020": HistoricalScenarioLibrary.get_scenario("pandemic_2020")
    }
    
    # Print scenario metadata
    for name, scenario in scenarios.items():
        print(f"\n{name.upper()}:")
        print(f"  Description: {scenario.description[:100]}...")
        print(f"  Date Range: {scenario.date_range[0]} to {scenario.date_range[1]}")
        print(f"  Max Drawdown: {scenario.max_drawdown*100:.1f}%")
        print(f"  Recovery Time: {scenario.recovery_days} days ({scenario.recovery_days/365:.1f} years)")
        print(f"  Volatility Spike: {scenario.volatility_spike:.1f}x normal")
        print(f"  Correlation Breakdown: {'Yes' if scenario.correlation_breakdown else 'No'}")
        print(f"  Number of Phases: {len(scenario.phases)}")
        for i, phase in enumerate(scenario.phases):
            print(f"    Phase {i+1}: {phase.name} ({phase.duration_days} days, vol={phase.volatility:.0%})")
    
    # Simulate both scenarios
    print("\n" + "="*70)
    print("Running simulations...")
    print("="*70)
    
    results = {}
    
    for scenario_name in scenarios.keys():
        config = SimulationConfig(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            asset_names=["SPY"],
            process_type="jump_diffusion",
            seed=42
        )
        
        engine = MarketSimulationEngine(config)
        n_steps = 300
        output = engine.simulate_with_scenario(scenario_name, n_steps)
        
        results[scenario_name] = {
            'output': output,
            'prices': output.prices['SPY'],
            'returns': output.returns['SPY'],
            'volume': output.volumes['SPY'],
            'regime': output.market_regime,
            'realized_vol': output.realized_volatility['SPY']
        }
        
        prices = results[scenario_name]['prices']
        peak = np.max(prices)
        trough = np.min(prices)
        drawdown = (trough - peak) / peak * 100
        final_return = (prices[-1] - prices[0]) / prices[0] * 100
        
        print(f"\n{scenario_name}:")
        print(f"  Start Price: ${prices[0]:.2f}")
        print(f"  Peak Price: ${peak:.2f}")
        print(f"  Trough Price: ${trough:.2f}")
        print(f"  Max Drawdown: {drawdown:.1f}%")
        print(f"  Final Return: {final_return:.1f}%")
        print(f"  Steps to trough: {np.argmin(prices)}/{n_steps}")
    
    # Create comprehensive comparison visualization
    print("\nGenerating comparison charts...")
    fig = plt.figure(figsize=(20, 16))
    fig.suptitle('2008 Financial Crisis vs 2020 Pandemic Crash - Comparison', 
                 fontsize=18, fontweight='bold')
    
    # 1. Normalized price paths (overlay)
    ax1 = plt.subplot(3, 2, 1)
    for name in results:
        prices = results[name]['prices']
        normalized = prices / prices[0] * 100
        label = "2008 Financial Crisis" if "2008" in name else "2020 Pandemic"
        ax1.plot(normalized, linewidth=2, label=label)
    
    ax1.set_title('Normalized Price Comparison', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Normalized Price (Start = 100)')
    ax1.set_xlabel('Time Step')
    ax1.legend(loc='upper right', fontsize=11)
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=100, color='gray', linestyle='--', linewidth=1)
    
    # 2. 2008 GFC detailed
    ax2 = plt.subplot(3, 2, 2)
    prices_2008 = results['financial_crisis_2008']['prices']
    x = range(len(prices_2008))
    ax2.fill_between(x, prices_2008, prices_2008[0], alpha=0.5, 
                     where=np.array(prices_2008) < prices_2008[0], 
                     color='red', label='Below Start')
    ax2.fill_between(x, prices_2008, prices_2008[0], alpha=0.5, 
                     where=np.array(prices_2008) >= prices_2008[0], 
                     color='green', label='Above Start')
    ax2.plot(prices_2008, linewidth=2, color='darkred')
    
    # Mark phases
    phases = scenarios['financial_crisis_2008'].phases
    step_per_phase = len(prices_2008) // len(phases)
    for i, phase in enumerate(phases):
        start = i * step_per_phase
        end = min((i + 1) * step_per_phase, len(prices_2008))
        if start < len(prices_2008):
            ax2.axvline(x=start, color='orange', linestyle=':', alpha=0.5)
            if i < 3:  # Show first 3 phase labels
                ax2.text(start, prices_2008[start], phase.name[:20], 
                        rotation=90, fontsize=7, va='bottom')
    
    ax2.set_title('2008 Financial Crisis - Detailed', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Price')
    ax2.set_xlabel('Time Step')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 3. 2020 Pandemic detailed
    ax3 = plt.subplot(3, 2, 3)
    prices_2020 = results['pandemic_2020']['prices']
    x = range(len(prices_2020))
    ax3.fill_between(x, prices_2020, prices_2020[0], alpha=0.5, 
                     where=np.array(prices_2020) < prices_2020[0], 
                     color='red', label='Below Start')
    ax3.fill_between(x, prices_2020, prices_2020[0], alpha=0.5, 
                     where=np.array(prices_2020) >= prices_2020[0], 
                     color='green', label='Above Start')
    ax3.plot(prices_2020, linewidth=2, color='darkblue')
    
    # Mark phases
    phases = scenarios['pandemic_2020'].phases
    step_per_phase = len(prices_2020) // len(phases)
    for i, phase in enumerate(phases):
        start = i * step_per_phase
        if start < len(prices_2020):
            ax3.axvline(x=start, color='orange', linestyle=':', alpha=0.5)
            if i < 4:
                ax3.text(start, prices_2020[start], phase.name[:20], 
                        rotation=90, fontsize=7, va='bottom')
    
    ax3.set_title('2020 Pandemic Crash - Detailed', fontsize=14, fontweight='bold')
    ax3.set_ylabel('Price')
    ax3.set_xlabel('Time Step')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # 4. Drawdown comparison
    ax4 = plt.subplot(3, 2, 4)
    for name in results:
        prices = results[name]['prices']
        peak = np.maximum.accumulate(prices)
        drawdown = (prices - peak) / peak * 100
        label = "2008 Financial Crisis" if "2008" in name else "2020 Pandemic"
        ax4.fill_between(range(len(drawdown)), drawdown, 0, alpha=0.4, label=label)
        ax4.plot(drawdown, linewidth=1.5)
    
    ax4.set_title('Drawdown Comparison', fontsize=14, fontweight='bold')
    ax4.set_ylabel('Drawdown (%)')
    ax4.set_xlabel('Time Step')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    
    # 5. Volatility comparison
    ax5 = plt.subplot(3, 2, 5)
    for name in results:
        vol = results[name]['realized_vol'] * 100
        label = "2008 Financial Crisis" if "2008" in name else "2020 Pandemic"
        ax5.plot(vol, linewidth=2, label=label)
    
    ax5.set_title('Realized Volatility Comparison', fontsize=14, fontweight='bold')
    ax5.set_ylabel('Annualized Volatility (%)')
    ax5.set_xlabel('Time Step')
    ax5.legend()
    ax5.grid(True, alpha=0.3)
    
    # 6. Volume comparison
    ax6 = plt.subplot(3, 2, 6)
    for name in results:
        volume = results[name]['volume']
        label = "2008 Financial Crisis" if "2008" in name else "2020 Pandemic"
        ax6.plot(volume, linewidth=1.5, alpha=0.7, label=label)
    
    ax6.set_title('Trading Volume Comparison', fontsize=14, fontweight='bold')
    ax6.set_ylabel('Volume')
    ax6.set_xlabel('Time Step')
    ax6.legend()
    ax6.grid(True, alpha=0.3)
    
    plt.tight_layout()
    output_file = Path(__file__).parent / 'crisis_comparison.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"✓ Saved: {output_file}")
    plt.close()
    
    # Print key differences
    print("\n" + "="*70)
    print("KEY DIFFERENCES")
    print("="*70)
    
    prices_2008 = results['financial_crisis_2008']['prices']
    prices_2020 = results['pandemic_2020']['prices']
    
    dd_2008 = (np.min(prices_2008) - np.max(prices_2008)) / np.max(prices_2008) * 100
    dd_2020 = (np.min(prices_2020) - np.max(prices_2020)) / np.max(prices_2020) * 100
    
    ret_2008 = (prices_2008[-1] - prices_2008[0]) / prices_2008[0] * 100
    ret_2020 = (prices_2020[-1] - prices_2020[0]) / prices_2020[0] * 100
    
    print(f"\n{'Metric':<25} {'2008 GFC':>12} {'2020 Pandemic':>15}")
    print("-"*55)
    print(f"{'Max Drawdown':<25} {dd_2008:>11.1f}% {dd_2020:>14.1f}%")
    print(f"{'Final Return':<25} {ret_2008:>11.1f}% {ret_2020:>14.1f}%")
    print(f"{'Recovery Time':<25} {'4 years':>12} {'5 months':>15}")
    print(f"{'Crisis Duration':<25} {'~2 years':>12} {'~2 months':>15}")
    print(f"{'Volatility Spike':<25} {'4.5x':>12} {'5.5x':>15}")
    print(f"{'Cause':<25} {'Credit crisis':>12} {'Health crisis':>15}")
    print(f"{'Fed Response':<25} {'Gradual':>12} {'Immediate':>15}")
    print(f"{'Market Structure':<25} {'Pre-HFT era':>12} {'HFT dominant':>15}")
    
    print("\n" + "="*70)
    print("✅ Comparison complete! Open crisis_comparison.png to see all charts")
    print("="*70)

if __name__ == "__main__":
    run_scenario_comparison()
