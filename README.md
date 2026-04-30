# Institutional-Grade HFT Simulation Platform

[![Rust](https://img.shields.io/badge/rust-1.75+-blue.svg)](https://www.rust-lang.org/)
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

A comprehensive High-Frequency Trading simulation platform designed to model heterogeneous market participants across global asset classes and demonstrate performance divergence during market stress events.

---

## 🎯 Key Features

### ✅ **Completed Components**

| Component | Technology | Description |
|-----------|-----------|-------------|
| **Matching Engine** | Rust | Level 3 order book with skip list, price-time priority |
| **Market Simulation** | Python | 6 stochastic processes, 6 historical scenarios, 5 market regimes |
| **Trading Agents** | Python | 6 agent types (Retail, Semi-Pro, Institutional, 3x HFT) |
| **Risk Management** | Python | Pre/post-trade checks, VaR, circuit breakers |
| **Regulatory Compliance** | Python | Spoofing, wash trading, front-running detection |
| **Analytics Engine** | Python | 30+ performance metrics, attribution analysis |
| **Bloomberg Terminal Dashboard** | FastAPI + Web | Professional real-time trading dashboard |

### 📊 Performance Targets

- **Order Matching**: <1μs latency
- **System Throughput**: ≥100,000 orders/second
- **HFT Agent Latency**: ~1μs (simulated)
- **Retail Agent Latency**: ~100ms (simulated)

---

## 🏗️ Architecture

```
quant_project/
├── hft-matching-engine/        # Rust core (nanosecond latency)
│   ├── src/
│   │   ├── order_book/         # Level 3 order book
│   │   ├── market_data.rs      # Ring buffer feeds
│   │   ├── network.rs          # FIX protocol
│   │   ├── latency.rs          # Latency simulation
│   │   ├── types.rs            # Core types
│   │   └── errors.rs           # Error handling
│   └── Cargo.toml
│
├── hft-simulation/             # Python market simulation
│   ├── stochastic_processes.py # GBM, Jump Diffusion, GARCH, Heston
│   ├── historical_scenarios.py # 6 stress scenarios
│   ├── macro_events.py         # Macro-economic events
│   └── examples/
│       └── demo_simulation.py  # Comprehensive demo
│
├── hft-strategies/             # Python trading agents
│   ├── base_agent.py           # Agent framework
│   ├── indicators.py           # Technical analysis library
│   ├── risk_management.py      # Risk controls
│   ├── regulatory_compliance.py# SEC/MiFID II compliance
│   └── agents/
│       ├── retail_trader.py    # Behavioral finance (Prospect Theory)
│       ├── semi_pro_trader.py  # Technical strategies
│       ├── institutional_trader.py  # TWAP, VWAP, IS
│       └── hft_agents.py       # Market making, arbitrage
│
├── hft-analytics/              # Python analytics
│   └── performance_analytics.py # Performance metrics
│
├── hft-dashboard/              # Bloomberg Terminal Dashboard ⭐ NEW
│   ├── dashboard_server.py     # FastAPI backend + WebSocket
│   ├── public/
│   │   └── index.html          # Professional terminal UI
│   ├── requirements.txt        # Python dependencies
│   ├── start_dashboard.bat     # Windows startup script
│   ├── README.md               # Dashboard quick start
│   └── DASHBOARD_GUIDE.md      # Complete user guide
│
└── docs/                       # Documentation
    ├── ARCHITECTURE.md         # System design
    ├── PROJECT_DOCUMENTATION.md # Complete docs
    └── QUICK_START.md          # Quick start guide
```

---

## 🚀 Quick Start

### 1. Build Rust Matching Engine

```bash
cd hft-matching-engine
cargo build --release
cargo run --release
```

### 2. Run Python Simulation

```bash
cd hft-simulation
pip install -r requirements.txt
python examples/demo_simulation.py
```

### 3. Launch Bloomberg Terminal Dashboard ⭐

```bash
cd hft-dashboard
pip install -r requirements.txt
python dashboard_server.py
```

Then open your browser to **http://localhost:8000**

**Keyboard Shortcuts:**
- `1` - Overview (portfolio, indices, charts)
- `2` - Live Prices (10 NSE stocks)
- `3` - Order Book (Level 2 depth)
- `4` - Agents (5 trading agents)
- `5` - Trades (real-time blotter)
- `6` - Risk (VaR, regime, volatility)
- `R` - Refresh data
- `F` - Toggle fullscreen

See [hft-dashboard/README.md](hft-dashboard/README.md) for details.

### 4. Create Trading Agents

```python
from hft_strategies import RetailTraderAgent, HFTMarketMakerAgent

# Retail trader with behavioral biases
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
```

See [QUICK_START.md](docs/QUICK_START.md) for detailed examples.

---

## 📈 Stochastic Processes

| Process | Use Case | Features |
|---------|----------|----------|
| **GBM** | Baseline price movement | Exact solution, Monte Carlo |
| **Jump Diffusion** | Sudden price discontinuities | Poisson jumps, crash modeling |
| **GARCH(1,1)** | Volatility clustering | Forecasting, mean-reverting variance |
| **Heston** | Stochastic volatility | Leverage effect, Feller condition |
| **Ornstein-Uhlenbeck** | Mean reversion | Pairs trading, half-life |

---

## 🎭 Historical Stress Scenarios

| Scenario | Date | Max DD | Recovery | Characteristics |
|----------|------|--------|----------|-----------------|
| **2010 Flash Crash** | May 6, 2010 | -9% | 1 day | Liquidity evaporation, algorithmic cascade |
| **2008 Financial Crisis** | 2007-2009 | -57% | 4 years | Credit crunch, systemic risk |
| **2020 Pandemic Crash** | Feb-Mar 2020 | -34% | 5 months | Fastest bear market, V-shaped recovery |
| **2022 Energy Crisis** | Feb-Jun 2022 | -20% | 1 year | Commodity shock, sector divergence |
| **2016 Brexit** | Jun 2016 | -11% | 3 weeks | Binary event, currency impact |
| **Dot-com Bubble** | 2000-2002 | -78% | 15 years | Valuation mean reversion |

---

## 🤖 Trading Agent Types

### Retail Trader
- **Behavioral Finance**: Prospect Theory, loss aversion (λ=2.0)
- **Biases**: Fear, greed, herd mentality, FOMO, panic selling
- **Latency**: ~100ms with high variance
- **Data**: Delayed feeds, incomplete information

### Semi-Professional Trader
- **Strategy**: Technical indicators (RSI, MACD, Bollinger Bands)
- **Risk Management**: 2% stop loss, 4% take profit
- **Latency**: ~1ms
- **Position Sizing**: Volatility-based

### Institutional Algorithmic Trader
- **Strategies**: TWAP, VWAP, Implementation Shortfall, POV
- **Focus**: Minimize market impact, benchmark tracking
- **Order Sizes**: Large (million+ dollar orders)
- **Latency**: ~100μs

### HFT Market Maker
- **Strategy**: Continuous bid-ask quoting, spread capture
- **Inventory Management**: Dynamic skewing, position limits
- **Latency**: ~1μs (co-location advantage)
- **Update Frequency**: 1000 Hz

### HFT Latency Arbitrageur
- **Strategy**: Cross-venue price discrepancies
- **Advantage**: 100ns latency differential
- **Profit Threshold**: 0.05% minimum

### HFT Statistical Arbitrageur
- **Strategy**: Pairs trading, mean reversion
- **Entry**: 2σ deviation, exit at 0.5σ
- **Market Neutral**: Long/short positions

---

## 🛡️ Risk & Compliance

### Pre-Trade Risk Checks
- ✅ Order size limits
- ✅ Position limits
- ✅ Capital adequacy
- ✅ Fat-finger detection (price & quantity)
- ✅ Daily loss limits
- ✅ Wash trade prevention

### Post-Trade Analysis
- ✅ Value at Risk (VaR): Historical, Parametric, Monte Carlo
- ✅ Expected Shortfall (CVaR)
- ✅ Maximum drawdown analysis
- ✅ Stress testing
- ✅ Risk attribution

### Regulatory Compliance (SEC/MiFID II)
- ✅ Spoofing detection (cancel ratio >80%)
- ✅ Layering detection (5+ price levels)
- ✅ Wash trading detection
- ✅ Quote stuffing detection (>100 msg/sec)
- ✅ Front running detection
- ✅ Marking the close detection
- ✅ Auto-suspension for critical violations

---

## 📊 Analytics & Metrics

### Performance Metrics (30+)
- **Basic**: Total trades, win rate, avg win/loss
- **Risk-Adjusted**: Sharpe, Sortino, Calmar, Omega ratios
- **Risk**: Max drawdown, VaR (95%, 99%), Expected Shortfall
- **Execution**: Slippage, fill rate, market impact
- **Advanced**: Profit factor, payoff ratio, tail ratio

### Performance Attribution
- Alpha vs Beta decomposition
- Factor analysis
- Tracking error
- Active return analysis

---

## 🔧 Technical Details

### Matching Engine (Rust)
```rust
// Create order book
let mut book = OrderBook::new(instrument);

// Add limit order
let order = Order::new(
    1, 1, 1,
    Side::Buy,
    OrderType::Limit,
    15000,  // $150.00
    100,
    TimeInForce::GTC
);
let trades = book.add_order(order).unwrap();

// Get snapshot
let snapshot = book.snapshot(5);
```

### Market Simulation (Python)
```python
# Run simulation
config = SimulationConfig(
    start_date=datetime(2024, 1, 1),
    asset_names=["SPY", "QQQ"],
    process_type="jump_diffusion"
)
engine = MarketSimulationEngine(config)
output = engine.simulate(n_steps=1000)

# With historical scenario
output = engine.simulate_with_scenario("flash_crash_2010", n_steps=500)
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and architecture |
| [PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md) | Complete platform documentation |
| [QUICK_START.md](docs/QUICK_START.md) | Quick start guide with examples |

---

## 🎓 Academic References

1. **Kahneman & Tversky (1979)** - Prospect Theory
2. **Merton (1976)** - Jump Diffusion Models
3. **Heston (1993)** - Stochastic Volatility
4. **Engle (1982)** - GARCH Models

---

## 🛠️ Extending the Platform

### Adding a New Strategy

```python
class MyCustomAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config)
        # Initialize strategy
    
    def on_market_data(self, instrument, data):
        # React to market data
        pass
    
    def generate_orders(self):
        # Generate orders based on strategy
        return []
```

### Adding a New Scenario

```python
MY_SCENARIO = HistoricalScenario(
    name="My Custom Scenario",
    scenario_type=ScenarioType.CUSTOM,
    phases=[...],
    max_drawdown=-0.15,
    ...
)
```

---

## 📝 License

MIT License - See LICENSE file for details

---

## ⚠️ Disclaimer

This is a **simulation platform** designed for educational and research purposes. It is NOT intended for live trading. All market data, order flow, and trading activity are simulated.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Implement and test your changes
4. Update documentation
5. Submit a pull request

---

**Built with ❤️ for quantitative finance education and research**

*Version: 0.1.0 | Status: Development*
