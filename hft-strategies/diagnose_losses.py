"""Diagnostic: analyze WHY each tactic loses money on real data."""
import os, sys
import numpy as np
import pandas as pd
from collections import deque

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

df = pd.read_parquet(os.path.join(SCRIPT_DIR, "data", "SBIN_real.parquet"))
print(f"Real SBIN data: {len(df):,} ticks, {df['timestamp'].dt.date.nunique()} days")
print(f"Price: {df['bid'].min():.2f} - {df['bid'].max():.2f}")
print()

# Compute V_t (100-tick rolling for SESO-style, 4-tick for others)
df['vt_100'] = df['trade_size'].rolling(100, min_periods=1).sum()
df['vt_4'] = df['trade_size'].rolling(4, min_periods=1).sum()
df['ir'] = (df['bid_size_l0'] + df['bid_size_l1'] + df['bid_size_l2']) / \
           (df['ask_size_l0'] + df['ask_size_l1'] + df['ask_size_l2']).replace(0, 1)
df['mid'] = (df['bid'] + df['ask']) / 2
df['spread'] = df['ask'] - df['bid']

# Rolling VWAP
df['roll_vwap'] = df['trade_price'].rolling(500, min_periods=100).median()

# Price returns
df['ret_1'] = df['mid'].pct_change()
df['ret_5'] = df['mid'].pct_change(5)
df['ret_10'] = df['mid'].pct_change(10)

# Session phase
df['minute'] = df['timestamp'].dt.hour * 60 + df['timestamp'].dt.minute
df['is_open'] = (df['minute'] >= 570) & (df['minute'] < 600)  # 9:30-10:00
df['is_close'] = (df['minute'] >= 900)  # 15:00+

print("=" * 80)
print("  LES DIAGNOSTIC: Why does it lose?")
print("=" * 80)

# Simulate LES with detailed tracking
VT_ENTRY_MAX = 10000
IR_ENTRY_MIN = 1.12
VT_EXIT = 15000
STOP_TICKS = 8
TICK_SIZE = 0.05
TICK_VALUE = 15.0
LOT_SIZE = 50
LEVELS = 3

ladders = []
active = None

for idx, row in df.iterrows():
    bid = row['bid']
    ask = row['ask']
    vt = row['vt_4']
    ir = row['ir']

    if active is None:
        if vt < VT_ENTRY_MAX and ir >= IR_ENTRY_MIN:
            # Arm ladder
            prices = [bid, bid - TICK_SIZE, bid - 2 * TICK_SIZE]
            fills = []
            for i, p in enumerate(prices):
                if i == 0 or bid <= p:
                    fills.append({'size': LOT_SIZE, 'price': p})
            total_filled = sum(f['size'] for f in fills)
            total_cost = sum(f['size'] * f['price'] for f in fills)
            avg = total_cost / total_filled if total_filled > 0 else 0
            active = {
                'entry_price': avg,
                'filled': total_filled,
                'cost': total_cost,
                'idx': idx,
                'ts': row['timestamp'],
                'levels_filled': len(fills),
                'entry_vt': vt,
                'entry_ir': ir,
                'entry_spread': row['spread'],
                'max_profit': 0,
            }
    else:
        vt = row['vt_4']
        # Fill remaining levels
        # Check exits
        avg = active['cost'] / active['filled']
        pnl_ticks = (bid - avg) / TICK_SIZE
        profit = pnl_ticks * active['filled'] * TICK_VALUE

        active['max_profit'] = max(active['max_profit'], profit)

        # Exit: V_t > threshold (acceleration)
        if vt > VT_EXIT:
            ladders.append({
                **active,
                'exit_price': ask,
                'exit_vt': vt,
                'pnl': profit,
                'exit_reason': 'TAPE_ACCEL',
                'hold_ticks': idx - active['idx'],
                'max_pnl': active['max_profit'],
            })
            active = None
        # Stop loss
        elif bid < avg - STOP_TICKS * TICK_SIZE:
            ladders.append({
                **active,
                'exit_price': bid,
                'exit_vt': vt,
                'pnl': profit,
                'exit_reason': 'STOP_LOSS',
                'hold_ticks': idx - active['idx'],
                'max_pnl': active['max_profit'],
            })
            active = None

# Force exit
if active is not None:
    avg = active['cost'] / active['filled']
    pnl_ticks = (df.iloc[-1]['bid'] - avg) / TICK_SIZE
    ladders.append({
        **active,
        'exit_price': df.iloc[-1]['bid'],
        'exit_vt': df.iloc[-1]['vt_4'],
        'pnl': pnl_ticks * active['filled'] * TICK_VALUE,
        'exit_reason': 'END',
        'hold_ticks': len(df) - active['idx'],
        'max_pnl': active['max_profit'],
    })

