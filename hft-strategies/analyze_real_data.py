"""Analyze real SBIN data distributions to calibrate thresholds."""
import pandas as pd
import numpy as np

df = pd.read_parquet("data/SBIN_real.parquet")

# V_t: rolling sum of trade_size, window=4 ticks (200ms)
df['vt'] = df['trade_size'].rolling(4, min_periods=1).sum()

# IR: bid/ask size ratio at top 3 levels
df['bid_sum'] = df['bid_size_l0'] + df['bid_size_l1'] + df['bid_size_l2']
df['ask_sum'] = df['ask_size_l0'] + df['ask_size_l1'] + df['ask_size_l2']
df['ir'] = df['bid_sum'] / df['ask_sum'].replace(0, 1)

print(f"Data: {len(df):,} ticks, {df['timestamp'].dt.date.nunique()} days")
print(f"Price: {df['bid'].min():.2f} - {df['bid'].max():.2f}")
print()

print("V_t distribution (4-tick rolling sum):")
for p in [10, 25, 50, 75, 90, 95, 99]:
    print(f"  P{p:2d}: {df['vt'].quantile(p/100):.0f}")

print(f"\nIR distribution:")
for p in [10, 25, 50, 75, 90, 95, 99]:
    print(f"  P{p:2d}: {df['ir'].quantile(p/100):.2f}")

# Trigger frequencies
print("\n--- Trigger Frequencies ---")
les_strict = (df['vt'] < 60) & (df['ir'] >= 1.5)
les_mid = (df['vt'] < 80) & (df['ir'] >= 1.3)
les_loose = (df['vt'] < 100) & (df['ir'] >= 1.2)

print(f"LES strict  (V_t<60,  IR>=1.5): {les_strict.sum():>6} ({les_strict.mean()*100:.2f}%)")
print(f"LES medium (V_t<80,  IR>=1.3): {les_mid.sum():>6} ({les_mid.mean()*100:.2f}%)")
print(f"LES loose  (V_t<100, IR>=1.2): {les_loose.sum():>6} ({les_loose.mean()*100:.2f}%)")

mp_strict = (df['vt'] > 80) & (df['ir'] >= 1.5)
mp_mid = (df['vt'] > 60) & (df['ir'] >= 1.3)
mp_loose = (df['vt'] > 50) & (df['ir'] >= 1.2)

print(f"MP strict  (V_t>80,  IR>=1.5): {mp_strict.sum():>6} ({mp_strict.mean()*100:.2f}%)")
print(f"MP medium (V_t>60,  IR>=1.3): {mp_mid.sum():>6} ({mp_mid.mean()*100:.2f}%)")
print(f"MP loose  (V_t>50,  IR>=1.2): {mp_loose.sum():>6} ({mp_loose.mean()*100:.2f}%)")

# Spread
spread = df['ask'] - df['bid']
print(f"\nSpread: mean={spread.mean():.3f}, median={spread.median():.3f}, p95={spread.quantile(0.95):.3f}")
