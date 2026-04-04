"""
Backtesting Engine Demo
Demonstrates event-driven backtesting with walk-forward optimization
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
    FixedCommission,
    PercentageCommission,
    FixedSlippage,
    PercentageSlippage
)

def demo_simple_backtest():
    """Run a simple backtest with MA crossover strategy"""
    print("="*70)
    print("DEMO: Simple Backtest - Moving Average Crossover")
    print("="*70)
    
    # Generate synthetic price data (uptrending with volatility)
    np.random.seed(42)
    n_days = 252  # 1 year
    dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n_days)]
    
    # GBM price generation
    mu = 0.08  # 8% annual return
    sigma = 0.20  # 20% annual vol
    dt = 1/252
    
    log_returns = np.random.normal(mu * dt, sigma * np.sqrt(dt), n_days)
    prices = 100 * np.exp(np.cumsum(log_returns))
    
    print(f"\nGenerated {n_days} days of price data")
    print(f"Start: ${prices[0]:.2f}, End: ${prices[-1]:.2f}")
    print(f"Total Return: {(prices[-1]/prices[0]-1)*100:.2f}%")
    
    # Create backtest engine
    engine = BacktestEngine(
        initial_capital=1_000_000.0,
        commission_model=PercentageCommission(0.001),  # 10 bps
        slippage_model=PercentageSlippage(0.0005)  # 5 bps
    )
    
    # Add strategy
    strategy = MovingAverageCrossoverStrategy({
        'short_window': 20,
        'long_window': 50
    })
    engine.add_strategy(strategy)
    
    # Load data
    engine.load_price_data("SPY", dates, prices)
    
    # Run backtest
    print("\nRunning backtest...")
    results = engine.run_backtest(verbose=False)
    
    # Print results
    print("\n" + "="*70)
    print("BACKTEST RESULTS")
    print("="*70)
    print(f"Initial Capital: ${results['initial_capital']:,.2f}")
    print(f"Final Equity: ${results['final_equity']:,.2f}")
    print(f"Total Return: {results['total_return_pct']:.2f}%")
    print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
    print(f"Sortino Ratio: {results['sortino_ratio']:.2f}")
    print(f"Max Drawdown: {results['max_drawdown_pct']:.2f}%")
    print(f"Win Rate: {results['win_rate_pct']:.2f}%")
    print(f"Total Trades: {results['total_trades']}")
    
    return results


def demo_strategy_comparison():
    """Compare multiple strategies"""
    print("\n" + "="*70)
    print("DEMO: Strategy Comparison")
    print("="*70)
    
    # Generate price data
    np.random.seed(42)
    n_days = 504  # 2 years
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(n_days)]
    
    mu = 0.06
    sigma = 0.25
    dt = 1/252
    log_returns = np.random.normal(mu * dt, sigma * np.sqrt(dt), n_days)
    prices = 100 * np.exp(np.cumsum(log_returns))
    
    strategies = [
        {
            'name': 'MA Crossover (20/50)',
            'class': MovingAverageCrossoverStrategy,
            'params': {'short_window': 20, 'long_window': 50}
        },
        {
            'name': 'MA Crossover (10/30)',
            'class': MovingAverageCrossoverStrategy,
            'params': {'short_window': 10, 'long_window': 30}
        },
        {
            'name': 'Mean Reversion (20, 2σ)',
            'class': MeanReversionStrategy,
            'params': {'window': 20, 'num_std': 2.0}
        },
        {
            'name': 'Mean Reversion (50, 1.5σ)',
            'class': MeanReversionStrategy,
            'params': {'window': 50, 'num_std': 1.5}
        }
    ]
    
    results_table = []
    
    for strat_config in strategies:
        print(f"\nTesting: {strat_config['name']}")
        
        engine = BacktestEngine(
            initial_capital=1_000_000.0,
            commission_model=PercentageCommission(0.001),
            slippage_model=PercentageSlippage(0.0005)
        )
        
        strategy = strat_config['class'](strat_config['params'])
        engine.add_strategy(strategy)
        engine.load_price_data("SPY", dates, prices)
        
        results = engine.run_backtest()
        
        results_table.append({
            'strategy': strat_config['name'],
            'return': results['total_return_pct'],
            'sharpe': results['sharpe_ratio'],
            'sortino': results['sortino_ratio'],
            'max_dd': results['max_drawdown_pct'],
            'win_rate': results['win_rate_pct'],
            'trades': results['total_trades']
        })
    
    # Print comparison table
    print("\n" + "="*70)
    print("STRATEGY COMPARISON")
    print("="*70)
    print(f"{'Strategy':<30} {'Return':>10} {'Sharpe':>8} {'Sortino':>8} {'MaxDD':>8} {'Win%':>8} {'Trades':>8}")
    print("-"*90)
    
    for r in results_table:
        print(f"{r['strategy']:<30} {r['return']:>9.2f}% {r['sharpe']:>8.2f} {r['sortino']:>8.2f} {r['max_dd']:>7.2f}% {r['win_rate']:>7.2f}% {r['trades']:>8}")
    
    # Find best strategy
    best_sharpe = max(results_table, key=lambda x: x['sharpe'])
    best_return = max(results_table, key=lambda x: x['return'])
    best_dd = min(results_table, key=lambda x: x['max_dd'])
    
    print("\n" + "-"*70)
    print(f"Best Sharpe: {best_sharpe['strategy']} ({best_sharpe['sharpe']:.2f})")
    print(f"Best Return: {best_return['strategy']} ({best_return['return']:.2f}%)")
    print(f"Lowest Drawdown: {best_dd['strategy']} ({best_dd['max_dd']:.2f}%)")
    
    return results_table


def demo_walk_forward_optimization():
    """Demonstrate walk-forward optimization"""
    print("\n" + "="*70)
    print("DEMO: Walk-Forward Optimization")
    print("="*70)
    
    # Generate longer price series
    np.random.seed(42)
    n_days = 1008  # 4 years
    dates = [datetime(2021, 1, 1) + timedelta(days=i) for i in range(n_days)]
    
    mu = 0.07
    sigma = 0.22
    dt = 1/252
    log_returns = np.random.normal(mu * dt, sigma * np.sqrt(dt), n_days)
    prices = 100 * np.exp(np.cumsum(log_returns))
    
    print(f"\nOptimizing MA Crossover on {n_days} days of data...")
    print(f"Training: 70% ({int(n_days*0.7)} days)")
    print(f"Testing: 30% ({n_days - int(n_days*0.7)} days)")
    
    # Parameter grid
    param_grid = {
        'short_window': [10, 20, 30, 50],
        'long_window': [50, 100, 200]
    }
    
    # Run walk-forward optimization
    optimizer = WalkForwardOptimizer(
        strategy_class=MovingAverageCrossoverStrategy,
        param_grid=param_grid,
        train_pct=0.7
    )
    
    print("\nTesting parameter combinations...")
    results = optimizer.optimize(dates, prices)
    
    print("\n" + "="*70)
    print("OPTIMIZATION RESULTS")
    print("="*70)
    print(f"Best Parameters: {results['best_params']}")
    print(f"In-Sample Return: {results['in_sample_return']:.2f}%")
    
    if results['out_of_sample_results']:
        oos = results['out_of_sample_results'][0]
        print(f"Out-of-Sample Return: {oos.get('total_return_pct', 0):.2f}%")
        print(f"Out-of-Sample Sharpe: {oos.get('sharpe_ratio', 0):.2f}")
        print(f"Out-of-Sample Max DD: {oos.get('max_drawdown_pct', 0):.2f}%")
    else:
        print("No out-of-sample data available")
    
    # Parameter sensitivity analysis
    print("\n" + "="*70)
    print("PARAMETER SENSITIVITY")
    print("="*70)
    
    # Test all combinations
    import itertools
    combos = list(itertools.product(param_grid['short_window'], param_grid['long_window']))
    
    print(f"{'Short MA':<12} {'Long MA':<12} {'Return':>10} {'Sharpe':>10}")
    print("-"*45)
    
    for short, long in combos:
        if short >= long:
            continue
        
        engine = BacktestEngine(initial_capital=1_000_000.0)
        strategy = MovingAverageCrossoverStrategy({
            'short_window': short,
            'long_window': long
        })
        engine.add_strategy(strategy)
        engine.load_price_data("SPY", dates[:int(n_days*0.7)], prices[:int(n_days*0.7)])
        
        results = engine.run_backtest()
        
        print(f"{short:<12} {long:<12} {results['total_return_pct']:>9.2f}% {results['sharpe_ratio']:>10.2f}")
    
    return results


def demo_stress_test():
    """Backtest under different market regimes"""
    print("\n" + "="*70)
    print("DEMO: Stress Testing Across Market Regimes")
    print("="*70)
    
    regimes = {
        'Bull Market': {'mu': 0.20, 'sigma': 0.15, 'jumps': False},
        'Bear Market': {'mu': -0.15, 'sigma': 0.35, 'jumps': True},
        'High Vol': {'mu': 0.05, 'sigma': 0.50, 'jumps': True},
        'Sideways': {'mu': 0.02, 'sigma': 0.10, 'jumps': False},
    }
    
    strategy_config = {
        'name': 'MA Crossover (20/50)',
        'class': MovingAverageCrossoverStrategy,
        'params': {'short_window': 20, 'long_window': 50}
    }
    
    results_table = []
    
    for regime_name, params in regimes.items():
        print(f"\nSimulating: {regime_name}")
        
        np.random.seed(42)
        n_days = 252
        dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n_days)]
        
        dt = 1/252
        log_returns = np.random.normal(params['mu'] * dt, params['sigma'] * np.sqrt(dt), n_days)
        
        if params['jumps']:
            jump_mask = np.random.random(n_days) < 0.05
            log_returns[jump_mask] += np.random.normal(-0.03, 0.02, jump_mask.sum())
        
        prices = 100 * np.exp(np.cumsum(log_returns))
        
        engine = BacktestEngine(initial_capital=1_000_000.0)
        strategy = strategy_config['class'](strategy_config['params'])
        engine.add_strategy(strategy)
        engine.load_price_data("SPY", dates, prices)
        
        results = engine.run_backtest()
        
        results_table.append({
            'regime': regime_name,
            'return': results['total_return_pct'],
            'sharpe': results['sharpe_ratio'],
            'max_dd': results['max_drawdown_pct'],
            'trades': results['total_trades']
        })
        
        print(f"  Return: {results['total_return_pct']:.2f}%, Sharpe: {results['sharpe_ratio']:.2f}, Max DD: {results['max_drawdown_pct']:.2f}%")
    
    print("\n" + "="*70)
    print("STRESS TEST SUMMARY")
    print("="*70)
    print(f"{'Regime':<20} {'Return':>10} {'Sharpe':>10} {'Max DD':>10} {'Trades':>10}")
    print("-"*65)
    
    for r in results_table:
        print(f"{r['regime']:<20} {r['return']:>9.2f}% {r['sharpe']:>10.2f} {r['max_dd']:>9.2f}% {r['trades']:>10}")
    
    return results_table


if __name__ == "__main__":
    print("HFT Simulation Platform - Backtesting Engine Demo")
    print("="*70)
    
    # Run all demos
    demo_simple_backtest()
    demo_strategy_comparison()
    demo_walk_forward_optimization()
    demo_stress_test()
    
    print("\n" + "="*70)
    print("✅ All backtesting demos completed!")
    print("="*70)