ldf = pd.DataFrame(ladders)

if len(ldf) == 0:
    print("  No ladders.")
else:
    winners = ldf[ldf['pnl'] > 0]
    losers = ldf[ldf['pnl'] <= 0]

    print(f"\n  Total ladders: {len(ldf)}")
    print(f"  Winners: {len(winners)} ({len(winners)/len(ldf)*100:.1f}%)")
    print(f"  Losers: {len(losers)} ({len(losers)/len(ldf)*100:.1f}%)")

    print(f"\n  --- WINNER CHARACTERISTICS (n={len(winners)}) ---")
    print(f"    Avg P&L:       Rs {winners['pnl'].mean():,.0f}")
    print(f"    Avg hold:      {winners['hold_ticks'].mean():.0f} ticks ({winners['hold_ticks'].mean()*0.05:.1f}s)")
    print(f"    Avg levels:    {winners['levels_filled'].mean():.1f} / 3")
    print(f"    Entry V_t:     {winners['entry_vt'].mean():,.0f}")
    print(f"    Entry IR:      {winners['entry_ir'].mean():.2f}")
    print(f"    Exit V_t:      {winners['exit_vt'].mean():,.0f}")
    print(f"    Max P&L seen:  Rs {winners['max_pnl'].mean():,.0f}")
    print(f"    Exit vs Max:   {(winners['pnl'].mean() / winners['max_pnl'].mean()*100):.0f}% captured")

    print(f"\n  --- LOSER CHARACTERISTICS (n={len(losers)}) ---")
    print(f"    Avg P&L:       Rs {losers['pnl'].mean():,.0f}")
    print(f"    Avg hold:      {losers['hold_ticks'].mean():.0f} ticks ({losers['hold_ticks'].mean()*0.05:.1f}s)")
    print(f"    Avg levels:    {losers['levels_filled'].mean():.1f} / 3")
    print(f"    Entry V_t:     {losers['entry_vt'].mean():,.0f}")
    print(f"    Entry IR:      {losers['entry_ir'].mean():.2f}")
    print(f"    Exit V_t:      {losers['exit_vt'].mean():,.0f}")
    print(f"    Max P&L seen:  Rs {losers['max_pnl'].mean():,.0f}")

    # Key diagnostic: How many losers were profitable at some point?
    losers_with_profit = losers[losers['max_pnl'] > 0]
    print(f"\n  --- KEY FINDING ---")
    print(f"    Losers that were profitable at some point: {len(losers_with_profit)} / {len(losers)} ({len(losers_with_profit)/len(losers)*100:.1f}%)")
    print(f"    They saw Rs {losers_with_profit['max_pnl'].mean():,.0f} max profit but exited at Rs {losers_with_profit['pnl'].mean():,.0f}")
    print(f"    → Problem: Stop loss gives back profit before it triggers")

    # Distribution of hold times
    print(f"\n  Hold time distribution (winners vs losers):")
    for label, data in [("WINNERS", winners), ("LOSERS", losers)]:
        h = data['hold_ticks']
        print(f"    {label:8s}: P25={h.quantile(0.25):.0f}t P50={h.median():.0f}t P75={h.quantile(0.75):.0f}t P90={h.quantile(0.90):.0f}t")

    # Entry conditions comparison
    print(f"\n  Entry condition comparison:")
    print(f"    Winners avg IR: {winners['entry_ir'].mean():.3f}")
    print(f"    Losers  avg IR: {losers['entry_ir'].mean():.3f}")
    print(f"    Winners avg V_t: {winners['entry_vt'].mean():,.0f}")
    print(f"    Losers  avg V_t: {losers['entry_vt'].mean():,.0f}")

print("\n" + "=" * 80)
print("  SESO DIAGNOSTIC: Why does it lose?")
print("=" * 80)

# SESO uses V_t 100-tick window
# Sweep detection: 4 consecutive price moves in same direction + V_t > 950K
# Scale out 70% on V_t drop to 60% of peak
# Trail runner at HWM - 3 ticks

SWEEP_VT = 950000
SWEEP_TICKS = 4

sweeps = []
sweep_dir = None
sweep_entry = 0
sweep_idx = 0
sweep_ts = None
scaled_out = False
scale_out_price = 0
scale_out_size = 0
runner_size = 0
runner_exit_price = 0
hwm = 0
vt_peak = 0

recent_prices = []

