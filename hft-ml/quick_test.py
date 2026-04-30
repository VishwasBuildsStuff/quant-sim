"""
Quick Baseline Test - Does ANY model learn from synthetic data?
Tests: Logistic Regression, Random Forest, Small GRU
"""

import sys
sys.path.insert(0, r'V:\pylibs')

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
import torch
import torch.nn as nn
import time

print("="*60)
print("🧪 QUICK BASELINE TEST")
print("="*60)

# Load data
print("\n📂 Loading data...")
df = pd.read_parquet('data/HNGSNGBEES.parquet')
print(f"  ✓ Loaded {len(df)} snapshots")

# === FEATURES ===
print("\n🔧 Engineering features...")
n = len(df)

# Mid price
mid = (df['bid_price_1'] + df['ask_price_1']) / 2

# Simple features
features = pd.DataFrame({
    'spread': df['ask_price_1'] - df['bid_price_1'],
    'bid_vol': df['bid_volume_1'],
    'ask_vol': df['ask_volume_1'],
    'vol_imbalance': (df['bid_volume_1'] - df['ask_volume_1']) / (df['bid_volume_1'] + df['ask_volume_1']),
    'mid_price': mid,
    'return_1': np.log(mid / mid.shift(1)).fillna(0),
    'return_5': np.log(mid / mid.shift(5)).fillna(0),
    'return_10': np.log(mid / mid.shift(10)).fillna(0),
    'vol_10': np.log(mid / mid.shift(10)).rolling(10).std().fillna(0),
    'vol_20': np.log(mid / mid.shift(20)).rolling(20).std().fillna(0),
})

features = features.dropna()
features = features.fillna(0)

# === LABELS ===
print("🏷️ Generating labels...")
horizon = 10
future_mid = mid.shift(-horizon)
price_change = future_mid - mid

# Use FIXED tolerance (not spread-based) since synthetic spread is too large
# This ensures we get all 3 classes
price_change_abs = price_change.abs()
tolerance = price_change_abs.quantile(0.33)  # Bottom 33% = unchanged

# 3-class labels (balanced by quantile)
labels = np.zeros(len(features), dtype=int)
labels[price_change.values > tolerance] = 2  # Up (top 33%)
labels[price_change.values < -tolerance] = 0  # Down (bottom 33%)
labels[(price_change.values >= -tolerance) & (price_change.values <= tolerance)] = 1  # Unchanged (middle 33%)

print(f"  Distribution: Down={np.sum(labels==0)}, Unchanged={np.sum(labels==1)}, Up={np.sum(labels==2)}")

# Trim to same length
features = features.iloc[:len(labels)]

# === SPLIT ===
X = features.values
y = labels

# Time-based split (no look-ahead)
split_idx = int(len(X) * 0.7)
X_train, X_test = X[:split_idx], X[split_idx:]
y_train, y_test = y[:split_idx], y[split_idx:]

print(f"\n📊 Train: {len(X_train)}, Test: {len(X_test)}")

# === 1. LOGISTIC REGRESSION ===
print("\n" + "="*60)
print("1️⃣ LOGISTIC REGRESSION")
print("="*60)

start = time.time()
lr = LogisticRegression(max_iter=1000, class_weight='balanced')
lr.fit(X_train, y_train)
lr_time = time.time() - start

lr_pred = lr.predict(X_test)
lr_acc = accuracy_score(y_test, lr_pred)
print(f"  Accuracy: {lr_acc:.3f}")
print(f"  Time: {lr_time:.2f}s")
print(f"  Report:\n{classification_report(y_test, lr_pred, zero_division=0)}")

# === 2. RANDOM FOREST ===
print("\n" + "="*60)
print("2️⃣ RANDOM FOREST")
print("="*60)

start = time.time()
rf = RandomForestClassifier(n_estimators=50, max_depth=10, class_weight='balanced', random_state=42)
rf.fit(X_train, y_train)
rf_time = time.time() - start

rf_pred = rf.predict(X_test)
rf_acc = accuracy_score(y_test, rf_pred)
print(f"  Accuracy: {rf_acc:.3f}")
print(f"  Time: {rf_time:.2f}s")
print(f"  Report:\n{classification_report(y_test, rf_pred, zero_division=0)}")

# Feature importance
importances = rf.feature_importances_
top_features = np.argsort(importances)[::-1][:5]
print(f"\n  Top 5 Features:")
for i, idx in enumerate(top_features):
    print(f"    {i+1}. {features.columns[idx]}: {importances[idx]:.3f}")

# === 3. SMALL GRU ===
print("\n" + "="*60)
print("3️⃣ SMALL GRU (1 layer, 32 hidden)")
print("="*60)

seq_len = 20
X_seq = []
y_seq = []
for i in range(seq_len, len(X)):
    X_seq.append(X[i-seq_len:i])
    y_seq.append(y[i])

X_seq = np.array(X_seq, dtype=np.float32)
y_seq = np.array(y_seq, dtype=np.int64)

split = int(len(X_seq) * 0.7)
X_train_seq, X_test_seq = X_seq[:split], X_seq[split:]
y_train_seq, y_test_seq = y_seq[:split], y_seq[split:]

class TinyGRU(nn.Module):
    def __init__(self, input_dim, hidden_dim=32, num_classes=3):
        super().__init__()
        self.gru = nn.GRU(input_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, num_classes)
    
    def forward(self, x):
        out, _ = self.gru(x)
        return self.fc(out[:, -1, :])

model = TinyGRU(X_seq.shape[2])
optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
criterion = nn.CrossEntropyLoss()

# Train for 5 epochs
start = time.time()
for epoch in range(5):
    model.train()
    optimizer.zero_grad()
    outputs = model(torch.FloatTensor(X_train_seq))
    loss = criterion(outputs, torch.LongTensor(y_train_seq))
    loss.backward()
    optimizer.step()

gru_time = time.time() - start

# Test
model.eval()
with torch.no_grad():
    outputs = model(torch.FloatTensor(X_test_seq))
    gru_pred = outputs.argmax(dim=1).numpy()

gru_acc = accuracy_score(y_test_seq, gru_pred)
print(f"  Accuracy: {gru_acc:.3f}")
print(f"  Time: {gru_time:.2f}s")
print(f"  Report:\n{classification_report(y_test_seq, gru_pred, zero_division=0)}")

# === SUMMARY ===
print("\n" + "="*60)
print("📊 BASELINE SUMMARY")
print("="*60)
print(f"{'Model':<20} {'Accuracy':<12} {'Time':<10}")
print("-"*42)
print(f"{'Logistic Regression':<20} {lr_acc:<12.3f} {lr_time:<10.2f}s")
print(f"{'Random Forest':<20} {rf_acc:<12.3f} {rf_time:<10.2f}s")
print(f"{'Small GRU':<20} {gru_acc:<12.3f} {gru_time:<10.2f}s")
print(f"{'Random Guess':<20} {1/3:<12.3f} {'0.00':<10}s")

if max(lr_acc, rf_acc, gru_acc) > 0.45:
    print("\n✅ At least one model learned something!")
    print("   → Synthetic data has SOME predictive signal")
else:
    print("\n⚠️ No model beats random on synthetic data")
    print("   → Expected: synthetic patterns too simple")
    print("   → Next step: Get REAL tick data")
