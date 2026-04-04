/// Error types for the HFT matching engine

use thiserror::Error;

#[derive(Error, Debug)]
pub enum MatchingEngineError {
    #[error("Order not found: {0}")]
    OrderNotFound(u64),

    #[error("Invalid order: {0}")]
    InvalidOrder(String),

    #[error("Insufficient liquidity")]
    InsufficientLiquidity,

    #[error("Price out of bounds")]
    PriceOutOfBounds,

    #[error("Quantity out of bounds")]
    QuantityOutOfBounds,

    #[error("Invalid price level")]
    InvalidPriceLevel,

    #[error("Trader not found: {0}")]
    TraderNotFound(u32),

    #[error("Instrument not found: {0}")]
    InstrumentNotFound(u32),

    #[error("Order book closed")]
    OrderBookClosed,

    #[error("Risk check failed: {0}")]
    RiskCheckFailed(String),

    #[error("Circuit breaker triggered")]
    CircuitBreaker,

    #[error("Trading halted")]
    TradingHalted,

    #[error("Duplicate order ID: {0}")]
    DuplicateOrderId(u64),

    #[error("Invalid order type for operation")]
    InvalidOrderType,

    #[error("Market data feed error: {0}")]
    MarketDataError(String),

    #[error("Network error: {0}")]
    NetworkError(String),

    #[error("Latency simulation error: {0}")]
    LatencyError(String),
}

pub type Result<T> = std::result::Result<T, MatchingEngineError>;