for idx, row in df.iterrows():
    bid = row['bid']
    ask = row['ask']
    vt = row['vt_100']
    tp = row['trade_price']

    recent_prices.append(tp)
    if len(recent_prices) > 10:
        recent_prices.pop(0)

    if len(recent_prices) >= SWEEP_TICKS:
        ups = sum(1 for i in range(1, SWEEP_TICKS) if recent_prices[-i] > recent_prices[-i-1])
        downs = sum(1 for i in range(1, SWEEP_TICKS) if recent_prices[-i] < recent_prices[-i-1])
    else:
        ups = downs = 0

    if sweep_dir is None:
        if ups >= SWEEP_TICKS - 1 and vt > SWEEP_VT:
            sweep_dir = "UP"
            sweep_entry = ask
            sweep_idx = idx
            sweep_ts = row['timestamp']
            hwm = ask
            vt_peak = vt
            scaled_out = False
            runner_size = 100
        elif downs >= SWEEP_TICKS - 1 and vt > SWEEP_VT:
            sweep_dir = "DOWN"
            sweep_entry = bid
            sweep_idx = idx
            sweep_ts = row['timestamp']
            hwm = bid
            vt_peak = vt
            scaled_out = False
            runner_size = 100
    else:
        if sweep_dir == "UP":
            hwm = max(hwm, ask)
            # Scale out on V_t drop
            if not scaled_out and vt < vt_peak * 0.6:
                scaled_out = True
                scale_out_price = ask
                scale_out_size = 70
                runner_size = 30
            # Trail stop on runner
            if scaled_out and runner_size > 0 and bid < hwm - 0.15:
                runner_exit_price = bid
                pnl_scale = (scale_out_price - sweep_entry) / TICK_SIZE * scale_out_size * TICK_VALUE
                pnl_runner = (runner_exit_price - sweep_entry) / TICK_SIZE * runner_size * TICK_VALUE
                sweeps.append({
                    'dir': 'UP',
                    'entry': sweep_entry,
                    'scale_px': scale_out_price,
                    'scale_pnl': pnl_scale,
                    'runner_px': runner_exit_price,
                    'runner_pnl': pnl_runner,
                    'total_pnl': pnl_scale + pnl_runner,
                    'reason': 'TRAIL',
                    'vt_entry': vt_peak,
                })
                sweep_dir = None
            # Time stop
            elif (row['timestamp'] - sweep_ts).total_seconds() > 20:
                if scaled_out:
                    runner_exit_price = ask
                    pnl_scale = (scale_out_price - sweep_entry) / TICK_SIZE * scale_out_size * TICK_VALUE
                    pnl_runner = (runner_exit_price - sweep_entry) / TICK_SIZE * runner_size * TICK_VALUE
                else:
                    pnl_scale = 0
                    pnl_runner = (ask - sweep_entry) / TICK_SIZE * 100 * TICK_VALUE
                    runner_exit_price = ask
                sweeps.append({
                    'dir': 'UP',
                    'entry': sweep_entry,
                    'scale_px': scale_out_price if scaled_out else 0,
                    'scale_pnl': pnl_scale,
                    'runner_px': runner_exit_price,
                    'runner_pnl': pnl_runner,
                    'total_pnl': pnl_scale + pnl_runner,
                    'reason': 'TIME',
                    'vt_entry': vt_peak,
                })
                sweep_dir = None
        else:  # DOWN
            hwm = min(hwm, bid)
            if not scaled_out and vt < vt_peak * 0.6:
                scaled_out = True
                scale_out_price = bid
                scale_out_size = 70
                runner_size = 30
            if scaled_out and runner_size > 0 and ask > hwm + 0.15:
                runner_exit_price = ask
                pnl_scale = (sweep_entry - scale_out_price) / TICK_SIZE * scale_out_size * TICK_VALUE
                pnl_runner = (sweep_entry - runner_exit_price) / TICK_SIZE * runner_size * TICK_VALUE
                sweeps.append({
                    'dir': 'DOWN',
                    'entry': sweep_entry,
                    'scale_px': scale_out_price,
                    'scale_pnl': pnl_scale,
                    'runner_px': runner_exit_price,
                    'runner_pnl': pnl_runner,
                    'total_pnl': pnl_scale + pnl_runner,
                    'reason': 'TRAIL',
                    'vt_entry': vt_peak,
                })
                sweep_dir = None
            elif (row['timestamp'] - sweep_ts).total_seconds() > 20:
                if scaled_out:
                    runner_exit_price = bid
                    pnl_scale = (sweep_entry - scale_out_price) / TICK_SIZE * scale_out_size * TICK_VALUE
                    pnl_runner = (sweep_entry - runner_exit_price) / TICK_SIZE * runner_size * TICK_VALUE
                else:
                    pnl_scale = 0
                    pnl_runner = (sweep_entry - bid) / TICK_SIZE * 100 * TICK_VALUE
                    runner_exit_price = bid
                sweeps.append({
                    'dir': 'DOWN',
                    'entry': sweep_entry,
                    'scale_px': scale_out_price if scaled_out else 0,
                    'scale_pnl': pnl_scale,
                    'runner_px': runner_exit_price,
                    'runner_pnl': pnl_runner,
                    'total_pnl': pnl_scale + pnl_runner,
                    'reason': 'TIME',
                    'vt_entry': vt_peak,
                })
                sweep_dir = None

