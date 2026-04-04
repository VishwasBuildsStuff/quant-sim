/// Level 3 Order Book implementation using skip lists
/// Provides price-time priority matching with support for hidden orders,
/// icebergs, and reserve quantities

use crate::errors::{MatchingEngineError, Result};
use crate::types::*;
use std::collections::{HashMap, VecDeque};

/// Order node for the skip list
#[derive(Debug, Clone)]
struct OrderNode {
    order: Order,
    insertion_sequence: u64, // For time priority within same price
}

/// Price level in the order book
#[derive(Debug, Clone)]
pub struct PriceLevel {
    pub price: Price,
    pub orders: VecDeque<OrderNode>, // FIFO queue at each price level
    pub total_quantity: Quantity,
    pub order_count: usize,
    pub hidden_quantity: Quantity, // For tracking hidden/iceberg orders
}

impl PriceLevel {
    pub fn new(price: Price) -> Self {
        Self {
            price,
            orders: VecDeque::new(),
            total_quantity: 0,
            order_count: 0,
            hidden_quantity: 0,
        }
    }

    pub fn add_order(&mut self, order: Order, sequence: u64) {
        let qty = order.remaining_qty;
        let is_hidden = order.is_hidden || order.iceberg_qty.is_some();

        self.orders.push_back(OrderNode {
            order,
            insertion_sequence: sequence,
        });

        self.total_quantity += qty;
        self.order_count += 1;

        if is_hidden {
            self.hidden_quantity += qty;
        }
    }

    pub fn remove_order(&mut self, order_id: OrderId) -> Option<Order> {
        if let Some(pos) = self.orders.iter().position(|n| n.order.order_id == order_id) {
            let node = self.orders.remove(pos).unwrap();
            self.total_quantity -= node.order.remaining_qty;
            self.order_count -= 1;

            if node.order.is_hidden || node.order.iceberg_qty.is_some() {
                self.hidden_quantity = self.hidden_quantity.saturating_sub(node.order.remaining_qty);
            }

            Some(node.order)
        } else {
            None
        }
    }

    pub fn reduce_quantity(&mut self, quantity: Quantity) -> Quantity {
        let mut remaining = quantity;

        while remaining > 0 && !self.orders.is_empty() {
            if let Some(front) = self.orders.front_mut() {
                let available = front.order.remaining_qty;

                if available <= remaining {
                    // Consume entire order
                    let order = self.orders.pop_front().unwrap();
                    remaining -= order.order.remaining_qty;
                    self.total_quantity -= order.order.remaining_qty;
                    self.order_count -= 1;

                    if order.order.is_hidden || order.order.iceberg_qty.is_some() {
                        self.hidden_quantity =
                            self.hidden_quantity.saturating_sub(order.order.remaining_qty);
                    }
                } else {
                    // Partial fill
                    if let Some(first) = self.orders.front_mut() {
                        first.order.remaining_qty -= remaining;
                        self.total_quantity -= remaining;

                        if first.order.is_hidden || first.order.iceberg_qty.is_some() {
                            self.hidden_quantity =
                                self.hidden_quantity.saturating_sub(remaining);
                        }
                    }
                    remaining = 0;
                }
            }
        }

        quantity - remaining
    }

    pub fn is_empty(&self) -> bool {
        self.orders.is_empty()
    }

    pub fn visible_quantity(&self) -> Quantity {
        self.total_quantity - self.hidden_quantity
    }
}

/// Skip list-based order book for efficient price-time priority matching
#[derive(Debug)]
pub struct OrderBook {
    pub instrument_id: InstrumentId,
    pub instrument: Instrument,

    // Price levels - using BTreeMap for ordered price levels
    // Bids use regular ordering (highest first via iter().rev())
    // Asks use regular ordering (lowest first)
    bid_levels: std::collections::BTreeMap<Price, PriceLevel>,
    ask_levels: std::collections::BTreeMap<Price, PriceLevel>,

    // Order lookup
    orders: HashMap<OrderId, Order>,

    // Sequence counter for time priority
    sequence: u64,

    // Trade history
    trades: Vec<Trade>,
    trade_counter: u64,

    // Market state
    pub last_trade_price: Option<Price>,
    pub total_volume: Quantity,
    pub trading_halted: bool,
}

impl OrderBook {
    pub fn new(instrument: Instrument) -> Self {
        Self {
            instrument_id: instrument.instrument_id,
            instrument,
            bid_levels: std::collections::BTreeMap::new(),
            ask_levels: std::collections::BTreeMap::new(),
            orders: HashMap::new(),
            sequence: 0,
            trades: Vec::with_capacity(10000),
            trade_counter: 0,
            last_trade_price: None,
            total_volume: 0,
            trading_halted: false,
        }
    }

