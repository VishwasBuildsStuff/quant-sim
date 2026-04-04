"""
Quick Test Script for Advanced Strategies, Database & Optimizer
Run this to verify everything is working.
"""

import sys
import os
sys.path.insert(0, os.getcwd())

import pandas as pd
import numpy as np
from datetime import datetime

def test_advanced_strategies():
    """Test Pairs Trading, Momentum Breakout, VWAP Reversion"""
    print("="*70)
    print("TESTING: Advanced Strategy Library")
    print("="*70)
    
    from advanced_strategies import PairsTradingStrategy, MomentumBreakoutStrategy, VWAPReversionStrategy
    from backtesting_engine import MarketEvent
    
    # Create sample market events
    ts = datetime.now()
    
    # Test Pairs Trading
    print("\n1️⃣ Pairs Trading Strategy")
    pairs = PairsTradingStrategy({
        'lookback': 20,
        'entry_z': 2.0,
        'exit_z': 0.5,
        'pair_symbol': 'TCS.NS'
    })
    print(f"   ✅ Initialized: Lookback={pairs.lookback}, Entry Z={pairs.entry_z}")
    
    # Test Momentum Breakout
    print("\n2️⃣ Momentum Breakout Strategy")
    momentum = MomentumBreakoutStrategy({
        'lookback': 20,
        'vol_multiplier': 2.0
    })
    print(f"   ✅ Initialized: Lookback={momentum.lookback}, Vol Multiplier={momentum.vol_multiplier}")
    
    # Test VWAP Reversion
    print("\n3️⃣ VWAP Reversion Strategy")
    vwap = VWAPReversionStrategy({
        'entry_std': 2.0,
        'exit_std': 0.5
    })
    print(f"   ✅ Initialized: Entry Std={vwap.entry_std}")
    
    print("\n✅ All strategies initialized successfully!")


def test_tick_database():
    """Test database storage and retrieval"""
    print("\n" + "="*70)
    print("TESTING: Tick Database")
    print("="*70)
    
    from tick_database import TickDatabase
    
    db = TickDatabase()
    
    # Download and store 5 days of 1-min data for RELIANCE
    print("\n📥 Fetching 1-minute data for RELIANCE.NS...")
    stored = db.fetch_and_store('RELIANCE.NS', period='5d', interval='1m')
    
    if stored > 0:
        print(f"✅ Successfully stored {stored} bars")
        
        # Count total records
        total = db.count_records()
        print(f"📊 Total records in database: {total}")
        
        # Test retrieval
        df = db.get_historical_data('RELIANCE.NS', '2020-01-01', '2030-12-31')
        if not df.empty:
            print(f"✅ Retrieved {len(df)} bars from database")
            print(f"   Date range: {df.index[0]} to {df.index[-1]}")
    else:
        print("⚠️ No data stored (market may be closed)")


def test_portfolio_optimizer():
    """Test Kelly Criterion, Correlation, Risk Parity"""
    print("\n" + "="*70)
    print("TESTING: Portfolio Optimizer")
    print("="*70)
    
    from portfolio_optimizer import KellyCriterion, CorrelationAnalyzer, RiskParityOptimizer
    
    # Test Kelly Criterion
    print("\n📐 Kelly Criterion Examples:")
    
    # Example 1: 60% win rate, 1.5 win/loss ratio
    kelly1 = KellyCriterion.calculate(0.60, 1.5)
    print(f"   Strategy A (60% WR, 1.5 W/L): Kelly = {kelly1*100:.1f}%")
    
    # Example 2: 40% win rate, 3.0 win/loss ratio
    kelly2 = KellyCriterion.calculate(0.40, 3.0)
    print(f"   Strategy B (40% WR, 3.0 W/L): Kelly = {kelly2*100:.1f}%")
    
    # Test Correlation Matrix
    print("\n🔗 Calculating Correlation Matrix...")
    symbols = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS']
    try:
        corr = CorrelationAnalyzer.calculate_correlation_matrix(symbols)
        if not corr.empty:
            print("✅ Correlation Matrix:")
            print(corr.round(2))
            
            # Find uncorrelated pairs
            pairs = CorrelationAnalyzer.find_uncorrelated_pairs(corr, threshold=0.5)
            if pairs:
                print(f"\n📊 Uncorrelated Pairs (|corr| < 0.5):")
                for a, b, c in pairs[:3]:
                    print(f"   {a.replace('.NS','')} & {b.replace('.NS','')}: {c:.2f}")
    except Exception as e:
        print(f"⚠️ Could not calculate correlation: {e}")
    
    # Test Risk Parity
    print("\n⚖️ Risk Parity Portfolio:")
    vols = {
        'RELIANCE': 0.25,
        'TCS': 0.20,
        'INFY': 0.22,
        'HDFCBANK': 0.28
    }
    
    weights = RiskParityOptimizer.calculate_weights(vols)
    print("   Optimal Weights:")
    for stock, weight in weights.items():
        print(f"   {stock}: {weight*100:.1f}%")


def test_all_together():
    """Run everything"""
    print("🚀 ADVANCED COMPONENTS TEST SUITE")
    print("="*70)
    
    test_advanced_strategies()
    test_tick_database()
    test_portfolio_optimizer()
    
    print("\n" + "="*70)
    print("✅ ALL TESTS COMPLETE!")
    print("="*70)
    print("\n📁 Files Created:")
    print("   • advanced_strategies.py (Pairs, Momentum, VWAP)")
    print("   • tick_database.py (SQLite Storage + Replay)")
    print("   • portfolio_optimizer.py (Kelly, Correlation, Risk Parity)")
    print("\n💡 Next Step: Integrate these into your paper_trader.py")

if __name__ == "__main__":
    test_all_together()
