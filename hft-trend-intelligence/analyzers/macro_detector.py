"""
Macroeconomic Shift Detector
Detects early signs of macro-level changes across industries
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict

# Industry classification database
INDUSTRY_MAP = {
    # Technology
    'AI': {'sector': 'Technology', 'industry': 'Artificial Intelligence', 'stocks': ['INFY.NS', 'TCS.NS', 'TECHM.NS']},
    'artificial intelligence': {'sector': 'Technology', 'industry': 'Artificial Intelligence', 'stocks': ['INFY.NS', 'TCS.NS']},
    'cloud': {'sector': 'Technology', 'industry': 'Cloud Computing', 'stocks': ['TCS.NS', 'INFY.NS']},
    'semiconductor': {'sector': 'Technology', 'industry': 'Semiconductors', 'stocks': ['TSM', 'NVDA']},
    'chip': {'sector': 'Technology', 'industry': 'Semiconductors', 'stocks': ['TSM', 'NVDA']},
    
    # Electric Vehicles & Energy
    'EV': {'sector': 'Automobile', 'industry': 'Electric Vehicles', 'stocks': ['TATAMOTORS.NS', 'M&M.NS']},
    'electric vehicle': {'sector': 'Automobile', 'industry': 'Electric Vehicles', 'stocks': ['TATAMOTORS.NS']},
    'tesla': {'sector': 'Automobile', 'industry': 'Electric Vehicles', 'stocks': ['TSLA', 'TATAMOTORS.NS']},
    'battery': {'sector': 'Energy', 'industry': 'Energy Storage', 'stocks': ['EXIDEIND.NS']},
    'solar': {'sector': 'Energy', 'industry': 'Renewable Energy', 'stocks': ['ADANIGREEN.NS', 'TATAPOWER.NS']},
    'renewable': {'sector': 'Energy', 'industry': 'Renewable Energy', 'stocks': ['ADANIGREEN.NS']},
    
    # Finance
    'bank': {'sector': 'Financial', 'industry': 'Banking', 'stocks': ['HDFCBANK.NS', 'ICICIBANK.NS', 'SBIN.NS']},
    'banking': {'sector': 'Financial', 'industry': 'Banking', 'stocks': ['HDFCBANK.NS', 'ICICIBANK.NS']},
    'fintech': {'sector': 'Financial', 'industry': 'Financial Technology', 'stocks': ['PAYTM.NS']},
    'crypto': {'sector': 'Financial', 'industry': 'Cryptocurrency', 'stocks': ['COIN']},
    'bitcoin': {'sector': 'Financial', 'industry': 'Cryptocurrency', 'stocks': ['COIN']},
    
    # Healthcare
    'pharma': {'sector': 'Healthcare', 'industry': 'Pharmaceuticals', 'stocks': ['SUNPHARMA.NS', 'DRREDDY.NS']},
    'healthcare': {'sector': 'Healthcare', 'industry': 'Healthcare Services', 'stocks': ['APOLLOHOSP.NS']},
    'vaccine': {'sector': 'Healthcare', 'industry': 'Biotechnology', 'stocks': ['BIOCON.NS']},
    
    # Consumer
    'FMCG': {'sector': 'Consumer', 'industry': 'Fast Moving Consumer Goods', 'stocks': ['HUL.NS', 'ITC.NS']},
    'retail': {'sector': 'Consumer', 'industry': 'Retail', 'stocks': ['TRENT.NS', 'RELIANCE.NS']},
    'e-commerce': {'sector': 'Consumer', 'industry': 'E-Commerce', 'stocks': []},
    
    # Infrastructure
    'infrastructure': {'sector': 'Infrastructure', 'industry': 'Construction', 'stocks': ['LT.NS']},
    'real estate': {'sector': 'Infrastructure', 'industry': 'Real Estate', 'stocks': ['DLF.NS', 'OBEROIRLTY.NS']},
    'housing': {'sector': 'Infrastructure', 'industry': 'Real Estate', 'stocks': ['DLF.NS']},
    
    # Commodities
    'gold': {'sector': 'Commodities', 'industry': 'Precious Metals', 'stocks': ['GOLDBEES.NS']},
    'oil': {'sector': 'Energy', 'industry': 'Oil & Gas', 'stocks': ['ONGC.NS', 'RELIANCE.NS']},
    'steel': {'sector': 'Materials', 'industry': 'Steel', 'stocks': ['TATASTEEL.NS', 'JSWSTEEL.NS']},
    
    # Macro indicators
    'recession': {'sector': 'Macro', 'industry': 'Economic Indicator', 'stocks': ['GOLDBEES.NS', 'VIX']},
    'inflation': {'sector': 'Macro', 'industry': 'Economic Indicator', 'stocks': ['GOLDBEES.NS']},
    'interest rate': {'sector': 'Macro', 'industry': 'Monetary Policy', 'stocks': ['HDFCBANK.NS']},
    'RBI': {'sector': 'Macro', 'industry': 'Monetary Policy', 'stocks': ['HDFCBANK.NS', 'ICICIBANK.NS']},
    'layoff': {'sector': 'Macro', 'industry': 'Labor Market', 'stocks': []},
    'unemployment': {'sector': 'Macro', 'industry': 'Labor Market', 'stocks': []},
}

class MacroShiftDetector:
    """Detects macroeconomic shifts from trend data"""
    
    def __init__(self):
        self.trend_history = []
        self.baseline_trends = {}
        self.alerts = []
    
    def classify_industry(self, keyword):
        """Classify keyword to industry/sector"""
        keyword_lower = keyword.lower()
        
        for term, classification in INDUSTRY_MAP.items():
            if term in keyword_lower:
                return classification
        
        return {'sector': 'Unknown', 'industry': 'Unknown', 'stocks': []}
    
    def detect_macro_shifts(self, trends_data):
        """Detect macroeconomic shifts from trend data"""
        shifts = []
        
        for trend in trends_data:
            keyword = trend.get('keyword', trend.get('topic', ''))
            score = trend.get('trend_score', trend.get('volume', 0))
            velocity = trend.get('velocity', 0)
            sentiment = trend.get('sentiment_score', 0)
            
            # Check if this is significant
            if score < 40:  # Only care about strong trends
                continue
            
            classification = self.classify_industry(keyword)
            
            # Detect different types of shifts
            shift = self._analyze_shift(keyword, trend, classification)
            if shift:
                shifts.append(shift)
        
        return shifts
    
    def _analyze_shift(self, keyword, trend, classification):
        """Analyze if trend represents a macro shift"""
        score = trend.get('trend_score', 0)
        velocity = trend.get('velocity', 0)
        
        shift_type = None
        confidence = 0
        impact = 'low'
        
        # Demand surge detection
        if velocity > 50 and score > 60:
            shift_type = 'demand_surge'
            confidence = min(100, (velocity + score) / 2)
            impact = 'high' if confidence > 70 else 'medium'
        
        # Sentiment shift detection
        elif abs(trend.get('sentiment_score', 0)) > 60:
            shift_type = 'sentiment_shift'
            confidence = abs(trend['sentiment_score'])
            impact = 'high' if confidence > 70 else 'medium'
        
        # Cross-sector correlation
        elif classification['sector'] == 'Macro' and score > 50:
            shift_type = 'macro_indicator'
            confidence = score
            impact = 'high'
        
        if not shift_type:
            return None
        
        # Get related stocks
        related_stocks = classification.get('stocks', [])
        
        # Generate trading implications
        implications = self._generate_implications(shift_type, classification, trend)
        
        return {
            'keyword': keyword,
            'shift_type': shift_type,
            'sector': classification['sector'],
            'industry': classification['industry'],
            'confidence': round(confidence, 2),
            'impact': impact,
            'related_stocks': related_stocks,
            'implications': implications,
            'timestamp': datetime.now().isoformat()
        }
    
    def _generate_implications(self, shift_type, classification, trend):
        """Generate trading/investment implications"""
        implications = []
        
        if shift_type == 'demand_surge':
            implications.append(f"Consider long positions in {classification['sector']} stocks")
            implications.append("Monitor for sustainability of trend")
            if classification['stocks']:
                implications.append(f"Watch: {', '.join(classification['stocks'][:3])}")
        
        elif shift_type == 'sentiment_shift':
            sentiment = trend.get('sentiment_score', 0)
            if sentiment > 0:
                implications.append("Positive sentiment shift - potential buying opportunity")
            else:
                implications.append("Negative sentiment shift - consider defensive positioning")
        
        elif shift_type == 'macro_indicator':
            implications.append("Macroeconomic signal - review portfolio allocation")
            implications.append("Consider hedging strategies")
        
        return implications
    
    def aggregate_sector_signals(self, shifts):
        """Aggregate signals by sector"""
        sector_signals = defaultdict(lambda: {
            'count': 0, 'avg_confidence': 0, 'total_impact': 0, 'shifts': []
        })
        
        for shift in shifts:
            sector = shift['sector']
            sector_signals[sector]['count'] += 1
            sector_signals[sector]['avg_confidence'] += shift['confidence']
            sector_signals[sector]['shifts'].append(shift)
            
            impact_score = {'low': 1, 'medium': 2, 'high': 3}.get(shift['impact'], 1)
            sector_signals[sector]['total_impact'] += impact_score
        
        # Calculate averages
        for sector in sector_signals:
            count = sector_signals[sector]['count']
            sector_signals[sector]['avg_confidence'] /= count
            sector_signals[sector]['avg_impact'] = sector_signals[sector]['total_impact'] / count
        
        return dict(sector_signals)
