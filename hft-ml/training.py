"""
HFT Model Training Pipeline
Walk-forward cross-validation, rolling re-training, multi-task training loop
"""

import os
import time
import json
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from typing import Dict, List, Tuple, Optional, Callable
from datetime import datetime, timedelta
from pathlib import Path
from tqdm import tqdm
import logging

from models.gru_cnn import GRUCNNModel, MultiTaskLoss, FocalLoss
from models.siamese_lstm_attention import SiameseLSTMAttention
from models.regime_adaptive import RegimeAdaptivePredictor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MultiTaskDataset(Dataset):
    """Custom dataset that supports dictionary labels"""
    
    def __init__(self, X: np.ndarray, y: Dict[str, np.ndarray]):
        self.X = torch.FloatTensor(X)
        self.y = {}
        for k, v in y.items():
            if v.dtype in [np.int32, np.int64]:
                self.y[k] = torch.LongTensor(v)
            else:
                self.y[k] = torch.FloatTensor(v)
    
    def __len__(self):
        return len(self.X)
    
    def __getitem__(self, idx):
        return self.X[idx], {k: v[idx] for k, v in self.y.items()}

class WalkForwardValidator:
    """
    Walk-forward cross-validation for time series

    Training: 1 week
    Validation: 1 day
    Test: 1 day (out-of-sample)
    Roll forward by 1 day
    """

    def __init__(self,
                 total_days: int,
                 train_days: int = 5,
                 val_days: int = 1,
                 test_days: int = 1,
                 roll_days: int = 1):
        self.total_days = total_days
        self.train_days = train_days
        self.val_days = val_days
        self.test_days = test_days
        self.roll_days = roll_days

        self.splits = self._generate_splits()

    def _generate_splits(self) -> List[Dict[str, Tuple[int, int]]]:
        """Generate train/val/test split indices"""
        splits = []
        day_in_samples = 5000  # Approximate samples per trading day (adjusted for smaller datasets)
        
        train_size = self.train_days * day_in_samples
        val_size = self.val_days * day_in_samples
        test_size = self.test_days * day_in_samples
        roll_size = self.roll_days * day_in_samples
        
        start = 0
        while start + train_size + val_size + test_size <= self.total_days * day_in_samples:
            train_end = start + train_size
            val_end = train_end + val_size
            test_end = val_end + test_size
            
            splits.append({
                'train': (start, train_end),
                'val': (train_end, val_end),
                'test': (val_end, test_end)
            })
            
            start += roll_size
        
        logger.info(f"Generated {len(splits)} walk-forward splits")
        return splits

    def get_split_data(self,
                       X: np.ndarray,
                       y: Dict[str, np.ndarray],
                       split_idx: int) -> Dict[str, Tuple[np.ndarray, Dict]]:
        """Get train/val/test data for a specific split"""
        if split_idx >= len(self.splits):
            raise ValueError(f"Split index {split_idx} out of range")

        split = self.splits[split_idx]
        result = {}

        for name, (start, end) in split.items():
            X_split = X[start:end]
            y_split = {k: v[start:end] for k, v in y.items()}
            result[name] = (X_split, y_split)

        return result


