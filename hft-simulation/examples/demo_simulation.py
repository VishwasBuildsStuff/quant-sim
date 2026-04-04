"""
Market Simulation Engine - Example Usage
Demonstrates all major features of the simulation platform
"""

import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add parent directory to path (hft-simulation contains the modules)
sys.path.insert(0, str(Path(__file__).parent.parent))

from stochastic_processes import (
    GBMParams,
    JumpDiffusionParams,
    GARCHParams,
    HestonParams,
    GeometricBrownianMotion,
    MertonJumpDiffusion,
    GARCHProcess,
    HestonModel,
    MarketMicrostructureNoise,
    MarketRegimeSimulator
)
from historical_scenarios import (
    HistoricalScenarioLibrary,
    ScenarioType
)
from macro_events import (
    SimulationConfig,
    MarketSimulationEngine,
    MacroEventScheduler
)


def demo_stochastic_processes():
    """Demonstrate different stochastic price processes"""
    print("=" * 70)
    print("DEMO: Stochastic Price Processes")
    print("=" * 70)
    
    n_steps = 1000
    np.random.seed(42)
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('Stochastic Price Processes Comparison', fontsize=16)
    
    # GBM
    gbm_params = GBMParams(
        initial_price=100.0,
        mu=0.05,
        sigma=0.20,
        seed=42
    )
    gbm = GeometricBrownianMotion(gbm_params)
    gbm_prices = gbm.generate(n_steps)
    
    axes[0, 0].plot(gbm_prices, label='GBM', linewidth=1.5)
    axes[0, 0].set_title('Geometric Brownian Motion')
    axes[0, 0].set_ylabel('Price')
    axes[0, 0].legend()
    axes[0, 0].grid(True, alpha=0.3)
    
    # Jump Diffusion
    jd_params = JumpDiffusionParams(
        initial_price=100.0,
        mu=0.05,
        sigma=0.20,
        jump_intensity=10.0,
        jump_mean=-0.02,
        jump_std=0.05,
        seed=42
    )
    jd = MertonJumpDiffusion(jd_params)
    jd_prices = jd.generate(n_steps)
    
    axes[0, 1].plot(jd_prices, label='Jump Diffusion', linewidth=1.5)
    axes[0, 1].set_title('Merton Jump Diffusion')
    axes[0, 1].set_ylabel('Price')
    axes[0, 1].legend()
    axes[0, 1].grid(True, alpha=0.3)
    
    # GARCH
    garch_params = GARCHParams(
        initial_price=100.0,
        omega=0.000002,
        alpha=0.1,
        beta=0.85,
        seed=42
    )
    garch = GARCHProcess(garch_params)
    garch_prices, garch_vars = garch.generate(n_steps)
    
    axes[1, 0].plot(garch_prices, label='GARCH', linewidth=1.5)
    axes[1, 0].set_title('GARCH (Volatility Clustering)')
    axes[1, 0].set_ylabel('Price')
    axes[1, 0].set_xlabel('Time Step')
    axes[1, 0].legend()
    axes[1, 0].grid(True, alpha=0.3)
    
    # Heston
    heston_params = HestonParams(
        initial_price=100.0,
        mu=0.05,
        kappa=2.0,
        theta=0.04,
        sigma=0.3,
        rho=-0.7,
        v0=0.04,
        seed=42
    )
    heston = HestonModel(heston_params)
    heston_prices, heston_vars = heston.generate(n_steps)
    
    axes[1, 1].plot(heston_prices, label='Heston', linewidth=1.5)
    axes[1, 1].set_title('Heston Stochastic Volatility')
    axes[1, 1].set_ylabel('Price')
    axes[1, 1].set_xlabel('Time Step')
    axes[1, 1].legend()
    axes[1, 1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('stochastic_processes.png', dpi=150, bbox_inches='tight')
    print("✓ Saved: stochastic_processes.png")
    plt.close()


def demo_market_regimes():
    """Demonstrate different market regimes"""
    print("\n" + "=" * 70)
    print("DEMO: Market Regimes")
    print("=" * 70)
    
    n_steps = 500
    regimes = MarketRegimeSimulator.get_regime_names()
    
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    fig.suptitle('Market Regime Comparison', fontsize=16)
    axes = axes.flatten()
    
    for idx, regime_name in enumerate(regimes):
        process = MarketRegimeSimulator.create_regime_process(
            regime_name,
            initial_price=100.0
        )
        prices = process.generate(n_steps)
        
        row, col = divmod(idx, 3)
        axes[idx].plot(prices, linewidth=1.5)
        axes[idx].set_title(regime_name.replace('_', ' ').title(), fontsize=11)
        axes[idx].set_ylabel('Price')
        axes[idx].set_xlabel('Time Step')
        axes[idx].grid(True, alpha=0.3)
        
        # Calculate and display stats
        returns = np.diff(np.log(prices))
        annualized_vol = np.std(returns) * np.sqrt(252) * 100
        max_dd = (np.minimum.accumulate(prices) / prices - 1).min() * 100
        
        axes[idx].text(
            0.02, 0.98,
            f'Vol: {annualized_vol:.1f}%\nMax DD: {max_dd:.1f}%',
            transform=axes[idx].transAxes,
            verticalalignment='top',
            fontsize=9,
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5)
        )
    
    plt.tight_layout()
    plt.savefig('market_regimes.png', dpi=150, bbox_inches='tight')
    print("✓ Saved: market_regimes.png")
    plt.close()


