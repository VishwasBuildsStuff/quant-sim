"""Detailed diagnosis of LES and EODPL losses on real data."""
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

TICK_SIZE = 0.05
TICK_VALUE = 15.0
COMMISSION = 0.05
SLIPPAGE_BPS = 5

# Compute V_t (4-tick rolling)
df['vt'] = df['trade_size'].rolling(4, min_periods=1).sum()
df['ir'] = (df['bid_size_l0'] + df['bid_size_l1'] + df['bid_size_l2']) / \
           (df['ask_size_l0'] + df['ask_size_l1'] + df['ask_size_l2']).replace(0, 1)
df['mid'] = (df['bid'] + df['ask']) / 2
df['spread'] = df['ask'] - df['bid']

# Rolling VWAP
df['roll_vwap'] = df['trade_price'].rolling(500, min_periods=100).median()

# Session phase
df['minute'] = df['timestamp'].dt.hour * 60 + df['timestamp'].dt.minute

print("=" * 80)
print("  LES DIAGNOSIS: Deep dive into 692 trades")
print("=" * 80)

# Simulate LES exactly as the script does
VT_ENTRY_MAX = 10000
IR_ENTRY_MIN = 1.12
VT_EXIT = 15000
STOP_TICKS = 8
LOT_SIZE = 50
LEVELS = 3

ladders = []
active = None

for idx, row in df.iterrows():
    bid = row['bid']
    ask = row['ask']
    vt = row['vt']
    ir = row['ir']

    if active is None:
        if vt < VT_ENTRY_MAX and ir >= IR_ENTRY_MIN:
            prices = [bid, bid - TICK_SIZE, bid - 2 * TICK_SIZE]
            fills = []
            for i, p in enumerate(prices):
                if i == 0 or bid <= p:
                    fills.append({'size': LOT_SIZE, 'price': p})
            total_filled = sum(f['size'] for f in fills)
            total_cost = sum(f['size'] * f['price'] for f in fills)
            avg = total_cost / total_filled if total_filled > 0 else 0
            
            entry_ret_5 = df.loc[idx:idx+5, 'mid'].pct_change().iloc[-1] if idx+5 < len(df) else 0
            
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
                'entry_ret_5': entry_ret_5,
                'entry_minute': row['minute'],
                'max_profit': 0,
                'confirm_deadline': idx + 20,
                'confirmed': False,
            }
    else:
        vt = row['vt']
        
        # V_t confirmation
        if not active['confirmed'] and idx > active['confirm_deadline']:
            if vt <= active['entry_vt'] * 1.3:
                ladders.append({
                    **active,
                    'exit_price': bid,
                    'exit_vt': vt,
                    'pnl': (bid - active['entry_price']) / TICK_SIZE * active['filled'] * TICK_VALUE,
                    'exit_reason': 'NO_MOMENTUM',
                    'hold_ticks': idx - active['idx'],
                    'max_pnl': active['max_profit'],
                })
                active = None
                continue
            else:
                active['confirmed'] = True

        avg = active['cost'] / active['filled']
        pnl_ticks = (bid - avg) / TICK_SIZE
        profit = pnl_ticks * active['filled'] * TICK_VALUE
        active['max_profit'] = max(active['max_profit'], profit)

        if vt > VT_EXIT:
            ladders.append({**active, 'exit_price': ask, 'exit_vt': vt, 'pnl': profit,
                           'exit_reason': 'TAPE_ACCEL', 'hold_ticks': idx - active['idx'],
                           'max_pnl': active['max_profit']})
            active = None
        elif bid < avg - STOP_TICKS * TICK_SIZE:
            ladders.append({**active, 'exit_price': bid, 'exit_vt': vt, 'pnl': profit,
                           'exit_reason': 'STOP_LOSS', 'hold_ticks': idx - active['idx'],
                           'max_pnl': active['max_profit']})
            active = None

if active is not None:
    avg = active['cost'] / active['filled']
    pnl = (df.iloc[-1]['bid'] - avg) / TICK_SIZE * active['filled'] * TICK_VALUE
    ladders.append({**active, 'exit_price': df.iloc[-1]['bid'], 'exit_vt': df.iloc[-1]['vt'],
                   'pnl': pnl, 'exit_reason': 'END', 'hold_ticks': len(df) - active['idx'],
                   'max_pnl': active['max_profit']})

ldf = pd.DataFrame(ladders)
winners = ldf[ldf['pnl'] > 0]
losers = ldf[ldf['pnl'] <= 0]

print(f"\n  Total: {len(ldf)} | Winners: {len(winners)} ({len(winners)/len(ldf)*100:.1f}%) | Losers: {len(losers)}")

