# 🧠 HFT ML Training Pipeline - Complete Documentation

## 📋 Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Model Architectures](#model-architectures)
3. [Training Methodology](#training-methodology)
4. [Evaluation Metrics](#evaluation-metrics)
5. [Deployment Guide](#deployment-guide)
6. [Risk Management](#risk-management)
7. [Data Integrity Checklist](#data-integrity-checklist)
8. [Hyperparameter Tuning](#hyperparameter-tuning)
9. [Quick Start](#quick-start)

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA LAYER                                │
├─────────────────────────────────────────────────────────────┤
│  TimescaleDB / Parquet Files / Kafka Streams                │
│  ↓                                                           │
│  LOBDataLoader → DataIntegrityChecker → FeatureEngineer     │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                  FEATURE ENGINEERING                         │
├─────────────────────────────────────────────────────────────┤
│  OFI, Depth Imbalance, Weighted Mid-Price, Book Slopes      │
│  Realized Vol/Skew, Level Imbalances, Trade Intensity        │
│  ↓                                                           │
│  LabelGenerator (Classification + Regression + Volatility)  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                    MODEL LAYER                               │
├─────────────────────────────────────────────────────────────┤
│  GRU-CNN Hybrid         │ Siamese LSTM + Attention          │
│  Kalman Filter Pairs    │ Regime-Adaptive Gating            │
│  ↓                                                           │
│  Multi-Task Learning (Classification + Regression + Vol)    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                 TRAINING & EVALUATION                        │
├─────────────────────────────────────────────────────────────┤
│  Walk-Forward CV │ Rolling Re-training │ Early Stopping     │
│  Focal Loss      │ Huber Loss        │ Sharpe Loss          │
│  ↓                                                           │
│  Out-of-Sample Metrics: Accuracy, F1, Sharpe, MaxDD        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                  DEPLOYMENT LAYER                            │
├─────────────────────────────────────────────────────────────┤
│  ONNX Export │ TensorRT Optimization │ FPGA Compilation     │
│  ↓                                                           │
│  Inference Latency < 10µs │ Signal Generation Rate > 95%   │
└─────────────────────────────────────────────────────────────┘
```

---

## Model Architectures

### 1. GRU-CNN Hybrid

**Purpose**: Predict short-term price direction (1-500 ticks ahead)

**Architecture**:
```
Input: (batch, seq_len=100, n_features=45)
  ↓
CNN Branch (Local patterns):
  Conv1D(32) → ReLU → MaxPool
  Conv1D(64) → ReLU → MaxPool
  Conv1D(128) → ReLU → MaxPool
  ↓
GRU Branch (Sequential deps):
  Bidirectional GRU(128, 2 layers) → Attention(4 heads)
  ↓
Fusion: [CNN features, GRU output] → Dense(256) → Dense(128)
  ↓
Multi-Task Output:
  - Classification: Dense(3) [Down, Unchanged, Up]
  - Regression: Dense(1) [Price change]
  - Volatility: Dense(1) → Softplus [Realized vol]
```

**Parameters**: ~2.5M  
**Inference Latency**: ~8µs (CPU), ~2µs (GPU)

---

### 2. Siamese LSTM + Attention

**Purpose**: Model bid/ask asymmetry with cross-attention

**Architecture**:
```
Input Bid: (batch, seq_len, 20)  │  Input Ask: (batch, seq_len, 20)
  ↓                                │
Shared LSTM(128, 2 layers)        │  (Same weights)
  ↓                                │
Bid LSTM Output                   │  Ask LSTM Output
  ↓                                │
Cross-Attention (Bid↔Ask)          │
  ↓
Concat → Project → Dense → Multi-Task Output
```

**Key Innovation**: Bid and ask sides processed separately, then attended to each other, capturing microstructure dynamics that single-sided models miss.

---

### 3. Kalman Filter Pairs Trading

**Purpose**: Dynamic hedge ratio estimation for statistical arbitrage

**How it works**:
```
For each timestamp:
  1. Observe: price_A, price_B
  2. Kalman Update:
     - State: [alpha, beta] (intercept, hedge ratio)
     - Predict spread = price_A - (alpha + beta * price_B)
  3. Compute z-score of spread residual
  4. Generate signal:
     - z > 2.0 → Short spread (sell A, buy B)
     - z < -2.0 → Long spread (buy A, sell B)
     - |z| < 0.5 → Exit position
```

**Advantages over static cointegration**:
- ✅ Adapts to changing relationships
- ✅ Handles structural breaks
- ✅ Provides uncertainty estimates
- ✅ No look-ahead bias

---

### 4. Regime-Adaptive Gating

**Purpose**: Blend predictions from multiple models based on market regime

**Architecture**:
```
Features → HMM Regime Detector (4 states):
  - Low Volatility
  - High Volatility
  - Trending
  - Mean-Reverting
  ↓
Gating Network → Weights for sub-models:
  - Regime 1: 60% GRU-CNN, 30% LSTM, 10% Kalman
  - Regime 2: 40% GRU-CNN, 50% LSTM, 10% Kalman
  - ...
  ↓
Blended Prediction
```

---

## Training Methodology

### Walk-Forward Cross-Validation

```
Time →
├─── Week 1 ───├─ Day 6 ─├─ Day 7 ─┤
│   Train      │   Val   │  Test   │
└──────────────┴─────────┴─────────┘
                ├─────────┴─────────┴─ Week 2 ─┤
                │   Train (Days 2-6)            │ Val │ Test │
                └───────────────────────────────┴─────┴──────┘
                                                ...
```

**Process**:
1. Train on 5 days of data
2. Validate on next 1 day
3. Test on next 1 day (out-of-sample)
4. Roll forward by 1 day
5. Repeat for entire dataset

**Why**: Mimics real-world deployment where you only have past data

### Rolling Re-Training

```python
# Re-train every 4 hours or daily
retrain_interval = timedelta(hours=4)
training_window = timedelta(days=5)  # Use most recent 5 days

if current_time - last_retrain > retrain_interval:
    # Get recent data
    recent_data = get_data(current_time - training_window, current_time)
    # Re-train model
    model.fit(recent_data)
    # Deploy new model
    deploy(model)
    last_retrain = current_time
```

### Loss Functions

| Task | Loss | Why |
|------|------|-----|
| Classification | Focal Loss (α=0.25, γ=2.0) | Handles class imbalance, focuses on hard examples |
| Regression | Huber Loss (δ=1.0) | Robust to outliers in price changes |
| Volatility | MSE | Positive targets, less noisy |
| Multi-Task | Uncertainty-weighted sum | Learns optimal task weights automatically |

---

## Evaluation Metrics

### Classification Metrics

| Metric | Target | How to Compute |
|--------|--------|----------------|
| **Accuracy** | > 55% (1-tick) | `(predictions == labels).mean()` |
| **F1 Macro** | > 0.5 | Harmonic mean of precision/recall per class |
| **F1 Up** | > 0.5 | F1 for class 2 (price increase) |
| **F1 Down** | > 0.5 | F1 for class 0 (price decrease) |

### Trading Metrics

| Metric | Target | Formula |
|--------|--------|---------|
| **Sharpe Ratio** | > 1.5 | `mean(excess_returns) / std(excess_returns) * sqrt(252)` |
| **Profit Factor** | > 1.3 | `gross_profit / gross_loss` |
| **Max Drawdown** | < 15% | `max((peak - trough) / peak)` |
| **Win Rate** | > 52% | `winning_trades / total_trades` |

### Latency Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Avg Inference** | < 10µs | `mean(perf_counter_ns() diff)` over 1000 runs |
| **P99 Latency** | < 20µs | 99th percentile |
| **P999 Latency** | < 50µs | 99.9th percentile |
| **Signal Rate** | > 95% | `signals_generated / lob_updates` |

---

## Deployment Guide

### ONNX Export

```python
import torch

# Load trained model
model = GRUCNNModel(n_features=45)
model.load_state_dict(torch.load('checkpoints/best_model.pth'))
model.eval()

# Export to ONNX
dummy_input = torch.randn(1, 100, 45)
torch.onnx.export(
    model,
    dummy_input,
    'gru_cnn.onnx',
    export_params=True,
    opset_version=14,
    input_names=['input'],
    output_names=['classification', 'regression', 'volatility']
)
```

### TensorRT Optimization (GPU Deployment)

```bash
# Convert ONNX to TensorRT engine
trtexec --onnx=gru_cnn.onnx \
        --saveEngine=gru_cnn.engine \
        --fp16 \
        --workspace=4096 \
        --minShapes=input:1x100x45 \
        --optShapes=input:1x100x45 \
        --maxShapes=input:1x100x45
```

### FPGA Deployment (Ultra-Low Latency)

For < 1µs latency, use FPGA with:
- **Xilinx Alveo U250** or **U280**
- Quantize model to INT8
- Use Vitis AI for compilation
- Deploy via multicast feed handler

---

## Risk Management

### Pre-Trade Checks

Every order passes through risk manager:

```python
allowed, reason = risk_manager.check_order(
    symbol='RELIANCE',
    side=1,  # Long
    quantity=100,
    price=2450.00,
    model_confidence=0.72,
    current_volatility=0.25
)

if not allowed:
    logger.warning(f"Order rejected: {reason}")
```

**Checks performed**:
1. ✅ Position limits (max 10,000 shares per symbol)
2. ✅ Portfolio exposure (max ₹10M total)
3. ✅ Concentration (max 20% in single symbol)
4. ✅ Daily loss limit (max ₹50K or 1%)
5. ✅ Maximum drawdown (5% from peak)
6. ✅ Volatility stop (if annualized vol > 50%)
7. ✅ Order rate limit (max 100/sec)
8. ✅ Model confidence (must be > 55%)

### Trading Halt Conditions

System automatically halts trading if:
- Daily loss exceeds limit
- Drawdown exceeds 5%
- Volatility spikes above threshold
- Exchange connectivity lost

**Cooling-off period**: 5 minutes before trading can resume

---

## Data Integrity Checklist

### ✅ Pre-Training Checks

- [ ] **No Look-Ahead Bias**: Features at time `t` only use data up to `t`
- [ ] **Timestamp Alignment**: All data streams synchronized to nanosecond
- [ ] **No Crossed Books**: `bid_price[0] < ask_price[0]` always
- [ ] **No NaN/Inf**: All features finite (use `np.nan_to_num`)
- [ ] **Timestamp Ordering**: Strictly increasing (no duplicates)
- [ ] **Exchange Downtime**: Gaps > 1s identified and handled
- [ ] **Volume Non-Negative**: All volumes >= 0
- [ ] **Price Positive**: All prices > 0
- [ ] **Feature Normalization**: Z-score normalization applied
- [ ] **Class Balance**: Check label distribution (avoid 90/10 splits)
- [ ] **Stationarity Check**: Returns, not prices, for training
- [ ] **Train/Val/Test Split**: No temporal overlap

### How to Verify

```python
from data_loader import DataIntegrityChecker

checker = DataIntegrityChecker()
issues = checker.validate_lob_data(data)

if issues:
    for issue in issues:
        print(f"⚠️ {issue}")
else:
    print("✅ All integrity checks passed")
```

---

## Hyperparameter Tuning

### Grid Search Ranges

| Hyperparameter | Range | Recommended |
|---------------|-------|-------------|
| **Learning Rate** | `[1e-4, 5e-4, 1e-3, 5e-3]` | `1e-3` |
| **Batch Size** | `[64, 128, 256, 512]` | `256` |
| **GRU Hidden** | `[64, 128, 256]` | `128` |
| **GRU Layers** | `[1, 2, 3]` | `2` |
| **CNN Channels** | `[[16,32,64], [32,64,128], [64,128,256]]` | `[32,64,128]` |
| **Attention Heads** | `[2, 4, 8]` | `4` |
| **Dropout** | `[0.1, 0.2, 0.3]` | `0.2` |
| **Sequence Length** | `[50, 100, 200]` | `100` |
| **Prediction Horizon** | `[1, 5, 10, 50]` | `10` |
| **Focal Gamma** | `[1.0, 2.0, 3.0]` | `2.0` |
| **Huber Delta** | `[0.5, 1.0, 2.0]` | `1.0` |

### Bayesian Optimization (Optuna)

```python
import optuna

def objective(trial):
    lr = trial.suggest_float('lr', 1e-4, 1e-2, log=True)
    hidden = trial.suggest_categorical('hidden', [64, 128, 256])
    dropout = trial.suggest_float('dropout', 0.1, 0.4)
    
    # Train model with these params
    model = GRUCNNModel(gru_hidden=hidden, gru_dropout=dropout)
    trainer = HFTTrainer(model, learning_rate=lr)
    history = trainer.train(train_loader, val_loader, max_epochs=20)
    
    return history['val_loss'][-1]

study = optuna.create_study(direction='minimize')
study.optimize(objective, n_trials=50)

print(f"Best params: {study.best_params}")
print(f"Best val loss: {study.best_value}")
```

---

## Quick Start

### 1. Install Dependencies

```bash
cd V:\quant_project\hft-ml
pip install -r requirements.txt
```

### 2. Prepare Data

Your data should be in parquet format with columns:
- `timestamp_ns` (int64)
- `bid_price_1` to `bid_price_10` (float64)
- `bid_volume_1` to `bid_volume_10` (float64)
- `ask_price_1` to `ask_price_10` (float64)
- `ask_volume_1` to `ask_volume_10` (float64)
- `last_trade_price` (float64)
- `last_trade_volume` (float64)
- `trade_side` (int8: 1=buy, -1=sell)

### 3. Run Training

```bash
python orchestrator.py \
    --symbol RELIANCE \
    --pair-symbol TCS \
    --data-dir ./data \
    --output-dir ./output \
    --horizon 10 \
    --epochs 50 \
    --batch-size 256 \
    --lr 1e-3 \
    --mixed-precision
```

### 4. View Results

```bash
cat output/training_report.json
```

### 5. Deploy Model

```python
import torch
import onnxruntime as ort

# Load ONNX model
session = ort.InferenceSession('output/gru_cnn.onnx')

# Run inference
inputs = {'input': features.astype(np.float32)}
outputs = session.run(None, inputs)

class_pred = outputs[0].argmax()  # 0=down, 1=unchanged, 2=up
reg_pred = outputs[1]             # Predicted price change
vol_pred = outputs[2]             # Predicted volatility
```

---

## 📚 File Structure

```
hft-ml/
├── __init__.py
├── data_pipeline.py          # Feature engineering & labeling
├── data_loader.py            # Data loading & integrity checks
├── models/
│   ├── __init__.py
│   ├── gru_cnn.py            # GRU-CNN hybrid model
│   ├── siamese_lstm_attention.py  # Siamese LSTM + Attention
│   ├── kalman_pairs.py       # Kalman Filter pairs trading
│   └── regime_adaptive.py    # Regime-adaptive gating
├── training.py               # Walk-forward training pipeline
├── evaluation.py             # Metrics & latency measurement
├── risk_manager.py           # Risk management overlay
├── orchestrator.py           # Main training orchestration
├── requirements.txt          # Dependencies
└── README.md                 # This file
```

---

## ⚠️ Important Notes

1. **No Look-Ahead Bias**: All features computed only from past data
2. **Non-Stationarity**: Markets change - retrain frequently (every 4 hours)
3. **Transaction Costs**: Always include slippage + fees in backtests
4. **Overfitting Risk**: Walk-forward CV essential, never trust single split
5. **Latency Matters**: Model accuracy useless if inference too slow
6. **Risk First**: Always deploy risk manager before any live trading

---

## 🎓 Academic References

1. **LOB Deep Learning**: "Deep Learning for Limit Order Books" (Zhang et al., 2019)
2. **OFI Features**: "Order Flow Imbalance" (Cont et al., 2014)
3. **Focal Loss**: "Focal Loss for Dense Object Detection" (Lin et al., 2017)
4. **Multi-Task Learning**: "Multi-Task Learning Using Uncertainty" (Kendall et al., 2018)
5. **Kalman Pairs**: "Kalman Filter for Statistical Arbitrage" (Jureček, 2020)
6. **Regime Detection**: "Hidden Markov Models for Financial Time Series" (Hassan & Nath, 2016)

---

**Built for institutional-grade HFT systems targeting sub-10µs inference latency** 🚀

*Version: 1.0.0 | Date: April 5, 2026*