sdf = pd.DataFrame(sweeps)
if len(sdf) == 0:
    print("  No sweeps.")
else:
    winners = sdf[sdf['total_pnl'] > 0]
    losers = sdf[sdf['total_pnl'] <= 0]

    print(f"\n  Total sweeps: {len(sdf)}")
    print(f"  Winners: {len(winners)} ({len(winners)/len(sdf)*100:.1f}%)")
    print(f"  Losers: {len(losers)} ({len(losers)/len(sdf)*100:.1f}%)")
    print(f"  Total P&L: Rs {sdf['total_pnl'].sum():,.0f}")

    print(f"\n  --- WINNER CHARACTERISTICS ---")
    print(f"    Avg total P&L:  Rs {winners['total_pnl'].mean():,.0f}")
    print(f"    Avg scale P&L:  Rs {winners['scale_pnl'].mean():,.0f}")
    print(f"    Avg runner P&L: Rs {winners['runner_pnl'].mean():,.0f}")

    print(f"\n  --- LOSER CHARACTERISTICS ---")
    print(f"    Avg total P&L:  Rs {losers['total_pnl'].mean():,.0f}")
    print(f"    Avg scale P&L:  Rs {losers['scale_pnl'].mean():,.0f}")
    print(f"    Avg runner P&L: Rs {losers['runner_pnl'].mean():,.0f}")

    # Direction breakdown
    for d in ['UP', 'DOWN']:
        mask = sdf['dir'] == d
        w = sdf[mask & (sdf['total_pnl'] > 0)]
        l = sdf[mask & (sdf['total_pnl'] <= 0)]
        print(f"\n  --- {d} SWEEPS (n={mask.sum()}) ---")
        print(f"    Winners: {len(w)} ({len(w)/mask.sum()*100:.1f}%), avg Rs {w['total_pnl'].mean():,.0f}")
        print(f"    Losers:  {len(l)} ({len(l)/mask.sum()*100:.1f}%), avg Rs {l['total_pnl'].mean():,.0f}")

    # Trail vs time exits
    for reason in sdf['reason'].unique():
        mask = sdf['reason'] == reason
        print(f"  Exit by {reason}: {mask.sum()} sweeps, avg Rs {sdf.loc[mask, 'total_pnl'].mean():,.0f}")

    print(f"\n  --- KEY FINDING ---")
    # How many losers had profitable scale-outs but lost on runner?
    bad_runner = sdf[(sdf['total_pnl'] < 0) & (sdf['scale_pnl'] > 0)]
    print(f"    Losers where scale-out was profitable but runner lost: {len(bad_runner)} / {len(losers)}")
    if len(bad_runner) > 0:
        print(f"    Avg scale P&L: Rs {bad_runner['scale_pnl'].mean():,.0f}")
        print(f"    Avg runner P&L: Rs {bad_runner['runner_pnl'].mean():,.0f}")
        print(f"    → Problem: Runner trail is too tight, giving back scale-out profits")


print("\n" + "=" * 80)
print("  VTDL DIAGNOSTIC: Why does it lose?")
print("=" * 80)

# VTDL: buy when price > 10 bps below rolling VWAP AND V_t < 10000
# Exit on VWAP return or stop loss at 15 bps deviation

vtdl_trades = []
active_v = None
last_exit = -999

