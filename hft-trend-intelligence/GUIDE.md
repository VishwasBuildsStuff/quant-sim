# 🚀 HFT Trend Intelligence - Complete Guide

## 🎯 What This System Does

**Detects macroeconomic shifts BEFORE they hit the news** by analyzing:
- Google search trends (what people are searching for)
- Reddit discussions (what retail investors are talking about)
- Financial news sentiment (what the media is reporting)
- Cross-platform correlation (when trends appear everywhere simultaneously)

This is **alternative data intelligence** - the same type of data that hedge funds pay $10M+/year for!

---

## 📂 Project Structure

```
hft-trend-intelligence/
├── scrapers/
│   ├── google_trends.py      # Google Trends API scraper
│   ├── reddit_scraper.py     # Reddit trending discussions
│   └── news_scraper.py       # Financial news headlines
│
├── analyzers/
│   ├── sentiment_analysis.py # NLP sentiment detection (VADER + TextBlob)
│   └── macro_detector.py     # Macroeconomic shift detection
│
├── dashboard/
│   └── trend_dashboard.py    # Web UI for trend visualization
│
├── main.py                   # Main orchestrator
├── requirements.txt          # Dependencies
└── README.md                 # This file
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd V:\quant_project\hft-trend-intelligence
pip install -r requirements.txt
```

### 2. Run Trend Analysis

```bash
python main.py
```

This will:
- ✅ Fetch trending searches from Google Trends
- ✅ Scrape Reddit for financial discussions
- ✅ Collect financial news headlines
- ✅ Analyze sentiment across all sources
- ✅ Detect macroeconomic shifts
- ✅ Generate sector signals
- ✅ Create actionable alerts

### 3. View Dashboard

```bash
python dashboard/trend_dashboard.py
```

Open: **http://localhost:8001**

---

## 🔧 How It Works

### Data Collection Pipeline

```
┌─────────────────────────────────────────────┐
│          DATA SOURCES                        │
├─────────────────────────────────────────────┤
│  Google Trends → Search volume data         │
│  Reddit        → Retail investor sentiment  │
│  News APIs     → Media sentiment            │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│          ANALYSIS ENGINE                     │
├─────────────────────────────────────────────┤
│  Sentiment Analysis (VADER + TextBlob)      │
│  Trend Velocity & Acceleration              │
│  Industry Classification                    │
│  Macro Shift Detection                      │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│          OUTPUT                              │
├─────────────────────────────────────────────┤
│  Trend Scores (0-100)                       │
│  Sentiment Scores (-100 to +100)            │
│  Sector Signals                             │
│  Actionable Alerts                          │
│  Related Stocks                             │
└─────────────────────────────────────────────┘
```

---

## 📊 Trend Scoring System

### Trend Score (0-100)
Calculated from:
- **Volume** (0-25): How many people searching/discussing?
- **Velocity** (0-25): How fast is it growing?
- **Acceleration** (0-25): Is growth speeding up?
- **Cross-Platform** (0-25): Appears on multiple platforms?

### Sentiment Score (-100 to +100)
- **-100 to -50**: Extremely Bearish
- **-50 to 0**: Bearish
- **0**: Neutral
- **0 to +50**: Bullish
- **+50 to +100**: Extremely Bullish

### Macro Impact Score (0-100)
- **0-20**: Noise (ignore)
- **20-40**: Minor trend (watch)
- **40-60**: Moderate trend (actionable)
- **60-80**: Strong trend (high conviction)
- **80-100**: Macro shift (major signal)

---

## 🎯 Example Detection Output

```
============================================================
📊 TREND INTELLIGENCE SUMMARY
============================================================

🔥 Top 5 Trending Searches:
  1. AI tools
  2. EV cars
  3. recession
  4. gold price
  5. layoffs

💭 Reddit Sentiment: bearish (-0.62)
💭 News Sentiment: neutral (0.05)

🌍 3 Macro Shifts Detected:
  ⚠️ AI tools - demand_surge (85%)
  ⚠️ recession - macro_indicator (72%)
  ⚠️ EV cars - demand_surge (78%)

🚨 3 Alerts Generated:
  [HIGH] Demand Surge detected in Technology: AI tools
  [MEDIUM] Strong bearish sentiment on Reddit: -0.62
  [HIGH] Macro indicator spike: recession

============================================================
```

