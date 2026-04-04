"""
NSE Model Validator (Yahoo Finance)
Tests strategies against real NSE data to validate model logic.
"""

import sys
import os
sys.path.insert(0, os.getcwd())

from nse_data_fetcher import NSEDataFetcher
from backtesting_engine import (
    BacktestEngine,
    MovingAverageCrossoverStrategy,
    MeanReversionStrategy,
    PercentageCommission,
    PercentageSlippage
)
import pandas as pd

def test_model_on_nse():
    print("="*80)
    print("NSE STRATEGY VALIDATION (Yahoo Finance Data)")
    print("="*80)

    fetcher = NSEDataFetcher()

    # Top NSE Stocks to test
    # Using Yahoo Finance tickers directly (.NS suffix)
    symbols = [
        'RELIANCE.NS',
        'TCS.NS',
        'INFY.NS',
        'HDFCBANK.NS',
        'TATAMOTORS.NS'
    ]

    strategy_params = {'short_window': 20, 'long_window': 50}

    results_table = []

    print(f"\nTesting Strategy: MA Crossover ({strategy_params['short_window']}/{strategy_params['long_window']})")
    print(f"Data Source: Yahoo Finance (Daily, 2 Years)")
    print("-"*80)

    for symbol in symbols:
        try:
            # 1. Fetch 2 Years of Data
            print(f"\nFetching data for {symbol}...")
            df = fetcher.get_historical_data(symbol, period='2y', interval='1d')

            if df.empty:
                print(f"⚠️ No data found for {symbol}")
                continue

            timestamps, prices, highs, lows, volumes = fetcher.prepare_backtest_data(df)

            # 2. Run Buy & Hold (Benchmark)
            bnh_return = (prices[-1] - prices[0]) / prices[0] * 100

            # 3. Run Strategy Backtest
            engine = BacktestEngine(
                initial_capital=1_000_000.0,
                commission_model=PercentageCommission(0.001), # 0.1% comm
                slippage_model=PercentageSlippage(0.0005)     # 0.05% slip
            )

            strategy = MovingAverageCrossoverStrategy(strategy_params)
            engine.add_strategy(strategy)
            engine.load_price_data(symbol, timestamps, prices, highs, lows, volumes)

            result = engine.run_backtest()

            # 4. Analyze Results
            strat_ret = result['total_return_pct']
            alpha = strat_ret - bnh_return
            sharpe = result['sharpe_ratio']

            # Verdict
            verdict = "✅ PASS" if sharpe > 1.0 else "❌ FAIL"
            if sharpe > 1.5: verdict = "🌟 EXCELLENT"

            print(f"  Return: {strat_ret:+.2f}% | B&H: {bnh_return:+.2f}% | Alpha: {alpha:+.2f}% | Sharpe: {sharpe:.2f} | {verdict}")

            results_table.append({
                'Symbol': symbol.replace('.NS', ''),
                'Strat_Return': strat_ret,
                'BNH_Return': bnh_return,
                'Alpha': alpha,
                'Sharpe': sharpe,
                'Verdict': verdict
            })

        except Exception as e:
            print(f"❌ Error testing {symbol}: {e}")

    # Summary
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    print(f"{'Symbol':<15} {'Strat%':>10} {'B&H%':>10} {'Alpha':>10} {'Sharpe':>8} {'Verdict':>10}")
    print("-"*70)

    passes = 0
    for r in results_table:
        print(f"{r['Symbol']:<15} {r['Strat_Return']:>+9.2f}% {r['BNH_Return']:>+9.2f}% {r['Alpha']:>+9.2f}% {r['Sharpe']:>8.2f} {r['Verdict']:>10}")
        if 'PASS' in r['Verdict']:
            passes += 1

    print("-"*70)
    print(f"Success Rate: {passes}/{len(results_table)} ({passes/len(results_table)*100:.0f}%)")

    if passes / len(results_table) > 0.5:
        print("\n🎉 MODEL VALIDATION SUCCESSFUL! Strategy shows promise on real data.")
    else:
        print("\n⚠️ MODEL WEAK. Strategy underperforms Buy & Hold. Optimization needed.")

if __name__ == "__main__":
    test_model_on_nse()