# Breakdown by exit reason
for reason in ldf['exit_reason'].unique():
    mask = ldf['exit_reason'] == reason
    subset = ldf[mask]
    wins = (subset['pnl'] > 0).sum()
    print(f"\n  --- {reason} (n={mask.sum()}) ---")
    print(f"    Win rate: {wins}/{mask.sum()} ({wins/mask.sum()*100:.1f}%)")
    print(f"    Avg P&L: Rs {subset['pnl'].mean():,.0f}")
    print(f"    Avg hold: {subset['hold_ticks'].mean():.0f} ticks ({subset['hold_ticks'].mean()*0.05:.1f}s)")
    print(f"    Avg entry V_t: {subset['entry_vt'].mean():,.0f}")
    print(f"    Avg entry IR: {subset['entry_ir'].mean():.3f}")
    print(f"    Avg levels filled: {subset['levels_filled'].mean():.1f}")

# Key: What time of day are losers vs winners?
print(f"\n  --- TIME OF DAY ANALYSIS ---")
for label, data in [("WINNERS", winners), ("LOSERS", losers)]:
    mins = data['entry_minute']
    open_trades = ((mins >= 570) & (mins < 600)).sum()  # 9:30-10:00
    mid_trades = ((mins >= 600) & (mins < 870)).sum()   # 10:00-14:30
    close_trades = (mins >= 870).sum()                   # 14:30+
    print(f"  {label:8s}: Open={open_trades} Mid={mid_trades} Close={close_trades} | Avg IR={data['entry_ir'].mean():.3f} Avg V_t={data['entry_vt'].mean():,.0f}")

# What % of losers were confirmed vs unconfirmed?
losers_no_momentum = losers[losers['exit_reason'] == 'NO_MOMENTUM']
losers_stop = losers[losers['exit_reason'] == 'STOP_LOSS']
losers_accel = losers[losers['exit_reason'] == 'TAPE_ACCEL']

print(f"\n  --- LOSER BREAKDOWN ---")
print(f"  NO_MOMENTUM: {len(losers_no_momentum)} ({len(losers_no_momentum)/len(losers)*100:.1f}% of losers)")
print(f"  STOP_LOSS:   {len(losers_stop)} ({len(losers_stop)/len(losers)*100:.1f}% of losers)")
print(f"  TAPE_ACCEL:  {len(losers_accel)} ({len(losers_accel)/len(losers)*100:.1f}% of losers)")

# NO_MOMENTUM losers: what were their entry conditions?
if len(losers_no_momentum) > 0:
    print(f"\n  --- NO_MOMENTUM LOSER CHARACTERISTICS ---")
    print(f"  Avg entry V_t: {losers_no_momentum['entry_vt'].mean():,.0f}")
    print(f"  Avg entry IR: {losers_no_momentum['entry_ir'].mean():.3f}")
    print(f"  Avg entry spread: {losers_no_momentum['entry_spread'].mean():.4f}")
    print(f"  Avg entry return (5 ticks ahead): {losers_no_momentum['entry_ret_5'].mean()*10000:.1f} bps")

# STOP_LOSS losers: did they ever go positive?
if len(losers_stop) > 0:
    profit_at_some_point = (losers_stop['max_pnl'] > 0).sum()
    print(f"\n  --- STOP_LOSS LOSER CHARACTERISTICS ---")
    print(f"  Were profitable at some point: {profit_at_some_point}/{len(losers_stop)} ({profit_at_some_point/len(losers_stop)*100:.1f}%)")
    print(f"  Avg max profit seen: Rs {losers_stop['max_pnl'].mean():,.0f}")
    print(f"  Avg exit loss: Rs {losers_stop['pnl'].mean():,.0f}")
    print(f"  Avg hold time: {losers_stop['hold_ticks'].mean():.0f} ticks")
    print(f"  Avg levels filled: {losers_stop['levels_filled'].mean():.1f}")


print("\n" + "=" * 80)
print("  EODPL DIAGNOSIS: Deep dive into 8 trades")
print("=" * 80)

# Simulate EODPL exactly
TIER_DEVIATIONS_BPS = [-20, -30, -40, -50]
TIER_SIZES = [25, 35, 45, 55]
PIN_CONVERGENCE_BPS = 5
STOP_LOSS_BPS = 30

eodpl_trades = []
active_e = None
pin_buffer = []
max_pain = None

pin_start = int(len(df) * 0.75)  # last 25% of session