---

## 🧠 Industry Classification

The system automatically maps trends to industries:

| Keyword Detected | Sector | Industry | Related Stocks |
|-----------------|--------|----------|----------------|
| AI, artificial intelligence | Technology | AI/ML | INFY, TCS, TECHM |
| EV, electric vehicle, tesla | Automobile | Electric Vehicles | TATAMOTORS, M&M |
| bank, banking | Financial | Banking | HDFCBANK, ICICIBANK, SBIN |
| solar, renewable | Energy | Renewable Energy | ADANIGREEN, TATAPOWER |
| recession, inflation | Macro | Economic Indicator | GOLDBEES, VIX |
| layoffs, unemployment | Macro | Labor Market | - |
| pharma, healthcare | Healthcare | Pharmaceuticals | SUNPHARMA, DRREDDY |
| gold, oil, steel | Commodities | Raw Materials | Various |

---

## 📈 Use Cases

### 1. **Early Recession Detection**
When "recession", "layoffs", "unemployment" searches spike:
- → Increase gold allocation
- → Reduce cyclical stocks
- → Consider VIX calls
- → Monitor bond yields

### 2. **Sector Rotation Signals**
When searches shift from one sector to another:
- → Rotate portfolio allocation
- → Enter trending sectors early
- → Exit declining sectors

### 3. **Product Demand Prediction**
When product-related searches surge:
- → Predict revenue beats/misses
- → Position before earnings
- → Monitor supply chain companies

### 4. **Sentiment-Driven Trading**
When retail sentiment becomes extreme:
- → Contrarian plays (fade the crowd)
- → Momentum plays (follow the crowd)
- → Volatility strategies

---

## 🔌 API Integration

### Google Trends API
```python
from scrapers.google_trends import GoogleTrendsScraper

scraper = GoogleTrendsScraper()

# Get trending searches
trending = scraper.fetch_trending_searches()

# Get search volume for keyword
volume = scraper.get_search_volume('EV cars')
print(volume)
# {
#   'keyword': 'EV cars',
#   'current_volume': 85,
#   'avg_volume': 62,
#   'trend_direction': 'strongly_increasing',
#   ...
# }
```

### Sentiment Analysis
```python
from analyzers.sentiment_analysis import SentimentAnalyzer

analyzer = SentimentAnalyzer()

# Analyze single text
result = analyzer.analyze_text("AI stocks are going to moon!")
print(result)
# {'score': 0.72, 'label': 'positive', 'confidence': 0.72}

# Aggregate sentiment across multiple texts
texts = ["Bullish on tech", "Market crashing soon", "Buy the dip"]
agg = analyzer.aggregate_sentiment(texts)
print(agg)
# {'overall_score': 0.15, 'overall_label': 'neutral', ...}
```

### Macro Shift Detection
```python
from analyzers.macro_detector import MacroShiftDetector

detector = MacroShiftDetector()

trends = [
    {'keyword': 'AI tools', 'trend_score': 85, 'velocity': 78},
    {'keyword': 'recession', 'trend_score': 72, 'velocity': 45}
]

shifts = detector.detect_macro_shifts(trends)
print(shifts)
# [
#   {
#     'keyword': 'AI tools',
#     'shift_type': 'demand_surge',
#     'sector': 'Technology',
#     'confidence': 81.5,
#     'related_stocks': ['INFY.NS', 'TCS.NS'],
#     ...
#   },
#   ...
# ]
```

---

## 🚨 Alert System

Alerts are generated when:

1. **Trend Score > 60** AND **Velocity > 50**
   - Indicates strong, fast-moving trend
   - Example: "AI tools searches up 340% in 30 days"

2. **Sentiment Score < -50 or > +50**
   - Extreme sentiment detected
   - Example: "Strong bearish sentiment on Reddit: -0.62"