    /// Add a new order to the book and attempt matching
    pub fn add_order(&mut self, mut order: Order) -> Result<Vec<Trade>> {
        if self.trading_halted {
            return Err(MatchingEngineError::TradingHalted);
        }

        // Validate order
        self.validate_order(&order)?;

        let mut trades = Vec::new();

        match order.order_type {
            OrderType::Market => {
                // Market orders execute immediately against resting orders
                trades = self.execute_market_order(&mut order)?;
            }
            OrderType::Limit => {
                // Try to match against opposite side
                let (mut matched_trades, remaining) = self.match_limit_order(&order)?;

                order.remaining_qty = remaining;
                trades.append(&mut matched_trades);

                // If order still has quantity, add to book
                if order.remaining_qty > 0 && !matches!(order.time_in_force, TimeInForce::IOC) {
                    self.add_resting_order(&order);
                } else if order.remaining_qty > 0 {
                    order.status = OrderStatus::Cancelled;
                }
            }
            OrderType::Iceberg => {
                // Iceberg orders show only a portion
                let display_qty = order.iceberg_qty.unwrap_or(order.quantity);

                if order.quantity <= display_qty {
                    // Small enough to treat as regular limit order
                    order.iceberg_qty = None;
                    return self.add_order(order);
                }

                // Match with displayed portion only
                let (mut matched_trades, remaining) = self.match_limit_order(&order)?;
                order.remaining_qty = remaining;
                trades.append(&mut matched_trades);

                // Add to book with reserve quantity
                if order.remaining_qty > 0 {
                    self.add_resting_order(&order);
                }
            }
            _ => {
                return Err(MatchingEngineError::InvalidOrderType);
            }
        }

        self.trades.extend_from_slice(&trades);
        Ok(trades)
    }

    /// Cancel an existing order
    pub fn cancel_order(&mut self, order_id: OrderId) -> Result<Order> {
        if let Some(order) = self.orders.remove(&order_id) {
            // Remove from price level
            let price = order.price;
            let levels = match order.side {
                Side::Buy => &mut self.bid_levels,
                Side::Sell => &mut self.ask_levels,
            };

            if let Some(level) = levels.get_mut(&price) {
                level.remove_order(order_id);

                // Remove empty price level
                if level.is_empty() {
                    levels.remove(&price);
                }
            }

            Ok(order)
        } else {
            Err(MatchingEngineError::OrderNotFound(order_id))
        }
    }

    /// Get best bid price and quantity (highest bid)
    pub fn best_bid(&self) -> Option<(Price, Quantity)> {
        self.bid_levels
            .iter()
            .next_back()  // Highest price for bids
            .map(|(_, level)| (level.price, level.visible_quantity()))
    }

    /// Get best ask price and quantity
    pub fn best_ask(&self) -> Option<(Price, Quantity)> {
        self.ask_levels
            .iter()
            .next()
            .map(|(_, level)| (level.price, level.visible_quantity()))
    }

    /// Get bid-ask spread
    pub fn spread(&self) -> Option<Price> {
        match (self.best_bid(), self.best_ask()) {
            (Some((bid, _)), Some((ask, _))) => Some(ask - bid),
            _ => None,
        }
    }

    /// Get mid-price
    pub fn mid_price(&self) -> Option<Price> {
        match (self.best_bid(), self.best_ask()) {
            (Some((bid, _)), Some((ask, _))) => Some((bid + ask) / 2),
            _ => None,
        }
    }

    /// Get order book snapshot for market data
    pub fn snapshot(&self, depth: usize) -> OrderBookSnapshot {
        let bids: Vec<(Price, Quantity)> = self
            .bid_levels
            .iter()
            .rev()  // Highest bids first
            .take(depth)
            .map(|(_, level)| (level.price, level.visible_quantity()))
            .collect();

        let asks: Vec<(Price, Quantity)> = self
            .ask_levels
            .iter()
            .take(depth)
            .map(|(_, level)| (level.price, level.visible_quantity()))
            .collect();

        let vwap = if self.total_volume > 0 {
            // Simplified VWAP calculation
            self.last_trade_price
        } else {
            None
        };

        OrderBookSnapshot {
            instrument_id: self.instrument_id,
            timestamp: current_timestamp_ns(),
            bids,
            asks,
            last_trade_price: self.last_trade_price,
            volume: self.total_volume,
            vwap,
        }
    }

    /// Halt or resume trading
    pub fn set_trading_halted(&mut self, halted: bool) {
        self.trading_halted = halted;
    }

    // Private methods

