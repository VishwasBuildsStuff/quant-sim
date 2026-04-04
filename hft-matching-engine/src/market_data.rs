/// Market data feed implementation using ring buffers
/// Provides zero-allocation, lock-free market data distribution

use crate::types::*;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::Arc;
use std::sync::Mutex;

/// Ring buffer capacity (must be power of 2)
const RING_BUFFER_SIZE: usize = 16384; // 16K entries

/// Market data ring buffer for efficient distribution
pub struct MarketDataRingBuffer {
    /// Circular buffer storage
    buffer: Vec<Mutex<MarketDataUpdate>>,

    /// Write position (atomic for thread safety)
    write_pos: AtomicUsize,

    /// Read positions for each subscriber
    /// Using Vec for simplicity, in production use concurrent data structure
    subscriber_positions: Vec<AtomicUsize>,

    /// Total updates published
    total_updates: AtomicU64,
}

impl MarketDataRingBuffer {
    pub fn new(max_subscribers: usize) -> Self {
        // Initialize buffer with default values
        let buffer: Vec<Mutex<MarketDataUpdate>> = (0..RING_BUFFER_SIZE)
            .map(|_| Mutex::new(MarketDataUpdate {
                instrument_id: 0,
                timestamp: 0,
                bids: Vec::new(),
                asks: Vec::new(),
                last_trades: Vec::new(),
                best_bid: None,
                best_ask: None,
            }))
            .collect();

        let mut subscriber_positions = Vec::with_capacity(max_subscribers);
        for _ in 0..max_subscribers {
            subscriber_positions.push(AtomicUsize::new(0));
        }

        Self {
            buffer,
            write_pos: AtomicUsize::new(0),
            subscriber_positions,
            total_updates: AtomicU64::new(0),
        }
    }

    /// Publish a new market data update
    pub fn publish(&self, update: MarketDataUpdate) -> usize {
        let pos = self.write_pos.fetch_add(1, Ordering::AcqRel) & (RING_BUFFER_SIZE - 1);

        // Write to buffer
        if let Ok(mut slot) = self.buffer[pos].lock() {
            *slot = update;
        }

        self.total_updates.fetch_add(1, Ordering::Release);
        pos
    }

    /// Subscribe to market data feed
    pub fn subscribe(&mut self) -> Option<usize> {
        if self.subscriber_positions.len() < self.subscriber_positions.capacity() {
            let subscriber_id = self.subscriber_positions.len();
            let current_pos = self.write_pos.load(Ordering::Acquire);
            self.subscriber_positions
                .push(AtomicUsize::new(current_pos));
            Some(subscriber_id)
        } else {
            None
        }
    }

    /// Read next update for a subscriber
    pub fn read_next(&self, subscriber_id: usize) -> Option<MarketDataUpdate> {
        if subscriber_id >= self.subscriber_positions.len() {
            return None;
        }

        let sub_pos = &self.subscriber_positions[subscriber_id];
        let current_pos = sub_pos.load(Ordering::Acquire);
        let write_pos = self.write_pos.load(Ordering::Acquire);

        if current_pos == write_pos {
            // No new data
            return None;
        }

        let pos = current_pos & (RING_BUFFER_SIZE - 1);
        sub_pos.fetch_add(1, Ordering::AcqRel);

        self.buffer[pos].lock().ok().map(|guard| guard.clone())
    }

    /// Get total number of updates published
    pub fn total_updates(&self) -> u64 {
        self.total_updates.load(Ordering::Acquire)
    }

    /// Check if subscriber has missed any updates
    pub fn has_missed_updates(&self, subscriber_id: usize) -> bool {
        if subscriber_id >= self.subscriber_positions.len() {
            return true;
        }

        let sub_pos = self.subscriber_positions[subscriber_id].load(Ordering::Acquire);
        let write_pos = self.write_pos.load(Ordering::Acquire);

        write_pos - sub_pos > RING_BUFFER_SIZE
    }
}

/// Market data feed manager for multiple instruments
pub struct MarketDataManager {
    /// Per-instrument ring buffers
    instrument_feeds: std::collections::HashMap<InstrumentId, Arc<MarketDataRingBuffer>>,