3. **Macro Indicator Spike**
   - Recession, inflation, layoffs trending
   - Example: "Recession searches spiking across platforms"

4. **Cross-Platform Correlation**
   - Same trend appearing on Google + Reddit + News
   - Example: "EV trend detected on 3 platforms simultaneously"

---

## 💡 Advanced Usage

### Custom Keyword Monitoring

```python
# Add your own keywords to track
CUSTOM_KEYWORDS = [
    'quantum computing',
    'metaverse',
    'hydrogen energy',
    'space tourism',
    'lab grown diamonds'
]

# Monitor these keywords
for keyword in CUSTOM_KEYWORDS:
    volume = scraper.get_search_volume(keyword)
    if volume and volume['trend_direction'] in ['increasing', 'strongly_increasing']:
        print(f"🔥 {keyword} is trending up!")
```

### Sector Rotation Strategy

```python
# Detect sector rotation
sector_signals = detector.aggregate_sector_signals(shifts)

for sector, data in sector_signals.items():
    if data['avg_confidence'] > 70 and data['trend'] == 'bullish':
        print(f"✅ Long {sector} sector")
    elif data['avg_confidence'] > 60 and data['trend'] == 'bearish':
        print(f"❌ Short {sector} sector")
```

### Portfolio Integration

```python
# Map trend alerts to your HFT dashboard stocks
TREND_TO_STOCKS = {
    'Technology': ['INFY.NS', 'TCS.NS', 'TECHM.NS'],
    'Automobile': ['TATAMOTORS.NS', 'M&M.NS'],
    'Financial': ['HDFCBANK.NS', 'ICICIBANK.NS'],
    'Energy': ['ADANIGREEN.NS', 'TATAPOWER.NS']
}

for alert in alerts:
    if alert['severity'] == 'HIGH':
        sector = alert.get('sector')
        if sector in TREND_TO_STOCKS:
            stocks = TREND_TO_STOCKS[sector]
            print(f"⚠️ Alert for {sector}: Watch {', '.join(stocks)}")
```

---

## 📊 Dashboard Features

The web dashboard (port 8001) shows:

1. **🔥 Trending Topics** - Top searches with scores
2. **🚨 Active Alerts** - High-priority trend alerts
3. **📊 Sector Signals** - Bullish/bearish by sector
4. **💭 Sentiment Chart** - Visual sentiment overview

---

## 🎓 What Makes This Valuable

### What Hedge Funds Pay For:
- **Alternative data subscriptions**: $50K-500K/year
- **Sentiment analysis tools**: $100K-2M/year
- **Macro early warning systems**: Priceless

### What You Built:
- ✅ **Open-source** alternative
- ✅ **Customizable** to your needs
- ✅ **No monthly fees**
- ✅ **Real-time** detection
- ✅ **Integrated** with your HFT platform

---

## 🔮 Future Enhancements

1. **Twitter/X Scraper** - Track trending hashtags
2. **Amazon Bestsellers** - E-commerce trend detection
3. **Product Hunt** - Tech product launches
4. **Government Data** - Import/export statistics
5. **Supply Chain Mapping** - Product origin detection
6. **Telegram Alerts** - Real-time notifications
7. **Backtesting** - Test trend signals against historical data
8. **Machine Learning** - Predict trend continuation probability

---

## ⚠️ Limitations

1. **API Rate Limits** - Google Trends has limits
2. **Data Quality** - Not all trends are meaningful
3. **False Positives** - Some alerts will be noise
4. **Lag Time** - Trends detected after they start
5. **Context Missing** - Doesn't understand nuance

**Always combine with other signals before trading!**

---

## 📞 Support & Documentation

- Main HFT Platform: `V:\quant_project\README.md`
- Dashboard Guide: `V:\quant_project\hft-dashboard\DASHBOARD_GUIDE.md`
- Trend Intelligence: `V:\quant_project\hft-trend-intelligence\README.md`

---

**Built to detect macroeconomic shifts before they hit the news!** 🚀

*This is the same type of alternative data intelligence that billion-dollar hedge funds use.*
