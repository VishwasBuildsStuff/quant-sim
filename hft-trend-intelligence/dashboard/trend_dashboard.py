"""
Trend Intelligence Dashboard Web App
FastAPI-based web UI for trend visualization
"""

import os
import sys
import json
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = FastAPI(title="Trend Intelligence Dashboard")

# Sample trend data (will be replaced by live data)
TREND_DATA = {
    "trending_topics": [
        {"keyword": "AI tools", "score": 85, "velocity": 78, "sentiment": 0.65, "sector": "Technology"},
        {"keyword": "EV cars", "score": 78, "velocity": 82, "sentiment": 0.55, "sector": "Automobile"},
        {"keyword": "recession", "score": 72, "velocity": 45, "sentiment": -0.45, "sector": "Macro"},
        {"keyword": "gold price", "score": 68, "velocity": 52, "sentiment": 0.25, "sector": "Commodities"},
        {"keyword": "layoffs", "score": 65, "velocity": 60, "sentiment": -0.62, "sector": "Macro"},
        {"keyword": "solar energy", "score": 62, "velocity": 55, "sentiment": 0.72, "sector": "Energy"},
        {"keyword": "banking crisis", "score": 58, "velocity": 40, "sentiment": -0.75, "sector": "Financial"},
        {"keyword": "crypto regulation", "score": 55, "velocity": 48, "sentiment": -0.35, "sector": "Financial"},
    ],
    "alerts": [
        {"type": "DEMAND_SURGE", "severity": "HIGH", "message": "AI tools searches up 340% in 30 days", "confidence": 85},
        {"type": "SENTIMENT_SHIFT", "severity": "MEDIUM", "message": "Bearish sentiment on Reddit: -0.62", "confidence": 72},
        {"type": "MACRO_SIGNAL", "severity": "HIGH", "message": "Recession searches spiking across platforms", "confidence": 78},
    ],
    "sector_signals": {
        "Technology": {"count": 5, "avg_confidence": 78, "trend": "bullish"},
        "Automobile": {"count": 3, "avg_confidence": 65, "trend": "bullish"},
        "Financial": {"count": 4, "avg_confidence": 70, "trend": "bearish"},
        "Energy": {"count": 2, "avg_confidence": 62, "trend": "bullish"},
        "Macro": {"count": 6, "avg_confidence": 82, "trend": "bearish"},
    }
}

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Trend Intelligence Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #0a0e17; color: #e1e3e8; font-family: -apple-system, sans-serif; padding: 20px; }
        .header { text-align: center; padding: 20px; margin-bottom: 30px; background: linear-gradient(135deg, #1a237e, #0d47a1); border-radius: 8px; }
        .header h1 { font-size: 2em; margin-bottom: 10px; }
        .header span { color: #ffd600; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .card { background: #1e2330; border: 1px solid #2a2f3e; border-radius: 8px; padding: 20px; }
        .card h2 { font-size: 1.2em; margin-bottom: 15px; color: #ffd600; border-bottom: 2px solid #2a2f3e; padding-bottom: 10px; }
        .trend-item { padding: 12px; margin: 8px 0; background: #131722; border-radius: 6px; border-left: 4px solid #2962ff; }
        .trend-item.bullish { border-left-color: #00c853; }
        .trend-item.bearish { border-left-color: #ff1744; }
        .trend-keyword { font-weight: 700; font-size: 1.1em; }
        .trend-meta { display: flex; gap: 15px; margin-top: 8px; font-size: 0.85em; color: #8b92a8; }
        .alert { padding: 12px; margin: 8px 0; border-radius: 6px; }
        .alert.HIGH { background: rgba(255, 23, 68, 0.15); border-left: 4px solid #ff1744; }
        .alert.MEDIUM { background: rgba(255, 152, 0, 0.15); border-left: 4px solid #ff9800; }
        .sector-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
        .sector-card { background: #131722; padding: 15px; border-radius: 6px; text-align: center; }
        .sector-card.bullish { border-top: 3px solid #00c853; }
        .sector-card.bearish { border-top: 3px solid #ff1744; }
        .sector-name { font-weight: 700; margin-bottom: 8px; }
        .sector-trend { font-size: 0.9em; }
        .sector-trend.bullish { color: #00c853; }
        .sector-trend.bearish { color: #ff1744; }
        canvas { max-height: 300px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🧠 <span>Trend Intelligence</span> Dashboard</h1>
        <p>Real-time consumer trend & macro shift detection</p>
    </div>

    <div class="grid">
        <!-- Trending Topics -->
        <div class="card">
            <h2>🔥 Trending Topics</h2>
            <div id="trendingList"></div>
        </div>

        <!-- Alerts -->
        <div class="card">
            <h2>🚨 Active Alerts</h2>
            <div id="alertsList"></div>
        </div>

        <!-- Sector Signals -->
        <div class="card">
            <h2>📊 Sector Signals</h2>
            <div class="sector-grid" id="sectorGrid"></div>
        </div>

        <!-- Sentiment Chart -->
        <div class="card">
            <h2>💭 Sentiment Overview</h2>
            <canvas id="sentimentChart"></canvas>
        </div>
    </div>

    <script>
        const trendData = """ + json.dumps(TREND_DATA) + """;

        // Render trending topics
        const trendingList = document.getElementById('trendingList');
        trendData.trending_topics.forEach(trend => {
            const sentimentClass = trend.sentiment > 0.2 ? 'bullish' : trend.sentiment < -0.2 ? 'bearish' : '';
            const sentimentIcon = trend.sentiment > 0.2 ? '📈' : trend.sentiment < -0.2 ? '📉' : '➡️';
            
            const html = `
                <div class="trend-item ${sentimentClass}">
                    <div class="trend-keyword">${trend.keyword}</div>
                    <div class="trend-meta">
                        <span>Score: ${trend.score}/100</span>
                        <span>Velocity: ${trend.velocity}</span>
                        <span>${sentimentIcon} ${(trend.sentiment * 100).toFixed(0)}%</span>
                        <span>Sector: ${trend.sector}</span>
                    </div>
                </div>
            `;
            trendingList.innerHTML += html;
        });

        // Render alerts
        const alertsList = document.getElementById('alertsList');
        trendData.alerts.forEach(alert => {
            const html = `
                <div class="alert ${alert.severity}">
                    <strong>[${alert.severity}]</strong> ${alert.message}
                    <div style="font-size: 0.85em; color: #8b92a8; margin-top: 4px;">Confidence: ${alert.confidence}%</div>
                </div>
            `;
            alertsList.innerHTML += html;
        });

        // Render sectors
        const sectorGrid = document.getElementById('sectorGrid');
        for (const [sector, data] of Object.entries(trendData.sector_signals)) {
            const trendClass = data.trend;
            const html = `
                <div class="sector-card ${trendClass}">
                    <div class="sector-name">${sector}</div>
                    <div class="sector-trend ${trendClass}">${data.trend.toUpperCase()}</div>
                    <div style="font-size: 0.85em; color: #8b92a8; margin-top: 4px;">
                        ${data.count} signals<br>
                        ${data.avg_confidence.toFixed(0)}% confidence
                    </div>
                </div>
            `;
            sectorGrid.innerHTML += html;
        }

        // Sentiment chart
        const ctx = document.getElementById('sentimentChart').getContext('2d');
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: trendData.trending_topics.map(t => t.keyword),
                datasets: [{
                    label: 'Sentiment Score',
                    data: trendData.trending_topics.map(t => t.sentiment * 100),
                    backgroundColor: trendData.trending_topics.map(t => 
                        t.sentiment > 0.2 ? 'rgba(0, 200, 83, 0.6)' : 
                        t.sentiment < -0.2 ? 'rgba(255, 23, 68, 0.6)' : 
                        'rgba(139, 146, 168, 0.6)'
                    ),
                    borderColor: trendData.trending_topics.map(t => 
                        t.sentiment > 0.2 ? '#00c853' : 
                        t.sentiment < -0.2 ? '#ff1744' : 
                        '#8b92a8'
                    ),
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    y: {
                        ticks: { color: '#8b92a8', callback: v => v + '%' },
                        grid: { color: 'rgba(255,255,255,0.05)' }
                    },
                    x: {
                        ticks: { color: '#8b92a8' },
                        grid: { color: 'rgba(255,255,255,0.05)' }
                    }
                }
            }
        });
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    import uvicorn
    print("\n" + "=" * 60)
    print("🧠 Trend Intelligence Dashboard")
    print("=" * 60)
    print("🌐 URL: http://localhost:8001")
    print("=" * 60)
    uvicorn.run(app, host='0.0.0.0', port=8001)
