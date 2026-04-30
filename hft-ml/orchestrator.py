"""
HFT ML Training Pipeline - Main Orchestrator
Complete end-to-end training and evaluation for all models
"""

import sys
import os

# Add custom PyTorch path and project root
sys.path.insert(0, r'V:\pylibs')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import time
import numpy as np
import pandas as pd
import torch
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

from data_pipeline import LOBFeatureEngineer, LabelGenerator, LOBSnapshot
from data_loader import LOBDataLoader, DataConfig, DataIntegrityChecker
from models.gru_cnn import GRUCNNModel, MultiTaskLoss
from models.siamese_lstm_attention import SiameseLSTMAttention
from models.kalman_pairs import KalmanFilterPairs
from models.regime_adaptive import RegimeAdaptivePredictor
from training import WalkForwardValidator, HFTTrainer
from evaluation import HFTModelEvaluator
from risk_manager import HFT_RiskManager, RiskLimits

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('training.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class HFTTrainingOrchestrator:
    """
    Complete training orchestration for HFT models
    Coordinates data loading, feature engineering, training, evaluation
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Initialize components
        self.feature_engineer = LOBFeatureEngineer(
            n_levels=config.get('n_levels', 10),
            tick_size=config.get('tick_size', 0.05)
        )
        
        self.label_generator = LabelGenerator(
            horizons=config.get('horizons', [1, 5, 10, 50, 100]),
            tolerance_spread_mult=config.get('tolerance_spread_mult', 0.5)
        )
        
        self.data_integrity = DataIntegrityChecker()
        self.evaluator = HFTModelEvaluator(
            tick_size=config.get('tick_size', 0.05),
            transaction_cost_bps=config.get('transaction_cost_bps', 5.0)
        )
        
        self.risk_manager = HFT_RiskManager(
            initial_capital=config.get('initial_capital', 10_000_000)
        )
        
        # Model registry
        self.models = {}
        self.trained_models = {}
        
        logger.info(f"HFT Training Orchestrator initialized on {self.device}")
    
    def load_and_prepare_data(self, data_path: str) -> Dict:
        """Load raw data and engineer features"""
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 1: DATA LOADING & FEATURE ENGINEERING")
        logger.info(f"{'='*60}")
        
        # Load data
        loader = LOBDataLoader(DataConfig(
            symbol=self.config['symbol'],
            asset_class=self.config['asset_class'],
            n_levels=self.config['n_levels'],
            data_dir=data_path
        ))
        
        data = loader.load_from_parquet(os.path.join(data_path, f"{self.config['symbol']}.parquet"))
        
        # Data integrity checks
        issues = self.data_integrity.validate_lob_data(data)
        if issues:
            logger.warning(f"Data integrity issues: {len(issues)}")
        
        logger.info(f"Loaded {len(data['timestamps'])} LOB snapshots")
        
        # Feature engineering
        logger.info("Engineering features...")
        features_list = []
        
        n_levels = self.config['n_levels']
        n_samples = len(data['timestamps'])
        
        # Pre-allocate feature matrix
        n_features = 40  # Total features
        feature_matrix = np.zeros((n_samples, n_features), dtype=np.float64)
        
        for i in range(n_samples):
            snapshot = LOBSnapshot(
                timestamp_ns=data['timestamps'][i],
                bid_prices=data['bid_prices'][i],
                bid_volumes=data['bid_volumes'][i],
                ask_prices=data['ask_prices'][i],
                ask_volumes=data['ask_volumes'][i],
                last_trade_price=data['last_trade_price'][i],
                last_trade_volume=data['last_trade_volume'][i],
                trade_side=data['trade_side'][i]
            )
            
            features = self.feature_engineer.compute_features(snapshot)
            
            # Pack features into matrix
            feature_matrix[i] = np.array([
                features.ofi,
                features.depth_imbalance,
                features.weighted_mid_price,
                features.spread_normalized,
                features.bid_slope,
                features.ask_slope,
                features.bid_volume_total,
                features.ask_volume_total,
                features.volume_imbalance,
                features.mid_price,
                features.log_return_1,
                features.log_return_5,
                features.log_return_10,
                features.realized_vol_5,
                features.realized_vol_10,
                features.realized_vol_20,
                features.realized_skew,
                features.queue_imbalance,
                features.trade_intensity,
                features.cancel_ratio,
                # Level imbalances (10 levels)
                *features.level_imbalances,
                # Cumulative volumes (10 levels each)
                *features.cumulative_bid_volumes[:5],
                *features.cumulative_ask_volumes[:5]
            ])
        
        # Handle NaN/Inf
        feature_matrix = np.nan_to_num(feature_matrix, nan=0.0, posinf=1e10, neginf=-1e10)
        
        # Normalize features (z-score)
        feature_mean = feature_matrix.mean(axis=0)
        feature_std = feature_matrix.std(axis=0) + 1e-10
        feature_matrix = (feature_matrix - feature_mean) / feature_std
        
        logger.info(f"Feature matrix shape: {feature_matrix.shape}")
        
        # Generate labels
        mid_prices = (data['bid_prices'][:, 0] + data['ask_prices'][:, 0]) / 2.0
        spreads = data['ask_prices'][:, 0] - data['bid_prices'][:, 0]
        
        logger.info("Generating labels...")
        labels = self.label_generator.generate_labels(mid_prices, spreads, data['timestamps'])
        
        return {
            'features': feature_matrix,
            'labels': labels,
            'timestamps': data['timestamps'],
            'mid_prices': mid_prices,
            'feature_mean': feature_mean,
            'feature_std': feature_std
        }
    
    def prepare_sequences(self, 
                         features: np.ndarray,
                         labels: Dict,
                         sequence_length: int = 100,
                         horizon: int = 10) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """Prepare sequential data for training"""
        n_samples = len(features)
        n_features = features.shape[1]
        
        # Create sequences
        X_sequences = []
        y_class = []
        y_reg = []
        y_vol = []
        valid_indices = []
        
        label_data = labels[f'h{horizon}']
        
        for i in range(sequence_length, n_samples - horizon):
            # Sequence of features
            seq = features[i - sequence_length:i]
            X_sequences.append(seq)
            
            # Labels at prediction horizon
            y_class.append(label_data['classification'][i])
            y_reg.append(label_data['regression'][i])
            y_vol.append(label_data['volatility'][i])
            valid_indices.append(i)
        
        X = np.array(X_sequences, dtype=np.float32)
        y = {
            'classification': np.array(y_class, dtype=np.int64),
            'regression': np.array(y_reg, dtype=np.float32),
            'volatility': np.array(y_vol, dtype=np.float32)
        }
        
        logger.info(f"Sequences: X={X.shape}, y_class={y['classification'].shape}")
        logger.info(f"Class distribution: {np.bincount(y['classification'])}")
        
        return X, y
    
    def train_gru_cnn(self, X: np.ndarray, y: Dict, save_dir: str) -> Dict:
        """Train GRU-CNN model"""
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 2: TRAINING GRU-CNN MODEL")
        logger.info(f"{'='*60}")
        
        n_features = X.shape[2]
        
        model = GRUCNNModel(
            n_features=n_features,
            seq_len=self.config.get('sequence_length', 100),
            n_levels=self.config['n_levels'],
            cnn_channels=[32, 64, 128],
            cnn_kernel_sizes=[3, 3, 3],
            gru_hidden=128,
            gru_layers=2,
            gru_dropout=0.2,
            n_classes=3,
            use_attention=True,
            n_attention_heads=4
        ).to(self.device)
        
        from models.gru_cnn import count_parameters
        logger.info(f"GRU-CNN parameters: {count_parameters(model):,}")
        
        # Walk-forward validator
        validator = WalkForwardValidator(
            total_days=max(10, len(X) // 10000),  # Ensure minimum 10 days
            train_days=3,  # Reduced from 5 for smaller datasets
            val_days=1,
            test_days=1,
            roll_days=1
        )
        
        # Trainer
        trainer = HFTTrainer(
            model=model,
            device=self.device,
            learning_rate=self.config.get('learning_rate', 1e-3),
            batch_size=self.config.get('batch_size', 256),
            max_epochs=self.config.get('max_epochs', 50),
            patience=self.config.get('patience', 5),
            use_mixed_precision=self.config.get('mixed_precision', False)
        )
        
        # Walk-forward training
        results = trainer.walk_forward_train(X, y, validator, save_dir=f'{save_dir}/gru_cnn')
        
        self.trained_models['gru_cnn'] = {
            'model': model,
            'trainer': trainer,
            'results': results
        }
        
        return results
    
    def train_kalman_pairs(self, 
                          data_A: Dict,
                          data_B: Dict,
                          save_dir: str) -> Dict:
        """Train Kalman Filter pairs trading model"""
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 3: TRAINING KALMAN FILTER PAIRS MODEL")
        logger.info(f"{'='*60}")
        
        # Extract mid-prices
        mid_A = (data_A['bid_prices'][:, 0] + data_A['ask_prices'][:, 0]) / 2.0
        mid_B = (data_B['bid_prices'][:, 0] + data_B['ask_prices'][:, 0]) / 2.0
        timestamps = data_A['timestamps']
        
        # Initialize Kalman filter
        kalman = KalmanFilterPairs(
            entry_threshold=2.0,
            exit_threshold=0.5,
            delta=1e-4
        )
        
        # Run through data
        signals = []
        trades = []
        
        for i in range(len(mid_A)):
            signal = kalman.update(mid_A[i], mid_B[i], timestamps[i])
            signals.append(signal)
            
            # Record trades when signal changes
            if signal.signal != 0:
                trades.append({
                    'timestamp': signal.timestamp,
                    'spread': signal.spread,
                    'z_score': signal.z_score,
                    'hedge_ratio': signal.hedge_ratio,
                    'signal': signal.signal
                })
        
        # Evaluate performance
        from evaluation import TradeRecord
        
        # Simulate trades
        simulated_trades = []
        for i in range(0, len(signals) - 1, 100):  # Every 100 ticks
            sig = signals[i]
            if sig.signal != 0:
                pnl = sig.z_score * 0.01  # Simplified PnL model
                trade = TradeRecord(
                    timestamp=sig.timestamp,
                    symbol=f"{self.config['symbol']}_pair",
                    side=sig.signal,
                    entry_price=mid_A[i],
                    exit_price=mid_A[i] + pnl,
                    quantity=100,
                    entry_time_ns=sig.timestamp,
                    exit_time_ns=sig.timestamp + 1000,
                    pnl=pnl * 100,
                    slippage=0.025,
                    transaction_cost=0.05
                )
                simulated_trades.append(trade)
        
        trading_metrics = self.evaluator.evaluate_trading_performance(simulated_trades)
        
        # Save results
        results = {
            'model': 'kalman_pairs',
            'n_signals': len([s for s in signals if s.signal != 0]),
            'n_trades': len(trades),
            'final_state': kalman.get_state(),
            'trading_metrics': trading_metrics
        }
        
        # Save to file
        os.makedirs(save_dir, exist_ok=True)
        with open(f'{save_dir}/kalman_pairs_results.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"Kalman Pairs Results:")
        logger.info(f"  Signals: {results['n_signals']}")
        logger.info(f"  Trades: {results['n_trades']}")
        logger.info(f"  Sharpe: {trading_metrics.get('sharpe_ratio', 0):.2f}")
        logger.info(f"  Max DD: {trading_metrics.get('max_drawdown', 0):.2%}")
        
        self.trained_models['kalman_pairs'] = {
            'model': kalman,
            'results': results
        }
        
        return results
    
    def measure_latencies(self, save_dir: str):
        """Measure inference latencies for all trained models"""
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 4: MEASURING INFERENCE LATENCIES")
        logger.info(f"{'='*60}")
        
        latency_results = {}
        
        if 'gru_cnn' in self.trained_models:
            model = self.trained_models['gru_cnn']['model']
            
            # CPU latency
            cpu_latencies = self.evaluator.measure_inference_latency(
                model, input_shape=(1, 100, 40), n_iterations=1000, device='cpu'
            )
            
            logger.info(f"\nGRU-CNN Latencies:")
            logger.info(f"  Avg: {cpu_latencies['avg_latency_us']:.2f} µs")
            logger.info(f"  P99: {cpu_latencies['p99_latency_us']:.2f} µs")
            logger.info(f"  P999: {cpu_latencies['p999_latency_us']:.2f} µs")
            
            latency_results['gru_cnn_cpu'] = cpu_latencies
            
            # GPU latency (if available)
            if torch.cuda.is_available():
                gpu_latencies = self.evaluator.measure_inference_latency(
                    model, input_shape=(1, 100, 40), n_iterations=1000, device='cuda'
                )
                logger.info(f"\nGRU-CNN GPU Latencies:")
                logger.info(f"  Avg: {gpu_latencies['avg_latency_us']:.2f} µs")
                logger.info(f"  P99: {gpu_latencies['p99_latency_us']:.2f} µs")
                
                latency_results['gru_cnn_gpu'] = gpu_latencies
        
        # Save latency results
        with open(f'{save_dir}/latency_results.json', 'w') as f:
            json.dump(latency_results, f, indent=2)
        
        return latency_results
    
    def export_to_onnx(self, save_dir: str):
        """Export trained models to ONNX for deployment"""
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 5: EXPORTING MODELS TO ONNX")
        logger.info(f"{'='*60}")
        
        if 'gru_cnn' in self.trained_models:
            model = self.trained_models['gru_cnn']['model']
            model.eval()
            
            dummy_input = torch.randn(1, 100, 40)
            onnx_path = f'{save_dir}/gru_cnn.onnx'
            
            try:
                torch.onnx.export(
                    model,
                    dummy_input,
                    onnx_path,
                    export_params=True,
                    opset_version=14,
                    do_constant_folding=True,
                    input_names=['input'],
                    output_names=['classification', 'regression', 'volatility'],
                    dynamic_axes={
                        'input': {0: 'batch_size'},
                        'classification': {0: 'batch_size'},
                        'regression': {0: 'batch_size'},
                        'volatility': {0: 'batch_size'}
                    },
                    dynamo=False  # Disable new exporter
                )
                logger.info(f"✓ Exported GRU-CNN to {onnx_path}")
            except Exception as e:
                logger.error(f"ONNX export failed: {e}")
    
    def generate_final_report(self, all_results: Dict, save_dir: str):
        """Generate comprehensive training report"""
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 6: GENERATING FINAL REPORT")
        logger.info(f"{'='*60}")
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'config': self.config,
            'summary': {
                'models_trained': list(self.trained_models.keys()),
                'gru_cnn_results': all_results.get('gru_cnn', {}),
                'kalman_pairs_results': all_results.get('kalman_pairs', {})
            },
            'performance_targets': self.evaluator.check_performance_targets({
                'accuracy': all_results.get('gru_cnn', {}).get('avg_accuracy', 0),
                'f1_macro': all_results.get('gru_cnn', {}).get('avg_f1_macro', 0),
                'sharpe_ratio': all_results.get('kalman_pairs', {}).get('trading_metrics', {}).get('sharpe_ratio', 0),
                'profit_factor': all_results.get('kalman_pairs', {}).get('trading_metrics', {}).get('profit_factor', 0),
                'max_drawdown': all_results.get('kalman_pairs', {}).get('trading_metrics', {}).get('max_drawdown', 1.0)
            })
        }
        
        # Save report
        report_path = f'{save_dir}/training_report.json'
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"\n✓ Training report saved to {report_path}")
        
        return report
    
    def run_full_pipeline(self, data_path: str, output_dir: str):
        """Run complete training pipeline"""
        logger.info(f"\n{'#'*60}")
        logger.info(f"# HFT ML TRAINING PIPELINE")
        logger.info(f"{'#'*60}")
        logger.info(f"Started: {datetime.now().isoformat()}")
        logger.info(f"Device: {self.device}")
        logger.info(f"Symbol: {self.config['symbol']}")
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Step 1: Load and prepare data
        data = self.load_and_prepare_data(data_path)
        
        # Step 2: Prepare sequences
        logger.info(f"\nPreparing sequences...")
        X, y = self.prepare_sequences(
            data['features'],
            data['labels'],
            sequence_length=self.config.get('sequence_length', 100),
            horizon=self.config.get('prediction_horizon', 10)
        )
        
        # Step 3: Train GRU-CNN
        gru_cnn_results = self.train_gru_cnn(X, y, save_dir=output_dir)
        
        # Step 4: Train Kalman Pairs (if pair symbol provided)
        kalman_results = {}
        if self.config.get('pair_symbol'):
            # Load pair data
            pair_data_path = os.path.join(data_path, f"{self.config['pair_symbol']}.parquet")
            if os.path.exists(pair_data_path):
                loader = LOBDataLoader(DataConfig(
                    symbol=self.config['pair_symbol'],
                    asset_class=self.config['asset_class'],
                    n_levels=self.config['n_levels'],
                    data_dir=data_path
                ))
                pair_data = loader.load_from_parquet(pair_data_path)
                kalman_results = self.train_kalman_pairs(data, pair_data, save_dir=output_dir)
        
        # Step 5: Measure latencies
        latency_results = self.measure_latencies(output_dir)
        
        # Step 6: Export to ONNX
        self.export_to_onnx(output_dir)
        
        # Step 7: Generate report
        all_results = {
            'gru_cnn': gru_cnn_results,
            'kalman_pairs': kalman_results,
            'latencies': latency_results
        }
        
        report = self.generate_final_report(all_results, output_dir)
        
        logger.info(f"\n{'#'*60}")
        logger.info(f"# PIPELINE COMPLETE")
        logger.info(f"{'#'*60}")
        logger.info(f"Finished: {datetime.now().isoformat()}")
        
        return report


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='HFT ML Training Pipeline')
    parser.add_argument('--symbol', type=str, default='RELIANCE', help='Symbol to train on')
    parser.add_argument('--pair-symbol', type=str, default=None, help='Pair symbol for arbitrage')
    parser.add_argument('--data-dir', type=str, default='./data', help='Data directory')
    parser.add_argument('--output-dir', type=str, default='./output', help='Output directory')
    parser.add_argument('--horizon', type=int, default=10, help='Prediction horizon (ticks)')
    parser.add_argument('--epochs', type=int, default=50, help='Max training epochs')
    parser.add_argument('--batch-size', type=int, default=256, help='Batch size')
    parser.add_argument('--lr', type=float, default=1e-3, help='Learning rate')
    parser.add_argument('--mixed-precision', action='store_true', help='Use mixed precision')
    
    args = parser.parse_args()
    
    # Configuration
    config = {
        'symbol': args.symbol,
        'pair_symbol': args.pair_symbol,
        'asset_class': 'equity',
        'n_levels': 10,
        'tick_size': 0.05,
        'horizons': [1, 5, 10, 50, 100],
        'tolerance_spread_mult': 0.5,
        'transaction_cost_bps': 5.0,
        'initial_capital': 10_000_000,
        'sequence_length': 100,
        'prediction_horizon': args.horizon,
        'learning_rate': args.lr,
        'batch_size': args.batch_size,
        'max_epochs': args.epochs,
        'patience': 5,
        'mixed_precision': args.mixed_precision
    }
    
    # Run pipeline
    orchestrator = HFTTrainingOrchestrator(config)
    report = orchestrator.run_full_pipeline(args.data_dir, args.output_dir)
    
    return report


if __name__ == '__main__':
    main()
