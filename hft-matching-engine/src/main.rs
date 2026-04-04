/// HFT Matching Engine - Main executable
/// High-performance order matching with latency simulation

use hft_matching_engine::*;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

fn main() {
    println!("Starting HFT Matching Engine...");

    // Initialize tracing
    tracing_subscriber::fmt::init();

    // Create test instrument
    let instrument = Instrument {
        instrument_id: 1,
        symbol: "AAPL".to_string(),
        asset_class: AssetClass::Equity,
        tick_size: 1,
        lot_size: 100,
        currency: "USD".to_string(),
        exchange: "NASDAQ".to_string(),
    };

    // Create order book
    let mut order_book = order_book::OrderBook::new(instrument.clone());
    println!("Created order book for {}", instrument.symbol);

    // Create market data manager
    let mut market_data = market_data::MarketDataManager::new(100);
    market_data.add_instrument(instrument.instrument_id);

    // Create latency simulator
    let mut latency_sim = latency::LatencySimulator::new();
    latency_sim.register_agent(1, latency::LatencyProfile::hft_profile());
    latency_sim.register_agent(2, latency::LatencyProfile::institutional_profile());
    latency_sim.register_agent(3, latency::LatencyProfile::retail_profile());

    // Simulate some orders
    println!("\n=== Simulating Order Flow ===");

    // Add some liquidity (market makers)
    for i in 1..=5 {
        let bid_order = Order::new(
            i,
            1, // HFT agent
            instrument.instrument_id,
            Side::Buy,
            OrderType::Limit,
            15000 - (i as Price), // $150.00 - decrementing
            100,
            TimeInForce::GTC,
        );

        match order_book.add_order(bid_order) {
            Ok(trades) => {
                if !trades.is_empty() {
                    println!("Bid {} resulted in {} trades", i, trades.len());
                }
            }
            Err(e) => eprintln!("Error adding bid: {}", e),
        }
    }

    for i in 6..=10 {
        let ask_order = Order::new(
            i,
            1, // HFT agent
            instrument.instrument_id,
            Side::Sell,
            OrderType::Limit,
            15000 + ((i - 5) as Price), // $150.00 + incrementing
            100,
            TimeInForce::GTC,
        );

        match order_book.add_order(ask_order) {
            Ok(trades) => {
                if !trades.is_empty() {
                    println!("Ask {} resulted in {} trades", i, trades.len());
                }
            }
            Err(e) => eprintln!("Error adding ask: {}", e),
        }
    }

    // Print order book snapshot
    println!("\n=== Order Book Snapshot ===");
    let snapshot = order_book.snapshot(5);
    println!("Best Bid: {:?}", order_book.best_bid());
    println!("Best Ask: {:?}", order_book.best_ask());
    println!("Spread: {:?}", order_book.spread());
    println!("Mid Price: {:?}", order_book.mid_price());

    // Simulate aggressive buy order
    println!("\n=== Simulating Market Order ===");
    let market_order = Order::new(
        100,
        3, // Retail agent (high latency)
        instrument.instrument_id,
        Side::Buy,
        OrderType::Market,
        0, // Market orders don't specify price
        200,
        TimeInForce::IOC,
    );

    match order_book.add_order(market_order) {
        Ok(trades) => {
            println!("Market order executed {} trades", trades.len());
            for trade in &trades {
                println!(
                    "  Trade: {} @ ${:.2}",
                    trade.quantity,
                    trade.price as f64 / 100.0
                );
            }
        }
        Err(e) => eprintln!("Market order error: {}", e),
    }

    // Print updated snapshot
    let snapshot = order_book.snapshot(5);
    println!("\n=== Updated Order Book ===");
    println!("Last Trade: ${:.2}", snapshot.last_trade_price.unwrap_or(0) as f64 / 100.0);
    println!("Total Volume: {}", snapshot.volume);

    // Simulate latency
    println!("\n=== Latency Simulation ===");
    for agent_id in &[1, 2, 3] {
        if let Some(latency) = latency_sim.simulate_agent_latency(*agent_id) {
            println!(
                "Agent {} latency: {:.2} μs",
                agent_id, latency
            );
        }
    }

    let stats = latency_sim.latency_stats();
    println!("\nLatency Statistics:");
    println!("  Mean: {:.2} μs", stats.mean);
    println!("  P50: {:.2} μs", stats.p50);
    println!("  P95: {:.2} μs", stats.p95);
    println!("  P99: {:.2} μs", stats.p99);

    println!("\nHFT Matching Engine simulation complete!");
}
