"""
Sentiment Analysis Engine
NLP-based sentiment detection for trends and news
"""

import re
import numpy as np
from collections import Counter
from datetime import datetime

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    HAS_VADER = True
except:
    HAS_VADER = False

try:
    from textblob import TextBlob
    HAS_TEXTBLOB = True
except:
    HAS_TEXTBLOB = False

class SentimentAnalyzer:
    """Multi-engine sentiment analysis for financial text"""
    
    def __init__(self):
        self.vader = SentimentIntensityAnalyzer() if HAS_VADER else None
        # Financial sentiment keywords
        self.bullish_keywords = [
            'bullish', 'buy', 'long', 'upgrade', 'outperform', 'beat', 'growth',
            'profit', 'rally', 'surge', 'breakout', 'momentum', 'strong',
            'positive', 'optimistic', 'gains', 'higher', 'upside', 'opportunity'
        ]
        self.bearish_keywords = [
            'bearish', 'sell', 'short', 'downgrade', 'underperform', 'miss',
            'decline', 'crash', 'drop', 'weak', 'negative', 'pessimistic',
            'losses', 'lower', 'downside', 'risk', 'fear', 'recession', 'layoffs'
        ]
    
    def analyze_text(self, text, method='vader'):
        """Analyze sentiment of text"""
        if not text:
            return {'score': 0, 'label': 'neutral', 'confidence': 0}
        
        if method == 'vader' and self.vader:
            return self._vader_sentiment(text)
        elif method == 'textblob' and HAS_TEXTBLOB:
            return self._textblob_sentiment(text)
        else:
            return self._keyword_sentiment(text)
    
    def _vader_sentiment(self, text):
        """VADER sentiment analysis"""
        scores = self.vader.polarity_scores(text)
        compound = scores['compound']
        
        if compound >= 0.05:
            label = 'positive'
        elif compound <= -0.05:
            label = 'negative'
        else:
            label = 'neutral'
        
        return {
            'score': compound,
            'label': label,
            'confidence': abs(compound),
            'positive': scores['pos'],
            'negative': scores['neg'],
            'neutral': scores['neu']
        }
    
    def _textblob_sentiment(self, text):
        """TextBlob sentiment analysis"""
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        
        if polarity > 0.1:
            label = 'positive'
        elif polarity < -0.1:
            label = 'negative'
        else:
            label = 'neutral'
        
        return {
            'score': polarity,
            'label': label,
            'confidence': abs(polarity)
        }
    
    def _keyword_sentiment(self, text):
        """Simple keyword-based sentiment"""
        text_lower = text.lower()
        bullish_count = sum(1 for kw in self.bullish_keywords if kw in text_lower)
        bearish_count = sum(1 for kw in self.bearish_keywords if kw in text_lower)
        
        total = bullish_count + bearish_count
        if total == 0:
            return {'score': 0, 'label': 'neutral', 'confidence': 0}
        
        score = (bullish_count - bearish_count) / total
        
        return {
            'score': score,
            'label': 'positive' if score > 0.1 else 'negative' if score < -0.1 else 'neutral',
            'confidence': abs(score),
            'bullish_keywords': bullish_count,
            'bearish_keywords': bearish_count
        }
    
    def batch_analyze(self, texts):
        """Analyze sentiment for multiple texts"""
        results = []
        for text in texts:
            results.append(self.analyze_text(text))
        return results
    
    def aggregate_sentiment(self, texts):
        """Get aggregate sentiment across multiple texts"""
        sentiments = self.batch_analyze(texts)
        
        if not sentiments:
            return {'overall_score': 0, 'overall_label': 'neutral'}
        
        avg_score = np.mean([s['score'] for s in sentiments])
        positive_count = sum(1 for s in sentiments if s['label'] == 'positive')
        negative_count = sum(1 for s in sentiments if s['label'] == 'negative')
        
        if avg_score > 0.1:
            label = 'bullish'
        elif avg_score < -0.1:
            label = 'bearish'
        else:
            label = 'neutral'
        
        return {
            'overall_score': round(avg_score, 3),
            'overall_label': label,
            'positive_ratio': positive_count / len(sentiments),
            'negative_ratio': negative_count / len(sentiments),
            'neutral_ratio': 1 - (positive_count + negative_count) / len(sentiments),
            'total_texts': len(sentiments),
            'timestamp': datetime.now().isoformat()
        }