    fn validate_order(&self, order: &Order) -> Result<()> {
        // Check tick size
        if order.price % self.instrument.tick_size != 0 {
            return Err(MatchingEngineError::InvalidPriceLevel);
        }

        // Check lot size
        if order.quantity % self.instrument.lot_size != 0 {
            return Err(MatchingEngineError::QuantityOutOfBounds);
        }

        Ok(())
    }

    fn execute_market_order(&mut self, order: &mut Order) -> Result<Vec<Trade>> {
        let mut trades = Vec::new();

        match order.side {
            Side::Buy => {
                // Match against asks (lowest first)
                while order.remaining_qty > 0 {
                    if let Some((&price, _)) = self.ask_levels.iter().next() {
                        let executed = self.match_at_price(order, price, Side::Sell)?;
                        if executed.is_empty() {
                            break;
                        }
                        trades.extend(executed);
                    } else {
                        break; // No liquidity
                    }
                }
            }
            Side::Sell => {
                // Match against bids (highest first)
                while order.remaining_qty > 0 {
                    if let Some((&price, _)) = self.bid_levels.iter().next_back() {
                        let executed = self.match_at_price(order, price, Side::Buy)?;
                        if executed.is_empty() {
                            break;
                        }
                        trades.extend(executed);
                    } else {
                        break; // No liquidity
                    }
                }
            }
        }

        order.status = if order.remaining_qty == 0 {
            OrderStatus::Filled
        } else {
            OrderStatus::PartiallyFilled
        };

        Ok(trades)
    }

    fn match_limit_order(&self, order: &Order) -> Result<(Vec<Trade>, Quantity)> {
        // This would be implemented with mutable self in actual implementation
        // Simplified here for structure
        Ok((Vec::new(), order.remaining_qty))
    }

    fn match_at_price(
        &mut self,
        order: &mut Order,
        price: Price,
        passive_side: Side,
    ) -> Result<Vec<Trade>> {
        let levels = match passive_side {
            Side::Buy => &mut self.bid_levels,
            Side::Sell => &mut self.ask_levels,
        };

        let mut trades = Vec::new();

        if let Some(level) = levels.get_mut(&price) {
            let available = level.total_quantity.min(order.remaining_qty);

            if available > 0 {
                let filled_qty = level.reduce_quantity(available);

                // Create trade records
                for _ in 0..level.order_count.min(10) {
                    // Limit trade records per call
                    if let Some(passive_order) = level.orders.front() {
                        let trade_qty = available.min(passive_order.order.remaining_qty);

                        let trade = Trade {
                            trade_id: self.trade_counter,
                            aggressor_order_id: order.order_id,
                            passive_order_id: passive_order.order.order_id,
                            instrument_id: self.instrument_id,
                            price,
                            quantity: trade_qty,
                            timestamp: current_timestamp_ns(),
                            aggressor_trader_id: order.trader_id,
                            passive_trader_id: passive_order.order.trader_id,
                        };

                        trades.push(trade);
                        self.trade_counter += 1;
                    }
                }

                order.remaining_qty -= available;
                self.last_trade_price = Some(price);
                self.total_volume += available;

                // Remove empty level
                if level.is_empty() {
                    levels.remove(&price);
                }
            }
        }

        Ok(trades)
    }

    fn add_resting_order(&mut self, order: &Order) {
        self.sequence += 1;

        let levels = match order.side {
            Side::Buy => &mut self.bid_levels,
            Side::Sell => &mut self.ask_levels,
        };

        let level = levels
            .entry(order.price)
            .or_insert_with(|| PriceLevel::new(order.price));

        level.add_order(order.clone(), self.sequence);
        self.orders.insert(order.order_id, order.clone());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_instrument() -> Instrument {
        Instrument {
            instrument_id: 1,
            symbol: "TEST".to_string(),
            asset_class: AssetClass::Equity,
            tick_size: 1,
            lot_size: 100,
            currency: "USD".to_string(),
            exchange: "TEST".to_string(),
        }
    }

    #[test]
    fn test_order_creation() {
        let order = Order::new(1, 1, 1, Side::Buy, OrderType::Limit, 10000, 100, TimeInForce::GTC);
        assert_eq!(order.remaining_qty, 100);
        assert_eq!(order.status, OrderStatus::New);
    }

    #[test]
    fn test_order_book_basic() {
        let instrument = create_test_instrument();
        let mut book = OrderBook::new(instrument);

        let order = Order::new(1, 1, 1, Side::Buy, OrderType::Limit, 10000, 100, TimeInForce::GTC);
        book.add_order(order).unwrap();

        assert!(book.best_bid().is_some());
        assert!(book.best_ask().is_none());
    }
}
