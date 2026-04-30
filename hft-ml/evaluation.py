"""
HFT Model Evaluation Metrics
Out-of-sample evaluation with slippage, latency, and transaction costs
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

@dataclass
class TradeRecord:
    """Single trade record for evaluation"""
    timestamp: int
    symbol: str
    side: int  # 1=long, -1=short
    entry_price: float
    exit_price: float
    quantity: int
    entry_time_ns: int
    exit_time_ns: int
    pnl: float
    slippage: float
    transaction_cost: float

@dataclass
class EvaluationMetrics:
    """Complete evaluation metrics"""
    # Classification metrics
    accuracy: float
    f1_macro: float
    f1_up: float
    f1_down: float
    precision: float
    recall: float

    # Trading metrics
    sharpe_ratio: float
    profit_factor: float
    max_drawdown: float
    total_return: float
    win_rate: float
    total_trades: int
    avg_trade_pnl: float
    avg_slippage: float

    # Latency metrics
    avg_inference_latency_us: float
    p99_latency_us: float
    p999_latency_us: float

    # Signal quality
    hit_rate_1tick: float
    hit_rate_5tick: float
    signal_generation_rate: float

class HFTModelEvaluator:
    """
    Comprehensive model evaluation for HFT systems
    """

    def __init__(self,
                 tick_size: float = 0.05,
                 lot_size: int = 1,
                 transaction_cost_bps: float = 5.0,
                 slippage_ticks: float = 0.5,
                 risk_free_rate: float = 0.05):

        self.tick_size = tick_size
        self.lot_size = lot_size
        self.transaction_cost_bps = transaction_cost_bps
        self.slippage_ticks = slippage_ticks
        self.risk_free_rate = risk_free_rate

    def evaluate_predictions(self,
                            y_true: np.ndarray,
                            y_pred: np.ndarray,
                            y_proba: Optional[np.ndarray] = None) -> Dict:
        """Evaluate classification predictions"""

        # Basic metrics
        accuracy = accuracy_score(y_true, y_pred)
        f1_macro = f1_score(y_true, y_pred, average='macro', zero_division=0)

        # Per-class metrics
        precision = precision_score(y_true, y_pred, average='macro', zero_division=0)
        recall = recall_score(y_true, y_pred, average='macro', zero_division=0)

        # F1 for up (class 2) and down (class 0)
        f1_up = f1_score(y_true, y_pred, labels=[2], average='micro', zero_division=0) if 2 in y_true else 0
        f1_down = f1_score(y_true, y_pred, labels=[0], average='micro', zero_division=0) if 0 in y_true else 0

        # Hit rate for 1-tick horizon
        hit_rate_1tick = (y_pred == y_true).mean()

        return {
            'accuracy': accuracy,
            'f1_macro': f1_macro,
            'f1_up': f1_up,
            'f1_down': f1_down,
            'precision': precision,
            'recall': recall,
            'hit_rate_1tick': hit_rate_1tick
        }

    def evaluate_trading_performance(self,
                                     trades: List[TradeRecord],
                                     initial_capital: float = 1_000_000.0) -> Dict:
        """Evaluate actual trading performance"""
        if not trades:
            return self._empty_metrics()

        # PnL series
        pnls = np.array([t.pnl for t in trades])
        cumulative_pnl = np.cumsum(pnls)
        equity_curve = initial_capital + cumulative_pnl

        # Total return
        total_return = (equity_curve[-1] - initial_capital) / initial_capital

        # Win rate
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl <= 0]
        win_rate = len(winning_trades) / len(trades)

        # Profit factor
        gross_profit = sum(t.pnl for t in winning_trades) if winning_trades else 0
        gross_loss = abs(sum(t.pnl for t in losing_trades)) if losing_trades else 1e-10
        profit_factor = gross_profit / gross_loss

        # Maximum drawdown
        peak = equity_curve[0]
        max_dd = 0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd

        # Sharpe ratio (annualized)
        if len(pnls) > 1:
            returns = np.diff(equity_curve) / equity_curve[:-1]
            excess_returns = returns - self.risk_free_rate / 252
            sharpe = np.mean(excess_returns) / (np.std(excess_returns) + 1e-10) * np.sqrt(252)
        else:
            sharpe = 0

        # Average slippage
        avg_slippage = np.mean([abs(t.slippage) for t in trades])

        return {
            'sharpe_ratio': sharpe,
            'profit_factor': profit_factor,
            'max_drawdown': max_dd,
            'total_return': total_return,
            'win_rate': win_rate,
            'total_trades': len(trades),
            'avg_trade_pnl': np.mean(pnls),
            'avg_slippage': avg_slippage,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss
        }

    def measure_inference_latency(self,
                                  model,
                                  input_shape: Tuple[int, int, int],
                                  n_iterations: int = 1000,
                                  device: str = 'cpu') -> Dict:
        """
        Measure model inference latency

        Returns:
            Latency statistics in microseconds
        """
        import time
        import torch

        model.eval()
        model.to(device)

        # Dummy input
        dummy_input = torch.randn(input_shape, device=device)

        # Warmup
        with torch.no_grad():
            for _ in range(100):
                _ = model(dummy_input)

        # Measure
        latencies = []
        with torch.no_grad():
            for _ in range(n_iterations):
                start = time.perf_counter_ns()
                _ = model(dummy_input)
                end = time.perf_counter_ns()
                latencies.append((end - start) / 1000)  # Convert to microseconds

        latencies = np.array(latencies)

        return {
            'avg_latency_us': np.mean(latencies),
            'median_latency_us': np.median(latencies),
            'p99_latency_us': np.percentile(latencies, 99),
            'p999_latency_us': np.percentile(latencies, 99.9),
            'min_latency_us': np.min(latencies),
            'max_latency_us': np.max(latencies),
            'std_latency_us': np.std(latencies),
            'signals_per_second': 1_000_000 / np.mean(latencies)
        }

    def check_performance_targets(self, metrics: Dict) -> Dict[str, bool]:
        """Check if metrics meet institutional targets"""
        targets = {
            'accuracy_55pct': metrics.get('accuracy', 0) > 0.55,
            'f1_above_05': metrics.get('f1_macro', 0) > 0.5,
            'sharpe_above_15': metrics.get('sharpe_ratio', 0) > 1.5,
            'profit_factor_above_13': metrics.get('profit_factor', 0) > 1.3,
            'max_drawdown_below_15': metrics.get('max_drawdown', 1) < 0.15,
            'latency_below_10us': metrics.get('avg_inference_latency_us', 100) < 10,
            'signal_rate_above_95': metrics.get('signal_generation_rate', 0) > 0.95
        }

        passed = sum(1 for v in targets.values() if v)
        total = len(targets)

        print(f"\n{'='*60}")
        print(f"PERFORMANCE TARGET CHECK")
        print(f"{'='*60}")
        for name, passed_check in targets.items():
            status = 'PASS' if passed_check else 'FAIL'
            print(f"  {status}: {name}")
        print(f"\nPassed: {passed}/{total} ({passed/total*100:.0f}%)")

        return targets

    def _empty_metrics(self) -> Dict:
        """Return empty metrics dict"""
        return {
            'sharpe_ratio': 0, 'profit_factor': 0, 'max_drawdown': 1.0,
            'total_return': 0, 'win_rate': 0, 'total_trades': 0,
            'avg_trade_pnl': 0, 'avg_slippage': 0
        }
