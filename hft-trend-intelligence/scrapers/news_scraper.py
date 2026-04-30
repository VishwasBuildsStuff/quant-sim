"""
News Scraper
Collects financial news headlines from Indian and global sources,
performs keyword frequency analysis, and detects unusual activity spikes.
"""

import os
import re
import time
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

try:
    from newsapi import NewsApiClient
    NEWSAPI_AVAILABLE = True
except ImportError:
    NEWSAPI_AVAILABLE = False

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False


# Financial news sources to scrape (fallback web scraping)
NEWS_SOURCES = [
    {
        'name': 'MoneyControl',
        'url': 'https://www.moneycontrol.com/news/technical-call/',
        'headline_selector': 'a[href*="moneycontrol.com/news/"]',
    },
    {
        'name': 'Economic Times',
        'url': 'https://economictimes.indiatimes.com/markets',
        'headline_selector': 'h3, a[href*="economictimes.indiatimes.com/"]',
    },
    {
        'name': 'Reuters India',
        'url': 'https://www.reuters.com/world/india/',
        'headline_selector': 'h3, a[data-testid="Heading"]',
    },
    {
        'name': 'Bloomberg Quint',
        'url': 'https://www.ndtvprofit.com/markets',
        'headline_selector': 'h3, a[href*="ndtvprofit.com/"]',
    },
]

# Common finance-related keywords for frequency analysis
FINANCE_KEYWORDS = [
    ' RBI', 'interest rate', 'inflation', 'GDP', 'bank', 'stock', 'market',
    'Sensex', 'Nifty', 'IPO', 'mutual fund', 'dividend', 'earnings', 'profit',
    'loss', 'revenue', 'budget', 'fiscal', 'tax', 'FDI', 'rupee', 'dollar',
    'crude', 'gold', 'oil', 'gas', 'EV', 'electric vehicle', 'semiconductor',
    'AI', 'artificial intelligence', 'startup', 'funding', 'valuation',
    'merger', 'acquisition', 'SEBI', 'IRDAI', 'NPA', 'credit', 'loan',
    'housing', 'real estate', 'infrastructure', 'defence', 'railway',
]


