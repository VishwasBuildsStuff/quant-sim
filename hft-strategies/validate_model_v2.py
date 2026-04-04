"""
NSE Model Validator V2 - Golden Cross & Improved Metrics
"""

import sys
import os
sys.path.insert(0, os.getcwd())

import numpy as np
from nse_data_fetcher import NSEDataFetcher
from backtesting_engine import (
    BacktestEngine,
    MovingAverageCrossoverStrategy,
    PercentageCommission,
    PercentageSlippage
)

def test_model_v2():
    print("="*80)
    print("NSE STRATEGY VALIDATION V2 (Golden Cross: 50/200 MA)")
    print("="*80)

    fetcher = NSEDataFetcher()

    # Fixed symbols
    symbols = [
        ('RELIANCE', 'RELIANCE.NS'),
        ('TCS', 'TCS.NS'),
        ('INFY', 'INFY.NS'),
        ('HDFCBANK', 'HDFCBANK.NS'),
        ('TATAMOTORS', 'TTM.NS') # Fixed ticker
    ]

    # Golden Cross Parameters (Standard for Daily Data)
    strategy_params = {'short_window': 50, 'long_window': 200}

    print(f"\nStrategy: Golden Cross ({strategy_params['short_window']}/{strategy_params['long_window']})")
    print(f"Data: Yahoo Finance (Daily, 2 Years)")
    print("-"*80)

    results_table = []

    for name, yf_symbol in symbols:
        try:
            print(f"\nFetching {name} ({yf_symbol})...")
            df = fetcher.get_historical_data(yf_symbol, period='2y', interval='1d')

            if df.empty:
                print(f"⚠️ No data found")
                continue

            timestamps, prices, highs, lows, volumes = fetcher.prepare_backtest_data(df)

            # 1. Buy & Hold Benchmark
            bnh_return = (prices[-1] - prices[0]) / prices[0] * 100

            # 2. Strategy Backtest
            engine = BacktestEngine(
                initial_capital=1_000_000.0,
                commission_model=PercentageCommission(0.001),
                slippage_model=PercentageSlippage(0.0005)
            )

            strategy = MovingAverageCrossoverStrategy(strategy_params)
            engine.add_strategy(strategy)
            engine.load_price_data(name, timestamps, prices, highs, lows, volumes)

            result = engine.run_backtest()

            # 3. Improved Analysis
            strat_ret = result['total_return_pct']
            trades = result['total_trades']
            win_rate = result['win_rate_pct']

            # Alpha (Outperformance vs Buy & Hold)
            alpha = strat_ret - bnh_return

            # Risk-Adjusted Score (Simplified for low-frequency trading)
            # If we lost less money than the market, that's a win in a bear market
            is_win = strat_ret > bnh_return

            # Verdict
            if strat_ret > 5 and win_rate > 40:
                verdict = "🌟 EXCELLENT"
            elif is_win:
                verdict = "✅ PASS (Beat Market)"
            else:
                verdict = "❌ FAIL"

            print(f"  Strat: {strat_ret:+.2f}% | B&H: {bnh_return:+.2f}% | Alpha: {alpha:+.2f}%")
            print(f"  Trades: {trades} | Win%: {win_rate:.1f}% | Verdict: {verdict}")

            results_table.append({
                'Symbol': name,
                'Strat%': strat_ret,
                'BNH%': bnh_return,
                'Alpha': alpha,
                'Trades': trades,
                'Win%': win_rate,
                'Verdict': verdict
            })

        except Exception as e:
            print(f"❌ Error: {e}")

    # Summary
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    print(f"{'Symbol':<15} {'Strat%':>8} {'BNH%':>8} {'Alpha':>8} {'Trades':>7} {'Win%':>6} {'Verdict':>15}")
    print("-"*75)

    passes = 0
    for r in results_table:
        print(f"{r['Symbol']:<15} {r['Strat%']:>+7.2f}% {r['BNH%']:>+7.2f}% {r['Alpha']:>+7.2f}% {r['Trades']:>7} {r['Win%']:>5.1f}% {r['Verdict']:>15}")
        if 'PASS' in r['Verdict'] or 'EXCELLENT' in r['Verdict']:
            passes += 1

    print("-"*75)
    print(f"Success Rate: {passes}/{len(results_table)}")

    if passes > len(results_table) / 2:
        print("\n🎉 VALIDATION SUCCESSFUL! Your strategy protects capital better than the market.")
    else:
        print("\n⚠️ Optimization needed. Strategy logic may need refinement.")

if __name__ == "__main__":
    test_model_v2()