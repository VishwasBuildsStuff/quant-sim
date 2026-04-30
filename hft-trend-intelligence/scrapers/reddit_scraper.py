"""
Reddit Scraper
Monitors Reddit for trending financial discussions and sentiment shifts
across key subreddits relevant to Indian and global markets.
"""

import os
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from collections import defaultdict
import json

try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False


# Subreddits to monitor
SUBREDDITS = [
    'IndianStreetBets',
    'wallstreetbets',
    'investing',
    'stocks',
    'economy',
]

# Fallback: scrape Reddit web when API is unavailable
REDDIT_WEB_BASE = 'https://www.reddit.com/r/{}/hot.json'


class RedditScraper:
    """Scrapes Reddit for trending financial discussions and sentiment."""

    def __init__(self, use_praw=True):
        """
        Initialise the scraper.

        Parameters
        ----------
        use_praw : bool
            If True and praw is installed, attempt to use the Reddit API
            (requires client_id, client_secret in environment variables).
            Falls back to web scraping otherwise.
        """
        self.use_praw = use_praw and PRAW_AVAILABLE
        self.reddit = None
        self.posts = []
        self.sentiment_analyzer = None
        self._engagement_baselines = {}  # subreddit -> list of engagement scores

        if VADER_AVAILABLE:
            self.sentiment_analyzer = SentimentIntensityAnalyzer()

        if self.use_praw:
            self._init_praw()

    # ------------------------------------------------------------------ #
    #  PRAW initialisation
    # ------------------------------------------------------------------ #
    def _init_praw(self):
        """Initialise the PRAW Reddit instance from environment variables."""
        try:
            client_id = os.environ.get('REDDIT_CLIENT_ID', '')
            client_secret = os.environ.get('REDDIT_CLIENT_SECRET', '')
            user_agent = os.environ.get('REDDIT_USER_AGENT', 'hft-trend-intelligence/1.0')

            if not client_id or not client_secret:
                print("Warning: REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set. "
                      "Falling back to web scraping.")
                self.use_praw = False
                return

            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
            print("PRAW Reddit client initialised successfully.")
        except Exception as e:
            print(f"PRAW initialisation failed ({e}). Falling back to web scraping.")
            self.use_praw = False

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #
    def fetch_posts(self, subreddits=None, limit=50):
        """
        Fetch hot posts from the specified subreddits.

        Parameters
        ----------
        subreddits : list[str] or None
            List of subreddit names. Defaults to SUBREDDITS.
        limit : int
            Maximum posts per subreddit.

        Returns
        -------
        list[dict]
            Structured post data.
        """
        subreddits = subreddits or SUBREDDITS
        self.posts = []

        for sub in subreddits:
            try:
                if self.use_praw and self.reddit:
                    posts = self._fetch_via_praw(sub, limit)
                else:
                    posts = self._fetch_via_web(sub, limit)

                for post in posts:
                    post['subreddit'] = sub
                    post['fetched_at'] = datetime.now().isoformat()
                    post['engagement_score'] = self._engagement_score(post)
                    post['sentiment'] = self._analyse_sentiment(post.get('title', '') + ' ' + post.get('selftext', ''))

                self.posts.extend(posts)
                print(f"  Fetched {len(posts)} posts from r/{sub}")
                time.sleep(1)  # polite delay
            except Exception as e:
                print(f"Error fetching r/{sub}: {e}")

        print(f"Total posts collected: {len(self.posts)}")
        return self.posts

    def detect_spikes(self, spike_threshold=10.0):
        """
        Detect posts whose engagement is >= *spike_threshold* times the
        rolling median for their subreddit.

        Parameters
        ----------
        spike_threshold : float
            Multiplier above the baseline median that qualifies as a spike.

        Returns
        -------
        list[dict]
            Posts flagged as unusual activity spikes.
        """
        if not self.posts:
            print("No posts collected yet. Call fetch_posts() first.")
            return []

        # Update baselines
        for sub in set(p['subreddit'] for p in self.posts):
            sub_posts = [p for p in self.posts if p['subreddit'] == sub]
            scores = [p['engagement_score'] for p in sub_posts]
            self._engagement_baselines[sub] = scores

        spikes = []
        for post in self.posts:
            sub = post['subreddit']
            baseline = self._engagement_baselines.get(sub, [])
            if not baseline:
                continue
            median_score = sorted(baseline)[len(baseline) // 2]
            if median_score > 0 and post['engagement_score'] >= spike_threshold * median_score:
                post['spike_ratio'] = round(post['engagement_score'] / median_score, 2)
                spikes.append(post)

        print(f"Detected {len(spikes)} engagement spikes (threshold={spike_threshold}x)")
        return spikes

    def get_trending_topics(self, top_n=20):
        """
        Return the top trending topics sorted by engagement score.

        Parameters
        ----------
        top_n : int
            Number of top topics to return.

        Returns
        -------
        list[dict]
        """
        if not self.posts:
            print("No posts collected yet. Call fetch_posts() first.")
            return []

        sorted_posts = sorted(self.posts, key=lambda p: p.get('engagement_score', 0), reverse=True)
        return sorted_posts[:top_n]

    def summary(self):
        """Print a human-readable summary."""
        if not self.posts:
            print("No posts to summarise.")
            return

        print("\n" + "=" * 60)
        print("REDDIT TRENDING TOPICS SUMMARY")
        print("=" * 60)

        for i, post in enumerate(self.get_trending_topics(10), 1):
            sentiment_label = post.get('sentiment', {}).get('label', 'neutral')
            print(f"  {i}. [{post['subreddit']}] {post['title']}")
            print(f"     Upvotes: {post['upvotes']} | Comments: {post['comment_count']} "
                  f"| Engagement: {post['engagement_score']:.0f} | Sentiment: {sentiment_label}")

        spikes = self.detect_spikes()
        if spikes:
            print(f"\n  Spike alerts: {len(spikes)} post(s) with unusual engagement")
            for s in spikes[:5]:
                print(f"    - r/{s['subreddit']}: {s['title']} (spike ratio: {s.get('spike_ratio', 'N/A')}x)")

        print("=" * 60)

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #
    def _fetch_via_praw(self, subreddit, limit):
        """Fetch hot posts using PRAW."""
        posts = []
        try:
            for submission in self.reddit.subreddit(subreddit).hot(limit=limit):
                posts.append({
                    'title': submission.title,
                    'selftext': submission.selftext[:500],  # truncate
                    'upvotes': submission.score,
                    'comment_count': submission.num_comments,
                    'url': f"https://reddit.com{submission.permalink}",
                    'created_utc': datetime.utcfromtimestamp(submission.created_utc).isoformat(),
                    'author': str(submission.author),
                    'awards': submission.total_awards_received,
                })
        except Exception as e:
            print(f"PRAW error on r/{subreddit}: {e}")
        return posts

    def _fetch_via_web(self, subreddit, limit):
        """
        Fetch hot posts by hitting Reddit's public JSON endpoint.
        This does NOT require authentication but is rate-limited.
        """
        url = REDDIT_WEB_BASE.format(subreddit)
        params = {'limit': limit}
        headers = {'User-Agent': 'hft-trend-intelligence/1.0'}

        posts = []
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for child in data.get('data', {}).get('children', []):
                d = child.get('data', {})
                posts.append({
                    'title': d.get('title', ''),
                    'selftext': d.get('selftext', '')[:500],
                    'upvotes': d.get('score', 0),
                    'comment_count': d.get('num_comments', 0),
                    'url': f"https://reddit.com{d.get('permalink', '')}",
                    'created_utc': datetime.utcfromtimestamp(d.get('created_utc', 0)).isoformat(),
                    'author': d.get('author', '[deleted]'),
                    'awards': len(d.get('all_awardings', [])),
                })
        except requests.exceptions.RequestException as e:
            print(f"Web scrape error on r/{subreddit}: {e}")
        except (ValueError, KeyError) as e:
            print(f"JSON parse error on r/{subreddit}: {e}")

        return posts

    @staticmethod
    def _engagement_score(post):
        """Simple engagement score = upvotes + 2 * comments + 5 * awards."""
        return (post.get('upvotes', 0)
                + 2 * post.get('comment_count', 0)
                + 5 * post.get('awards', 0))

    def _analyse_sentiment(self, text):
        """
        Return a sentiment dict using VADER if available, else a simple
        keyword heuristic.
        """
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

        # Fallback keyword heuristic
        text_lower = text.lower()
        pos_words = {'bull', 'buy', 'rally', 'surge', 'gain', 'profit', 'moon', 'long'}
        neg_words = {'bear', 'sell', 'crash', 'dump', 'loss', 'short', 'bleed', 'down'}
        pos_count = sum(1 for w in pos_words if w in text_lower)
        neg_count = sum(1 for w in neg_words if w in text_lower)
        if pos_count > neg_count:
            label = 'positive'
        elif neg_count > pos_count:
            label = 'negative'
        else:
            label = 'neutral'
        return {'compound': 0.0, 'label': label}

    def to_dataframe(self):
        """Return posts as a pandas DataFrame."""
        import pandas as pd
        if not self.posts:
            return pd.DataFrame()
        return pd.DataFrame(self.posts)

    def save_json(self, filepath):
        """Save collected posts to a JSON file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.posts, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(self.posts)} posts to {filepath}")


if __name__ == '__main__':
    print("=" * 60)
    print("Reddit Scraper - Test Run")
    print("=" * 60)

    scraper = RedditScraper(use_praw=True)

    # Fetch posts from all monitored subreddits
    print("\nFetching posts...")
    scraper.fetch_posts(subreddits=['wallstreetbets', 'IndianStreetBets'], limit=25)

    # Show trending topics
    print("\nTop Trending Topics:")
    for i, post in enumerate(scraper.get_trending_topics(10), 1):
        print(f"  {i}. [{post['subreddit']}] {post['title']}")
        print(f"     Score: {post['engagement_score']:.0f} | "
              f"Sentiment: {post['sentiment']['label']}")

    # Detect spikes
    scraper.detect_spikes(spike_threshold=10.0)

    # Full summary
    scraper.summary()

    # Optional: save results
    output_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'reddit_posts.json')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    scraper.save_json(output_path)
