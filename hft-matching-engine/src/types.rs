/// Core types for the HFT matching engine

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::fmt;

/// Unique identifier for orders
pub type OrderId = u64;

/// Unique identifier for traders/agents
pub type TraderId = u32;

/// Unique identifier for instruments
pub type InstrumentId = u32;

/// Price type (fixed-point for precision)
pub type Price = i64;

/// Quantity type
pub type Quantity = u64;

/// Timestamp in nanoseconds
pub type Timestamp = u64;

/// Side of the market
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Side {
    Buy,
    Sell,
}

impl fmt::Display for Side {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Side::Buy => write!(f, "BUY"),
            Side::Sell => write!(f, "SELL"),
        }
    }
}

/// Order type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OrderType {
    Market,
    Limit,
    StopLoss,
    StopLimit,
    Iceberg,
    Hidden,
}

/// Time in force
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TimeInForce {
    GTC, // Good Till Cancel
    IOC, // Immediate Or Cancel
    FOK, // Fill Or Kill
    GTD, // Good Till Date
    Day,
}

/// Order status
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OrderStatus {
    New,
    PartiallyFilled,
    Filled,
    Cancelled,
    Rejected,
    Expired,
}

/// Asset class
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AssetClass {
    Equity,
    FX,
    Commodity,
    Cryptocurrency,
    FixedIncome,
}

/// Market regime
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MarketRegime {
    Bull,
    Bear,
    Sideways,
    HighFrequencyNoise,
    BlackSwan,
}

/// Order representation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Order {
    pub order_id: OrderId,
    pub trader_id: TraderId,
    pub instrument_id: InstrumentId,
    pub side: Side,
    pub order_type: OrderType,
    pub price: Price,
    pub quantity: Quantity,
    pub remaining_qty: Quantity,
    pub time_in_force: TimeInForce,
    pub status: OrderStatus,
    pub timestamp: Timestamp,
    pub is_hidden: bool,
    pub iceberg_qty: Option<Quantity>, // For iceberg orders
    pub min_qty: Option<Quantity>,     // Minimum quantity for FOK
}

impl Order {
    pub fn new(
        order_id: OrderId,
        trader_id: TraderId,
        instrument_id: InstrumentId,
        side: Side,
        order_type: OrderType,
        price: Price,
        quantity: Quantity,
        time_in_force: TimeInForce,
    ) -> Self {
        Self {
            order_id,
            trader_id,
            instrument_id,
            side,
            order_type,
            price,
            quantity,
            remaining_qty: quantity,
            time_in_force,
            status: OrderStatus::New,
            timestamp: current_timestamp_ns(),
            is_hidden: false,
            iceberg_qty: None,
            min_qty: None,
        }
    }

    pub fn with_hidden(mut self, is_hidden: bool) -> Self {
        self.is_hidden = is_hidden;
        self
    }

    pub fn with_iceberg(mut self, display_qty: Quantity) -> Self {
        self.iceberg_qty = Some(display_qty);
        self
    }
}

/// Trade/execution representation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Trade {
    pub trade_id: u64,
    pub aggressor_order_id: OrderId,
    pub passive_order_id: OrderId,
    pub instrument_id: InstrumentId,
    pub price: Price,
    pub quantity: Quantity,
    pub timestamp: Timestamp,
    pub aggressor_trader_id: TraderId,
    pub passive_trader_id: TraderId,
}

/// Market data update
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketDataUpdate {
    pub instrument_id: InstrumentId,
    pub timestamp: Timestamp,
    pub bids: Vec<(Price, Quantity)>, // Price levels
    pub asks: Vec<(Price, Quantity)>,
    pub last_trades: Vec<Trade>,
    pub best_bid: Option<(Price, Quantity)>,
    pub best_ask: Option<(Price, Quantity)>,
}

/// Order book snapshot
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderBookSnapshot {
    pub instrument_id: InstrumentId,
    pub timestamp: Timestamp,
    pub bids: Vec<(Price, Quantity)>,
    pub asks: Vec<(Price, Quantity)>,
    pub last_trade_price: Option<Price>,
    pub volume: Quantity,
    pub vwap: Option<Price>,
}

/// Instrument definition
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Instrument {
    pub instrument_id: InstrumentId,
    pub symbol: String,
    pub asset_class: AssetClass,
    pub tick_size: Price,
    pub lot_size: Quantity,
    pub currency: String,
    pub exchange: String,
}

/// Get current timestamp in nanoseconds
pub fn current_timestamp_ns() -> Timestamp {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos() as u64
}

/// Message types for FIX protocol simulation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FIXMessage {
    NewOrderSingle(Order),
    OrderCancelRequest {
        order_id: OrderId,
        trader_id: TraderId,
    },
    OrderCancelReject {
        order_id: OrderId,
        reason: String,
    },
    OrderCancelAck {
        order_id: OrderId,
    },
    ExecutionReport {
        order_id: OrderId,
        status: OrderStatus,
        filled_qty: Quantity,
        avg_px: Option<Price>,
        last_qty: Option<Quantity>,
        last_px: Option<Price>,
    },
    MarketData(MarketDataUpdate),
    Heartbeat,
}