for idx, row in df.iterrows():
    bid = row['bid']
    ask = row['ask']
    vt = row['vt_4']
    vwap = row['roll_vwap']

    if vwap != vwap:  # NaN
        continue

    dev_bps = (vwap - bid) / vwap * 10000

    if active_v is None and idx > last_exit + 80:
        if vt < 10000 and dev_bps >= 10:
            # Arm
            t1_price = round(vwap * (1 - 0.0010), 2)
            t2_price = round(vwap * (1 - 0.0020), 2)
            t3_price = round(vwap * (1 - 0.0030), 2)

            fills = []
            if bid <= t1_price:
                fills.append({'price': bid, 'size': 10})
            if bid <= t2_price:
                fills.append({'price': t2_price, 'size': 15})
            if bid <= t3_price:
                fills.append({'price': t3_price, 'size': 20})

            if fills:
                total_filled = sum(f['size'] for f in fills)
                total_cost = sum(f['size'] * f['price'] for f in fills)
                active_v = {
                    'vwap': vwap,
                    'avg': total_cost / total_filled,
                    'filled': total_filled,
                    'idx': idx,
                    'ts': row['timestamp'],
                    'dev_bps': dev_bps,
                    'levels': len(fills),
                    'vt_entry': vt,
                }

    if active_v is not None:
        dev_from_vwap = (active_v['vwap'] - bid) / active_v['vwap'] * 10000
        ticks_profit = (bid - active_v['avg']) / TICK_SIZE

        if abs(dev_from_vwap) <= 10:
            pnl = ticks_profit * active_v['filled'] * TICK_VALUE
            vtdl_trades.append({**active_v, 'exit_reason': 'VWAP_RETURN', 'pnl': pnl, 'exit_dev': dev_from_vwap})
            active_v = None
            last_exit = idx
        elif ticks_profit >= 3:
            pnl = ticks_profit * active_v['filled'] * TICK_VALUE
            vtdl_trades.append({**active_v, 'exit_reason': 'PARTIAL_PROFIT', 'pnl': pnl, 'exit_dev': dev_from_vwap})
            active_v = None
            last_exit = idx
        elif dev_from_vwap > 15:
            pnl = ticks_profit * active_v['filled'] * TICK_VALUE
            vtdl_trades.append({**active_v, 'exit_reason': 'STOP_LOSS', 'pnl': pnl, 'exit_dev': dev_from_vwap})
            active_v = None
            last_exit = idx

if active_v is not None:
    pnl = (df.iloc[-1]['bid'] - active_v['avg']) / TICK_SIZE * active_v['filled'] * TICK_VALUE
    vtdl_trades.append({**active_v, 'exit_reason': 'END', 'pnl': pnl, 'exit_dev': 0})

vdf = pd.DataFrame(vtdl_trades)
if len(vdf) == 0:
    print("  No VTDL trades.")
else:
    winners = vdf[vdf['pnl'] > 0]
    losers = vdf[vdf['pnl'] <= 0]

    print(f"\n  Total trades: {len(vdf)}")
    print(f"  Winners: {len(winners)} ({len(winners)/len(vdf)*100:.1f}%)")
    print(f"  Losers: {len(losers)} ({len(losers)/len(vdf)*100:.1f}%)")
    print(f"  Total P&L: Rs {vdf['pnl'].sum():,.0f}")

    for reason in vdf['exit_reason'].unique():
        mask = vdf['exit_reason'] == reason
        print(f"  Exit by {reason}: {mask.sum()} trades, avg Rs {vdf.loc[mask, 'pnl'].mean():,.0f}")

    print(f"\n  --- WINNER CHARACTERISTICS ---")
    print(f"    Avg entry dev: {winners['dev_bps'].mean():.1f} bps")
    print(f"    Avg levels filled: {winners['levels'].mean():.1f}")
    print(f"    Avg entry V_t: {winners['vt_entry'].mean():,.0f}")

    print(f"\n  --- LOSER CHARACTERISTICS ---")
    print(f"    Avg entry dev: {losers['dev_bps'].mean():.1f} bps")
    print(f"    Avg exit dev: {losers['exit_dev'].mean():.1f} bps")
    print(f"    Avg levels filled: {losers['levels'].mean():.1f}")

    # Check if losers were in trending regimes
    print(f"\n  --- KEY FINDING ---")
    # What % of losers entered when price was already trending away from VWAP?
    losing_entries = losers[losers['exit_reason'] == 'STOP_LOSS']
    if len(losing_entries) > 0:
        print(f"    Stop loss losers: {len(losing_entries)} / {len(losers)}")
        print(f"    Avg entry deviation: {losing_entries['dev_bps'].mean():.1f} bps")
        print(f"    Avg exit deviation: {losing_entries['exit_dev'].mean():.1f} bps")
        print(f"    → Problem: Price was already deviating {losing_entries['dev_bps'].mean():.0f} bps and continued to {losing_entries['exit_dev'].mean():.0f} bps")
        print(f"    → Entry condition captures falling knives, not reversions")
