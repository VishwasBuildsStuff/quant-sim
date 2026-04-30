"""
Autonomous HFT Trading Bot
Complete automated trading system that runs in background
"""

import sys
sys.path.insert(0, r'V:\pylibs')
sys.path.insert(0, '.')

import os
import json
import time
import logging
import numpy as np
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path

from watchlist_manager import WatchlistManager
from portfolio_manager import PortfolioManager
from multi_model_ensemble import MultiModelEnsemble

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('auto_trader.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AutonomousTrader:
    """
    Fully autonomous HFT trading bot
    
    Features:
    - Monitors watchlist of stocks
    - Uses multi-model ensemble for predictions
    - Makes automated trading decisions
    - Manages portfolio and risk
    - Runs continuously in background
    """
    
    def __init__(self, config_path: str = 'auto_trader_config.json'):
        
        # Load config
        self.config = self._load_config(config_path)
        
        # Initialize components
        logger.info("\n" + "="*60)
        logger.info("🤖 AUTONOMOUS HFT TRADING BOT")
        logger.info("="*60)
        
        # Watchlist
        self.watchlist = WatchlistManager(
            watchlist_path=self.config.get('watchlist_path', 'watchlist.json'),
            update_interval=self.config.get('update_interval', 10),
            max_symbols=self.config.get('max_symbols', 5)
        )
        
        # Portfolio
        self.portfolio = PortfolioManager(
            initial_capital=self.config.get('initial_capital', 1000000),
            max_positions=self.config.get('max_positions', 5),
            risk_per_trade=self.config.get('risk_per_trade', 0.02),
            max_position_pct=self.config.get('max_position_pct', 0.20),
            stop_loss_pct=self.config.get('stop_loss_pct', 0.02),
            max_drawdown_pct=self.config.get('max_drawdown_pct', 0.05)
        )
        
        # Models
        self.models: Dict[str, MultiModelEnsemble] = {}
        self._load_models()
        
        # State
        self.is_running = False
        self.cycle_count = 0
        self.last_trade_time: Dict[str, datetime] = {}
        self.cooldown_seconds = self.config.get('trade_cooldown', 60)
        
        # Trade log
        self.trade_history = []
        
        logger.info("\n✅ Autonomous Trader initialized")
        logger.info(f"   Capital: ₹{self.config.get('initial_capital', 1000000):,.0f}")
        logger.info(f"   Max Positions: {self.config.get('max_positions', 5)}")
        logger.info(f"   Update Interval: {self.config.get('update_interval', 10)}s")
    
    def _load_config(self, path: str) -> Dict:
        """Load configuration file"""
        if Path(path).exists():
            with open(path, 'r') as f:
                return json.load(f)
        else:
            # Default config
            default_config = {
                'initial_capital': 1000000,
                'max_positions': 5,
                'risk_per_trade': 0.02,
                'max_position_pct': 0.20,
                'stop_loss_pct': 0.02,
                'max_drawdown_pct': 0.05,
                'update_interval': 10,
                'max_symbols': 5,
                'trade_cooldown': 60,
                'confidence_threshold': 0.65,
                'watchlist_path': 'watchlist.json',
                'model_dir': 'output',
                'log_trades': True
            }
            
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                json.dump(default_config, f, indent=2)
            
            logger.info(f"📝 Created default config: {path}")
            return default_config
    
    def _load_models(self):
        """Load trained models for all symbols"""
        model_dir = self.config.get('model_dir', 'output')
        
        if not Path(model_dir).exists():
            logger.warning(f"⚠️ Model directory not found: {model_dir}")
            return
        
        # Find all model files
        model_files = list(Path(model_dir).glob('*ensemble*.joblib')) + \
                      list(Path(model_dir).glob('*multi*.joblib')) + \
                      list(Path(model_dir).glob('*trained*.joblib'))
        
        for model_file in model_files:
            try:
                # Extract symbol from filename
                filename = model_file.stem
                symbol = filename.split('_')[0].upper()
                
                # Load model
                model = MultiModelEnsemble.load(str(model_file))
                self.models[symbol] = model
                
                logger.info(f"  ✓ {symbol}: Model loaded ({model_file.name})")
                
            except Exception as e:
                logger.error(f"  ✗ {model_file.name}: Failed to load - {e}")
        
        if not self.models:
            logger.warning("⚠️ No models loaded! Trading will use random predictions")
        else:
            logger.info(f"\n✅ Loaded {len(self.models)} models")
    
    def start(self):
        """Start autonomous trading"""
        logger.info("\n" + "="*60)
        logger.info("🚀 STARTING AUTONOMOUS TRADING BOT")
        logger.info("="*60)
        
        # Start live data feeds
        self.watchlist.start_live_feeds()
        
        self.is_running = True
        
        logger.info("\n🤖 Bot is now RUNNING")
        logger.info("⏹️  Press Ctrl+C to stop\n")
        
        # Main trading loop
        try:
            while self.is_running:
                self.cycle_count += 1
                self._trading_cycle()
                
                # Sleep
                time.sleep(self.config.get('update_interval', 10))
                
        except KeyboardInterrupt:
            logger.info("\n\n⏹️  Stop signal received")
        except Exception as e:
            logger.error(f"\n❌ Fatal error: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self.stop()
    
    def _trading_cycle(self):
        """One complete trading cycle"""
        logger.info(f"\n{'─'*60}")
        logger.info(f"🔄 CYCLE #{self.cycle_count} - {datetime.now().strftime('%H:%M:%S')}")
        logger.info(f"{'─'*60}")
        
        # 1. Update portfolio prices
        self._update_portfolio_prices()
        
        # 2. Get signals from all symbols
        signals = self._get_all_signals()
        
        # 3. Make trading decisions
        recommendations = self.portfolio.get_recommendations(signals)
        
        # 4. Execute trades
        for rec in recommendations:
            if rec['action'] in ['BUY', 'SELL', 'SHORT', 'COVER']:
                self._execute_recommendation(rec)
        
        # 5. Log status
        self._log_status()
    
    def _update_portfolio_prices(self):
        """Update current prices for all positions"""
        price_data = {}
        
        for symbol in self.portfolio.positions:
            price = self.watchlist.get_latest_price(symbol)
            if price is not None:
                price_data[symbol] = price
        
        if price_data:
            self.portfolio.update_prices(price_data)
    
    def _get_all_signals(self) -> Dict[str, Dict]:
        """
        Get trading signals for all symbols
        
        Returns:
            {symbol: {prediction, confidence, price, votes}}
        """
        signals = {}
        confidence_threshold = self.config.get('confidence_threshold', 0.65)
        
        for symbol in self.watchlist.watchlist:
            if not self.watchlist.watchlist[symbol]['enabled']:
                continue
            
            # Get latest price
            price = self.watchlist.get_latest_price(symbol)
            
            if price is None:
                signals[symbol] = {
                    'prediction': 1,  # UNCH
                    'confidence': 0.0,
                    'price': 0,
                    'votes': 'No data'
                }
                continue
            
            # Get features
            features_result = self.watchlist.get_features_for_symbol(symbol)
            
            if features_result is None:
                signals[symbol] = {
                    'prediction': 1,
                    'confidence': 0.0,
                    'price': price,
                    'votes': 'Insufficient data'
                }
                continue
            
            features, feature_names = features_result
            
            # Get model prediction
            if symbol in self.models:
                model = self.models[symbol]
                
                try:
                    pred = model.predict(features)[0]
                    proba = model.predict_proba(features)[0]
                    confidence = np.max(proba)
                    agreement = model.get_model_agreement(features)[0]
                    
                    # Adjust confidence by agreement
                    adjusted_confidence = confidence * agreement
                    
                    # Format votes
                    votes_str = f"XGB:{proba[2]:.0%} LGB:{proba[1]:.0%} RF:{proba[0]:.0%}"
                    
                    signals[symbol] = {
                        'prediction': int(pred),
                        'confidence': adjusted_confidence,
                        'raw_confidence': confidence,
                        'agreement': agreement,
                        'price': price,
                        'votes': votes_str,
                        'probabilities': {
                            'DOWN': proba[0],
                            'UNCH': proba[1],
                            'UP': proba[2]
                        }
                    }
                    
                except Exception as e:
                    logger.error(f"Prediction error for {symbol}: {e}")
                    signals[symbol] = {
                        'prediction': 1,
                        'confidence': 0.0,
                        'price': price,
                        'votes': f'Error: {e}'
                    }
            else:
                # No model for this symbol
                signals[symbol] = {
                    'prediction': 1,
                    'confidence': 0.0,
                    'price': price,
                    'votes': 'No model'
                }
        
        return signals
    
    def _execute_recommendation(self, rec: Dict):
        """Execute a trading recommendation"""
        symbol = rec['symbol']
        action = rec['action']
        
        # Check cooldown
        if symbol in self.last_trade_time:
            time_since_last = (datetime.now() - self.last_trade_time).total_seconds()
            if time_since_last < self.cooldown_seconds:
                logger.info(f"⏳ {symbol}: Cooldown ({self.cooldown_seconds - time_since_last:.0f}s)")
                return
        
        # Check if we should trade
        can_trade, reason = self.portfolio.should_trade(symbol)
        
        if not can_trade:
            logger.info(f"🚫 {symbol}: {reason}")
            return
        
        # Execute
        try:
            trade = self.portfolio.execute_trade(
                symbol=symbol,
                action=action,
                quantity=rec.get('quantity', 0),
                price=rec.get('price', 0),
                confidence=rec.get('confidence', 0),
                model_votes=rec.get('votes', '')
            )
            
            self.last_trade_time[symbol] = datetime.now()
            self.trade_history.append(trade)
            
            logger.info(
                f"✅ {action} {symbol} | "
                f"Qty: {rec.get('quantity', 0)} | "
                f"Price: ₹{rec.get('price', 0):.2f} | "
                f"Conf: {rec.get('confidence', 0):.1%} | "
                f"Reason: {rec.get('reason', '')}"
            )
            
        except Exception as e:
            logger.error(f"❌ Trade execution failed for {symbol}: {e}")
    
    def _log_status(self):
        """Log current status"""
        summary = self.portfolio.get_portfolio_summary()
        
        logger.info(f"\n📊 PORTFOLIO STATUS:")
        logger.info(f"   Equity: ₹{summary['total_equity']:,.0f}")
        logger.info(f"   PnL: ₹{summary['total_pnl']:,.0f} ({summary['return_pct']:.2f}%)")
        logger.info(f"   Positions: {summary['open_positions']}/{summary['max_positions']}")
        logger.info(f"   Daily Trades: {summary['daily_trades']}")
        logger.info(f"   Win Rate: {summary['win_rate']:.1%}")
        logger.info(f"   Drawdown: {summary['drawdown']:.1%}")
        
        # Log positions
        if summary['positions']:
            logger.info(f"\n📈 OPEN POSITIONS:")
            for symbol, pos in summary['positions'].items():
                pnl_str = f"+₹{pos['unrealized_pnl']:,.0f}" if pos['unrealized_pnl'] >= 0 else f"₹{pos['unrealized_pnl']:,.0f}"
                logger.info(
                    f"   {symbol}: {pos['quantity']} shares @ ₹{pos['entry_price']:.2f} | "
                    f"Current: ₹{pos['current_price']:.2f} | "
                    f"PnL: {pnl_str} ({pos['pnl_pct']:.2%})"
                )
    
    def stop(self):
        """Stop autonomous trading"""
        logger.info("\n" + "="*60)
        logger.info("🛑 STOPPING AUTONOMOUS TRADING BOT")
        logger.info("="*60)
        
        self.is_running = False
        
        # Stop live feeds
        self.watchlist.stop_live_feeds()
        
        # Close all positions
        self._close_all_positions()
        
        # Save trade history
        self._save_trade_history()
        
        # Final summary
        summary = self.portfolio.get_portfolio_summary()
        
        logger.info(f"\n📊 FINAL SUMMARY:")
        logger.info(f"   Total Cycles: {self.cycle_count}")
        logger.info(f"   Total Trades: {summary['total_trades']}")
        logger.info(f"   Final Equity: ₹{summary['total_equity']:,.0f}")
        logger.info(f"   Total PnL: ₹{summary['total_pnl']:,.0f}")
        logger.info(f"   Return: {summary['return_pct']:.2f}%")
        logger.info(f"   Win Rate: {summary['win_rate']:.1%}")
        logger.info("="*60)
    
    def _close_all_positions(self):
        """Close all open positions"""
        logger.info("\n📉 Closing all positions...")
        
        for symbol in list(self.portfolio.positions.keys()):
            pos = self.portfolio.positions[symbol]
            price = self.watchlist.get_latest_price(symbol)
            
            if price is None:
                continue
            
            if pos.quantity > 0:
                self.portfolio.execute_trade(symbol, 'SELL', pos.quantity, price)
                logger.info(f"  ✓ Closed {symbol} LONG @ ₹{price:.2f}")
            elif pos.quantity < 0:
                self.portfolio.execute_trade(symbol, 'COVER', abs(pos.quantity), price)
                logger.info(f"  ✓ Closed {symbol} SHORT @ ₹{price:.2f}")
    
    def _save_trade_history(self):
        """Save trade history to file"""
        if not self.trade_history:
            return
        
        filename = f"trade_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        trades_data = []
        for trade in self.trade_history:
            trades_data.append({
                'timestamp': trade.timestamp.isoformat(),
                'symbol': trade.symbol,
                'action': trade.action,
                'quantity': trade.quantity,
                'price': trade.price,
                'pnl': trade.pnl,
                'confidence': trade.confidence,
                'model_votes': trade.model_votes
            })
        
        with open(filename, 'w') as f:
            json.dump(trades_data, f, indent=2)
        
        logger.info(f"💾 Trade history saved to {filename}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Autonomous HFT Trading Bot')
    parser.add_argument('--config', type=str, default='auto_trader_config.json', help='Config file')
    parser.add_argument('--capital', type=float, help='Override initial capital')
    parser.add_argument('--max-pos', type=int, help='Override max positions')
    parser.add_argument('--interval', type=int, help='Override update interval')
    
    args = parser.parse_args()
    
    # Create and start bot
    bot = AutonomousTrader(config_path=args.config)
    
    # Apply overrides
    if args.capital:
        bot.portfolio.current_capital = args.capital
        bot.portfolio.initial_capital = args.capital
    if args.max_pos:
        bot.portfolio.max_positions = args.max_pos
    if args.interval:
        bot.config['update_interval'] = args.interval
    
    # Start
    bot.start()


if __name__ == '__main__':
    main()