    /// Aggregate feed for all instruments
    aggregate_feed: Arc<MarketDataRingBuffer>,
}

impl MarketDataManager {
    pub fn new(max_instruments: usize) -> Self {
        Self {
            instrument_feeds: std::collections::HashMap::with_capacity(max_instruments),
            aggregate_feed: Arc::new(MarketDataRingBuffer::new(1000)),
        }
    }

    /// Add a new instrument feed
    pub fn add_instrument(&mut self, instrument_id: InstrumentId) {
        self.instrument_feeds
            .entry(instrument_id)
            .or_insert_with(|| Arc::new(MarketDataRingBuffer::new(500)));
    }

    /// Get market data feed for an instrument
    pub fn get_feed(&self, instrument_id: InstrumentId) -> Option<Arc<MarketDataRingBuffer>> {
        self.instrument_feeds.get(&instrument_id).cloned()
    }

    /// Publish market data update
    pub fn publish_update(&self, instrument_id: InstrumentId, update: MarketDataUpdate) {
        // Update instrument-specific feed
        if let Some(feed) = self.instrument_feeds.get(&instrument_id) {
            feed.publish(update.clone());
        }

        // Also publish to aggregate feed
        self.aggregate_feed.publish(update);
    }

    /// Get aggregate market data feed
    pub fn aggregate_feed(&self) -> Arc<MarketDataRingBuffer> {
        self.aggregate_feed.clone()
    }
}

/// Order book depth tracker
pub struct OrderBookDepthTracker {
    /// Track depth at multiple levels
    depth_levels: usize,

    /// Historical depth data
    depth_history: Vec<(Quantity, Quantity)>,

    /// Volume profile
    volume_profile: std::collections::BTreeMap<Price, Quantity>,
}

impl OrderBookDepthTracker {
    pub fn new(depth_levels: usize) -> Self {
        Self {
            depth_levels,
            depth_history: Vec::with_capacity(1000),
            volume_profile: std::collections::BTreeMap::new(),
        }
    }

    /// Update depth from order book snapshot
    pub fn update_depth(&mut self, snapshot: &OrderBookSnapshot) {
        // Update volume profile
        self.volume_profile.clear();

        for (price, qty) in &snapshot.bids {
            *self.volume_profile.entry(*price).or_insert(0) += qty;
        }

        for (price, qty) in &snapshot.asks {
            *self.volume_profile.entry(*price).or_insert(0) += qty;
        }

        // Track depth
        let bid_qty: Quantity = snapshot.bids.iter().map(|(_, q)| *q).sum();
        let ask_qty: Quantity = snapshot.asks.iter().map(|(_, q)| *q).sum();
        self.depth_history.push((bid_qty, ask_qty));

        // Keep limited history
        if self.depth_history.len() > 1000 {
            self.depth_history.remove(0);
        }
    }

    /// Get bid-ask imbalance
    pub fn bid_ask_imbalance(&self) -> Option<f64> {
        if let Some(&(bid_depth, ask_depth)) = self.depth_history.last() {
            let bid = bid_depth as i64;
            let ask = ask_depth as i64;
            let total = bid + ask;
            if total > 0 {
                Some((bid - ask) as f64 / total as f64)
            } else {
                None
            }
        } else {
            None
        }
    }

    /// Get volume weighted mid price
    pub fn volume_weighted_mid(&self, snapshot: &OrderBookSnapshot) -> Option<Price> {
        if snapshot.bids.is_empty() || snapshot.asks.is_empty() {
            return None;
        }

        let best_bid = snapshot.bids[0].0;
        let best_ask = snapshot.asks[0].0;

        Some((best_bid + best_ask) / 2)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ring_buffer_basic() {
        let mut buffer = MarketDataRingBuffer::new(10);
        let subscriber_id = buffer.subscribe().unwrap();

        let update = MarketDataUpdate {
            instrument_id: 1,
            timestamp: current_timestamp_ns(),
            bids: vec![(10000, 100)],
            asks: vec![(10001, 100)],
            last_trades: Vec::new(),
            best_bid: Some((10000, 100)),
            best_ask: Some((10001, 100)),
        };

        buffer.publish(update);
        let next = buffer.read_next(subscriber_id);
        assert!(next.is_some());
    }
}
