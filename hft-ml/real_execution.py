"""
HFT Execution Wrapper
Defaults to Paper Trading (DRY RUN) for 3-month testing phase.
"""

from datetime import datetime

class BrokerAPI:
    """
    Paper Trading Broker API (DRY RUN).
    To switch to Live: Change self.dry_run = False and add API keys.
    """
    
    def __init__(self, dry_run=True):
        self.dry_run = dry_run

    def place_order(self, symbol, qty, price, side, order_type='LIMIT'):
        """
        Execute order (Simulated for Paper Trading)
        """
        if self.dry_run:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[📝 PAPER TRADE] {timestamp} | {side} {qty} {symbol} @ ₹{price}")
            return {'success': True, 'order_id': f'PAPER_{timestamp.replace(":","")}'}
        
        # This section is only reached if dry_run=False
        try:
            # TODO: Add your Broker API (Zerodha/Upstox) here later
            # order_id = broker.place_order(...)
            return {'success': False, 'error': 'Live trading not yet configured'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