class NewsScraper:
    """Scrapes financial news headlines and performs keyword analysis."""

    def __init__(self, use_newsapi=True):
        """
        Initialise the scraper.

        Parameters
        ----------
        use_newsapi : bool
            If True and newsapi-python is installed with a valid API key,
            use the News API. Falls back to web scraping otherwise.
        """
        self.use_newsapi = use_newsapi and NEWSAPI_AVAILABLE
        self.newsapi_client = None
        self.articles = []
        self.keyword_history = defaultdict(list)  # keyword -> list of counts over time
        self.sentiment_analyzer = None

        if VADER_AVAILABLE:
            self.sentiment_analyzer = SentimentIntensityAnalyzer()

        if self.use_newsapi:
            self._init_newsapi()

    # ------------------------------------------------------------------ #
    #  NewsAPI initialisation
    # ------------------------------------------------------------------ #
    def _init_newsapi(self):
        api_key = os.environ.get('NEWSAPI_KEY', '')
        if not api_key:
            print("Warning: NEWSAPI_KEY not set. Falling back to web scraping.")
            self.use_newsapi = False
            return
        try:
            self.newsapi_client = NewsApiClient(api_key=api_key)
            print("NewsAPI client initialised successfully.")
        except Exception as e:
            print(f"NewsAPI initialisation failed ({e}). Falling back to web scraping.")
            self.use_newsapi = False

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #
    def fetch_headlines(self, query='finance India', sources=None, max_results=50):
        """
        Fetch financial news headlines.

        Parameters
        ----------
        query : str
            Search query for News API.
        sources : list[dict] or None
            List of source dicts for web scraping fallback.
            Defaults to NEWS_SOURCES.
        max_results : int
            Maximum articles to collect.

        Returns
        -------
        list[dict]
        """
        self.articles = []

        if self.use_newsapi and self.newsapi_client:
            self.articles = self._fetch_via_newsapi(query, max_results)

        # If NewsAPI returned nothing or is disabled, fall back to scraping
        if not self.articles:
            self.articles = self._fetch_via_web(sources or NEWS_SOURCES, max_results)

        # Enrich articles with sentiment and keyword data
        for article in self.articles:
            article['sentiment'] = self._analyse_sentiment(article.get('headline', ''))
            article['keywords'] = self._extract_keywords(article.get('headline', ''))
            article['fetched_at'] = datetime.now().isoformat()

        print(f"Total articles collected: {len(self.articles)}")
        return self.articles

    def analyse_keyword_frequency(self, keywords=None):
        """
        Perform keyword frequency analysis on collected articles.

        Parameters
        ----------
        keywords : list[str] or None
            Keywords to track. Defaults to FINANCE_KEYWORDS.

        Returns
        -------
        dict
            Mapping of keyword -> count across all articles.
        """
        keywords = [k.strip().lower() for k in (keywords or FINANCE_KEYWORDS)]
        frequency = Counter()

        for article in self.articles:
            text = (article.get('headline', '') + ' ' + article.get('description', '')).lower()
            for kw in keywords:
                if kw.lower() in text:
                    frequency[kw] += 1

        # Store in history for spike detection
        timestamp = datetime.now().isoformat()
        for kw, count in frequency.items():
            self.keyword_history[kw].append({'timestamp': timestamp, 'count': count})

        return dict(frequency.most_common())

    def detect_keyword_spikes(self, spike_threshold=3.0):
        """
        Detect keywords whose current frequency is >= *spike_threshold* times
        the historical average.

        Parameters
        ----------
        spike_threshold : float
            Multiplier above the historical average that qualifies as a spike.

        Returns
        -------
        dict
            Keyword -> {'current': count, 'average': float, 'spike_ratio': float}
        """
        spikes = {}
        for kw, history in self.keyword_history.items():
            if len(history) < 2:
                continue
            current = history[-1]['count']
            past_counts = [h['count'] for h in history[:-1]]
            avg = sum(past_counts) / len(past_counts) if past_counts else 0

            if avg > 0 and current >= spike_threshold * avg:
                spikes[kw] = {
                    'current': current,
                    'average': round(avg, 2),
                    'spike_ratio': round(current / avg, 2),
                }
            elif avg == 0 and current > 0:
                spikes[kw] = {
                    'current': current,
                    'average': 0,
                    'spike_ratio': float('inf'),
                }

        print(f"Detected {len(spikes)} keyword spikes (threshold={spike_threshold}x)")
        return spikes

    def summary(self):
        """Print a human-readable summary."""
        if not self.articles:
            print("No articles to summarise.")
            return

        print("\n" + "=" * 60)
        print("FINANCIAL NEWS HEADLINES SUMMARY")
        print("=" * 60)

        for i, article in enumerate(self.articles[:15], 1):
            sentiment_label = article.get('sentiment', {}).get('label', 'neutral')
            print(f"  {i}. [{article.get('source', 'Unknown')}] {article['headline']}")
            print(f"     Time: {article.get('timestamp', 'N/A')} | Sentiment: {sentiment_label}")

        # Keyword frequency
        print("\nKeyword Frequency:")
        freq = self.analyse_keyword_frequency()
        for kw, count in list(freq.items())[:15]:
            print(f"  {kw}: {count}")

        # Spikes
        spikes = self.detect_keyword_spikes()
        if spikes:
            print("\nKeyword Spikes:")
            for kw, info in spikes.items():
                print(f"  {kw}: current={info['current']}, avg={info['average']}, "
                      f"ratio={info['spike_ratio']}x")

        print("=" * 60)

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #
    def _fetch_via_newsapi(self, query, max_results):
        """Fetch articles using NewsAPI."""
        articles = []
        try:
            result = self.newsapi_client.get_everything(
                q=query,
                language='en',
                sort_by='publishedAt',
                page_size=max_results,
            )
            for article in result.get('articles', []):
                articles.append({
                    'headline': article.get('title', ''),
                    'description': article.get('description', ''),
                    'url': article.get('url', ''),
                    'source': article.get('source', {}).get('name', 'Unknown'),
                    'timestamp': article.get('publishedAt', ''),
                    'content': (article.get('content', '') or '')[:500],
                })
            print(f"Fetched {len(articles)} articles via NewsAPI.")
        except Exception as e:
            print(f"NewsAPI error: {e}")
        return articles

    def _fetch_via_web(self, sources, max_results):
        """
        Scrape financial news sites directly.
        Uses a simple heuristic approach since many sites require JS rendering.
        """
        articles = []
        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            )
        }

        for source in sources:
            if len(articles) >= max_results:
                break
            try:
                url = source['url']
                resp = requests.get(url, headers=headers, timeout=15)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, 'lxml')

                # Strategy 1: use the specified selector
                elements = soup.select(source.get('headline_selector', 'h1, h2, h3'))
                found = 0

                for el in elements:
                    if len(articles) >= max_results:
                        break

                    # Get the headline text
                    if el.name == 'a':
                        headline = el.get_text(strip=True)
                        link = el.get('href', '')
                    else:
                        headline = el.get_text(strip=True)
                        parent_link = el.find_parent('a')
                        link = parent_link.get('href', '') if parent_link else ''

                    # Filter: must be reasonably long and look like a headline
                    if len(headline) < 20:
                        continue

                    # Normalise relative URLs
                    if link and not link.startswith('http'):
                        from urllib.parse import urljoin
                        link = urljoin(url, link)

                    articles.append({
                        'headline': headline,
                        'description': '',
                        'url': link,
                        'source': source['name'],
                        'timestamp': datetime.now().isoformat(),
                        'content': '',
                    })
                    found += 1

                print(f"  Scraped {found} headlines from {source['name']}")
                time.sleep(1)  # polite delay
            except requests.exceptions.RequestException as e:
                print(f"  Failed to scrape {source['name']}: {e}")
            except Exception as e:
                print(f"  Error processing {source['name']}: {e}")

        return articles

    def _analyse_sentiment(self, text):
        """Return sentiment dict using VADER or fallback heuristic."""
        if self.sentiment_analyzer and text.strip():
            scores = self.sentiment_analyzer.polarity_scores(text)
            compound = scores['compound']
            if compound >= 0.05:
                label = 'positive'
            elif compound <= -0.05:
                label = 'negative'
            else:
                label = 'neutral'
            return {'compound': compound, 'label': label, **scores}

        # Fallback heuristic
        text_lower = text.lower()
        pos_words = {'rise', 'gain', 'rally', 'bull', 'growth', 'surge', 'profit', 'up'}
        neg_words = {'fall', 'crash', 'bear', 'loss', 'decline', 'dump', 'down', 'slump'}
        pos_count = sum(1 for w in pos_words if w in text_lower)
        neg_count = sum(1 for w in neg_words if w in text_lower)
        if pos_count > neg_count:
            label = 'positive'
        elif neg_count > pos_count:
            label = 'negative'
        else:
            label = 'neutral'
        return {'compound': 0.0, 'label': label}

    def _extract_keywords(self, text):
        """Extract finance-related keywords from text."""
        text_lower = text.lower()
        found = []
        for kw in FINANCE_KEYWORDS:
            if kw.strip().lower() in text_lower:
                found.append(kw.strip())
        return found

    def to_dataframe(self):
        """Return articles as a pandas DataFrame."""
        import pandas as pd
        if not self.articles:
            return pd.DataFrame()
        return pd.DataFrame(self.articles)

    def save_json(self, filepath):
        """Save collected articles to a JSON file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.articles, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(self.articles)} articles to {filepath}")


if __name__ == '__main__':
    print("=" * 60)
    print("News Scraper - Test Run")
    print("=" * 60)

    scraper = NewsScraper(use_newsapi=True)

    # Fetch headlines
    print("\nFetching financial news headlines...")
    scraper.fetch_headlines(query='Indian stock market finance', max_results=30)

    # Show headlines
    print(f"\nCollected {len(scraper.articles)} headlines:")
    for i, article in enumerate(scraper.articles[:10], 1):
        print(f"  {i}. [{article['source']}] {article['headline']}")

    # Keyword frequency analysis
    print("\nKeyword Frequency Analysis:")
    freq = scraper.analyse_keyword_frequency()
    for kw, count in list(freq.items())[:10]:
        print(f"  {kw}: {count}")

    # Detect spikes (requires multiple runs to build history)
    print("\nKeyword Spike Detection:")
    spikes = scraper.detect_keyword_spikes()
    if spikes:
        for kw, info in spikes.items():
            print(f"  {kw}: ratio={info['spike_ratio']}x")
    else:
        print("  No spikes detected (need multiple data points).")

    # Full summary
    scraper.summary()

    # Optional: save results
    output_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'news_articles.json')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    scraper.save_json(output_path)