def demo_historical_scenarios():
    """Demonstrate historical stress scenarios"""
    print("\n" + "=" * 70)
    print("DEMO: Historical Stress Scenarios")
    print("=" * 70)
    
    scenarios = HistoricalScenarioLibrary.get_all_scenarios()
    
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    fig.suptitle('Historical Stress Scenarios', fontsize=16)
    axes = axes.flatten()
    
    for idx, (scenario_name, scenario) in enumerate(scenarios.items()):
        print(f"\nScenario: {scenario.name}")
        print(f"  Type: {scenario.scenario_type.value}")
        print(f"  Max Drawdown: {scenario.max_drawdown * 100:.1f}%")
        print(f"  Recovery Days: {scenario.recovery_days}")
        print(f"  Volatility Spike: {scenario.volatility_spike:.1f}x")
        print(f"  Correlation Breakdown: {scenario.correlation_breakdown}")
        
        # Simulate scenario
        config = SimulationConfig(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            asset_names=["SPY"],
            process_type="jump_diffusion",
            seed=42
        )
        
        engine = MarketSimulationEngine(config)
        n_steps = 200
        output = engine.simulate_with_scenario(scenario_name, n_steps)
        
        prices = output.prices["SPY"]
        
        axes[idx].plot(prices, linewidth=1.5)
        axes[idx].set_title(scenario.name, fontsize=11)
        axes[idx].set_ylabel('Price')
        axes[idx].set_xlabel('Time Step')
        axes[idx].grid(True, alpha=0.3)
        
        # Mark max drawdown
        peak = np.maximum.accumulate(prices)
        drawdown = (prices - peak) / peak
        min_idx = np.argmin(drawdown)
        axes[idx].axvline(x=min_idx, color='r', linestyle='--', alpha=0.5)
        axes[idx].text(
            min_idx, prices[min_idx],
            f'{drawdown[min_idx]*100:.1f}%',
            fontsize=9,
            color='red'
        )
    
    plt.tight_layout()
    plt.savefig('historical_scenarios.png', dpi=150, bbox_inches='tight')
    print("\n✓ Saved: historical_scenarios.png")
    plt.close()