class HFTTrainer:
    """
    Trains HFT models with multi-task learning
    Supports: GRU-CNN, Siamese LSTM, Regime-Adaptive
    """

    def __init__(self,
                 model: nn.Module,
                 device: str = 'cuda' if torch.cuda.is_available() else 'cpu',
                 learning_rate: float = 1e-3,
                 weight_decay: float = 1e-5,
                 batch_size: int = 256,
                 max_epochs: int = 50,
                 patience: int = 5,
                 gradient_clip: float = 1.0,
                 use_mixed_precision: bool = False):

        self.model = model
        self.device = torch.device(device)
        self.model.to(self.device)

        self.learning_rate = learning_rate
        self.weight_decay = weight_decay
        self.batch_size = batch_size
        self.max_epochs = max_epochs
        self.patience = patience
        self.gradient_clip = gradient_clip

        # Mixed precision for faster training on GPU
        self.use_mixed_precision = use_mixed_precision and device == 'cuda'
        self.scaler = torch.cuda.amp.GradScaler() if self.use_mixed_precision else None

        # Optimizer with learning rate scheduling
        self.optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=learning_rate,
            weight_decay=weight_decay,
            betas=(0.9, 0.999)
        )

        self.scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer,
            mode='min',
            factor=0.5,
            patience=5,
            min_lr=1e-5,
            cooldown=2
        )

        # Multi-task loss
        self.criterion = MultiTaskLoss(
            class_weight=1.0,
            reg_weight=0.5,
            vol_weight=0.3
        )

        # Training history
        self.history = {
            'train_loss': [],
            'val_loss': [],
            'train_acc': [],
            'val_acc': [],
            'lr': []
        }

        self.best_model_state = None
        self.best_val_loss = float('inf')
        self.epochs_without_improvement = 0

        logger.info(f"Model on {self.device} | Params: {sum(p.numel() for p in model.parameters()):,}")

    def train_epoch(self, dataloader: DataLoader) -> Dict[str, float]:
        """Single training epoch"""
        self.model.train()
        total_loss = 0
        total_class_loss = 0
        total_reg_loss = 0
        total_vol_loss = 0
        correct = 0
        total = 0
        
        pbar = tqdm(dataloader, desc='Training', leave=False)
        
        for batch_idx, (X_batch, y_batch) in enumerate(pbar):
            X_batch = X_batch.to(self.device)
            y_batch = {k: v.to(self.device) for k, v in y_batch.items()}
            
            # Forward pass
            outputs = self.model(X_batch)
            
            # Normalize loss components to same scale
            class_loss = self.criterion.focal_loss(outputs['classification'], y_batch['classification'])
            reg_loss = self.criterion.huber_loss(outputs['regression'], y_batch['regression'])
            vol_loss = self.criterion.mse_loss(outputs['volatility'], y_batch['volatility'])
            
            # Weight losses equally (uncertainty weighting handles scaling)
            loss = self.criterion.class_weight * class_loss + \
                   self.criterion.reg_weight * reg_loss + \
                   self.criterion.vol_weight * vol_loss
            
            # Backward pass
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.gradient_clip)
            self.optimizer.step()
            self.optimizer.zero_grad()
            
            # Metrics
            total_loss += loss.item()
            total_class_loss += class_loss.item()
            total_reg_loss += reg_loss.item()
            total_vol_loss += vol_loss.item()
            class_preds = outputs['classification'].argmax(dim=1)
            correct += (class_preds == y_batch['classification']).sum().item()
            total += len(y_batch['classification'])
            
            pbar.set_postfix({
                'loss': f'{loss.item():.4f}',
                'acc': f'{correct/total:.3f}',
                'cls': f'{class_loss.item():.3f}',
                'reg': f'{reg_loss.item():.3f}'
            })
        
        return {
            'loss': total_loss / len(dataloader),
            'class_loss': total_class_loss / len(dataloader),
            'reg_loss': total_reg_loss / len(dataloader),
            'vol_loss': total_vol_loss / len(dataloader),
            'accuracy': correct / total
        }

    @torch.no_grad()
    def validate(self, dataloader: DataLoader) -> Dict[str, float]:
        """Validation pass"""
        self.model.eval()
        total_loss = 0
        correct = 0
        total = 0

        for X_batch, y_batch in dataloader:
            X_batch = X_batch.to(self.device)
            y_batch = {k: v.to(self.device) for k, v in y_batch.items()}

            outputs = self.model(X_batch)
            loss = self.criterion(outputs, y_batch)

            total_loss += loss.item()
            class_preds = outputs['classification'].argmax(dim=1)
            correct += (class_preds == y_batch['classification']).sum().item()
            total += len(y_batch['classification'])

        return {
            'loss': total_loss / len(dataloader),
            'accuracy': correct / total
        }

    def train(self,
              train_loader: DataLoader,
              val_loader: DataLoader,
              save_dir: str = './checkpoints') -> Dict:
        """
        Full training loop with early stopping
        """
        Path(save_dir).mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting training: {self.max_epochs} epochs, patience={self.patience}")

        for epoch in range(self.max_epochs):
            # Train
            train_metrics = self.train_epoch(train_loader)

            # Validate
            val_metrics = self.validate(val_loader)

            # Update learning rate
            self.scheduler.step(val_metrics['loss'])
            current_lr = self.optimizer.param_groups[0]['lr']

            # Record history
            self.history['train_loss'].append(train_metrics['loss'])
            self.history['val_loss'].append(val_metrics['loss'])
            self.history['train_acc'].append(train_metrics['accuracy'])
            self.history['val_acc'].append(val_metrics['accuracy'])
            self.history['lr'].append(current_lr)

            # Early stopping check
            if val_metrics['loss'] < self.best_val_loss:
                self.best_val_loss = val_metrics['loss']
                self.best_model_state = {
                    k: v.cpu().clone() for k, v in self.model.state_dict().items()
                }
                self.epochs_without_improvement = 0

                # Save checkpoint
                checkpoint_path = os.path.join(save_dir, 'best_model.pth')
                torch.save({
                    'epoch': epoch,
                    'model_state_dict': self.best_model_state,
                    'optimizer_state_dict': self.optimizer.state_dict(),
                    'val_loss': self.best_val_loss,
                    'val_acc': val_metrics['accuracy']
                }, checkpoint_path)
            else:
                self.epochs_without_improvement += 1

            # Logging
            logger.info(
                f"Epoch {epoch+1}/{self.max_epochs} | "
                f"Train Loss: {train_metrics['loss']:.4f} | "
                f"Val Loss: {val_metrics['loss']:.4f} | "
                f"Val Acc: {val_metrics['accuracy']:.3f} | "
                f"LR: {current_lr:.2e} | "
                f"Patience: {self.epochs_without_improvement}/{self.patience}"
            )

            if self.epochs_without_improvement >= self.patience:
                logger.info(f"Early stopping at epoch {epoch+1}")
                break

        # Load best model
        if self.best_model_state:
            self.model.load_state_dict(self.best_model_state)
            self.model.to(self.device)

        return self.history

    def walk_forward_train(self,
                          X: np.ndarray,
                          y: Dict[str, np.ndarray],
                          validator: WalkForwardValidator,
                          save_dir: str = './walk_forward_checkpoints') -> Dict:
        """
        Walk-forward training across all splits
        """
        all_results = []

        for split_idx in range(len(validator.splits)):
            logger.info(f"\n{'='*60}")
            logger.info(f"WALK-FORWARD SPLIT {split_idx+1}/{len(validator.splits)}")
            logger.info(f"{'='*60}")

            # Get split data
            splits = validator.get_split_data(X, y, split_idx)
            X_train, y_train = splits['train']
            X_val, y_val = splits['val']
            X_test, y_test = splits['test']
            
            # Create data loaders using MultiTaskDataset
            train_dataset = MultiTaskDataset(X_train, y_train)
            val_dataset = MultiTaskDataset(X_val, y_val)
            
            train_loader = DataLoader(train_dataset, batch_size=self.batch_size, shuffle=True, num_workers=0)
            val_loader = DataLoader(val_dataset, batch_size=self.batch_size, shuffle=False, num_workers=0)

            # Reset model for each split (to avoid data leakage)
            self.model.apply(self._reset_weights)
            self.best_model_state = None
            self.best_val_loss = float('inf')

            # Train on this split
            history = self.train(train_loader, val_loader,
                               save_dir=f'{save_dir}/split_{split_idx}')

            # Evaluate on test set
            test_metrics = self.evaluate_split(X_test, y_test)

            all_results.append({
                'split': split_idx,
                'train_history': history,
                'test_metrics': test_metrics,
                'best_val_loss': self.best_val_loss
            })

        # Aggregate results
        return self._aggregate_results(all_results)

    def _reset_weights(self, m):
        """Reset model weights for fresh training on each split"""
        if hasattr(m, 'reset_parameters'):
            m.reset_parameters()

    @torch.no_grad()
    def evaluate_split(self, X: np.ndarray, y: Dict[str, np.ndarray]) -> Dict:
        """Evaluate on test split"""
        self.model.eval()
        
        dataset = MultiTaskDataset(X, y)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=False)

        all_preds = []
        all_labels = []

        for X_batch, y_batch in loader:
            X_batch = X_batch.to(self.device)
            outputs = self.model(X_batch)

            preds = outputs['classification'].argmax(dim=1).cpu().numpy()
            labels = y_batch['classification'].cpu().numpy()

            all_preds.append(preds)
            all_labels.append(labels)

        all_preds = np.concatenate(all_preds)
        all_labels = np.concatenate(all_labels)

        # Metrics
        accuracy = (all_preds == all_labels).mean()

        # Per-class metrics
        from sklearn.metrics import classification_report, f1_score
        report = classification_report(all_labels, all_preds, output_dict=True, zero_division=0)

        return {
            'accuracy': accuracy,
            'f1_macro': f1_score(all_labels, all_preds, average='macro', zero_division=0),
            'f1_up': report.get('2', {}).get('f1-score', 0),
            'f1_down': report.get('0', {}).get('f1-score', 0),
            'precision': report.get('macro avg', {}).get('precision', 0),
            'recall': report.get('macro avg', {}).get('recall', 0),
            'classification_report': report
        }

    def _aggregate_results(self, all_results: List[Dict]) -> Dict:
        """Aggregate walk-forward results"""
        agg = {
            'n_splits': len(all_results),
            'avg_accuracy': np.mean([r['test_metrics']['accuracy'] for r in all_results]),
            'avg_f1_macro': np.mean([r['test_metrics']['f1_macro'] for r in all_results]),
            'avg_f1_up': np.mean([r['test_metrics']['f1_up'] for r in all_results]),
            'avg_f1_down': np.mean([r['test_metrics']['f1_down'] for r in all_results]),
            'avg_val_loss': np.mean([r['best_val_loss'] for r in all_results]),
            'per_split': all_results
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"WALK-FORWARD SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Splits: {agg['n_splits']}")
        logger.info(f"Accuracy: {agg['avg_accuracy']:.3f}")
        logger.info(f"F1 Macro: {agg['avg_f1_macro']:.3f}")
        logger.info(f"F1 Up: {agg['avg_f1_up']:.3f}")
        logger.info(f"F1 Down: {agg['avg_f1_down']:.3f}")

        return agg
