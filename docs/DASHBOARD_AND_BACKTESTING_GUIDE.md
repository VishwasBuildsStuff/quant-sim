# HFT Dashboard & Backtesting Engine Guide

## 🚀 Quick Start

### 1. Visualization Dashboard (Works Immediately!)

The HTML dashboard requires **no installation** - just open in your browser:

```
V:\quant_project\hft-dashboard\public\index.html
```

**Simply double-click the file** or run:

```bash
start V:\quant_project\hft-dashboard\public\index.html
```

**Features:**
- 📊 Real-time equity curve visualization
- 📉 Drawdown tracking
- 📖 Level 2 order book display
- 🤖 Agent performance comparison
- 📈 Volatility monitoring
- 📊 Returns distribution
- 🎭 Scenario switching (Flash Crash, GFC, Pandemic)

---

### 2. Backtesting Engine

```bash
cd V:\quant_project\hft-strategies
python run_backtest_demo.py
```

**What it runs:**
- ✅ Simple backtest with MA crossover strategy
- ✅ Strategy comparison (4 different strategies)
- ✅ Walk-forward optimization
- ✅ Stress testing across market regimes

---

## 📊 Dashboard Features

### Key Metrics Displayed:
- **Portfolio Value** - Current equity
- **Total Return** - Cumulative return %
- **Sharpe Ratio** - Risk-adjusted returns
- **Max Drawdown** - Peak-to-trough loss
- **Total Trades** - Number of executions
- **Win Rate** - Percentage profitable

### Interactive Scenarios:
Click buttons to switch between:
- **Default Simulation** - Normal market conditions
- **Flash Crash 2010** - 9% intraday crash
- **GFC 2008** - 57% credit crisis
- **Pandemic 2020** - V-shaped recovery

---

## 🔬 Backtesting Engine Architecture

### Event-Driven Design:
```
Market Data → Strategy → Signal → Order → Fill → Portfolio
     ↓
   Event Queue
```

### Components:

#### 1. **Strategies** (Plug-in Interface)
```python
class MovingAverageCrossoverStrategy(Strategy):
    def on_data(self, market_event):
        # Process market data
        # Return SignalEvent or None
        pass
```

#### 2. **Portfolio Manager**
- Tracks positions and cash
- Calculates equity in real-time
- Records performance snapshots

#### 3. **Execution Handler**
- Simulates realistic fills
- Commission models (fixed, percentage)
- Slippage models (fixed, percentage)

#### 4. **Walk-Forward Optimizer**
- Splits data into train/test
- Optimizes parameters on in-sample
- Validates on out-of-sample
- Rolls forward and repeats

---

## 💻 Usage Examples

### Simple Backtest:
```python
from backtesting_engine import *

# Create engine
engine = BacktestEngine(
    initial_capital=1_000_000.0,
    commission_model=PercentageCommission(0.001),
    slippage_model=PercentageSlippage(0.0005)
)

# Add strategy
strategy = MovingAverageCrossoverStrategy({
    'short_window': 20,
    'long_window': 50
})
engine.add_strategy(strategy)

# Load data
engine.load_price_data("SPY", dates, prices)

# Run
results = engine.run_backtest()
print(f"Return: {results['total_return_pct']:.2f}%")
print(f"Sharpe: {results['sharpe_ratio']:.2f}")
```

### Custom Strategy:
```python
class MyStrategy(Strategy):
    def __init__(self, params=None):
        super().__init__("My Strategy", params)
        self.lookback = params.get('lookback', 20)
    
    def on_data(self, market_event):
        # Your logic here
        if some_condition:
            return SignalEvent(
                timestamp=market_event.timestamp,
                instrument=market_event.instrument,
                signal_type="LONG",
                strength=1.0
            )
        return None
```

### Walk-Forward Optimization:
```python
optimizer = WalkForwardOptimizer(
    strategy_class=MovingAverageCrossoverStrategy,
    param_grid={
        'short_window': [10, 20, 30],
        'long_window': [50, 100, 200]
    },
    train_pct=0.7
)

results = optimizer.optimize(dates, prices)
print(f"Best params: {results['best_params']}")
```

---

## 📈 Built-in Strategies

### 1. Moving Average Crossover
- **Logic**: Buy when short MA crosses above long MA
- **Params**: short_window, long_window
- **Best for**: Trending markets

### 2. Mean Reversion (Bollinger Bands)
- **Logic**: Buy at lower band, sell at upper band
- **Params**: window, num_std
- **Best for**: Range-bound markets

---

## 🎯 Performance Metrics

The backtester calculates:
- **Total Return** - Cumulative gain/loss
- **Sharpe Ratio** - Return per unit risk
- **Sortino Ratio** - Downside risk-adjusted return
- **Max Drawdown** - Worst peak-to-trough
- **Win Rate** - Percentage winning trades
- **Total Trades** - Number of executions

---

## 🔧 Advanced Features

### Commission Models:
```python
FixedCommission(0.005)           # $0.005 per share
PercentageCommission(0.001)      # 10 bps of trade value
```

### Slippage Models:
```python
FixedSlippage(0.01)              # $0.01 per share
PercentageSlippage(0.0005)       # 5 bps of price
```

### Stress Testing:
```python
# Test across regimes
regimes = {
    'Bull': {'mu': 0.20, 'sigma': 0.15},
    'Bear': {'mu': -0.15, 'sigma': 0.35},
    'High Vol': {'mu': 0.05, 'sigma': 0.50}
}
```

---

## 📁 File Structure

```
hft-dashboard/
└── public/
    └── index.html          # Standalone dashboard (works immediately)

hft-strategies/
├── backtesting_engine.py   # Event-driven backtester
├── examples/
│   └── demo_backtesting.py # Comprehensive demo
└── run_backtest_demo.py    # Quick runner script
```

---

## 🚀 Next Steps

### Extend the Dashboard:
- Connect to live simulation data
- Add real-time WebSocket updates
- Implement React version (package.json provided)

### Extend the Backtester:
- Add more strategies (RSI, MACD, etc.)
- Integrate with historical data feeds
- Add portfolio optimization
- Implement machine learning strategies

---

**Enjoy backtesting your strategies! 📊**
