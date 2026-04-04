"""
Multi-Backtest Runner
Run multiple backtests simultaneously and compare results
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from datetime import datetime, timedelta
from backtesting_engine import (
    BacktestEngine,
    MovingAverageCrossoverStrategy,
    MeanReversionStrategy,
    WalkForwardOptimizer,
    PercentageCommission,
    PercentageSlippage
)

def generate_test_data(n_days=504, seed=42, mu=0.08, sigma=0.20):
    """Generate synthetic price data"""
    np.random.seed(seed)
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(n_days)]
    dt = 1/252
    log_returns = np.random.normal(mu * dt, sigma * np.sqrt(dt), n_days)
    prices = 100 * np.exp(np.cumsum(log_returns))
    return dates, prices


def run_multi_backtest():
    """Run multiple backtests with different strategies"""
    
    print("="*80)
    print("MULTI-BACKTEST RUNNER - Running 6 Strategies Simultaneously")
    print("="*80)
    
    # Generate common test data
    dates, prices = generate_test_data(n_days=504, seed=42)
    
    print(f"\nTest Data: {len(prices)} days")
    print(f"Price Range: ${prices[0]:.2f} → ${prices[-1]:.2f}")
    print(f"Buy & Hold Return: {(prices[-1]/prices[0]-1)*100:.2f}%")
    
    # Define multiple strategies
    strategies = [
        {
            'name': 'MA Crossover (10/30)',
            'strategy': MovingAverageCrossoverStrategy,
            'params': {'short_window': 10, 'long_window': 30}
        },
        {
            'name': 'MA Crossover (20/50)',
            'strategy': MovingAverageCrossoverStrategy,
            'params': {'short_window': 20, 'long_window': 50}
        },
        {
            'name': 'MA Crossover (50/200)',
            'strategy': MovingAverageCrossoverStrategy,
            'params': {'short_window': 50, 'long_window': 200}
        },
        {
            'name': 'Mean Reversion (20, 2σ)',
            'strategy': MeanReversionStrategy,
            'params': {'window': 20, 'num_std': 2.0}
        },
        {
            'name': 'Mean Reversion (50, 1.5σ)',
            'strategy': MeanReversionStrategy,
            'params': {'window': 50, 'num_std': 1.5}
        },
        {
            'name': 'Mean Reversion (100, 2.5σ)',
            'strategy': MeanReversionStrategy,
            'params': {'window': 100, 'num_std': 2.5}
        }
    ]
    
    # Run all backtests
    results = []
    
    for i, strat_config in enumerate(strategies, 1):
        print(f"\n[{i}/{len(strategies)}] Running: {strat_config['name']}...")
        
        engine = BacktestEngine(
            initial_capital=1_000_000.0,
            commission_model=PercentageCommission(0.001),
            slippage_model=PercentageSlippage(0.0005)
        )
        
        strategy = strat_config['strategy'](strat_config['params'])
        engine.add_strategy(strategy)
        engine.load_price_data("SPY", dates, prices)
        
        result = engine.run_backtest()
        result['strategy_name'] = strat_config['name']
        results.append(result)
        
        # Print summary
        print(f"  Return: {result['total_return_pct']:+.2f}% | "
              f"Sharpe: {result['sharpe_ratio']:.2f} | "
              f"Max DD: {result['max_drawdown_pct']:.2f}% | "
              f"Trades: {result['total_trades']}")
    
    # Print comprehensive comparison table
    print("\n" + "="*80)
    print("COMPREHENSIVE STRATEGY COMPARISON")
    print("="*80)
    
    header = f"{'Strategy':<30} {'Return':>9} {'Sharpe':>8} {'Sortino':>8} {'MaxDD':>8} {'Win%':>8} {'Trades':>7}"
    print(header)
    print("-"*90)
    
    for r in results:
        print(f"{r['strategy_name']:<30} "
              f"{r['total_return_pct']:>+8.2f}% "
              f"{r['sharpe_ratio']:>8.2f} "
              f"{r['sortino_ratio']:>8.2f} "
              f"{r['max_drawdown_pct']:>7.2f}% "
              f"{r['win_rate_pct']:>7.2f}% "
              f"{r['total_trades']:>7}")
    
    # Find best performers
    best_return = max(results, key=lambda x: x['total_return_pct'])
    best_sharpe = max(results, key=lambda x: x['sharpe_ratio'])
    best_sortino = max(results, key=lambda x: x['sortino_ratio'])
    lowest_dd = min(results, key=lambda x: x['max_drawdown_pct'])
    highest_win = max(results, key=lambda x: x['win_rate_pct'])
    most_trades = max(results, key=lambda x: x['total_trades'])
    
    print("\n" + "="*80)
    print("WINNERS BY CATEGORY")
    print("="*80)
    print(f"🏆 Best Return:    {best_return['strategy_name']:<30} ({best_return['total_return_pct']:+.2f}%)")
    print(f"🏆 Best Sharpe:    {best_sharpe['strategy_name']:<30} ({best_sharpe['sharpe_ratio']:.2f})")
    print(f"🏆 Best Sortino:   {best_sortino['strategy_name']:<30} ({best_sortino['sortino_ratio']:.2f})")
    print(f"🏆 Lowest Drawdown:{lowest_dd['strategy_name']:<30} ({lowest_dd['max_drawdown_pct']:.2f}%)")
    print(f"🏆 Highest Win %:  {highest_win['strategy_name']:<30} ({highest_win['win_rate_pct']:.2f}%)")
    print(f"🏆 Most Trades:    {most_trades['strategy_name']:<30} ({most_trades['total_trades']})")
    
    # Calculate ensemble performance (average of all strategies)
    avg_return = np.mean([r['total_return_pct'] for r in results])
    avg_sharpe = np.mean([r['sharpe_ratio'] for r in results])
    avg_dd = np.mean([r['max_drawdown_pct'] for r in results])
    
    print("\n" + "-"*80)
    print(f"{'Ensemble Average (6 strategies)':<30} "
          f"{avg_return:>+8.2f}% "
          f"{avg_sharpe:>8.2f} "
          f"{'N/A':>8} "
          f"{avg_dd:>7.2f}% "
          f"{'N/A':>7} "
          f"{'N/A':>7}")
    print("="*80)
    
    return results


def run_parameter_sweep():
    """Run parameter sweep for single strategy"""
    
    print("\n" + "="*80)
    print("PARAMETER SWEEP - MA Crossover Strategy")
    print("="*80)
    
    dates, prices = generate_test_data(n_days=504, seed=42)
    
    # Test different parameter combinations
    short_windows = [5, 10, 20, 30, 50]
    long_windows = [20, 50, 100, 200]
    
    print(f"\nTesting {len(short_windows) * len(long_windows)} parameter combinations...")
    print(f"Short windows: {short_windows}")
    print(f"Long windows: {long_windows}")
    
    results = []
    
    for short in short_windows:
        for long in long_windows:
            if short >= long:
                continue
            
            engine = BacktestEngine(initial_capital=1_000_000.0)
            strategy = MovingAverageCrossoverStrategy({
                'short_window': short,
                'long_window': long
            })
            engine.add_strategy(strategy)
            engine.load_price_data("SPY", dates, prices)
            
            result = engine.run_backtest()
            results.append({
                'short': short,
                'long': long,
                'return': result['total_return_pct'],
                'sharpe': result['sharpe_ratio'],
                'max_dd': result['max_drawdown_pct'],
                'trades': result['total_trades']
            })
    
    # Sort by Sharpe ratio
    results.sort(key=lambda x: x['sharpe'], reverse=True)
    
    # Print top 10
    print("\n" + "="*80)
    print("TOP 10 PARAMETER COMBINATIONS (by Sharpe)")
    print("="*80)
    print(f"{'Short MA':<12} {'Long MA':<12} {'Return':>9} {'Sharpe':>8} {'MaxDD':>8} {'Trades':>8}")
    print("-"*70)
    
    for r in results[:10]:
        print(f"{r['short']:<12} {r['long']:<12} {r['return']:>+8.2f}% {r['sharpe']:>8.2f} {r['max_dd']:>7.2f}% {r['trades']:>8}")
    
    # Worst 5
    print("\n" + "-"*70)
    print("BOTTOM 5 (by Sharpe):")
    print("-"*70)
    for r in results[-5:]:
        print(f"{r['short']:<12} {r['long']:<12} {r['return']:>+8.2f}% {r['sharpe']:>8.2f} {r['max_dd']:>7.2f}% {r['trades']:>8}")
    
    return results


def run_stress_test():
    """Test strategies across different market regimes"""
    
    print("\n" + "="*80)
    print("STRESS TEST - All Strategies Across Market Regimes")
    print("="*80)
    
    regimes = {
        'Bull Market': {'mu': 0.25, 'sigma': 0.15},
        'Bear Market': {'mu': -0.20, 'sigma': 0.40},
        'High Volatility': {'mu': 0.05, 'sigma': 0.60},
        'Low Volatility': {'mu': 0.08, 'sigma': 0.10},
        'Crash Recovery': {'mu': -0.10, 'sigma': 0.80},
    }
    
    strategies = [
        {'name': 'MA (10/30)', 'class': MovingAverageCrossoverStrategy, 'params': {'short_window': 10, 'long_window': 30}},
        {'name': 'MA (20/50)', 'class': MovingAverageCrossoverStrategy, 'params': {'short_window': 20, 'long_window': 50}},
        {'name': 'Mean Rev (20)', 'class': MeanReversionStrategy, 'params': {'window': 20, 'num_std': 2.0}},
        {'name': 'Mean Rev (50)', 'class': MeanReversionStrategy, 'params': {'window': 50, 'num_std': 1.5}},
    ]
    
    # Test matrix: strategies x regimes
    results_matrix = {}
    
    for regime_name, regime_params in regimes.items():
        print(f"\n{'='*60}")
        print(f"REGIME: {regime_name}")
        print(f"{'='*60}")
        
        dates, prices = generate_test_data(
            n_days=252, 
            seed=42,
            mu=regime_params['mu'],
            sigma=regime_params['sigma']
        )
        
        regime_results = []
        
        for strat_config in strategies:
            engine = BacktestEngine(initial_capital=1_000_000.0)
            strategy = strat_config['class'](strat_config['params'])
            engine.add_strategy(strategy)
            engine.load_price_data("SPY", dates, prices)
            
            result = engine.run_backtest()
            regime_results.append({
                'strategy': strat_config['name'],
                'return': result['total_return_pct'],
                'sharpe': result['sharpe_ratio'],
                'max_dd': result['max_drawdown_pct']
            })
        
        results_matrix[regime_name] = regime_results
        
        # Print regime results
        print(f"{'Strategy':<20} {'Return':>10} {'Sharpe':>10} {'MaxDD':>10}")
        print("-"*55)
        for r in regime_results:
            print(f"{r['strategy']:<20} {r['return']:>+9.2f}% {r['sharpe']:>10.2f} {r['max_dd']:>9.2f}%")
    
    # Summary
    print("\n" + "="*80)
    print("STRESS TEST SUMMARY - Best Strategy Per Regime")
    print("="*80)
    
    for regime_name, regime_results in results_matrix.items():
        best = max(regime_results, key=lambda x: x['sharpe'])
        print(f"{regime_name:<20} → {best['strategy']:<20} (Sharpe: {best['sharpe']:.2f})")
    
    return results_matrix


def run_ensemble_backtest():
    """Run ensemble: average signals from multiple strategies"""
    
    print("\n" + "="*80)
    print("ENSEMBLE BACKTEST - Combining Multiple Strategies")
    print("="*80)
    
    dates, prices = generate_test_data(n_days=504, seed=42)
    
    # Run individual strategies
    strategies = [
        MovingAverageCrossoverStrategy({'short_window': 10, 'long_window': 30}),
        MovingAverageCrossoverStrategy({'short_window': 20, 'long_window': 50}),
        MeanReversionStrategy({'window': 20, 'num_std': 2.0}),
        MeanReversionStrategy({'window': 50, 'num_std': 1.5})
    ]
    
    print("\nRunning ensemble with 4 strategies...")
    
    # Simple ensemble: track all and average results
    individual_results = []
    
    for strategy in strategies:
        engine = BacktestEngine(initial_capital=250_000.0)  # Split capital
        engine.add_strategy(strategy)
        engine.load_price_data("SPY", dates, prices)
        
        result = engine.run_backtest()
        individual_results.append(result)
    
    # Calculate ensemble metrics
    total_final = sum(r['final_equity'] for r in individual_results)
    total_initial = sum(r['initial_capital'] for r in individual_results)
    ensemble_return = (total_final / total_initial - 1) * 100
    
    print(f"\n{'='*70}")
    print(f"{'Individual Results':^70}")
    print(f"{'='*70}")
    
    for i, r in enumerate(individual_results):
        print(f"Strategy {i+1}: ${r['final_equity']:>12,.2f} ({r['total_return_pct']:+.2f}%)")
    
    print(f"\n{'='*70}")
    print(f"{'Ensemble Performance':^70}")
    print(f"{'='*70}")
    print(f"Total Initial Capital: ${total_initial:>12,.2f}")
    print(f"Total Final Equity:    ${total_final:>12,.2f}")
    print(f"Ensemble Return:       {ensemble_return:+.2f}%")
    print(f"Average Sharpe:        {np.mean([r['sharpe_ratio'] for r in individual_results]):.2f}")
    print(f"Average Max DD:        {np.mean([r['max_drawdown_pct'] for r in individual_results]):.2f}%")
    
    return {
        'ensemble_return': ensemble_return,
        'total_final': total_final,
        'individual_results': individual_results
    }


if __name__ == "__main__":
    print("HFT Multi-Backtest Runner")
    print("="*80)
    
    # Run all tests
    run_multi_backtest()
    run_parameter_sweep()
    run_stress_test()
    run_ensemble_backtest()
    
    print("\n" + "="*80)
    print("✅ ALL MULTI-BACKTESTS COMPLETE!")
    print("="*80)
