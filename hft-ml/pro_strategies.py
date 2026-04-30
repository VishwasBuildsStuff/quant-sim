"""
HFT Pro Strategy Detection Engine v2.0
12 Institutional-Grade HFT-Adjacent Strategies for Manual/Semi-Auto DMA Terminals
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
from datetime import datetime

class ProStrategyDetector:
    """
    Analyzes DOM, Tape, and Imbalance data to detect 12 specific HFT setups.
    Designed for manual/semi-auto execution on Level II DMA terminals.
    """
    
    def __init__(self):
        self.tape_history = []
        self.dom_history = []
        self.price_history = []
        self.vwap_history = []
        
        # Strategy Parameters (Terminal-Specific Thresholds)
        self.PARAMS = {
            'SCALPING': {
                'max_spread_ticks': 2,
                'imbalance_min': 0.40,
                'imbalance_max': 0.60,
                'max_tape_speed': 8,  # prints/sec
                'max_print_size': 5000,
                'queue_ratio_min': 0.7,
                'queue_ratio_max': 1.3
            },
            'MOMENTUM': {
                'large_block_size': 10000,
                'consecutive_block_prints': 3,
                'min_imbalance': 0.65,
                'max_wait_for_continuation': 5,
                'atr_mult': 1.0
            },
            'WALL_FADE': {
                'wall_size_mult': 3.0,
                'wall_absorption_threshold': 0.20,
                'max_time_to_absorb': 5.0,
                'max_imbalance_spike': 0.75
            },
            'REBATE': {
                'min_spread_ticks': 2,
                'max_queue_size': 5000,
                'max_volatility': 0.005,
                'imbalance_neutral_min': 0.45,
                'imbalance_neutral_max': 0.55,
                'max_vix': 15,
                'max_beta': 1.2
            },
            'STOP_HUNT': {
                'liquidity_vacuum_size': 2000,
                'spike_acceleration': 3.0,
                'reversal_imbalance_snap': 0.50,
                'min_wick_size_ticks': 4
            },
            'DARK_POOL': {
                'dark_print_min_size_mult': 2.0,
                'trf_adf_codes': ['TRF', 'ADF', 'ORF', 'D'],
                'lit_queue_shift_threshold': 0.30,
                'max_spread_ticks': 2
            },
            'SWEEP': {
                'min_exchanges_swept': 3,
                'max_sweep_time_ms': 2000,
                'liquidity_drop_pct': 0.60,
                'min_imbalance_extreme': 0.70
            },
            'AUCTION_FADE': {
                'min_imbalance_shares': 1_000_000,
                'max_opening_gap_pct': 0.02,
                'first_candle_stall_time': 60,
                'post_open_decay_threshold': 0.50
            },
            'NEWS_FADE': {
                'volatility_spike_mult': 3.0,
                'rejection_wick_threshold': 0.60,
                'volume_decay_pct': 0.40,
                'spread_widen_threshold_ticks': 4
            },
            'ICEBERG': {
                'min_refresh_count': 5,
                'static_visible_size': 500,
                'repetition_tolerance_ms': 5000,
                'technical_level_proximity': 0.01
            },
            'QUEUE_ARB': {
                'large_order_threshold': 10000,
                'depletion_pct': 0.70,
                'consecutive_prints': 3,
                'min_imbalance_tightening': 0.05
            },
            'VWAP_REVERT': {
                'std_dev_threshold': 2.0,
                'volume_drop_pct': 0.40,
                'opposing_delta_threshold': 0.55,
                'vwap_slope_max_deg': 0.5
            }
        }

    def update_data(self, dom_snapshot: Dict, tape_prints: List[Dict], 
                   price_history: Optional[List[float]] = None,
                   vwap_data: Optional[Dict] = None):
        """Ingest live DOM, Tape, Price, and VWAP data"""
        self.dom_history.append(dom_snapshot)
        if len(self.dom_history) > 50: self.dom_history.pop(0)
        
        self.tape_history.extend(tape_prints)
        if len(self.tape_history) > 200: self.tape_history = self.tape_history[-200:]
        
        if price_history:
            self.price_history.extend(price_history)
            if len(self.price_history) > 500: self.price_history = self.price_history[-500:]
            
        if vwap_data:
            self.vwap_history.append(vwap_data)
            if len(self.vwap_history) > 100: self.vwap_history = self.vwap_history[-100:]

    def detect_setups(self) -> List[Dict]:
        """Run all 12 strategy detectors and return active signals"""
        alerts = []
        if not self.dom_history: return alerts

        strategies = [
            ('SCALPING', self._check_scalping),
            ('MOMENTUM', self._check_momentum),
            ('WALL_FADE', self._check_wall_fade),
            ('REBATE', self._check_rebate),
            ('STOP_HUNT', self._check_stop_hunt),
            ('DARK_POOL', self._check_dark_pool),
            ('SWEEP', self._check_sweep),
            ('AUCTION_FADE', self._check_auction_fade),
            ('NEWS_FADE', self._check_news_fade),
            ('ICEBERG', self._check_iceberg),
            ('QUEUE_ARB', self._check_queue_arb),
            ('VWAP_REVERT', self._check_vwap_revert)
        ]
        
        for strat_name, check_func in strategies:
            result = check_func()
            if result:
                alerts.append(result)
            
        return alerts

    # ============================================================
    # STRATEGY 1: Scalping the Bid/Ask Spread
    # ============================================================
    def _check_scalping(self) -> Optional[Dict]:
        """Tight spread, balanced queue, low tape speed"""
        dom = self.dom_history[-1]
        spread_ticks = dom.get('spread_ticks', 10)
        imbalance = dom.get('imbalance', 0.5)
        tape_speed = len(self.tape_history[-20:]) / 5.0
        bid_ask_ratio = dom.get('bid_ask_ratio', 1.0)
        max_print = max([t.get('size', 0) for t in self.tape_history[-10:]] or [0])
        
        p = self.PARAMS['SCALPING']
        if (spread_ticks <= p['max_spread_ticks'] and 
            p['imbalance_min'] <= imbalance <= p['imbalance_max'] and 
            tape_speed <= p['max_tape_speed'] and
            max_print <= p['max_print_size'] and
            p['queue_ratio_min'] <= bid_ask_ratio <= p['queue_ratio_max']):
            
            return {
                'type': 'SCALPING',
                'icon': '⚡',
                'msg': f'Spread {spread_ticks}t | Queue {bid_ask_ratio:.2f}:1 | Tape {tape_speed:.1f}/s',
                'action': 'LMT_JOIN_BID/ASK (POST_ONLY, NSDQ/ARCA)',
                'color': 'cyan',
                'hotkey': 'F1',
                'details': 'Enter: 1 tick inside NBBO. Exit: 1-2 ticks. Stop: 1 tick below entry.'
            }
        return None

    # ============================================================
    # STRATEGY 2: Tape Reading Momentum Ignition
    # ============================================================
    def _check_momentum(self) -> Optional[Dict]:
        """Large block prints and aggressive tape"""
        if len(self.tape_history) < 3: return None
        
        recent = self.tape_history[-3:]
        blocks = [t for t in recent if t.get('size', 0) >= self.PARAMS['MOMENTUM']['large_block_size']]
        
        if len(blocks) >= self.PARAMS['MOMENTUM']['consecutive_block_prints']:
            dom = self.dom_history[-1]
            imbalance = dom.get('imbalance', 0.5)
            
            return {
                'type': 'MOMENTUM',
                'icon': '🔥',
                'msg': f'{len(blocks)}x Blocks ({blocks[0].get("size", 0):,} sh) | Imb {imbalance:.0%}',
                'action': 'BUY_MKT_CONT / STOP_LMT_ASK (EDGX/BATS)',
                'color': 'red',
                'hotkey': 'F2',
                'details': 'Enter: +1 tick above block. Target: +1.5x risk. Stop: 2 ticks below entry.'
            }
        return None

    # ============================================================
    # STRATEGY 3: Order Book Imbalance Fade
    # ============================================================
    def _check_wall_fade(self) -> Optional[Dict]:
        """Abnormal queue size at specific price levels"""
        dom = self.dom_history[-1]
        avg_bid_size = dom.get('avg_bid_size', 1000)
        avg_ask_size = dom.get('avg_ask_size', 1000)
        
        for side in ['bids', 'asks']:
            for level in dom.get(side, []):
                size = level.get('size', 0)
                avg = avg_bid_size if side == 'bids' else avg_ask_size
                
                if size >= avg * self.PARAMS['WALL_FADE']['wall_size_mult']:
                    return {
                        'type': 'WALL_FADE',
                        'icon': '🧱',
                        'msg': f'{side.upper()} Wall @ {level["price"]} ({size:,} vs {avg:,.0f} avg)',
                        'action': 'FADE_WALL_SHORT/LONG (POST_ONLY, Route Away)',
                        'color': 'yellow',
                        'hotkey': 'F3',
                        'details': 'Enter: 1-2t outside wall. Target: 3-5t to mid. Stop: 1t inside wall.'
                    }
        return None

    # ============================================================
    # STRATEGY 4: Rebate Trading
    # ============================================================
    def _check_rebate(self) -> Optional[Dict]:
        """Wide spread and thin queues"""
        dom = self.dom_history[-1]
        spread_ticks = dom.get('spread_ticks', 0)
        best_bid_size = dom['bids'][0]['size'] if dom.get('bids') else 0
        best_ask_size = dom['asks'][0]['size'] if dom.get('asks') else 0
        imbalance = dom.get('imbalance', 0.5)
        
        p = self.PARAMS['REBATE']
        if (spread_ticks >= p['min_spread_ticks'] and 
            min(best_bid_size, best_ask_size) <= p['max_queue_size'] and
            p['imbalance_neutral_min'] <= imbalance <= p['imbalance_neutral_max']):
            
            return {
                'type': 'REBATE',
                'icon': '💰',
                'msg': f'Spread {spread_ticks}t | Queue {min(best_bid_size, best_ask_size):,} | Imb {imbalance:.0%}',
                'action': 'ADD_LIQ_BID/ASK (POST_ONLY, TIF:DAY, NSDQ/ARCA/EDGX)',
                'color': 'green',
                'hotkey': 'F4',
                'details': 'Target: Rebate + 0-1t. Stop: 2t against. Cancel if unfilled 4-6s.'
            }
        return None

    # ============================================================
    # STRATEGY 5: Stop Hunt Liquidity Grab
    # ============================================================
    def _check_stop_hunt(self) -> Optional[Dict]:
        """Liquidity vacuums and rapid reversals"""
        if len(self.tape_history) < 10: return None
        
        # Detect liquidity vacuum (thin book beyond level)
        dom = self.dom_history[-1]
        beyond_levels = dom.get('beyond_levels', [])
        vacuum = any(l.get('size', 0) < self.PARAMS['STOP_HUNT']['liquidity_vacuum_size'] 
                     for l in beyond_levels)
        
        # Detect spike and reversal
        recent_speed = len(self.tape_history[-5:])
        recent_imbalance = dom.get('imbalance', 0.5)
        snapped_back = recent_imbalance < self.PARAMS['STOP_HUNT']['reversal_imbalance_snap']
        
        if vacuum and recent_speed > 8 and snapped_back:
            return {
                'type': 'STOP_HUNT',
                'icon': '🎯',
                'msg': f'Vacuum Detected | Imb Snap {recent_imbalance:.0%} | Rev Reversal',
                'action': 'REVERSE_STOP_HUNT (LMT, IEX/NSDQ)',
                'color': 'magenta',
                'hotkey': 'F5',
                'details': 'Enter: 1t back inside range. Target: 4-8t to mid. Stop: 2t beyond wick.'
            }
        return None

    # ============================================================
    # STRATEGY 6: Dark Pool Footprint Replication
    # ============================================================
    def _check_dark_pool(self) -> Optional[Dict]:
        """Clustered TRF/ADF prints while lit DOM holds steady"""
        if len(self.tape_history) < 5: return None
        
        dark_prints = [t for t in self.tape_history[-10:] 
                      if t.get('exchange', '') in self.PARAMS['DARK_POOL']['trf_adf_codes']]
        
        avg_size = np.mean([t.get('size', 500) for t in self.tape_history[-20:]])
        large_dark = any(t.get('size', 0) >= avg_size * self.PARAMS['DARK_POOL']['dark_print_min_size_mult'] 
                        for t in dark_prints)
        
        dom = self.dom_history[-1]
        lit_steady = dom.get('lit_queue_shift', 0) < self.PARAMS['DARK_POOL']['lit_queue_shift_threshold']
        tight_spread = dom.get('spread_ticks', 5) <= self.PARAMS['DARK_POOL']['max_spread_ticks']
        
        if dark_prints and large_dark and lit_steady and tight_spread:
            return {
                'type': 'DARK_POOL',
                'icon': '🕵️',
                'msg': f'{len(dark_prints)} Dark Prints (TRF/ADF) | Lit DOM Steady',
                'action': 'LMT_FOLLOW_DARK (POST_ONLY, NSDQ/IEX)',
                'color': 'blue',
                'hotkey': 'F6',
                'details': 'Enter: NBBO+1c. Target: 8-15c or delta flip. Stop: 1c below dark exec.'
            }
        return None

    # ============================================================
    # STRATEGY 7: Sweep-to-Fill Momentum
    # ============================================================
    def _check_sweep(self) -> Optional[Dict]:
        """Machine gun pattern across 3+ exchanges in <2s"""
        if len(self.tape_history) < 5: return None
        
        recent = self.tape_history[-10:]
        exchanges = set(t.get('exchange', '') for t in recent)
        
        # Check for rapid multi-exchange execution
        same_side = all(t.get('side', '') == recent[0].get('side', '') for t in recent[:5])
        liquidity_drop = self._check_liquidity_vacuum()
        imbalance_extreme = self.dom_history[-1].get('imbalance', 0.5) > self.PARAMS['SWEEP']['min_imbalance_extreme']
        
        if len(exchanges) >= self.PARAMS['SWEEP']['min_exchanges_swept'] and same_side and liquidity_drop and imbalance_extreme:
            return {
                'type': 'SWEEP',
                'icon': '🌊',
                'msg': f'{len(exchanges)} ECNs Swept | Liq Drop {liquidity_drop:.0%} | Imb Extreme',
                'action': 'MKT_LIMIT_SWEEP (SMART/AGG, IOC)',
                'color': 'orange',
                'hotkey': 'F7',
                'details': 'Enter: Market Limit ±0.03. Target: 10-20c. Stop: Reversal sweep or +0.02 fail.'
            }
        return None

    # ============================================================
    # STRATEGY 8: Opening Auction Imbalance Fade
    # ============================================================
    def _check_auction_fade(self) -> Optional[Dict]:
        """Large pre-open imbalance + post-open stall"""
        dom = self.dom_history[-1]
        tape = self.tape_history[-30:]
        
        imbalance_shares = dom.get('pre_open_imbalance', 0)
        gap_pct = dom.get('opening_gap_pct', 0)
        post_open_stall = dom.get('post_open_stall_seconds', 0) > 60
        volume_decay = self._check_volume_decay()
        
        p = self.PARAMS['AUCTION_FADE']
        if (abs(imbalance_shares) >= p['min_imbalance_shares'] and
            abs(gap_pct) >= p['max_opening_gap_pct'] and
            post_open_stall and volume_decay):
            
            return {
                'type': 'AUCTION_FADE',
                'icon': '🔔',
                'msg': f'Imb {imbalance_shares:,} sh | Gap {gap_pct:.1%} | Stall {post_open_stall}s',
                'action': 'LMT_FADE_AUCTION (POST_ONLY, NSDQ/ARCA)',
                'color': 'white',
                'hotkey': 'F8',
                'details': 'Wait 60s post-open. Enter: 1c inside 1-min range. Target: Pre-mkt VWAP.'
            }
        return None

    # ============================================================
    # STRATEGY 9: News-Fueled Liquidity Sweep Fade
    # ============================================================
    def _check_news_fade(self) -> Optional[Dict]:
        """Violent spike + rejection wicks + volume decay"""
        dom = self.dom_history[-1]
        tape = self.tape_history[-20:]
        
        vol_spike = dom.get('volatility_ratio', 1.0) > self.PARAMS['NEWS_FADE']['volatility_spike_mult']
        rejection_wick = dom.get('wick_rejection_pct', 0) > self.PARAMS['NEWS_FADE']['rejection_wick_threshold']
        vol_decay = self._check_volume_decay()
        spread_widened = dom.get('spread_ticks', 2) > self.PARAMS['NEWS_FADE']['spread_widen_threshold_ticks']
        
        if vol_spike and rejection_wick and vol_decay and spread_widened:
            return {
                'type': 'NEWS_FADE',
                'icon': '📰',
                'msg': f'Vol {vol_spike:.1f}x | Wick {rejection_wick:.0%} | Spread {dom.get("spread_ticks", 0)}t',
                'action': 'LMT_FADE_NEWS (POST_ONLY, IEX/NSDQ)',
                'color': 'red',
                'hotkey': 'F9',
                'details': 'Enter: Extreme ±0.02. Target: 80% retrace. Stop: 1t beyond spike extreme.'
            }
        return None

    # ============================================================
    # STRATEGY 10: Iceberg Order Detection
    # ============================================================
    def _check_iceberg(self) -> Optional[Dict]:
        """Static visible size refreshing 5+ times"""
        if len(self.dom_history) < 10: return None
        
        dom = self.dom_history[-1]
        refresh_count = dom.get('iceberg_refresh_count', 0)
        static_size = dom.get('static_level_size', 0)
        is_at_tech_level = dom.get('at_technical_level', False)
        
        p = self.PARAMS['ICEBERG']
        if refresh_count >= p['min_refresh_count'] and static_size > 0 and is_at_tech_level:
            return {
                'type': 'ICEBERG',
                'icon': '🧊',
                'msg': f'Iceberg @ {static_size:,} (Refreshed {refresh_count}x) | Tech Level',
                'action': 'MKT_ICEBERG_BREAK / LMT_ICEBERG_PULL (SMART)',
                'color': 'cyan',
                'hotkey': 'F10',
                'details': 'Breakout: MKT/STOP_LMT beyond. Pull: LIMIT at cleared price. Stop: 15s reclaim.'
            }
        return None

    # ============================================================
    # STRATEGY 11: Queue Position Arbitrage
    # ============================================================
    def _check_queue_arb(self) -> Optional[Dict]:
        """Step ahead of large order before it absorbs flow"""
        dom = self.dom_history[-1]
        tape = self.tape_history[-10:]
        
        large_order_size = dom.get('large_resting_size', 0)
        depletion_pct = dom.get('queue_depletion_pct', 0)
        consecutive_prints = self._count_consecutive_hits()
        imbalance_tightening = dom.get('imbalance_tightening', 0) > self.PARAMS['QUEUE_ARB']['min_imbalance_tightening']
        
        if (large_order_size >= self.PARAMS['QUEUE_ARB']['large_order_threshold'] and
            depletion_pct >= self.PARAMS['QUEUE_ARB']['depletion_pct'] and
            consecutive_prints >= self.PARAMS['QUEUE_ARB']['consecutive_prints'] and
            imbalance_tightening):
            
            return {
                'type': 'QUEUE_ARB',
                'icon': '📍',
                'msg': f'Large Order {large_order_size:,} | Depleted {depletion_pct:.0%} | {consecutive_prints}x Hits',
                'action': 'STEP_AHEAD_LMT (POST_ONLY, NSDQ/ARCA)',
                'color': 'yellow',
                'hotkey': 'F11',
                'details': 'Enter: 1t ahead of large order. Target: 1-2t. Stop: Order pulls/eaten <2s.'
            }
        return None

    # ============================================================
    # STRATEGY 12: Anchored VWAP/Tape Divergence Reversion
    # ============================================================
    def _check_vwap_revert(self) -> Optional[Dict]:
        """Price >2 SD from VWAP + tape flow contradicts"""
        if len(self.vwap_history) < 10: return None
        
        dom = self.dom_history[-1]
        std_dev_from_vwap = dom.get('std_dev_from_vwap', 0)
        tape_volume_drop = self._check_volume_decay()
        opposing_delta = dom.get('opposing_delta_pct', 0)
        vwap_slope = abs(dom.get('vwap_slope_degrees', 0))
        
        p = self.PARAMS['VWAP_REVERT']
        if (std_dev_from_vwap >= p['std_dev_threshold'] and
            tape_volume_drop and
            opposing_delta >= p['opposing_delta_threshold'] and
            vwap_slope <= p['vwap_slope_max_deg']):
            
            return {
                'type': 'VWAP_REVERT',
                'icon': '📉',
                'msg': f'{std_dev_from_vwap:.1f} SD from VWAP | Vol Drop {tape_volume_drop:.0%} | Opp Delta {opposing_delta:.0%}',
                'action': 'LMT_VWAP_REVERT (POST_ONLY, IEX/NSDQ)',
                'color': 'magenta',
                'hotkey': 'F12',
                'details': 'Enter: Extreme wick. Target: Session VWAP. Stop: Break swing high/low.'
            }
        return None

    # ============================================================
    # Helper Methods
    # ============================================================
    def _check_liquidity_vacuum(self) -> float:
        """Estimate liquidity drop across recent DOM snapshots"""
        if len(self.dom_history) < 3: return 0
        recent_total = sum(d.get('total_liquidity', 0) for d in self.dom_history[-3:]) / 3
        prev_total = sum(d.get('total_liquidity', 0) for d in self.dom_history[-6:-3]) / 3 or 1
        return recent_total / prev_total if prev_total > 0 else 1.0

    def _check_volume_decay(self) -> float:
        """Calculate volume decay ratio"""
        if len(self.tape_history) < 10: return 1.0
        recent_vol = sum(t.get('size', 0) for t in self.tape_history[-5:])
        prev_vol = sum(t.get('size', 0) for t in self.tape_history[-10:-5]) or 1
        return recent_vol / prev_vol if prev_vol > 0 else 1.0

    def _count_consecutive_hits(self) -> int:
        """Count consecutive prints hitting the same side"""
        if not self.tape_history: return 0
        count = 1
        last_side = self.tape_history[-1].get('side', '')
        for t in reversed(self.tape_history[:-1]):
            if t.get('side', '') == last_side:
                count += 1
            else:
                break
        return count