def demo_complete_simulation():
    """Demonstrate complete market simulation with all features"""
    print("\n" + "=" * 70)
    print("DEMO: Complete Market Simulation")
    print("=" * 70)
    
    # Configuration
    config = SimulationConfig(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 6, 30),
        n_assets=5,
        asset_names=["SPY", "QQQ", "IWM", "TLT", "GLD"],
        process_type="jump_diffusion",
        initial_prices={
            "SPY": 450.0,
            "QQQ": 380.0,
            "IWM": 195.0,
            "TLT": 95.0,
            "GLD": 185.0
        },
        base_volatility=0.20,
        base_drift=0.05,
        seed=42
    )
    
    print(f"Configuration:")
    print(f"  Assets: {config.asset_names}")
    print(f"  Period: {config.start_date.date()} to {config.end_date.date()}")
    print(f"  Process: {config.process_type}")
    print(f"  Base Vol: {config.base_volatility * 100:.1f}%")
    
    # Run simulation
    engine = MarketSimulationEngine(config)
    n_steps = 1000
    
    print(f"\nRunning simulation with {n_steps} steps...")
    output = engine.simulate(
        n_steps=n_steps,
        include_macro_events=True,
        include_microstructure=True,
        shock_probability=0.005
    )
    
    print(f"\nSimulation Results:")
    print(f"  Generated {len(output.prices)} asset paths")
    print(f"  Time steps: {n_steps}")
    
    # Plot results
    fig, axes = plt.subplots(3, 2, figsize=(14, 12))
    fig.suptitle('Complete Market Simulation Results', fontsize=16)
    
    # Price paths
    ax = axes[0, 0]
    for asset_name in config.asset_names:
        prices = output.prices[asset_name]
        normalized = prices / prices[0] * 100
        ax.plot(normalized, label=asset_name, linewidth=1.5)
    ax.set_title('Normalized Price Paths')
    ax.set_ylabel('Normalized Price')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Volume profile
    ax = axes[0, 1]
    for asset_name in config.asset_names[:3]:  # Top 3 for clarity
        ax.plot(output.volumes[asset_name], label=asset_name, linewidth=1.0, alpha=0.7)
    ax.set_title('Trading Volume')
    ax.set_ylabel('Volume')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Realized volatility
    ax = axes[1, 0]
    for asset_name in config.asset_names:
        ax.plot(output.realized_volatility[asset_name] * 100, label=asset_name, linewidth=1.2)
    ax.set_title('Realized Volatility (Annualized)')
    ax.set_ylabel('Volatility %')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Market regimes
    ax = axes[1, 1]
    regime_colors = {
        'bull': 'green',
        'bear': 'red',
        'sideways': 'gray',
        'high_freq_noise': 'orange',
        'black_swan': 'purple',
        'unknown': 'white'
    }
    
    for i, regime in enumerate(output.market_regime):
        color = regime_colors.get(regime, 'white')
        ax.axvline(x=i, color=color, alpha=0.3)
    ax.set_title('Market Regime Classification')
    ax.set_ylabel('Regime')
    ax.grid(True, alpha=0.3)
    
    # Drawdown
    ax = axes[2, 0]
    for asset_name in config.asset_names:
        prices = output.prices[asset_name]
        peak = np.maximum.accumulate(prices)
        drawdown = (prices - peak) / peak * 100
        ax.plot(drawdown, label=asset_name, linewidth=1.2)
    ax.set_title('Drawdown (%)')
    ax.set_ylabel('Drawdown %')
    ax.set_xlabel('Time Step')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    
    # Returns distribution
    ax = axes[2, 1]
    for asset_name in config.asset_names:
        returns = output.returns[asset_name]
        ax.hist(returns, bins=100, alpha=0.5, label=asset_name, density=True)
    ax.set_title('Returns Distribution')
    ax.set_xlabel('Return')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('complete_simulation.png', dpi=150, bbox_inches='tight')
    print("✓ Saved: complete_simulation.png")
    plt.close()
    
    # Print summary statistics
    print("\n" + "=" * 70)
    print("SIMULATION SUMMARY STATISTICS")
    print("=" * 70)
    
    for asset_name in config.asset_names:
        prices = output.prices[asset_name]
        returns = output.returns[asset_name]
        
        total_return = (prices[-1] / prices[0] - 1) * 100
        annualized_vol = np.std(returns) * np.sqrt(252) * 100
        max_drawdown = (np.minimum.accumulate(prices) / prices - 1).min() * 100
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        
        print(f"\n{asset_name}:")
        print(f"  Total Return: {total_return:.2f}%")
        print(f"  Annualized Vol: {annualized_vol:.2f}%")
        print(f"  Max Drawdown: {max_drawdown:.2f}%")
        print(f"  Sharpe Ratio: {sharpe:.2f}")
        print(f"  Final Price: ${prices[-1]:.2f}")