for idx, row in df.iterrows():
    bid = row['bid']
    ask = row['ask']
    
    if idx >= pin_start:
        pin_buffer.append(bid)
        if len(pin_buffer) >= 200:
            max_pain = float(np.median(pin_buffer[-200:]))
    
    if idx < pin_start:
        if active_e is not None:
            avg = active_e['cost'] / active_e['filled']
            pnl = (bid - avg) / TICK_SIZE * active_e['filled'] * TICK_VALUE
            eodpl_trades.append({**active_e, 'exit_price': bid, 'pnl': pnl, 'exit_reason': 'OUTSIDE_WINDOW'})
            active_e = None
        continue
    
    if max_pain is None:
        continue
    
    dev_bps = (max_pain - bid) / max_pain * 10000
    
    if active_e is None:
        if 0 < dev_bps < 25:
            tiers = []
            for i in range(4):
                price = round(max_pain * (1 + TIER_DEVIATIONS_BPS[i] / 10000), 2)
                tiers.append({"price": price, "size": TIER_SIZES[i], "filled": 0, "fill_price": 0})
            
            # Fill tiers at or below current bid
            for tier in tiers:
                if bid <= tier["price"]:
                    tier["filled"] = tier["size"]
                    tier["fill_price"] = bid
            
            total_filled = sum(t['size'] for t in tiers if t['filled'] > 0)
            total_cost = sum(t['size'] * t['fill_price'] for t in tiers if t['filled'] > 0)
            
            if total_filled > 0:
                active_e = {
                    'idx': idx,
                    'ts': row['timestamp'],
                    'max_pain': max_pain,
                    'tiers': tiers,
                    'filled': total_filled,
                    'cost': total_cost,
                    'entry_avg': total_cost / total_filled,
                    'dev_bps': dev_bps,
                    'levels': sum(1 for t in tiers if t['filled'] > 0),
                }
    
    if active_e is not None:
        avg = active_e['entry_avg']
        dev_from_pin = (max_pain - bid) / max_pain * 10000
        pnl = (bid - avg) / TICK_SIZE * active_e['filled'] * TICK_VALUE
        
        if abs(dev_from_pin) <= PIN_CONVERGENCE_BPS:
            eodpl_trades.append({**active_e, 'exit_price': ask, 'pnl': pnl, 'exit_reason': 'CONVERGENCE',
                                'exit_dev': dev_from_pin, 'hold_ticks': idx - active_e['idx']})
            active_e = None
        elif dev_from_pin > STOP_LOSS_BPS:
            eodpl_trades.append({**active_e, 'exit_price': bid, 'pnl': pnl, 'exit_reason': 'STOP_LOSS',
                                'exit_dev': dev_from_pin, 'hold_ticks': idx - active_e['idx']})
            active_e = None

if active_e is not None:
    avg = active_e['entry_avg']
    pnl = (df.iloc[-1]['bid'] - avg) / TICK_SIZE * active_e['filled'] * TICK_VALUE
    eodpl_trades.append({**active_e, 'exit_price': df.iloc[-1]['bid'], 'pnl': pnl,
                        'exit_reason': 'END', 'exit_dev': 0, 'hold_ticks': len(df) - active_e['idx']})

edf = pd.DataFrame(eodpl_trades)

if len(edf) == 0:
    print("  No EODPL trades.")
else:
    winners = edf[edf['pnl'] > 0]
    losers = edf[edf['pnl'] <= 0]
    
    print(f"\n  Total: {len(edf)} | Winners: {len(winners)} | Losers: {len(losers)}")
    print(f"  Total P&L: Rs {edf['pnl'].sum():,.0f}")
    
    for reason in edf['exit_reason'].unique():
        mask = edf['exit_reason'] == reason
        subset = edf[mask]
        print(f"\n  --- {reason} (n={mask.sum()}) ---")
        print(f"    Avg P&L: Rs {subset['pnl'].mean():,.0f}")
        print(f"    Avg entry deviation: {subset['dev_bps'].mean():.1f} bps")
        print(f"    Avg exit deviation: {subset.get('exit_dev', pd.Series([0])).mean():.1f} bps")
        print(f"    Avg levels filled: {subset['levels'].mean():.1f}")
        print(f"    Avg hold: {subset['hold_ticks'].mean():.0f} ticks ({subset['hold_ticks'].mean()*0.05:.1f}s)")
        print(f"    Max pain at entry: Rs {subset['max_pain'].mean():.2f}")
    
    # Critical: How far was max_pain from actual price?
    print(f"\n  --- KEY FINDINGS ---")
    if len(losers) > 0:
        print(f"  Stop loss losers avg entry dev: {losers['dev_bps'].mean():.1f} bps")
        print(f"  Stop loss losers avg exit dev: {losers.get('exit_dev', pd.Series([0])).mean():.1f} bps")
        print(f"  → Price moved AWAY from max_pain by {losers.get('exit_dev', pd.Series([0])).mean() - losers['dev_bps'].mean():.1f} bps")
        print(f"  → This is NOT mean-reversion. The pin proxy (rolling median) drifts with price.")
