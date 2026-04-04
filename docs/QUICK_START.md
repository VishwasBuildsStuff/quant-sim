# Quick Start Guide - HFT Simulation Platform

## Prerequisites

### Required Software
- **Rust**: 1.75 or later (install from https://rustup.rs/)
- **Python**: 3.10 or later
- **Git**: For version control

### Installation

#### 1. Rust Matching Engine

```bash
# Navigate to matching engine directory
cd V:\quant_project\hft-matching-engine

# Build in release mode (optimized)
cargo build --release

# Run the example
cargo run --release

# Run tests
cargo test

# Run benchmarks (optional)
cargo bench
```

#### 2. Python Simulation & Strategies

```bash
# Navigate to project root
cd V:\quant_project

# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install simulation dependencies
cd hft-simulation
pip install -r requirements.txt

# Install strategies dependencies (if different)
cd ../hft-strategies
pip install -r requirements.txt  # if exists

# Run demo simulation
cd hft-simulation
python examples/demo_simulation.py
```

---

## Quick Examples

### Example 1: Basic Order Book Usage (Rust)

```rust
use hft_matching_engine::*;

fn main() {
    // Create instrument
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
    let mut book = OrderBook::new(instrument);
    
    // Add liquidity (market maker)
    let bid = Order::new(
        1, 1, 1,
        Side::Buy,
        OrderType::Limit,
        15000,  // $150.00
        100,
        TimeInForce::GTC
    );
    book.add_order(bid).unwrap();
    
    // Add ask
    let ask = Order::new(
        2, 1, 1,
        Side::Sell,
        OrderType::Limit,
        15010,  // $150.10
        100,
        TimeInForce::GTC
    );
    book.add_order(ask).unwrap();
    
    // Execute market order
    let market_order = Order::new(
        3, 2, 1,
        Side::Buy,
        OrderType::Market,
        0,
        100,
        TimeInForce::IOC
    );
    
    let trades = book.add_order(market_order).unwrap();
    println!("Executed {} trades", trades.len());
    
    // Get order book snapshot
    let snapshot = book.snapshot(5);
    println!("Best bid: {:?}", snapshot.best_bid());
    println!("Best ask: {:?}", snapshot.best_ask());
}
```

### Example 2: Market Simulation (Python)

```python
from datetime import datetime
from hft_simulation import (
    MarketSimulationEngine,
    SimulationConfig,
    HistoricalScenarioLibrary
)

# Simple simulation
config = SimulationConfig(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 3, 31),
    asset_names=["SPY", "QQQ"],
    process_type="jump_diffusion",
    initial_prices={"SPY": 450.0, "QQQ": 380.0},
    seed=42
)

engine = MarketSimulationEngine(config)
output = engine.simulate(n_steps=1000)

# Access results
print(f"Generated {len(output.prices)} asset paths")
print(f"SPY final price: ${output.prices['SPY'][-1]:.2f}")
print(f"QQQ final price: ${output.prices['QQQ'][-1]:.2f}")

# With historical scenario
output = engine.simulate_with_scenario("flash_crash_2010", n_steps=500)
print(f"Flash crash max drawdown: {output.config.historical_scenario.max_drawdown:.2%}")
```

### Example 3: Creating Trading Agents (Python)

```python
from hft_strategies import (
    RetailTraderAgent,
    SemiProfessionalTraderAgent,
    HFTMarketMakerAgent,
    InstitutionalTraderAgent
)

# Retail trader
retail = RetailTraderAgent(
    agent_id="retail_001",
    initial_capital=100_000.0,
    loss_aversion_coefficient=2.0
)

# HFT Market Maker
mm = HFTMarketMakerAgent(
    agent_id="hft_mm_001",
    initial_capital=10_000_000.0,
    target_spread=0.02
)

# Institutional VWAP trader
inst = InstitutionalTraderAgent(
    agent_id="inst_001",
    initial_capital=100_000_000.0,
    execution_strategy="vwap"
)

# Simulate market data
market_data = {
    'price': 450.50,
    'high': 451.00,
    'low': 450.00,
    'volume': 1000000
}

mm.on_market_data("SPY", market_data)
retail.on_market_data("SPY", market_data)

# Generate orders
mm_orders = mm.generate_orders()
retail_orders = retail.generate_orders()

print(f"Market maker generated {len(mm_orders)} orders")
print(f"Retail trader generated {len(retail_orders)} orders")
```

### Example 4: Risk Management (Python)

```python
from hft_strategies.risk_management import (
    PreTradeRiskEngine,
    RiskLimits,
    CircuitBreaker
)

# Configure risk limits
limits = RiskLimits(
    max_position_size=1_000_000.0,
    max_order_size=100_000.0,
    max_daily_loss=50_000.0
)

risk_engine = PreTradeRiskEngine(limits)

# Check order before submission
passed, reason = risk_engine.check_order(
    instrument="SPY",
    side="buy",
    quantity=1000,
    price=450.0,
    order_type="limit",
    current_market_price=449.50,
    available_capital=500_000.0
)

if passed:
    print("Order approved")
else:
    print(f"Order rejected: {reason}")

# Circuit breaker
circuit_breaker = CircuitBreaker(
    level1_pct=0.05,
    level2_pct=0.10,
    level3_pct=0.20
)

halted, reason = circuit_breaker.check_price_move(470.0)
if halted:
    print(f"Trading halted: {reason}")
```

### Example 5: Performance Analytics (Python)

```python
from hft_analytics.performance_analytics import (
    AnalyticsEngine,
    TradeRecord
)
from datetime import datetime

# Initialize analytics
analytics = AnalyticsEngine(initial_capital=1_000_000.0)

# Record some trades
trades = [
    TradeRecord("T1", "agent_001", "SPY", "buy", 100, 450.0, 1.0, datetime.now(), pnl=50.0),
    TradeRecord("T2", "agent_001", "SPY", "sell", 100, 451.0, 1.0, datetime.now(), pnl=100.0),
    TradeRecord("T3", "agent_001", "SPY", "buy", 100, 452.0, 1.0, datetime.now(), pnl=-200.0),
]

for trade in trades:
    analytics.record_trade(trade)

# Generate report
report = analytics.generate_report()

print(f"Total Trades: {report['performance']['total_trades']}")
print(f"Win Rate: {report['performance']['win_rate']:.2%}")
print(f"Sharpe Ratio: {report['performance']['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {report['performance']['max_drawdown']:.2%}")
print(f"Profit Factor: {report['performance']['profit_factor']:.2f}")
```

---

## Running the Demo

The demo script showcases all major features:

```bash
cd V:\quant_project\hft-simulation
python examples/demo_simulation.py
```

This will generate:
- `stochastic_processes.png` - Comparison of price processes
- `market_regimes.png` - Different market regimes
- `historical_scenarios.png` - Historical stress scenarios
- `complete_simulation.png` - Full simulation results
- `flash_crash_analysis.png` - Deep dive into 2010 Flash Crash

---

## Next Steps

### 1. Explore the Code
- Read `docs/PROJECT_DOCUMENTATION.md` for full details
- Check out example scripts in `hft-simulation/examples/`
- Review test files in each module

### 2. Customize Strategies
- Create your own trading agent by extending `BaseAgent`
- Implement custom technical indicators
- Add new historical scenarios

### 3. Run Simulations
- Test different market regimes
- Compare agent performance
- Analyze behavior during stress scenarios

### 4. Extend the Platform
- Add new asset classes (FX, Crypto, Commodities)
- Implement additional HFT strategies
- Create visualization dashboard
- Build backtesting engine

---

## Troubleshooting

### Rust Build Errors

**Error: Package not found**
```bash
# Make sure you're in the correct directory
cd V:\quant_project\hft-matching-engine
cargo build
```

**Error: Dependency compilation failed**
```bash
# Clean and rebuild
cargo clean
cargo build --release
```

### Python Import Errors

**Error: Module not found**
```bash
# Make sure packages are installed
pip install -r requirements.txt

# Check Python path
import sys
print(sys.path)
```

**Error: Numpy/Scipy not found**
```bash
# Install scientific Python stack
pip install numpy scipy matplotlib pandas
```

### Performance Issues

**Slow simulation**
- Reduce `n_steps` parameter
- Use fewer assets
- Disable microstructure noise if not needed

**Memory issues**
- Reduce lookback window in technical analysis
- Limit history storage in agents
- Use generators instead of lists where possible

---

## Getting Help

### Documentation
- `docs/ARCHITECTURE.md` - System design
- `docs/PROJECT_DOCUMENTATION.md` - Complete documentation
- Inline code comments in all files

### Code Structure
Each module is well-documented with docstrings explaining:
- Purpose and functionality
- Parameters and return values
- Usage examples

### Contributing
To add features:
1. Fork the repository
2. Create a feature branch
3. Implement and test
4. Submit pull request with documentation

---

## Performance Tips

### Matching Engine (Rust)
```bash
# Build with optimizations
cargo build --release

# Enable LTO (Link Time Optimization)
# Already enabled in Cargo.toml
```

### Simulation (Python)
```python
# Use vectorized operations
prices = np.array(prices)  # Not list
returns = np.diff(np.log(prices))  # Fast

# Pre-allocate arrays
results = np.zeros(n_simulations)

# Use numba for JIT compilation (optional)
from numba import jit

@jit(nopython=True)
def fast_calculation(data):
    # Your code here
    pass
```

---

**Happy Trading! 📈**

For questions or issues, refer to the full documentation or open an issue in the repository.
