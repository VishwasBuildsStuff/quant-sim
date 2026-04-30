"""
HFT Terminal Trading Dashboard
Complete Bloomberg Terminal-style interface in the terminal
Real-time prices, order book, buy/sell, portfolio tracking
AUTONOMOUS TRADING integration
"""

import sys
sys.path.insert(0, r'V:\pylibs')
sys.path.insert(0, '.')

import os
import time
import json
import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import deque

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.columns import Columns
from rich.align import Align
from rich.box import DOUBLE, ROUNDED
from rich.live import Live
from rich.syntax import Syntax

# Import charting module
try:
    from terminal_charts import TerminalCharts
    HAS_CHARTS = True
except:
    HAS_CHARTS = False

# Import Strategy Detection Engine
from pro_strategies import ProStrategyDetector

# Import Real Execution Wrapper (Paper Trading by Default)
from real_execution import BrokerAPI

# Import Trade Optimizer (Realistic pricing + risk controls)
from trade_optimizer import TradeOptimizer

# Import autonomous trading components
try:
    from auto_trader import AutonomousTrader
    from watchlist_manager import WatchlistManager
    from multi_model_ensemble import MultiModelEnsemble
    HAS_AUTONOMOUS = True
except:
    HAS_AUTONOMOUS = False

# Try Yahoo Finance
try:
    import yfinance as yf
    HAS_YAHOO = True
except:
    HAS_YAHOO = False

console = Console()

# ============================================================
# WATCHLIST & MARKET DATA
# ============================================================

class MarketDataFeed:
    """
    Real-time market data feed
    Falls back to realistic simulation if Yahoo unavailable
    """
    
    def __init__(self, symbols: Dict[str, str]):
        self.symbols = symbols
        self.prices = {}
        self.prev_prices = {}
        self.order_books = {}
        self.ticker_history = {name: deque(maxlen=200) for name in symbols}
        self.indices = {}

        # AR(1) momentum state per symbol: tracks short-term drift
        self.momentum = {}       # current momentum (% per tick)
        self.anchor_prices = {}  # slowly-moving VWAP anchor for mean reversion

        self._init_prices()
    
    def _init_prices(self):
        """Initialize prices from realistic NSE base values."""
        base_prices = {
            'NIFTY50': 22045.30, 'BANKNIFTY': 48123.45, 'SENSEX': 72845.20,
            'RELIANCE': 2450.0, 'TCS': 3850.0, 'INFY': 1520.0,
            'HDFCBANK': 1680.0, 'TATAMOTORS': 920.0, 'SBIN': 620.0,
            'WIPRO': 480.0, 'ADANIENT': 2850.0, 'ICICIBANK': 980.0
        }
        for name in self.symbols.keys():
            price = base_prices.get(name, 1000.0)
            self.prices[name] = price
            self.prev_prices[name] = price
            self.momentum[name] = 0.0
            self.anchor_prices[name] = price
            self._generate_order_book(name)
    
    def _generate_order_book(self, name: str):
        """Generate realistic Level 2 order book"""
        price = self.prices.get(name, 1000.0)
        spread = price * 0.0002
        bids = []
        asks = []
        
        for i in range(5):
            bid_p = price - (spread * i) - random.uniform(0.01, 0.05)
            ask_p = price + (spread * i) + random.uniform(0.01, 0.05)
            bids.append({'price': round(bid_p, 2), 'size': random.randint(100, 5000)})
            asks.append({'price': round(ask_p, 2), 'size': random.randint(100, 5000)})
        
        self.order_books[name] = {
            'bids': sorted(bids, key=lambda x: x['price'], reverse=True),
            'asks': sorted(asks, key=lambda x: x['price'])
        }
    
    def update_prices(self):
        """
        AR(1) momentum price model — calibrated to realistic NSE intraday behaviour.

        Math:
          sigma = 0.00012 per 0.5s tick  →  annual vol ≈ 18%  (correct for large-caps)
          Stop survival:  E[ticks to stop] = (stop_bps / sigma_bps)²
            50 bps stop  → (50/12)² ≈ 17 minutes      ← enough room to breathe
            15 bps stop  → (15/12)² ≈ 90 seconds       ← still survivable

          AR(1) persistence α=0.40 creates positive autocorrelation:
            If last tick was +0.05%, next tick expected +0.02% → momentum is exploitable.

          Slow mean-reversion to anchor (2% pull per tick) prevents runaway drift.
        """
        SIGMA = 0.00012   # noise per tick: 0.012%  (was 0.063% — 5x too high!)
        ALPHA = 0.40      # momentum persistence (AR coefficient)
        MR_STRENGTH = 0.002  # mean-reversion pull toward anchor (0.2% per tick)

        for name in self.symbols.keys():
            self.prev_prices[name] = self.prices[name]
            base = self.prices[name]
            anchor = self.anchor_prices[name]

            # Random shock this tick
            shock = random.gauss(0, SIGMA)

            # AR(1): momentum = alpha * prev_momentum + shock
            prev_mom = self.momentum.get(name, 0.0)
            new_mom = ALPHA * prev_mom + shock
            self.momentum[name] = new_mom

            # Slow mean-reversion toward anchor (prevents runaway drift)
            mr = MR_STRENGTH * ((anchor / base) - 1)

            # Apply: new price = base * (1 + momentum + mean_reversion)
            new_price = round(base * (1 + new_mom + mr), 2)
            # Hard floor: never drop >12% from anchor (circuit breaker)
            new_price = max(new_price, anchor * 0.88)
            self.prices[name] = new_price

            # Drift anchor slowly toward current price (0.1% per tick)
            self.anchor_prices[name] = round(
                anchor * 0.999 + new_price * 0.001, 2
            )

            self.ticker_history[name].append({
                'price': new_price,
                'time': datetime.now()
            })
            self._generate_order_book(name)

        # Indices move proportionally to RELIANCE
        rel_move = (self.prices.get('RELIANCE', 1) / self.prev_prices.get('RELIANCE', 1)) - 1
        self.indices = {
            'NIFTY 50':   {'value': round(22045.30  * (1 + rel_move * 0.6), 2), 'change': round(rel_move * 60,  2)},
            'BANK NIFTY': {'value': round(48123.45  * (1 + rel_move * 0.8), 2), 'change': round(rel_move * 80,  2)},
            'SENSEX':     {'value': round(72845.20  * (1 + rel_move * 0.6), 2), 'change': round(rel_move * 60,  2)},
        }
    
    def get_price_change(self, name: str) -> tuple:
        """Get price change (absolute, percent)"""
        curr = self.prices.get(name, 0)
        prev = self.prev_prices.get(name, curr)
        change = curr - prev
        pct = (change / prev * 100) if prev else 0
        return change, pct
    
    def get_ticker_line(self) -> str:
        """Get scrolling ticker line"""
        parts = []
        for name in list(self.symbols.keys())[:8]:
            change, pct = self.get_price_change(name)
            symbol = name[:6]
            price = f"{self.prices[name]:.2f}"
            arrow = "▲" if change >= 0 else "▼"
            color = "green" if change >= 0 else "red"
            parts.append(f"[{color}]{symbol} {price} {arrow}{abs(pct):.2f}%[/{color}]")
        return "  ".join(parts)

# ============================================================
# PORTFOLIO & TRADES
# ============================================================

