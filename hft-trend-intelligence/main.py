"""
HFT Trend Intelligence - Main Orchestrator
Coordinates all scrapers, analyzers, and detectors
"""

import sys
import os
import asyncio
from datetime import datetime
from scrapers.google_trends import GoogleTrendsScraper
from scrapers.reddit_scraper import RedditScraper
from scrapers.news_scraper import NewsScraper
from scrapers.twitter_scraper import TwitterScraper
from scrapers.amazon_scraper import AmazonBestsellerScraper
from scrapers.government_data import GovernmentDataScraper
from analyzers.sentiment_analysis import SentimentAnalyzer
from analyzers.macro_detector import MacroShiftDetector

class TrendIntelligenceEngine:
    """Main engine that coordinates all trend analysis components"""
    
    def __init__(self):
        print("🧠 Initializing Trend Intelligence Engine v2.0...")
        
        # Initialize scrapers
        self.google_trends = GoogleTrendsScraper()
        self.reddit_scraper = RedditScraper()
        self.news_scraper = NewsScraper()
        self.twitter_scraper = TwitterScraper()
        self.amazon_scraper = AmazonBestsellerScraper()
        self.gov_data_scraper = GovernmentDataScraper()
        
        # Initialize analyzers
        self.sentiment = SentimentAnalyzer()
        self.macro_detector = MacroShiftDetector()
        
        self.all_trends = []
        self.alerts = []
        
        print("✅ Trend Intelligence Engine ready!\n")
        print("=" * 60)
        print("📡 Data Sources:")
        print("  ✓ Google Trends (Search volumes)")
        print("  ✓ Reddit (Retail investor sentiment)")
        print("  ✓ Financial News (Media sentiment)")
        print("  ✓ Twitter/X (Hashtag trends)")
        print("  ✓ Amazon (E-commerce demand)")
        print("  ✓ Government Data (Macro indicators)")
        print("=" * 60 + "\n")
    
    async def run_full_analysis(self):
        """Run complete trend analysis pipeline"""
        print("=" * 60)
        print("🔍 Starting Full Trend Analysis Pipeline v2.0")
        print("=" * 60)
        
        # Step 1: Collect data from ALL sources
        print("\n📡 Step 1: Collecting data from all sources...")
        google_data = self.google_trends.fetch_trending_searches()
        reddit_data = self.reddit_scraper.get_trending_topics()
        news_data = self.news_scraper.collect_headlines()
        twitter_data = self.twitter_scraper.get_trending_topics()
        twitter_sectors = self.twitter_scraper.get_trending_hashtags_by_sector()
        twitter_unusual = self.twitter_scraper.detect_unusual_activity()
        amazon_data = self.amazon_scraper.run_full_tracking()
        gov_data = self.gov_data_scraper.run_full_analysis()
        
        # Step 2: Analyze sentiment
        print("\n💭 Step 2: Analyzing sentiment across platforms...")
        reddit_sentiment = self.sentiment.aggregate_sentiment(
            [post['title'] for post in reddit_data[:20]] if reddit_data else []
        )
        news_sentiment = self.sentiment.aggregate_sentiment(
            [article['headline'] for article in news_data[:30]] if news_data else []
        )
        
        # Step 3: Detect macro shifts
        print("\n🌍 Step 3: Detecting macroeconomic shifts...")
        trends_for_analysis = []
        
        # Prepare Google Trends data
        for item in (google_data or []):
            trends_for_analysis.append({
                'keyword': str(item),
                'trend_score': 70,
                'velocity': 75,
                'sentiment_score': 0,
                'source': 'google_trends'
            })
        
        # Prepare Reddit trends
        if reddit_data:
            for post in reddit_data[:10]:
                engagement_score = min(100, (post.get('engagement_score', 0) / 100) * 100)
                trends_for_analysis.append({
                    'keyword': post.get('title', ''),
                    'trend_score': engagement_score,
                    'velocity': 60,
                    'sentiment_score': post.get('sentiment', {}).get('score', 0) * 100,
                    'source': 'reddit'
                })
        
        # Prepare Twitter trends
        if twitter_data:
            for tweet in twitter_data[:10]:
                engagement_score = min(100, tweet.get('engagement_score', 0) / 1000)
                trends_for_analysis.append({
                    'keyword': tweet.get('topic', ''),
                    'trend_score': engagement_score,
                    'velocity': 70,
                    'sentiment_score': 0,
                    'source': 'twitter'
                })
        
        # Prepare Amazon demand signals
        if amazon_data and amazon_data.get('demand_shifts'):
            for shift in amazon_data['demand_shifts'][:5]:
                trends_for_analysis.append({
                    'keyword': f"{shift['product']} ({shift['category']})",
                    'trend_score': min(100, shift['magnitude'] * 10),
                    'velocity': 80,
                    'sentiment_score': 50 if shift['direction'] == 'rising' else -50,
                    'source': 'amazon_ecommerce'
                })
        
        macro_shifts = self.macro_detector.detect_macro_shifts(trends_for_analysis)
        
        # Add government macro signals
        if gov_data and gov_data.get('macro_signals'):
            macro_shifts.extend(gov_data['macro_signals'])
        
        # Step 4: Aggregate sector signals
        print("\n📊 Step 4: Aggregating sector signals...")
        sector_signals = self.macro_detector.aggregate_sector_signals(macro_shifts)
        
        # Add Twitter sector data
        if twitter_sectors:
            for sector, data in twitter_sectors.items():
                if sector in sector_signals:
                    sector_signals[sector]['twitter_engagement'] = data['total_engagement']
                    sector_signals[sector]['twitter_hashtags'] = data['hashtag_count']
                else:
                    sector_signals[sector] = {
                        'count': data['hashtag_count'],
                        'avg_confidence': min(100, data['avg_engagement'] / 100),
                        'trend': 'bullish' if data['avg_engagement'] > 10000 else 'bearish',
                        'twitter_engagement': data['total_engagement'],
                        'twitter_hashtags': data['hashtag_count'],
                        'shifts': []
                    }
        
        # Step 5: Generate alerts
        print("\n⚠️ Step 5: Generating alerts...")
        alerts = self._generate_alerts(macro_shifts, sector_signals, reddit_sentiment, 
                                       news_sentiment, twitter_unusual, amazon_data, gov_data)
        
        # Compile results
        results = {
            'timestamp': datetime.now().isoformat(),
            'data_sources': {
                'google_trends': google_data[:15] if google_data else [],
                'reddit_trends': reddit_data[:10] if reddit_data else [],
                'news_headlines': news_data[:15] if news_data else [],
                'twitter_trends': twitter_data[:15] if twitter_data else [],
                'twitter_sectors': twitter_sectors,
                'amazon_bestsellers': amazon_data,
                'government_data': gov_data
            },
            'sentiment': {
                'reddit': reddit_sentiment,
                'news': news_sentiment
            },
            'macro_shifts': macro_shifts,
            'sector_signals': sector_signals,
            'alerts': alerts
        }
        
        self.all_trends = trends_for_analysis
        self.alerts = alerts
        
        # Print summary
        self._print_summary(results)
        
        return results
    
    def _generate_alerts(self, macro_shifts, sector_signals, reddit_sentiment, 
                         news_sentiment, twitter_unusual, amazon_data, gov_data):
        """Generate actionable alerts from all sources"""
        alerts = []
        
        # High-confidence macro shifts
        for shift in macro_shifts:
            if shift.get('confidence', 0) > 60:
                alerts.append({
                    'type': 'MACRO_SHIFT',
                    'severity': 'HIGH' if shift['confidence'] > 80 else 'MEDIUM',
                    'message': f"{shift.get('shift_type', 'Trend').replace('_', ' ').title()}: {shift.get('keyword', 'Unknown')}",
                    'confidence': shift['confidence'],
                    'stocks': shift.get('related_stocks', []),
                    'source': 'trend_analysis',
                    'timestamp': shift.get('timestamp', datetime.now().isoformat())
                })
        
        # Government macro signals
        if gov_data and gov_data.get('macro_signals'):
            for signal in gov_data['macro_signals'][:3]:
                alerts.append({
                    'type': signal['type'],
                    'severity': signal['severity'],
                    'message': signal['message'],
                    'confidence': 75 if signal['severity'] == 'HIGH' else 60,
                    'stocks': signal.get('related_sectors', []),
                    'source': 'government_data',
                    'timestamp': signal.get('timestamp', datetime.now().isoformat())
                })
        
        # Twitter unusual activity
        if twitter_unusual:
            for item in twitter_unusual[:3]:
                alerts.append({
                    'type': 'TWITTER_SPIKE',
                    'severity': 'MEDIUM',
                    'message': f"Twitter: {item['hashtag']} activity {item['spike_factor']}x normal",
                    'confidence': min(90, item['spike_factor'] * 20),
                    'source': 'twitter',
                    'timestamp': item.get('timestamp', datetime.now().isoformat())
                })
        
        # Amazon demand shifts
        if amazon_data and amazon_data.get('demand_shifts'):
            for shift in amazon_data['demand_shifts'][:3]:
                alerts.append({
                    'type': 'ECOMMERCE_DEMAND',
                    'severity': 'MEDIUM',
                    'message': f"Amazon: {shift['product']} rank {'↑' if shift['direction'] == 'rising' else '↓'} by {shift['magnitude']} positions",
                    'confidence': min(80, shift['magnitude'] * 10),
                    'source': 'amazon',
                    'timestamp': shift.get('timestamp', datetime.now().isoformat())
                })
        
        # Extreme sentiment alerts
        if reddit_sentiment.get('overall_score', 0) > 0.5:
            alerts.append({
                'type': 'SENTIMENT_SPIKE',
                'severity': 'MEDIUM',
                'message': f"Strong bullish sentiment on Reddit: {reddit_sentiment['overall_score']:.2f}",
                'confidence': 70,
                'source': 'reddit',
                'timestamp': datetime.now().isoformat()
            })
        elif reddit_sentiment.get('overall_score', 0) < -0.5:
            alerts.append({
                'type': 'SENTIMENT_SPIKE',
                'severity': 'HIGH',
                'message': f"Strong bearish sentiment on Reddit: {reddit_sentiment['overall_score']:.2f}",
                'confidence': 75,
                'source': 'reddit',
                'timestamp': datetime.now().isoformat()
            })
        
        return alerts
    
    def _print_summary(self, results):
        """Print comprehensive analysis summary"""
        print("\n" + "=" * 60)
        print("📊 COMPREHENSIVE TREND INTELLIGENCE SUMMARY")
        print("=" * 60)
        
        # Google Trends
        if results['data_sources']['google_trends']:
            print("\n🔥 Top 5 Google Trends:")
            for i, trend in enumerate(results['data_sources']['google_trends'][:5], 1):
                print(f"  {i}. {trend}")
        
        # Twitter trends
        if results['data_sources']['twitter_trends']:
            print("\n🐦 Top 5 Twitter Trends:")
            for i, trend in enumerate(results['data_sources']['twitter_trends'][:5], 1):
                print(f"  {i}. {trend.get('topic', 'N/A')} (Engagement: {trend.get('engagement_score', 0):,})")
        
        # Sentiment
        print(f"\n💭 Reddit Sentiment: {results['sentiment']['reddit'].get('overall_label', 'N/A')}")
        print(f"💭 News Sentiment: {results['sentiment']['news'].get('overall_label', 'N/A')}")
        
        # Macro shifts
        if results['macro_shifts']:
            print(f"\n🌍 {len(results['macro_shifts'])} Macro Shifts Detected:")
            for shift in results['macro_shifts'][:3]:
                print(f"  ⚠️ {shift.get('keyword', shift.get('message', 'Unknown'))} - {shift.get('shift_type', shift.get('type', 'N/A'))}")
        
        # Amazon demand
        if results['data_sources']['amazon_bestsellers']:
            amazon = results['data_sources']['amazon_bestsellers']
            if amazon.get('demand_shifts'):
                print(f"\n🛒 Top 3 Amazon Demand Shifts:")
                for shift in amazon['demand_shifts'][:3]:
                    direction = '📈' if shift['direction'] == 'rising' else '📉'
                    print(f"  {direction} {shift['product']} - {shift['rank_change']:+d} positions")
        
        # Government signals
        if results['data_sources']['government_data']:
            gov = results['data_sources']['government_data']
            if gov.get('macro_signals'):
                print(f"\n🏛️ {len(gov['macro_signals'])} Government Macro Signals:")
                for signal in gov['macro_signals'][:3]:
                    print(f"  [{signal['severity']}] {signal['message']}")
        
        # Alerts
        if results['alerts']:
            print(f"\n🚨 {len(results['alerts'])} Total Alerts Generated:")
            for alert in results['alerts'][:5]:
                source_tag = f"[{alert.get('source', 'unknown')[:4].upper()}]"
                print(f"  [{alert['severity']}] {source_tag} {alert['message']}")
        
        print("\n" + "=" * 60)

async def main():
    """Main entry point"""
    engine = TrendIntelligenceEngine()
    results = await engine.run_full_analysis()
    
    # Save results
    import json
    output_file = os.path.join(os.path.dirname(__file__), 'trend_results.json')
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to: {output_file}")
    return results

if __name__ == '__main__':
    asyncio.run(main())