def demo_flash_crash_deep_dive():
    """Deep dive analysis of 2010 Flash Crash scenario"""
    print("\n" + "=" * 70)
    print("DEEP DIVE: 2010 Flash Crash Analysis")
    print("=" * 70)
    
    config = SimulationConfig(
        start_date=datetime(2010, 5, 6),
        end_date=datetime(2010, 5, 7),
        asset_names=["ES", "SPY", "QQQ"],
        process_type="jump_diffusion",
        initial_prices={"ES": 1080.0, "SPY": 110.0, "QQQ": 44.0},
        seed=42
    )
    
    engine = MarketSimulationEngine(config)
    output = engine.simulate_with_scenario("flash_crash_2010", n_steps=500)
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('2010 Flash Crash - Detailed Analysis', fontsize=16)
    
    # Price paths with crash visualization
    ax = axes[0, 0]
    for asset in ["SPY"]:
        prices = output.prices[asset]
        normalized = prices / prices[0] * 100
        ax.plot(normalized, linewidth=2)
    ax.set_title('Flash Crash Price Action')
    ax.set_ylabel('Normalized Price')
    ax.axhline(y=91, color='r', linestyle='--', alpha=0.5, label='9% Drop')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Intraday volatility spike
    ax = axes[0, 1]
    vol = output.realized_volatility["SPY"] * 100
    ax.plot(vol, linewidth=2, color='orange')
    ax.set_title('Volatility Spike During Crash')
    ax.set_ylabel('Realized Vol %')
    ax.set_xlabel('Time Step')
    ax.grid(True, alpha=0.3)
    
    # Volume surge
    ax = axes[1, 0]
    volume = output.volumes["SPY"]
    ax.plot(volume, linewidth=1.5, color='green')
    ax.set_title('Volume Surge During Crash')
    ax.set_ylabel('Volume')
    ax.set_xlabel('Time Step')
    ax.grid(True, alpha=0.3)
    
    # Drawdown
    ax = axes[1, 1]
    prices = output.prices["SPY"]
    peak = np.maximum.accumulate(prices)
    drawdown = (prices - peak) / peak * 100
    ax.fill_between(range(len(drawdown)), drawdown, 0, alpha=0.5, color='red')
    ax.set_title('Drawdown Profile')
    ax.set_ylabel('Drawdown %')
    ax.set_xlabel('Time Step')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('flash_crash_analysis.png', dpi=150, bbox_inches='tight')
    print("✓ Saved: flash_crash_analysis.png")
    plt.close()
    
    # Print crash statistics
    prices = output.prices["SPY"]
    peak = np.max(prices)
    trough = np.min(prices)
    crash_magnitude = (trough - peak) / peak * 100
    
    print(f"\nFlash Crash Statistics:")
    print(f"  Peak Price: ${peak:.2f}")
    print(f"  Trough Price: ${trough:.2f}")
    print(f"  Crash Magnitude: {crash_magnitude:.2f}%")
    print(f"  Recovery: {'Yes' if prices[-1] > peak * 0.95 else 'Partial'}")


if __name__ == "__main__":
    print("HFT Market Simulation Engine - Demonstration")
    print("=" * 70)
    
    # Run all demos
    demo_stochastic_processes()
    demo_market_regimes()
    demo_historical_scenarios()
    demo_complete_simulation()
    demo_flash_crash_deep_dive()
    
    print("\n" + "=" * 70)
    print("All demonstrations complete!")
    print("=" * 70)
