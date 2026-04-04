# HFT Simulation Platform - System Architecture

## Overview
Institutional-grade High-Frequency Trading simulation platform with hybrid architecture:
- **Core Engine**: Rust (memory-safe, zero-cost abstractions, nanosecond latency)
- **Strategy/Analytics**: Python (flexibility, data science ecosystem)
- **Communication**: ZeroMQ/Redis for inter-process messaging

## Repository Structure

```
quant_project/
├── hft-matching-engine/        # Rust core matching engine
│   ├── src/
│   │   ├── order_book/         # Level 3 order book implementation
│   │   ├── matching/           # Price-time priority matching
│   │   ├── market_data/        # Market data feeds (ring buffers)
│   │   ├── network/            # FIX protocol simulation
│   │   └── latency/            # Network latency simulation
│   └── Cargo.toml
│
├── hft-strategies/             # Python strategy layer
│   ├── agents/                 # Trader agent implementations
│   │   ├── retail/             # Behavioral finance models
│   │   ├── semi_pro/           # Technical indicator strategies
│   │   ├── institutional/      # TWAP, VWAP, IS algorithms
│   │   └── hft/                # Market making, arbitrage
│   ├── indicators/             # Technical analysis library
│   └── risk/                   # Risk management
│
├── hft-analytics/              # Python analytics engine
│   ├── metrics/                # Performance metrics
│   ├── attribution/            # PnL attribution
│   └── reporting/              # Simulation reports
│
├── hft-simulation/             # Simulation orchestrator
│   ├── scenarios/              # Historical stress scenarios
│   ├── market_regime/          # Market regime simulation
│   └── macro/                  # Macro-economic events
│
├── hft-dashboard/              # Visualization interface
│   ├── frontend/               # React dashboard
│   └── backend/                # Python API server
│
└── docs/                       # Documentation
```

## Core Components

### 1. Matching Engine (Rust)
- **Order Book**: Skip list-based Level 3 order book
- **Matching**: Price-time priority with hidden order support
- **Latency**: Sub-microsecond order processing
- **Throughput**: ≥100,000 orders/second

### 2. Market Simulation (Python/Rust FFI)
- **Price Formation**: GBM, Jump Diffusion, GARCH models
- **Multi-Asset**: Equities, FX, Crypto, Commodities
- **Liquidity**: Fragmented across simulated exchanges
- **Regimes**: Bull, Bear, Sideways, High-Frequency Noise, Black Swan

### 3. Agent Framework (Python)
- **Retail**: Prospect Theory, emotional bias, delayed data
- **Semi-Pro**: Technical indicators, moderate risk
- **Institutional**: Execution algorithms, market impact models
- **HFT**: Market making, latency/stat-arb, co-location simulation

### 4. Risk & Compliance (Python)
- **Pre-Trade**: Position limits, capital checks, fat-finger prevention
- **Post-Trade**: VaR, stress testing, PnL analysis
- **Regulatory**: Spoofing/wash trading detection (SEC, MiFID II)
- **Circuit Breakers**: Volatility halts, limit up/limit down

### 5. Analytics (Python)
- **Metrics**: Sharpe, Sortino, Calmar, Max Drawdown, VaR
- **Attribution**: PnL decomposition, execution slippage
- **Backtesting**: Event-driven, walk-forward analysis

### 6. Dashboard (React + Python)
- **Real-Time**: Order book depth, equity curves, position tracking
- **Historical**: Heatmaps, performance charts, regime analysis
- **Monitoring**: System throughput, latency distribution

## Communication Protocol
- **Engine ↔ Agents**: ZeroMQ for low-latency messaging
- **Market Data**: Ring buffers with lock-free publishing
- **FIX Protocol**: Emulated for order entry/market data

## Performance Targets
- Order matching: <1μs latency
- System throughput: ≥100,000 orders/sec
- Market data updates: <100μs propagation
- Simulation speed: ≥100x real-time

## Data Structures
- **Order Book**: Skip lists for O(log n) operations
- **Market Data**: Ring buffers (zero-allocation)
- **Priority Queues**: Binary heaps for order matching
- **Time Series**: Columnar storage for analytics
