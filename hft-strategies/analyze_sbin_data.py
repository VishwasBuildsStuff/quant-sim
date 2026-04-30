import pandas as pd

# Read parquet file
df = pd.read_parquet(r"V:\quant_project\hft-strategies\data\SBIN_real.parquet")

print("=" * 60)
print("1. FIRST 5 ROWS")
print("=" * 60)
print(df.head())

print("\n" + "=" * 60)
print("2. COLUMN NAMES AND DTYPES")
print("=" * 60)
print(df.dtypes)

print("\n" + "=" * 60)
print("3. BASIC STATISTICS FOR trade_size, bid, ask")
print("=" * 60)
cols = [c for c in ["trade_size", "bid", "ask"] if c in df.columns]
if cols:
    print(df[cols].describe())
else:
    print("Columns not found. Available columns:", list(df.columns))

print("\n" + "=" * 60)
print("4. TIMESTAMP REGULARITY CHECK")
print("=" * 60)
# Find timestamp column
ts_col = None
for col in df.columns:
    if "time" in col.lower() or "date" in col.lower():
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            ts_col = col
            break

if ts_col is None:
    print("No datetime column found. Available columns:", list(df.columns))
else:
    print(f"Using timestamp column: {ts_col}")
    sorted_ts = df[ts_col].sort_values()
    diffs = sorted_ts.diff().dropna()
    print(f"Total timestamps: {len(diffs) + 1}")
    print(f"Min delta: {diffs.min()}")
    print(f"Max delta: {diffs.max()}")
    print(f"Mean delta: {diffs.mean()}")
    print(f"Median delta: {diffs.median()}")
    print(f"Std delta: {diffs.std()}")
    print(f"\nValue counts of most common deltas:")
    print(diffs.value_counts().head(10))
    coef_var = diffs.std() / diffs.mean() if diffs.mean() != pd.Timedelta(0) else float('inf')
    print(f"\nCoefficient of variation: {coef_var:.4f}")
    print("Timestamps are NOT regularly spaced (high variability)" if coef_var > 0.5 else "Timestamps appear regularly spaced")