class PortfolioManager:
    """Manages portfolio, positions, and trade execution"""

    def __init__(self, initial_capital: float = 10_000_000.0, broker=None, optimizer=None):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}  # {symbol: {qty, avg_price, current_price, ...}}
        self.trades = []  # List of executed trades
        self.daily_pnl = 0.0
        self.peak_capital = initial_capital
        self.total_trades = 0
        self.broker = broker  # Broker API for order routing
        self.optimizer = optimizer  # Trade Optimizer for realistic pricing & risk

        # Persistent stats for every stock traded (even if sold completely)
        self.stock_stats = {}
        # Format: {symbol: {'qty_bought': 0, 'qty_sold': 0, 'realized_pnl': 0.0, 'trade_count': 0}}
    
    def buy(self, symbol: str, qty: int, price: float,
             strategy_key: str = '') -> dict:
        """Execute buy order with risk checks, stop and take-profit levels."""
        realistic_price = self.optimizer.calculate_realistic_price(price, 'BUY', qty)
        cost = qty * realistic_price

        risk_check = self.optimizer.check_risk_limits(
            position_value=cost,
            total_equity=self.get_portfolio_value(),
            daily_pnl=self.daily_pnl
        )
        if not risk_check['allowed']:
            return {'success': False, 'error': ' | '.join(risk_check['alerts'])}
        if cost > self.cash:
            return {'success': False, 'error': 'Insufficient funds'}

        # Pre-compute stop and target
        targets = self.optimizer.get_strategy_targets(realistic_price, 'BUY', strategy_key or 'F1')

        result = self.broker.place_order(symbol, qty, realistic_price, 'BUY', 'LIMIT')
        
        if result['success']:
            commission = self.optimizer.calculate_commission(cost)
            self.cash -= cost + commission

            if symbol not in self.positions:
                self.positions[symbol] = {
                    'qty': 0, 'avg_price': 0, 'current_price': realistic_price,
                    'side': 'BUY',
                    'unrealized_pnl': 0.0, 'realized_pnl': 0.0, 'history': [],
                    'stop_loss': targets['stop'],
                    'take_profit': targets['target'],
                    'strategy': strategy_key,
                }

            pos = self.positions[symbol]
            old_qty = pos['qty']
            old_avg = pos['avg_price']
            new_qty = old_qty + qty
            pos['avg_price'] = ((old_avg * old_qty) + (realistic_price * qty)) / new_qty if new_qty > 0 else realistic_price
            pos['qty'] = new_qty
            pos['side'] = 'BUY'
            # Refresh stop/target based on new avg price
            refreshed = self.optimizer.get_strategy_targets(pos['avg_price'], 'BUY', strategy_key or 'F1')
            pos['stop_loss'] = refreshed['stop']
            pos['take_profit'] = refreshed['target']

            if symbol not in self.stock_stats:
                self.stock_stats[symbol] = {'qty_bought': 0, 'qty_sold': 0, 'realized_pnl': 0.0, 'trade_count': 0}
            self.stock_stats[symbol]['qty_bought'] += qty
            self.stock_stats[symbol]['trade_count'] += 1

            trade = {
                'time': datetime.now(), 'symbol': symbol, 'side': 'BUY',
                'qty': qty, 'price': realistic_price, 'notional': cost,
                'commission': commission, 'pnl': -commission,
                'slippage': round(realistic_price - price, 2),
                'stop': targets['stop'], 'target': targets['target'],
                'strategy': strategy_key,
            }
            self.trades.insert(0, trade)
            self.optimizer.log_trade(trade)
            self.total_trades += 1
            return {'success': True, 'trade': trade}
        else:
            return {'success': False, 'error': result.get('error', 'Unknown error')}
    
    def sell(self, symbol: str, qty: int, price: float,
              strategy_key: str = '', reason: str = 'MANUAL') -> dict:
        """Execute sell (closing) order with PnL tracking."""
        if symbol not in self.positions:
            return {'success': False, 'error': 'No position'}

        pos = self.positions[symbol]
        if pos['qty'] < qty:
            return {'success': False, 'error': f'Only {pos["qty"]} shares held'}

        realistic_price = self.optimizer.calculate_realistic_price(price, 'SELL', qty)
        revenue = qty * realistic_price
        commission = self.optimizer.calculate_commission(revenue)

        result = self.broker.place_order(symbol, qty, realistic_price, 'SELL', 'LIMIT')
        if result['success']:
            self.cash += revenue - commission
            realized_pnl = (realistic_price - pos['avg_price']) * qty - commission
            self.daily_pnl += realized_pnl
            pos['realized_pnl'] += realized_pnl
            pos['qty'] -= qty

            if pos['qty'] == 0:
                self.optimizer.clear_trailing(symbol)
                del self.positions[symbol]

            if symbol not in self.stock_stats:
                self.stock_stats[symbol] = {'qty_bought': 0, 'qty_sold': 0, 'realized_pnl': 0.0, 'trade_count': 0}
            self.stock_stats[symbol]['qty_sold'] += qty
            self.stock_stats[symbol]['realized_pnl'] += realized_pnl
            self.stock_stats[symbol]['trade_count'] += 1

            trade = {
                'time': datetime.now(), 'symbol': symbol, 'side': 'SELL',
                'qty': qty, 'price': realistic_price, 'notional': revenue,
                'commission': commission, 'pnl': realized_pnl,
                'slippage': round(price - realistic_price, 2),
                'reason': reason,
                'strategy': strategy_key,
            }
            self.trades.insert(0, trade)
            self.optimizer.log_trade(trade)
            self.total_trades += 1

            warning = None
            if self.daily_pnl < -self.initial_capital * self.optimizer.daily_loss_limit:
                warning = 'DAILY LOSS LIMIT BREACHED'
            return {'success': True, 'trade': trade, 'warning': warning}
        else:
            return {'success': False, 'error': result.get('error', 'Unknown error')}
            
    def _calculate_holding_period(self, symbol: str) -> str:
        """Calculate how long position was held"""
        if symbol not in self.positions:
            return "Closed"
        pos = self.positions[symbol]
        if pos.get('history'):
            entry_time = pos['history'][0].get('time')
            if entry_time:
                entry_dt = datetime.strptime(entry_time, '%H:%M:%S') if isinstance(entry_time, str) else entry_time
                hold_time = datetime.now() - entry_dt.replace(year=entry_dt.year, month=entry_dt.month, day=entry_dt.day)
                return str(hold_time)
        return "Unknown"
    
    def update_market_prices(self, market_data: MarketDataFeed):
        """Update position values with current market prices"""
        total_equity = self.cash
        
        for symbol, pos in self.positions.items():
            if symbol in market_data.prices:
                pos['current_price'] = market_data.prices[symbol]
                # Update Unrealized PnL based on LIVE price
                pos['unrealized_pnl'] = (pos['current_price'] - pos['avg_price']) * pos['qty']
                total_equity += pos['current_price'] * pos['qty']
            else:
                # Fallback if market data missing
                total_equity += pos['current_price'] * pos['qty']
        
        self.total_equity = total_equity
        self.peak_capital = max(self.peak_capital, total_equity)
    
    def get_portfolio_value(self) -> float:
        return getattr(self, 'total_equity', self.initial_capital)
    
    def get_drawdown(self) -> float:
        equity = self.get_portfolio_value()
        return (self.peak_capital - equity) / self.peak_capital * 100

# ============================================================
# TERMINAL DASHBOARD
# ============================================================

