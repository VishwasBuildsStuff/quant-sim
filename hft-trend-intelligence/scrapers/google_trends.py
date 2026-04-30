"""
Google Trends Scraper
Captures search volume shifts to detect consumer interest changes
"""

import pandas as pd
import numpy as np
from pytrends.request import TrendReq
from datetime import datetime, timedelta
import json
import os

class GoogleTrendsScraper:
    """Scrapes Google Trends data for trend detection"""
    
    def __init__(self):
        self.pytrends = TrendReq(hl='en-IN', tz=330)  # India timezone
        self.trending_searches = []
        
    def fetch_trending_searches(self, geo='IN'):
        """Get current trending searches in India"""
        try:
            trending = self.pytrends.trending_searches(pn=geo)
            self.trending_searches = trending.head(20).to_dict('records')
            print(f"✅ Fetched {len(self.trending_searches)} trending searches")
            return self.trending_searches
        except Exception as e:
            print(f"⚠️ Error fetching trending searches: {e}")
            return []
    
    def get_search_volume(self, keyword, timeframe='today 1-m', geo='IN'):
        """Get search volume for specific keyword"""
        try:
            self.pytrends.build_payload([keyword], cat=0, timeframe=timeframe, geo=geo)
            data = self.pytrends.interest_over_time()
            
            if data.empty:
                return None
            
            return {
                'keyword': keyword,
                'current_volume': int(data.iloc[-1][keyword]),
                'avg_volume': int(data[keyword].mean()),
                'max_volume': int(data[keyword].max()),
                'trend_direction': self._calculate_trend(data[keyword].values),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            print(f"⚠️ Error fetching volume for {keyword}: {e}")
            return None
    
    def get_related_queries(self, keyword):
        """Get related queries for keyword"""
        try:
            self.pytrends.build_payload([keyword], cat=0, timeframe='today 1-m', geo='IN')
            related = self.pytrends.related_queries()
            
            if keyword in related and related[keyword]['top'] is not None:
                top_queries = related[keyword]['top'].head(10).to_dict('records')
                rising_queries = related[keyword]['rising'].head(10).to_dict('records') if related[keyword]['rising'] is not None else []
                
                return {
                    'keyword': keyword,
                    'top_related': top_queries,
                    'rising_related': rising_queries
                }
        except Exception as e:
            print(f"⚠️ Error fetching related queries: {e}")
        
        return None
    
    def compare_keywords(self, keywords):
        """Compare multiple keywords"""
        try:
            self.pytrends.build_payload(keywords, cat=0, timeframe='today 1-m', geo='IN')
            data = self.pytrends.interest_over_time()
            
            if data.empty:
                return None
            
            result = {
                'keywords': keywords,
                'current_volumes': {kw: int(data.iloc[-1][kw]) if kw in data.columns else 0 for kw in keywords},
                'avg_volumes': {kw: int(data[kw].mean()) if kw in data.columns else 0 for kw in keywords},
                'trend_directions': {kw: self._calculate_trend(data[kw].values) for kw in keywords if kw in data.columns},
                'timestamp': datetime.now().isoformat()
            }
            
            return result
        except Exception as e:
            print(f"⚠️ Error comparing keywords: {e}")
            return None
    
    def _calculate_trend(self, values):
        """Calculate trend direction from time series"""
        if len(values) < 5:
            return 'stable'
        
        # Simple linear regression slope
        x = np.arange(len(values))
        slope = np.polyfit(x, values, 1)[0]
        
        if slope > 5:
            return 'strongly_increasing'
        elif slope > 1:
            return 'increasing'
        elif slope < -5:
            return 'strongly_decreasing'
        elif slope < -1:
            return 'decreasing'
        else:
            return 'stable'
    
    def get_category_trends(self, category_id=0, geo='IN'):
        """Get trending by category"""
        # Categories: 0=all, 3=autos, 5=books, 12=food, 20=health, 27=tech, 39=finance
        try:
            self.pytrends.build_payload([], cat=category_id, timeframe='today 1-m', geo=geo)
            related = self.pytrends.related_topics()
            return related
        except Exception as e:
            print(f"⚠️ Error fetching category trends: {e}")
            return {}

if __name__ == '__main__':
    scraper = GoogleTrendsScraper()
    
    # Fetch trending searches
    trending = scraper.fetch_trending_searches()
    print("\n📈 Top 10 Trending Searches in India:")
    for i, item in enumerate(trending[:10], 1):
        print(f"  {i}. {item}")
    
    # Get volume for example keyword
    print("\n📊 Testing search volume for 'EV cars':")
    volume = scraper.get_search_volume('EV cars')
    if volume:
        print(f"  Current Volume: {volume['current_volume']}")
        print(f"  Trend: {volume['trend_direction']}")
