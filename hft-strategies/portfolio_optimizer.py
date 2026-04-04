"""
Portfolio Optimizer
Kelly Criterion, Correlation Matrix Analysis, Risk Parity
Helps optimize position sizing and portfolio allocation
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
import yfinance as yf

class KellyCriterion:
    """
    Calculates optimal position size using the Kelly Criterion.
    Maximizes long-term geometric growth rate.
    """
    
    @staticmethod
    def calculate(win_rate: float, win_loss_ratio: float) -> float:
        """
        Kelly % = W - [(1 - W) / R]
        
        Args:
            win_rate: Win rate (0 to 1)
            win_loss_ratio: Average Win / Average Loss
            
        Returns:
            Kelly fraction (0 to 1). Never bet more than this % of capital.
        """
        if win_loss_ratio <= 0:
            return 0.0
            
        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)
        
        # Safety: Half-Kelly (less volatile, still near-optimal)
        half_kelly = kelly / 2.0
        
        return max(0.0, min(half_kelly, 0.25))  # Cap at 25%

    @staticmethod
    def optimal_size_from_backtest(trades_log: pd.DataFrame, account_size: float) -> float:
        """
        Calculate Kelly % from historical trade log
        
        Args:
            trades_log: DataFrame with 'PnL' column from paper_trading_log.csv
            account_size: Current total capital
            
        Returns:
            Optimal bet size in currency
        """
        if trades_log.empty or len(trades_log) < 10:
            return account_size * 0.01  # Default 1% if not enough data
            
        wins = trades_log[trades_log['PnL'] > 0]
        losses = trades_log[trades_log['PnL'] <= 0]
        
        if len(wins) == 0 or len(losses) == 0:
            return account_size * 0.01
            
        win_rate = len(wins) / len(trades_log)
        avg_win = wins['PnL'].mean()
        avg_loss = abs(losses['PnL'].mean())
        
        win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 1.0
        
        kelly_pct = KellyCriterion.calculate(win_rate, win_loss_ratio)
        
        return account_size * kelly_pct


class CorrelationAnalyzer:
    """
    Analyzes correlation between stocks to avoid over-concentration
    """
    
    @staticmethod
    def calculate_correlation_matrix(symbols: List[str], period='1y') -> pd.DataFrame:
        """
        Download data and calculate correlation matrix
        
        Returns:
            DataFrame with correlation coefficients (-1 to 1)
        """
        print(f"📊 Calculating correlation matrix for {len(symbols)} stocks...")
        
        # Download all stocks at once
        data = {}
        for sym in symbols:
            try:
                yf_sym = sym if '.NS' in sym else f'{sym}.NS'
                df = yf.download(yf_sym, period=period, progress=False)
                if not df.empty:
                    data[sym] = df['Close'].pct_change()
            except:
                pass
                
        if not data:
            return pd.DataFrame()
            
        returns_df = pd.DataFrame(data)
        returns_df.dropna(inplace=True)
        
        return returns_df.corr()

    @staticmethod
    def find_uncorrelated_pairs(corr_matrix: pd.DataFrame, threshold: float = 0.5) -> List[Tuple]:
        """
        Find pairs of stocks with correlation below threshold.
        Good for Pairs Trading or diversification.
        """
        pairs = []
        stocks = corr_matrix.columns.tolist()
        
        for i, stock_a in enumerate(stocks):
            for stock_b in stocks[i+1:]:
                corr = corr_matrix.loc[stock_a, stock_b]
                if abs(corr) < threshold:
                    pairs.append((stock_a, stock_b, corr))
                    
        # Sort by lowest correlation
        pairs.sort(key=lambda x: abs(x[2]))
        
        return pairs

    @staticmethod
    def portfolio_concentration(corr_matrix: pd.DataFrame, weights: Dict[str, float]) -> float:
        """
        Calculate portfolio variance based on correlation and weights.
        Lower is better (more diversified).
        """
        stocks = list(weights.keys())
        w = np.array([weights.get(s, 0) for s in stocks])
        
        # Get sub-correlation matrix for portfolio stocks
        sub_corr = corr_matrix.loc[stocks, stocks].fillna(0)
        
        # Portfolio variance = w' * Cov * w (assuming unit variance for simplicity)
        portfolio_var = w @ sub_corr.values @ w
        
        return portfolio_var


class RiskParityOptimizer:
    """
    Allocates capital so each asset contributes equally to portfolio risk.
    More robust than equal-weight or market-cap weighting.
    """
    
    @staticmethod
    def calculate_weights(volatilities: Dict[str, float]) -> Dict[str, float]:
        """
        Simple Risk Parity: Inverse volatility weighting.
        Higher volatility -> Smaller allocation.
        
        Args:
            volatilities: Dict of {stock: annualized_volatility}
            
        Returns:
            Dict of {stock: weight} where weights sum to 1.0
        """
        if not volatilities:
            return {}
            
        # Inverse volatility
        inv_vol = {k: 1.0 / v for k, v in volatilities.items()}
        total_inv_vol = sum(inv_vol.values())
        
        # Normalize to sum to 1
        weights = {k: v / total_inv_vol for k, v in inv_vol.items()}
        
        return weights

    @staticmethod
    def calculate_optimal_portfolio(prices_df: pd.DataFrame, target_vol: float = 0.15) -> Dict:
        """
        Calculate risk-parity portfolio targeting specific volatility.
        
        Args:
            prices_df: DataFrame with stock prices as columns
            target_vol: Target portfolio annual volatility (e.g., 0.15 = 15%)
            
        Returns:
            Dict with weights, expected_vol, and allocation amounts
        """
        returns = prices_df.pct_change().dropna()
        
        # Calculate individual volatilities
        vols = {}
        for col in returns.columns:
            vols[col] = returns[col].std() * np.sqrt(252)
            
        # Risk parity weights
        weights = RiskParityOptimizer.calculate_weights(vols)
        
        # Portfolio volatility
        corr = returns.corr()
        w = np.array([weights[c] for c in returns.columns])
        port_vol = np.sqrt(w @ corr.values @ np.array(list(vols.values())) * w)
        
        # Scale weights to match target volatility
        if port_vol > 0:
            scale = target_vol / port_vol
            weights = {k: v * scale for k, v in weights.items()}
        
        return {
            'weights': weights,
            'expected_vol': target_vol,
            'individual_vols': vols
        }


# ============================================================
# Helper Functions for Paper Trader Integration
# ============================================================

def analyze_and_optimize(trades_file: str = 'paper_trading_log.csv', 
                         watchlist: Dict[str, str] = None) -> Dict:
    """
    Run full analysis: Kelly sizing, Correlation, Risk Parity
    """
    import os
    
    results = {}
    
    # 1. Kelly Criterion from trade log
    if os.path.exists(trades_file):
        trades_df = pd.read_csv(trades_file)
        if not trades_df.empty:
            kelly_size = KellyCriterion.optimal_size_from_backtest(
                trades_df, 
                account_size=1_000_000
            )
            results['kelly_position_size'] = kelly_size
            print(f"📐 Kelly Criterion suggests: ₹{kelly_size:.0f} per trade")
            
    # 2. Correlation Analysis
    if watchlist:
        symbols = list(watchlist.keys())
        corr_matrix = CorrelationAnalyzer.calculate_correlation_matrix(symbols)
        
        if not corr_matrix.empty:
            # Find uncorrelated pairs
            pairs = CorrelationAnalyzer.find_uncorrelated_pairs(corr_matrix)
            results['uncorrelated_pairs'] = pairs
            print(f"🔗 Found {len(pairs)} uncorrelated pairs for diversification")
            
            if pairs:
                print(f"   Best pair: {pairs[0][0]} & {pairs[0][1]} (Corr: {pairs[0][2]:.2f})")
                
            # Risk Parity
            # Need volatilities
            vols = {}
            for sym in symbols:
                try:
                    yf_sym = watchlist[sym]
                    hist = yf.download(yf_sym, period='1y', progress=False)
                    if not hist.empty:
                        rets = hist['Close'].pct_change()
                        vols[sym] = rets.std() * np.sqrt(252)
                except:
                    pass
                    
            if vols:
                rp = RiskParityOptimizer.calculate_weights(vols)
                results['risk_parity_weights'] = rp
                print(f"⚖️ Risk Parity Weights:")
                for stock, weight in rp.items():
                    print(f"   {stock}: {weight*100:.1f}%")
                    
    return results