class TerminalDashboard:
    """
    Complete Bloomberg Terminal-style interface in the terminal
    """
    
    def __init__(self):
        self.symbols = {
            'RELIANCE': 'RELIANCE.NS', 'TCS': 'TCS.NS', 'INFY': 'INFY.NS',
            'HDFCBANK': 'HDFCBANK.NS', 'TATAMOTORS': 'TATAMOTORS.NS',
            'SBIN': 'SBIN.NS', 'WIPRO': 'WIPRO.NS', 'ICICIBANK': 'ICICIBANK.NS'
        }
        
        self.market = MarketDataFeed(self.symbols)
        
        # 🛡️ Real Execution Wrapper (Default: Paper Trading)
        self.broker = BrokerAPI(dry_run=True)
        
        # 📊 Trade Optimizer (Realistic pricing + risk controls)
        self.optimizer = TradeOptimizer(slippage_bps=5.0, commission_bps=2.5)
        
        # Portfolio & Trading State
        self.portfolio = PortfolioManager(broker=self.broker, optimizer=self.optimizer)

        # Order entry state
        self.order_symbol = ''
        self.order_side = 'BUY'
        self.order_qty = 0
        self.order_status = ''
        
        # State Machine State
        self.input_state = "IDLE" # Options: IDLE, BUY_PENDING, SELL_PENDING
        self.input_buffer = ""
        self.current_strategy_key = ""  # Tracks which F-key strategy is pending
        
        # Search mode (triggered by /)
        self.search_mode = False
        self.search_buffer = ''
        self.search_results = []

        # Active tab
        self.active_tab = 0
        self.tabs = ['OVERVIEW', 'ORDER BOOK', 'TRADES', 'PORTFOLIO', 'CHARTS', 'AUTO', 'STRATEGY', 'REPORT']

        # AUTONOMOUS TRADING INTEGRATION
        self.autonomous_enabled = False
        self.autonomous_bot: Optional[AutonomousTrader] = None
        self.auto_signals = {}
        self.auto_trades_log = []
        self.auto_status = "⏹️ STOPPED"
        self.auto_cycle_count = 0
        self.models_loaded = 0

        # Try to load autonomous components
        if HAS_AUTONOMOUS:
            try:
                # Load watchlist manager
                self.watchlist_mgr = WatchlistManager('watchlist.json')
                
                # Load models
                self.models: Dict[str, MultiModelEnsemble] = {}
                self._load_trading_models()
                
                console.print(f"[dim]✓ Autonomous trading components loaded ({self.models_loaded} models)[/dim]")
            except Exception as e:
                console.print(f"[dim]⚠ Autonomous components not ready: {e}[/dim]")
                self.watchlist_mgr = None
                self.models = {}
        else:
            console.print("[dim]⚠ Autonomous trading not available[/dim]")
            self.watchlist_mgr = None
            self.models = {}

        # Initialize charting
        if HAS_CHARTS:
            self.chart_generator = TerminalCharts()

        # Strategy Detection Engine
        self.strategy_detector = ProStrategyDetector()
        self.active_alerts = []

        # Command input
        self.command_buffer = ''

        console.clear()
        console.print("[bold green]HFT Terminal Trading Dashboard[/bold green]")
        console.print("[dim]Press Q to quit | 1-6 for tabs | B=Buy, S=Sell | A=Toggle Auto | Enter=execute[/dim]\n")
    
    def _load_trading_models(self):
        """Load multi-model ensembles for autonomous trading"""
        import os
        from pathlib import Path
        
        model_dir = 'output'
        if not Path(model_dir).exists():
            return
        
        # Find all multi-ensemble models
        model_files = list(Path(model_dir).glob('*multi*.joblib')) + \
                      list(Path(model_dir).glob('*ensemble*.joblib'))
        
        for model_file in model_files:
            try:
                filename = model_file.stem
                symbol = filename.split('_')[0].upper()
                
                model = MultiModelEnsemble.load(str(model_file))
                self.models[symbol] = model
                self.models_loaded += 1
                
            except Exception as e:
                pass
    
    def _run_autonomous_cycle(self):
        """Run one autonomous trading cycle"""
        if not self.autonomous_enabled or not self.models:
            return
        
        self.auto_cycle_count += 1
        self.auto_signals = {}
        
        # Get features and predictions for each symbol
        for symbol in list(self.symbols.keys())[:5]:  # Top 5 symbols
            try:
                # Skip if no model
                if symbol not in self.models:
                    continue
                
                # Get live price
                price = self.market.prices.get(symbol, 0)
                if price == 0:
                    continue
                
                # Generate simple features from market data
                # (Simplified version - full features would need LOB data)
                model = self.models[symbol]
                
                # For now, create a placeholder signal
                # In production, you'd engineer full features here
                self.auto_signals[symbol] = {
                    'prediction': 1,  # HOLD
                    'confidence': 0.0,
                    'price': price,
                    'reason': 'No live features yet'
                }
                
            except Exception as e:
                self.auto_signals[symbol] = {
                    'prediction': 1,
                    'confidence': 0.0,
                    'price': self.market.prices.get(symbol, 0),
                    'reason': f'Error: {str(e)[:50]}'
                }
    
    def create_auto_panel(self) -> Panel:
        """Create AUTONOMOUS TRADING panel"""
        if not HAS_AUTONOMOUS:
            return Panel(
                "[red]Autonomous trading not available.\nInstall required packages first.[/red]",
                title="[bold red]AUTONOMOUS TRADING[/bold red]",
                border_style="red"
            )
        
        # Status section
        status_color = "green" if self.autonomous_enabled else "red"
        status_icon = "▶️ RUNNING" if self.autonomous_enabled else "⏹️ STOPPED"
        
        status_text = Text()
        status_text.append("Status: ", style="bold")
        status_text.append(f"{status_icon}\n", style=f"bold {status_color}")
        status_text.append(f"Cycles: {self.auto_cycle_count}\n", style="dim")
        status_text.append(f"Models: {self.models_loaded} loaded\n", style="dim")
        status_text.append(f"Signals: {len(self.auto_signals)} active", style="dim")
        
        # Signals table
        signals_table = Table(box=ROUNDED, show_header=True, header_style="bold cyan", expand=True)
        signals_table.add_column("Symbol", style="bold white", width=12)
        signals_table.add_column("Price", justify="right", width=10)
        signals_table.add_column("Signal", justify="center", width=10)
        signals_table.add_column("Confidence", justify="right", width=12)
        signals_table.add_column("Reason", style="dim", width=30)
        
        for symbol in list(self.symbols.keys())[:5]:
            price = self.market.prices.get(symbol, 0)
            
            if symbol in self.auto_signals:
                sig = self.auto_signals[symbol]
                pred_map = {0: ("🔴 SELL", "red"), 1: ("🟡 HOLD", "yellow"), 2: ("🟢 BUY", "green")}
                sig_text, sig_color = pred_map.get(sig.get('prediction', 1), ("🟡 HOLD", "yellow"))
                conf = sig.get('confidence', 0)
                reason = sig.get('reason', '')[:30]
            else:
                sig_text, sig_color = "⏳ WAIT", "dim"
                conf = 0.0
                reason = 'No model/data'
            
            conf_text = f"{conf:.1%}" if conf > 0 else "N/A"
            signals_table.add_row(
                symbol,
                f"₹{price:.2f}",
                f"[{sig_color}]{sig_text}[/{sig_color}]",
                conf_text,
                reason
            )
        
        # Auto trades log
        trades_text = Text()
        if self.auto_trades_log:
            trades_text.append("\nRecent Auto-Trades:\n", style="bold")
            for trade in self.auto_trades_log[-5:]:
                trades_text.append(f"  {trade}\n", style="dim")
        else:
            trades_text.append("\nNo auto-trades yet", style="dim")
        
        # Controls
        controls = Text()
        controls.append("\n", style="dim")
        controls.append("Controls:\n", style="bold yellow")
        controls.append("  A = Toggle Autonomous Trading\n", style="dim")
        controls.append("  Models trade automatically when", style="dim")
        controls.append("  confidence > 65%", style="dim")
        
        content = Text()
        content.append(status_text)
        content.append("\n")
        
        # Build panel content
        from rich.console import Group
        content_group = Group(
            status_text,
            signals_table,
            trades_text,
            controls
        )
        
        return Panel(
            content_group,
            title="[bold green]AUTONOMOUS TRADING[/bold green]",
            border_style="green"
        )
    
    def create_header(self) -> Panel:
        """Create header with market indices and time"""
        now = datetime.now().strftime('%H:%M:%S')
        
        # Use a Text object for precise styling
        header_content = Text()
        header_content.append(f"TIME: {now}  ", style="bold cyan")
        
        indices = getattr(self.market, 'indices', {})
        for name, data in indices.items():
            change = data.get('change', 0)
            value = data.get('value', 0)
            
            # Color logic: Green for positive, Red for negative
            color = "green" if change >= 0 else "red"
            arrow = "▲" if change >= 0 else "▼"
            
            # 1. Stock Name & Price (Neutral White)
            header_content.append(f"{name}: {value:.2f} ", style="bold white")
            
            # 2. Change Percentage (Dynamic Red/Green)
            header_content.append(f"{arrow}{abs(change):.2f}%  ", style=f"bold {color}")
        
        # Equity and P&L section
        equity = self.portfolio.get_portfolio_value()
        pnl = equity - self.portfolio.initial_capital
        pnl_pct = (pnl / self.portfolio.initial_capital) * 100
        
        # Determine P&L Color (Green=Profit, Red=Loss, Yellow=Break-even)
        if pnl > 0: pnl_color = "green"
        elif pnl < 0: pnl_color = "red"
        else: pnl_color = "yellow"
        
        header_content.append(f"\nEQUITY: ", style="bold yellow")
        header_content.append(f"₹{equity:,.0f}  ", style=f"bold {pnl_color}")
        header_content.append(f"P&L: {pnl:+,.0f} ({pnl_pct:+.2f}%)", style=f"bold {pnl_color}")
        
        return Panel(
            header_content,
            title="[bold white on blue] HFT TERMINAL TRADING DASHBOARD [/bold white on blue]",
            border_style="blue"
        )
    
    def create_watchlist_panel(self) -> Panel:
        """Create watchlist with live prices"""
        table = Table(box=DOUBLE, show_header=True, header_style="bold cyan", expand=True)
        table.add_column("Symbol", style="bold white", width=12)
        table.add_column("Last", justify="right", width=10)
        table.add_column("Chg", justify="right", width=10)
        table.add_column("Chg%", justify="right", width=8)
        table.add_column("High", justify="right", width=10)
        table.add_column("Low", justify="right", width=10)
        table.add_column("Signal", justify="center", width=8)
        
        for name in self.symbols.keys():
            change, pct = self.market.get_price_change(name)
            price = self.market.prices[name]
            color = "green" if change >= 0 else "red"
            arrow = "▲" if change >= 0 else "▼"
            
            # Generate fake high/low from history
            history = list(self.market.ticker_history[name])
            if history:
                high = max(h['price'] for h in history)
                low = min(h['price'] for h in history)
            else:
                high = price * 1.01
                low = price * 0.99
            
            # Simple signal based on recent momentum
            signal = "HOLD"
            if len(history) > 10:
                recent = [h['price'] for h in history[-10:]]
                if recent[-1] > recent[0] * 1.001:
                    signal = "[green]BUY[/green]"
                elif recent[-1] < recent[0] * 0.999:
                    signal = "[red]SELL[/red]"
            
            table.add_row(
                f"[bold cyan]{name}[/bold cyan]",
                f"[{color}]{price:.2f}[/{color}]",
                f"[{color}]{arrow}{abs(change):.2f}[/{color}]",
                f"[{color}]{pct:+.2f}%[/{color}]",
                f"{high:.2f}",
                f"{low:.2f}",
                signal
            )
        
        return Panel(table, title="[bold yellow] WATCHLIST [/bold yellow]", border_style="yellow")
    
    def create_order_book_panel(self) -> Panel:
        """Create order book visualization for selected symbol"""
        symbol = self.order_symbol or 'RELIANCE'
        ob = self.market.order_books.get(symbol, {})
        
        if not ob:
            return Panel("No order book data", title=f"[bold] Order Book: {symbol} [/bold]")
        
        table = Table(box=DOUBLE, show_header=False, expand=True)
        table.add_column("Bid Size", justify="right", style="green", width=10)
        table.add_column("Bid Price", justify="right", style="bold green", width=10)
        table.add_column(" ", width=2)
        table.add_column("Ask Price", justify="left", style="bold red", width=10)
        table.add_column("Ask Size", justify="left", style="red", width=10)
        
        bids = ob.get('bids', [])[:5]
        asks = ob.get('asks', [])[:5]
        
        for i in range(5):
            bid = bids[i] if i < len(bids) else {'size': '-', 'price': '-'}
            ask = asks[i] if i < len(asks) else {'size': '-', 'price': '-'}
            
            table.add_row(
                f"{bid['size']:,}" if isinstance(bid['size'], int) else str(bid['size']),
                f"{bid['price']:.2f}" if isinstance(bid['price'], float) else str(bid['price']),
                "│",
                f"{ask['price']:.2f}" if isinstance(ask['price'], float) else str(ask['price']),
                f"{ask['size']:,}" if isinstance(ask['size'], int) else str(ask['size'])
            )
        
        spread = asks[0]['price'] - bids[0]['price'] if bids and asks else 0
        mid = (bids[0]['price'] + asks[0]['price']) / 2 if bids and asks else 0
        
        header = Text()
        header.append(f"{symbol}  ", style="bold cyan")
        header.append(f"MID: {mid:.2f}  ", style="bold yellow")
        header.append(f"SPREAD: {spread:.2f}", style="bold white")
        
        return Panel(table, title=header, border_style="cyan")
    
    def create_order_entry_panel(self) -> Panel:
        """Create order entry interface"""
        text = Text()
        text.append("ORDER ENTRY\n\n", style="bold underline")
        text.append(f"Symbol: ", style="bold cyan")
        text.append(f"{self.order_symbol or 'RELIANCE'}\n", style="bold white")
        text.append(f"Side: ", style="bold cyan")
        side_color = "green" if self.order_side == 'BUY' else "red"
        text.append(f"{self.order_side}\n", style=f"bold {side_color}")
        text.append(f"Qty: ", style="bold cyan")
        text.append(f"{self.order_qty}\n", style="bold white")
        text.append(f"Status: ", style="bold cyan")
        text.append(f"{self.order_status}\n", style="bold yellow")
        text.append("\n[dim]Commands: B=Buy, S=Sell, R=RELIANCE, T=TCS, etc.[/dim]\n")
        text.append("[dim]Type number for qty, then Enter to execute[/dim]", style="dim")
        
        return Panel(text, title="[bold magenta] ORDER ENTRY [/bold magenta]", border_style="magenta")
    
    def create_trades_panel(self) -> Panel:
        """Create recent trades blotter"""
        table = Table(box=ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Time", width=10)
        table.add_column("Symbol", style="bold white")
        table.add_column("Side", width=6)
        table.add_column("Qty", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Notional", justify="right")
        table.add_column("PnL", justify="right")

        for trade in self.portfolio.trades[:10]:
            side_color = "green" if trade['side'] == 'BUY' else "red"
            pnl_color = "green" if trade['pnl'] >= 0 else "red"
            pnl_str = f"{trade['pnl']:+,.0f}" if trade['pnl'] != 0 else "-"

            # FIX: Format time safely to avoid datetime rendering errors
            trade_time = trade.get('time')
            if hasattr(trade_time, 'strftime'):
                time_str = trade_time.strftime('%H:%M:%S')
            else:
                time_str = str(trade_time)

            table.add_row(
                time_str,
                trade['symbol'],
                f"[{side_color}]{trade['side']}[/{side_color}]",
                f"{trade['qty']:,}",
                f"₹{trade['price']:.2f}",
                f"₹{trade['notional']:,.0f}",
                f"[{pnl_color}]{pnl_str}[/{pnl_color}]"
            )

        if not self.portfolio.trades:
            table.add_row("-", "-", "-", "-", "-", "-", "[dim]No trades yet[/dim]")

        return Panel(table, title=f"[bold green] RECENT TRADES ({self.portfolio.total_trades}) [/bold green]", border_style="green")
    
    def create_portfolio_panel(self) -> Panel:
        """Create portfolio positions table with detailed tracking"""
        table = Table(box=ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Symbol", style="bold white", width=12)
        table.add_column("Qty", justify="right", width=8)
        table.add_column("Avg Price", justify="right", width=10)
        table.add_column("LTP", justify="right", width=10)
        table.add_column("Unrealized\nP&L", justify="right", width=12)
        table.add_column("Realized\nP&L", justify="right", width=12)
        table.add_column("Net\nReturn", justify="right", width=10)
        
        equity = self.portfolio.get_portfolio_value()
        pnl = equity - self.portfolio.initial_capital
        pnl_pct = (pnl / self.portfolio.initial_capital) * 100
        dd = self.portfolio.get_drawdown()
        
        # Detailed row for each position
        for symbol, pos in self.portfolio.positions.items():
            # Colors
            un_color = "green" if pos['unrealized_pnl'] >= 0 else "red"
            re_color = "green" if pos['realized_pnl'] >= 0 else "red"
            
            # Calculate Net Return % based on invested amount
            invested = pos['avg_price'] * pos['qty']
            net_pnl = pos['unrealized_pnl'] + pos['realized_pnl']
            net_pct = (net_pnl / invested * 100) if invested > 0 else 0
            net_color = "green" if net_pnl >= 0 else "red"
            
            table.add_row(
                symbol,
                f"{pos['qty']:,}",
                f"₹{pos['avg_price']:.2f}",
                f"₹{pos['current_price']:.2f}",
                f"[{un_color}]{pos['unrealized_pnl']:+,.0f}[/{un_color}]",
                f"[{re_color}]{pos['realized_pnl']:+,.0f}[/{re_color}]",
                f"[{net_color}]{net_pct:+.2f}%[/{net_color}]"
            )
        
        if not self.portfolio.positions:
            table.add_row("-", "-", "-", "-", "-", "-", "[dim]No positions[/dim]")
        
        # Summary Footer for the Panel
        pnl_color = "green" if pnl >= 0 else "red"
        
        # Breakdown of P&L types
        total_unrealized = sum(pos['unrealized_pnl'] for pos in self.portfolio.positions.values())
        total_realized = self.portfolio.daily_pnl  # Daily P&L tracks realized gains from closed trades
        
        summary_text = Text()
        summary_text.append(f"\nPortfolio Equity: ", style="bold")
        summary_text.append(f"₹{equity:,.0f}  ", style="bold yellow")
        
        summary_text.append(f"Today's Realized P&L: ", style="bold")
        summary_text.append(f"₹{total_realized:+,.0f}  ", style=f"bold {'green' if total_realized >= 0 else 'red'}")
        
        summary_text.append(f"Open Unrealized P&L: ", style="bold")
        summary_text.append(f"₹{total_unrealized:+,.0f}  ", style=f"bold {'green' if total_unrealized >= 0 else 'red'}")
        
        summary_text.append(f"\nDrawdown: ", style="bold")
        summary_text.append(f"{dd:.2f}%  ", style="bold red" if dd > 2 else "bold green")
        
        summary_text.append(f"Cash: ", style="bold")
        summary_text.append(f"₹{self.portfolio.cash:,.0f}", style="bold cyan")
        
        # Combine table and summary
        combined = Table.grid(padding=0)
        combined.add_column()
        combined.add_row(table)
        combined.add_row(summary_text)
        
        return Panel(combined, title="[bold blue] PORTFOLIO HOLDINGS & PERFORMANCE [/bold blue]", border_style="blue")
    
    def create_charts_panel(self) -> Panel:
        """Create charts panel with line and candlestick charts"""
        if not HAS_CHARTS:
            return Panel("[red]Charts module not available[/red]", title="[bold] CHARTS [/bold]")
        
        # Generate charts
        symbol = self.order_symbol or 'RELIANCE'
        
        try:
            # Get line chart
            line_chart = self.chart_generator.get_line_chart(symbol=symbol, width=78, height=15)
            
            # Get candlestick chart
            candle_chart = self.chart_generator.get_candlestick_chart(symbol=symbol, width=78, height=15)
            
            # Combine into single panel
            combined_text = Text()
            combined_text.append("LINE CHART - CLOSING PRICE\n", style="bold cyan")
            combined_text.append(line_chart)
            combined_text.append("\n\n")
            combined_text.append("CANDLESTICK CHART\n", style="bold yellow")
            combined_text.append(candle_chart)
            
            return Panel(combined_text, title=f"[bold magenta] CHARTS: {symbol} [/bold magenta]", border_style="magenta")
            
        except Exception as e:
            return Panel(f"[red]Error generating charts: {str(e)}[/red]", title="[bold] CHARTS [/bold]")
    
    def create_tabs(self) -> str:
        """Create tab bar"""
        tabs = []
        for i, tab in enumerate(self.tabs):
            if i == self.active_tab:
                tabs.append(f"[bold white on blue] {tab} [/bold white on blue]")
            else:
                tabs.append(f"[dim]{tab}[/dim]")
        return "  ".join(tabs)
    
    def update_strategy_alerts(self):
        """Update alerts based on current market data"""
        # Construct DOM snapshot for detector
        active_sym = self.order_symbol or 'RELIANCE'
        ob = self.market.order_books.get(active_sym, {})
        
        # Calculate spread in ticks (assuming 0.05 tick size)
        spread = ob.get('spread', 0.10)
        spread_ticks = max(1, int(spread / 0.05))
        
        # Calculate imbalance
        bids = ob.get('bids', [])
        asks = ob.get('asks', [])
        bid_vol = sum(b.get('size', 0) for b in bids)
        ask_vol = sum(a.get('size', 0) for a in asks)
        total_vol = bid_vol + ask_vol + 1
        imbalance = bid_vol / total_vol
        
        # Calculate average sizes
        avg_bid = bid_vol / len(bids) if bids else 1000
        avg_ask = ask_vol / len(asks) if asks else 1000
        
        dom_snapshot = {
            'spread_ticks': spread_ticks,
            'imbalance': imbalance,
            'bids': bids,
            'asks': asks,
            'avg_bid_size': avg_bid,
            'avg_ask_size': avg_ask
        }
        
        # Simulate tape prints (replace with real tape when available)
        tape_prints = [{'size': random.randint(100, 5000), 'side': 'BUY'} for _ in range(random.randint(1, 5))]
        
        self.strategy_detector.update_data(dom_snapshot, tape_prints)
        self.active_alerts = self.strategy_detector.detect_setups()

    def create_performance_panel(self) -> Panel:
        """Show trading performance analytics"""
        report = self.optimizer.get_performance_report()
        
        if isinstance(report, dict) and 'message' in report:
            content = Text()
            content.append("No trades yet. Start paper trading to see analytics.\n", style="dim")
            content.append("\nRisk Controls Active:\n", style="bold white")
            content.append(f"  Stop Loss: {self.optimizer.stop_loss_pct*100:.1f}%\n", style="yellow")
            content.append(f"  Max Position: {self.optimizer.max_position_pct*100:.1f}% of equity\n", style="yellow")
            content.append(f"  Daily Loss Limit: {self.optimizer.daily_loss_limit*100:.1f}%\n", style="yellow")
            content.append(f"  Slippage: {self.optimizer.slippage_bps:.1f} bps\n", style="yellow")
            content.append(f"  Commission: {self.optimizer.commission_bps:.1f} bps\n", style="yellow")
            return Panel(content, title="[bold cyan] PERFORMANCE ANALYTICS [/bold cyan]")
        
        content = Text()
        content.append("TRADING PERFORMANCE\n\n", style="bold white")
        
        content.append(f"Total Trades: {report['total_trades']}\n", style="cyan")
        content.append(f"Win Rate: {report['win_rate']:.1f}% ({report['winning_trades']}W / {report['losing_trades']}L)\n", style="green" if report['win_rate'] > 50 else "red")
        content.append(f"Total P&L: {report['total_pnl']:+,.0f}\n", style="green" if report['total_pnl'] > 0 else "red")
        content.append(f"Avg Win: {report['avg_win']:,.0f} | Avg Loss: {report['avg_loss']:,.0f}\n", style="dim")
        content.append(f"Profit Factor: {report['profit_factor']:.2f}\n", style="yellow")
        content.append(f"Max Drawdown: {report['max_drawdown']:+,.0f}\n", style="red")
        content.append(f"Sharpe Ratio: {report['sharpe_ratio']:.2f}\n\n", style="cyan")
        
        if report.get('recent_trades'):
            content.append("Last 5 Trades:\n", style="bold underline")
            for t in report['recent_trades']:
                pnl = t.get('pnl', 0)
                pnl_color = "green" if pnl > 0 else "red"
                
                # Safely format time
                trade_time = t.get('time')
                if hasattr(trade_time, 'strftime'):
                    time_str = trade_time.strftime('%H:%M')
                else:
                    time_str = str(trade_time) if trade_time else "N/A"
                
                # Safe getters
                side = t.get('side', '?')
                qty = t.get('qty', 0)
                symbol = t.get('symbol', '?')
                price = t.get('price', 0.0)
                
                content.append(f"  {time_str} | {side} {qty} {symbol} @ {price:.2f} | PnL: {pnl:+,.0f}\n", style=pnl_color)
        
        return Panel(content, title="[bold cyan] PERFORMANCE ANALYTICS [/bold cyan]")

    def create_strategy_panel(self) -> Panel:
        """Show active HFT strategy setups + Cheat Sheet"""
        if not self.active_alerts:
            content = Text()
            content.append("No Active Setups Detected\n\n", style="bold dim")
            content.append("🔍 Scanning 12 Institutional Strategies:\n", style="bold white")
            content.append("  ⚡  1. Scalping (Spread + Queue)        🔥  2. Momentum (Blocks)\n", style="cyan")
            content.append("  🧱  3. Wall Fade (Imbalance)            💰  4. Rebate (Add Liq)\n", style="yellow")
            content.append("  🎯  5. Stop Hunt (Reversal)             🕵️  6. Dark Pool (TRF/ADF)\n", style="magenta")
            content.append("  🌊  7. Sweep (Multi-ECN)                🔔  8. Auction Fade\n", style="orange")
            content.append("  📰  9. News Fade                        🧊 10. Iceberg Break\n", style="red")
            content.append("  📍 11. Queue Arb                       📉 12. VWAP Revert\n", style="blue")
            content.append("\n🎮 Hotkeys:\n", style="bold underline white")
            content.append("  F1-F12 = Execute Strategy  |  F = Cheat Sheet  |  Esc = Cancel\n", style="dim")
            return Panel(content, title="[bold magenta] STRATEGY SCANNER [/bold magenta]")
        
        # Show active alerts
        content = Text()
        content.append("⚠️ ACTIVE SETUPS:\n\n", style="bold green")
        
        for i, alert in enumerate(self.active_alerts, 1):
            content.append(f"  {alert.get('icon', '•')} ", style=alert.get('color', 'white'))
            content.append(f"{alert.get('type', 'UNKNOWN')}", style=f"bold {alert.get('color', 'white')}")
            content.append(f" [{alert.get('hotkey', '')}]\n", style="bold dim")
            content.append(f"     {alert.get('msg', '')}\n", style="white")
            content.append(f"     Action: {alert.get('action', '')}\n", style="bold underline white")
            if alert.get('details'):
                content.append(f"     {alert['details']}\n\n", style="dim")
            else:
                content.append("\n")
            
        return Panel(content, title="[bold magenta] ⚠️ ACTIVE SIGNALS [/bold magenta]")

    def create_cheat_sheet_panel(self) -> Panel:
        """Terminal Setup Cheat Sheet"""
        content = Text()
        content.append("🔑 TIME & SALES COLUMNS:\n", style="bold cyan")
        content.append("  Exchange  | Size  | Time(ms)  | B/A  | Cond\n", style="dim")
        content.append("  NSDQ=Ret  | <500=Retail  | <100ms=Momentum  | ZERO=Dark\n\n", style="dim")
        
        content.append("⚡ MANDATORY HOTKEYS (F1-F12):\n", style="bold yellow")
        content.append("  F1: LMT_JOIN_BID (POST, NSDQ)    F2: BUY_MKT_CONT (EDGX)\n", style="white")
        content.append("  F3: FADE_WALL (POST, Away)       F4: ADD_LIQ (NSDQ/ARCA)\n", style="white")
        content.append("  F5: REV_STOP_HUNT (IEX)          F6: FOLLOW_DARK (NSDQ)\n", style="white")
        content.append("  F7: MKT_SWEEP (SMART/AGG)        F8: FADE_AUC (NSDQ)\n", style="white")
        content.append("  F9: FADE_NEWS (IEX)              F10: ICEBERG (SMART)\n", style="white")
        content.append("  F11: STEP_AHEAD (POST, NSDQ)     F12: VWAP_REV (IEX)\n\n", style="white")
        
        content.append("🛠️ PRO CONFIG:\n", style="bold green")
        content.append("  DOM: 100ms | Min Print: 100 | VWD Overlay | Auto-Flatten 3x ATR\n", style="dim")
        content.append("  Routing: CTRL+R=Rebate | CTRL+A=Aggressive\n", style="dim")
        
        return Panel(content, title="[bold white on blue] TERMINAL CHEAT SHEET [/bold white on blue]")

    def execute_strategy_hotkey(self, strategy_type: str):
        """Handle all 12 strategy-specific hotkeys with stop/target preview."""
        strategy_map = {
            'F1':  ('BUY_PENDING',  '[bold cyan]⚡ SCALPING[/bold cyan]'),
            'F2':  ('BUY_PENDING',  '[bold red]🔥 MOMENTUM[/bold red]'),
            'F3':  ('SELL_PENDING', '[bold yellow]🧱 WALL FADE SHORT[/bold yellow]'),
            'F4':  ('BUY_PENDING',  '[bold green]💰 REBATE ADD-LIQ[/bold green]'),
            'F5':  ('BUY_PENDING',  '[bold magenta]🎯 STOP HUNT REVERSAL[/bold magenta]'),
            'F6':  ('BUY_PENDING',  '[bold blue]🕵️ DARK POOL FOLLOW[/bold blue]'),
            'F7':  ('BUY_PENDING',  '[bold yellow]🌊 SWEEP MOMENTUM[/bold yellow]'),
            'F8':  ('SELL_PENDING', '[bold white]🔔 AUCTION FADE[/bold white]'),
            'F9':  ('SELL_PENDING', '[bold red]📰 NEWS FADE[/bold red]'),
            'F10': ('BUY_PENDING',  '[bold cyan]🧊 ICEBERG BREAK[/bold cyan]'),
            'F11': ('BUY_PENDING',  '[bold yellow]📍 QUEUE ARB[/bold yellow]'),
            'F12': ('SELL_PENDING', '[bold magenta]📉 VWAP REVERT[/bold magenta]'),
        }

        if strategy_type not in strategy_map:
            return

        state, label = strategy_map[strategy_type]
        side = 'BUY' if state == 'BUY_PENDING' else 'SELL'
        symbol = self.order_symbol or 'RELIANCE'
        price = self.market.prices.get(symbol, 0)

        # === SIGNAL VALIDATION: check momentum direction before arming ===
        history = self.market.ticker_history.get(symbol, [])
        is_valid, rejection_msg = self.optimizer.validate_entry(strategy_type, side, history)
        if not is_valid:
            # Don't arm the order — show rejection with actionable advice
            self.order_status = rejection_msg
            self.input_state = 'IDLE'
            self.current_strategy_key = ''
            return

        # Signal confirmed — arm the order state
        self.input_state = state
        self.input_buffer = ''
        self.current_strategy_key = strategy_type

        # Show stop/target preview
        if price > 0:
            targets = self.optimizer.get_strategy_targets(price, side, strategy_type)
            stop_bps = self.optimizer.strategy_stop_bps.get(strategy_type, 50)
            rr = self.optimizer.strategy_min_rr.get(strategy_type, 2.0)
            equity = self.portfolio.get_portfolio_value()
            preview_qty = self.optimizer.calculate_position_size(
                equity, price, targets['stop'], strategy_type
            )
            self.order_status = (
                f"[green]SIGNAL OK[/green] {label} | {symbol} {side} @ \u20b9{price:.2f} | "
                f"Stop: \u20b9{targets['stop']:.2f} ({stop_bps}bps) | "
                f"Target: \u20b9{targets['target']:.2f} (R:R {rr:.1f}) | "
                f"Kelly qty: {preview_qty} | Press Enter to execute or type qty first"
            )
        else:
            self.order_status = f"{label} \u2014 Enter quantity, then press Enter"


    def handle_key(self, key: str):
        """Handle keyboard input with State Machine Logic"""
        
        # === QUIT ===
        if key.lower() == 'q':
            return 'quit'

        # === MODE: TYPING QUANTITY (Entry State) ===
        if self.input_state in ["BUY_PENDING", "SELL_PENDING"]:

            # Enter to Execute
            if key == '\r' or key == '\n':
                symbol = self.order_symbol
                if not symbol:
                    self.order_status = "[red]Select a stock first (R/T/I/H/M)[/red]"
                    self.input_state = 'IDLE'
                    self.input_buffer = ''
                    return None

                price = self.market.prices.get(symbol, 0)
                strategy_key = getattr(self, 'current_strategy_key', '')

                # Auto-size if user pressed Enter without typing a qty
                if not self.input_buffer or not self.input_buffer.isdigit():
                    targets = self.optimizer.get_strategy_targets(
                        price, 'BUY' if self.input_state == 'BUY_PENDING' else 'SELL', strategy_key or 'F1'
                    )
                    qty = self.optimizer.calculate_position_size(
                        self.portfolio.get_portfolio_value(), price, targets['stop'], strategy_key or 'F1'
                    )
                else:
                    qty = int(self.input_buffer)

                if qty <= 0:
                    self.order_status = "[red]Invalid quantity[/red]"
                else:
                    if self.input_state == "BUY_PENDING":
                        res = self.portfolio.buy(symbol, qty, price, strategy_key=strategy_key)
                    else:
                        res = self.portfolio.sell(symbol, qty, price, strategy_key=strategy_key, reason='MANUAL')

                    if res['success']:
                        trade = res['trade']
                        stop_str = f" | Stop: ₹{trade.get('stop', 0):.2f}" if trade.get('stop') else ''
                        tgt_str = f" | Target: ₹{trade.get('target', 0):.2f}" if trade.get('target') else ''
                        self.order_status = (
                            f"[green]FILLED: {trade['side']} {qty} {symbol} "
                            f"@ ₹{trade['price']:.2f}{stop_str}{tgt_str}[/green]"
                        )
                    else:
                        self.order_status = f"[red]ERROR: {res['error']}[/red]"

                self.input_state = 'IDLE'
                self.input_buffer = ''
                self.current_strategy_key = ''
                return None

            # Escape to Cancel
            if key == '\x1b' or key.lower() == 'c':
                self.input_state = "IDLE"
                self.input_buffer = ""
                self.order_status = "Cancelled"
                return None

            # Digits (0-9)
            if key.isdigit():
                self.input_buffer += key
                self.order_status = f"[{ 'green' if self.input_state=='BUY_PENDING' else 'red' }] {self.input_state.replace('_PENDING','')} {self.order_symbol}: [bold white]{self.input_buffer}[/bold white] shares | Enter to confirm, Esc to cancel"
                return None
            
            # Backspace
            if key in ['\x08', '\x7f']:
                self.input_buffer = self.input_buffer[:-1]
                self.order_status = f"Qty: {self.input_buffer}"
                return None

            # Ignore everything else (including tab switching keys)
            return None

        # === MODE: IDLE (Navigation State) ===
        # Here, keys switch tabs or setup orders.
        
        # Tab Switching
        if key in ['1','2','3','4','5','6']:
            self.active_tab = int(key) - 1
            return None

        # Auto-Trade Toggle
        if key.lower() == 'a':
            if not self.autonomous_enabled:
                self.autonomous_enabled = True
                self.auto_status = "▶️ RUNNING"
                self.order_status = "[green]Auto-Trade STARTED[/green]"
            else:
                self.autonomous_enabled = False
                self.auto_status = "⏹️ STOPPED"
                self.order_status = "[red]Auto-Trade STOPPED[/red]"
            return None
            
        # Post-Market Report
        if key.lower() == 'd' and not self.autonomous_enabled:
            # Generate report on 'D' key
            pass 

        # --- SETUP ORDER (Transitions to Entry State) ---
        if key.lower() == 'b':
            self.input_state = "BUY_PENDING"
            self.input_buffer = ""
            self.order_status = "[bold green]BUYING[/bold green] - Enter Quantity:"
            return None
            
        if key.lower() == 's':
            self.input_state = "SELL_PENDING"
            self.input_buffer = ""
            self.order_status = "[bold red]SELLING[/bold red] - Enter Quantity:"
            return None
            
        # --- STOCK SELECTION ---
        # Remapped to avoid conflicts with Buy(B), Sell(S), Auto(A)
        if key.lower() == 'r': self.order_symbol = 'RELIANCE'
        elif key.lower() == 't': self.order_symbol = 'TCS'
        elif key.lower() == 'i': self.order_symbol = 'INFY'
        elif key.lower() == 'h': self.order_symbol = 'HDFCBANK'
        elif key.lower() == 'm': self.order_symbol = 'TATAMOTORS'
        elif key.lower() == 'n': self.order_symbol = 'SBIN'      # Changed S -> N
        elif key.lower() == 'w': self.order_symbol = 'WIPRO'
        elif key.lower() == 'd': self.order_symbol = 'ADANIENT'  # Changed A -> D
        elif key.lower() == 'c': self.order_symbol = 'ICICIBANK'
        
        # --- Pro Strategy Hotkeys F1-F12 (Only in IDLE state) ---
        # Windows sends \x00 then a scan code char for function keys
        if self.input_state == "IDLE":
            # Check if this is part of a function key sequence (scan code follows \x00)
            if key in [';', '<', '=', '>', '?', '@', 'A', 'B', 'C', 'D', 'E', 'F']:
                fkey_map = {
                    ';': 'F1', '<': 'F2', '=': 'F3', '>': 'F4',
                    '?': 'F5', '@': 'F6', 'A': 'F7', 'B': 'F8',
                    'C': 'F9', 'D': 'F10', 'E': 'F11', 'F': 'F12'
                }
                if key in fkey_map:
                    self.execute_strategy_hotkey(fkey_map[key])
                    return None
                    
            # Legacy single-key shortcuts
            if key.lower() == 'f':
                # Toggle cheat sheet view (handled in layout)
                self.show_cheat_sheet = not getattr(self, 'show_cheat_sheet', False)
                return None

        return None
    
    def _update_search_results(self):
        """Update search results based on current buffer"""
        if not self.search_buffer:
            self.search_results = []
            return
        
        search_term = self.search_buffer.upper()
        self.search_results = []
        
        for symbol in self.symbols.keys():
            if search_term in symbol.upper():
                self.search_results.append(symbol)
    
    def create_search_panel(self) -> Panel:
        """Create stock search/order panel"""
        if not self.search_mode:
            return None
        
        # Left side: Search input
        search_text = Text()
        search_text.append("🔍 SEARCH STOCKS\n\n", style="bold cyan")
        search_text.append(f"Type: ", style="bold")
        search_text.append(f"{self.search_buffer}█", style="bold yellow blink")
        search_text.append("\n\n", style="default")
        search_text.append("Press ENTER to select\n", style="dim")
        search_text.append("Press ESC to cancel\n", style="dim")
        
        left_panel = Panel(search_text, title="[bold cyan]SEARCH[/bold cyan]", border_style="cyan")
        
        # Right side: Search results with prices
        if self.search_results:
            results_table = Table(box=ROUNDED, show_header=True, header_style="bold cyan", expand=True)
            results_table.add_column("Symbol", style="bold white", width=15)
            results_table.add_column("Price", justify="right", width=12)
            results_table.add_column("Change", justify="right", width=12)
            results_table.add_column("Signal", justify="center", width=10)
            
            for symbol in self.search_results[:5]:  # Top 5 results
                price = self.market.prices.get(symbol, 0)
                
                # Calculate change (compare to previous)
                prev_price = self.market.prev_prices.get(symbol, price)
                change = price - prev_price
                change_pct = (change / prev_price * 100) if prev_price else 0
                
                # Determine if up or down
                if change > 0:
                    change_str = f"[green]▲ +{change_pct:.2f}%[/green]"
                    signal = "[green]📈 UP[/green]"
                elif change < 0:
                    change_str = f"[red]▼ {change_pct:.2f}%[/red]"
                    signal = "[red]📉 DOWN[/red]"
                else:
                    change_str = f"[yellow]➡ {change_pct:.2f}%[/yellow]"
                    signal = "[yellow]🟡 FLAT[/yellow]"
                
                results_table.add_row(
                    symbol,
                    f"₹{price:.2f}",
                    change_str,
                    signal
                )
            
            right_panel = Panel(results_table, title="[bold green]RESULTS[/bold green]", border_style="green")
        else:
            no_results = Text()
            no_results.append("\n", style="default")
            if self.search_buffer:
                no_results.append(f"No matches for '{self.search_buffer}'", style="bold red")
            else:
                no_results.append("Type to search...", style="dim")
            no_results.append("\n\n", style="default")
            no_results.append("Available stocks:\n", style="bold")
            for symbol in list(self.symbols.keys())[:8]:
                price = self.market.prices.get(symbol, 0)
                prev_price = self.market.prev_prices.get(symbol, price)
                change_pct = ((price - prev_price) / prev_price * 100) if prev_price else 0
                
                if change_pct > 0:
                    no_results.append(f"  {symbol:12} ₹{price:10.2f}  [green]▲ +{change_pct:.2f}%[/green]\n", style="default")
                elif change_pct < 0:
                    no_results.append(f"  {symbol:12} ₹{price:10.2f}  [red]▼ {change_pct:.2f}%[/red]\n", style="default")
                else:
                    no_results.append(f"  {symbol:12} ₹{price:10.2f}  [yellow]➡ {change_pct:.2f}%[/yellow]\n", style="default")
            
            right_panel = Panel(no_results, title="[bold yellow]ALL STOCKS[/bold yellow]", border_style="yellow")
        
        # Combine left and right panels
        from rich.console import Group
        content = Group(
            left_panel,
            right_panel
        )
        
        return Panel(content, title="[bold green]🔍 STOCK SEARCH & ORDER[/bold green]", border_style="green")
    
    def build_layout(self) -> Layout:
        """Build the complete terminal layout"""
        layout = Layout()
        
        # Show search panel if active
        if self.search_mode:
            search_panel = self.create_search_panel()
            layout.split_column(
                Layout(name="header", size=5),
                Layout(name="body"),
                Layout(name="footer", size=3)
            )
            layout["body"].update(search_panel)
            layout["header"].update(self.create_header())
            
            footer_text = Text()
            footer_text.append("SEARCH MODE: ", style="bold cyan")
            footer_text.append("Type stock name | ", style="dim")
            footer_text.append("ENTER=Select | ", style="bold yellow")
            footer_text.append("ESC=Cancel | ", style="dim")
            footer_text.append("Q=Quit", style="bold red")
            layout["footer"].update(Panel(footer_text, border_style="cyan"))
            
            return layout

        # Split into header and body
        layout.split_column(
            Layout(name="header", size=5),
            Layout(name="tabs", size=2),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )
        
        # Body splits
        if self.active_tab == 0:  # OVERVIEW
            layout["body"].split_row(
                Layout(name="left"),
                Layout(name="right")
            )
            layout["left"].split_column(
                Layout(name="watchlist"),
                Layout(name="order_entry", size=12)
            )
            layout["right"].update(self.create_portfolio_panel())
            layout["watchlist"].update(self.create_watchlist_panel())
            layout["order_entry"].update(self.create_order_entry_panel())
        
        elif self.active_tab == 1:  # ORDER BOOK
            layout["body"].split_row(
                Layout(name="ob_left"),
                Layout(name="ob_right")
            )
            layout["ob_left"].update(self.create_order_book_panel())
            layout["ob_right"].split_column(
                Layout(name="watchlist_small"),
                Layout(name="order_entry_small")
            )
            layout["watchlist_small"].update(self.create_watchlist_panel())
            layout["order_entry_small"].update(self.create_order_entry_panel())
        
        elif self.active_tab == 2:  # TRADES
            layout["body"].update(self.create_trades_panel())

        elif self.active_tab == 3:  # PORTFOLIO
            layout["body"].split_row(
                Layout(name="positions"),
                Layout(name="performance")
            )
            layout["positions"].update(self.create_portfolio_panel())
            layout["performance"].update(self.create_performance_panel())
        
        elif self.active_tab == 4:  # CHARTS
            if HAS_CHARTS:
                layout["body"].update(self.create_charts_panel())
            else:
                layout["body"].update(Panel("[red]Charts not available. Install plotext: pip install plotext[/red]", title="CHARTS"))

        elif self.active_tab == 5:  # AUTO - AUTONOMOUS TRADING
            layout["body"].update(self.create_auto_panel())

        elif self.active_tab == 6:  # STRATEGIES TAB
            # Update alerts before drawing
            self.update_strategy_alerts()
            layout["body"].split_row(
                Layout(name="alerts"),
                Layout(name="order_book")
            )
            
            # Show cheat sheet if toggled
            if getattr(self, 'show_cheat_sheet', False):
                layout["alerts"].update(self.create_cheat_sheet_panel())
            else:
                layout["alerts"].update(self.create_strategy_panel())
            layout["order_book"].update(self.create_order_book_panel())
        
        # Header and tabs
        layout["header"].update(self.create_header())
        layout["tabs"].update(Panel(self.create_tabs(), border_style="dim"))
        
        # Footer
        footer_text = Text()
        footer_text.append("KEYS: ", style="bold")
        footer_text.append("1-7=Tabs | F1-F12=Strategies | F=CheatSheet | ", style="dim")
        footer_text.append("B=Buy S=Sell | R/T/I/H/M=Symbol | 0-9=Qty | Enter=Execute | ", style="dim")
        footer_text.append("A=AutoTrade | ", style="bold yellow")
        footer_text.append("Q=Quit", style="bold red")
        layout["footer"].update(Panel(footer_text, border_style="dim"))
        
        return layout
    
    def run(self, update_interval: float = 0.5):
        """Run the live terminal dashboard"""
        import keyboard
        import msvcrt

        console.clear()
        console.print("[bold green]Starting HFT Terminal... Press Q to quit[/bold green]\n")

        with Live(self.build_layout(), console=console, refresh_per_second=4, screen=True) as live:
            cycle_counter = 0
            
            while True:
                # Update market data
                self.market.update_prices()
                self.portfolio.update_market_prices(self.market)
                
                # === POSITION MANAGEMENT: Stop-Loss | Take-Profit | Trailing Stop ===
                for symbol in list(self.portfolio.positions.keys()):
                    pos = self.portfolio.positions.get(symbol)
                    if not pos:
                        continue
                    current_price = self.market.prices.get(symbol, 0)
                    if current_price <= 0:
                        continue

                    qty = pos['qty']
                    avg = pos['avg_price']
                    stop  = pos.get('stop_loss', 0)
                    target = pos.get('take_profit', 0)
                    side = pos.get('side', 'BUY')
                    strategy_key = pos.get('strategy', '')

                    exit_reason = None

                    # 1. Take-profit
                    if target and self.optimizer.check_take_profit(avg, current_price, side, target):
                        exit_reason = 'TAKE_PROFIT'

                    # 2. Update trailing stop and check
                    elif stop:
                        new_trail = self.optimizer.update_trailing_stop(symbol, current_price, side, avg)
                        if new_trail:
                            # Tighten stop as we trail
                            if side == 'BUY':
                                pos['stop_loss'] = max(pos['stop_loss'], new_trail)
                            else:
                                pos['stop_loss'] = min(pos['stop_loss'], new_trail)
                            stop = pos['stop_loss']

                        if self.optimizer.check_stop_loss(avg, current_price, side, stop):
                            exit_reason = 'STOP_LOSS'

                    if exit_reason:
                        result = self.portfolio.sell(
                            symbol, qty, current_price,
                            strategy_key=strategy_key, reason=exit_reason
                        )
                        if result['success']:
                            trade = result['trade']
                            color = 'green' if trade['pnl'] >= 0 else 'red'
                            pnl_str = f"₹{trade['pnl']:+,.0f}"
                            self.order_status = (
                                f"[{color}]{exit_reason}: Sold {qty} {symbol} "
                                f"@ ₹{current_price:.2f} | PnL: {pnl_str}[/{color}]"
                            )

                # Refresh display
                live.update(self.build_layout())

                # Check for keypress (non-blocking)
                if msvcrt.kbhit():
                    first_byte = msvcrt.getch()
                    
                    # Handle Windows function key sequences (\x00 or \xe0 + scan code)
                    if first_byte in [b'\x00', b'\xe0']:
                        scan_code = msvcrt.getch()
                        # Pass scan code directly to handle_key for F1-F12 mapping
                        result = self.handle_key(scan_code.decode('utf-8', errors='ignore'))
                    else:
                        key = first_byte.decode('utf-8', errors='ignore')
                        result = self.handle_key(key)
                        
                    if result == 'quit':
                        console.print("\n[bold red]Shutting down HFT Terminal...[/bold red]")
                        break

                time.sleep(update_interval)

# ============================================================
# MAIN
# ============================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='HFT Terminal Trading Dashboard')
    parser.add_argument('--capital', type=float, default=10_000_000, help='Initial capital')
    parser.add_argument('--interval', type=float, default=0.5, help='Update interval (seconds)')
    
    args = parser.parse_args()
    
    dashboard = TerminalDashboard()
    # Override initial capital if provided, but KEEP the broker reference!
    dashboard.portfolio.initial_capital = args.capital
    dashboard.portfolio.cash = args.capital
    dashboard.run(update_interval=args.interval)

if __name__ == '__main__':
    main()
