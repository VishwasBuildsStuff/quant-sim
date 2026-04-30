// HFT Matching Engine - Core Library

pub mod types;
pub mod errors;
pub mod order_book;
pub mod market_data;
pub mod network;
pub mod latency;

pub use types::*;
pub use errors::*;

use pyo3::prelude::*;
use pyo3::types::PyDict;

#[pyclass]
pub struct EngineWrapper {
    order_books: std::collections::HashMap<String, order_book::OrderBook>,
    next_order_id: u64,
}

#[pymethods]
impl EngineWrapper {
    #[new]
    fn new() -> Self {
        Self {
            order_books: std::collections::HashMap::new(),
            next_order_id: 1,
        }
    }

    fn add_instrument(&mut self, symbol: &str) {
        let instrument = Instrument {
            instrument_id: self.order_books.len() as u32 + 1,
            symbol: symbol.to_string(),
            asset_class: AssetClass::Equity,
            tick_size: 1, // in cents/paisa depending on currency
            lot_size: 1,
            currency: "INR".to_string(),
            exchange: "NSE".to_string(),
        };
        self.order_books.insert(symbol.to_string(), order_book::OrderBook::new(instrument));
    }

    fn add_order(&mut self, symbol: &str, side_str: &str, price: i64, qty: u64, agent_id: u32) -> PyResult<u64> {
        let side = if side_str.to_uppercase() == "BUY" { Side::Buy } else { Side::Sell };
        
        let orderbook = match self.order_books.get_mut(symbol) {
            Some(ob) => ob,
            None => return Err(pyo3::exceptions::PyValueError::new_err("Instrument not found")),
        };
        
        let order = Order::new(
            self.next_order_id,
            agent_id,
            orderbook.instrument_id,
            side,
            OrderType::Limit,
            price,
            qty,
            TimeInForce::GTC,
        );
        
        let id = self.next_order_id;
        self.next_order_id += 1;
        
        let _trades = orderbook.add_order(order).unwrap_or_default();
        Ok(id)
    }

    fn get_snapshot<'py>(&self, py: Python<'py>, symbol: &str, depth: usize) -> PyResult<Bound<'py, PyDict>> {
        let orderbook = match self.order_books.get(symbol) {
            Some(ob) => ob,
            None => return Err(pyo3::exceptions::PyValueError::new_err("Instrument not found")),
        };
        
        let snapshot = orderbook.snapshot(depth);
        
        let dict = PyDict::new_bound(py);
        
        let bids: Vec<(i64, u64)> = snapshot.bids.clone();
        let asks: Vec<(i64, u64)> = snapshot.asks.clone();
        
        dict.set_item("symbol", symbol)?;
        dict.set_item("bids", bids)?;
        dict.set_item("asks", asks)?;
        dict.set_item("last_trade_price", snapshot.last_trade_price)?;
        dict.set_item("volume", snapshot.volume)?;
        
        Ok(dict)
    }
}

#[pymodule]
fn hft_matching_engine(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<EngineWrapper>()?;
    Ok(())
}
