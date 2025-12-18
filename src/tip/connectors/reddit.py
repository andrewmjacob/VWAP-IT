"""Real Reddit connector for r/wallstreetbets and other finance subreddits."""
from __future__ import annotations

import logging
import re
from typing import Iterable, Dict, Any, List, Optional
from datetime import datetime, timezone

import requests

from tip.connectors.base import BaseConnector, ConnectorConfig
from tip.models import EventType

logger = logging.getLogger(__name__)

# Common stock ticker pattern
TICKER_PATTERN = re.compile(r'\$([A-Z]{1,5})\b|\b([A-Z]{2,5})\b')

# Filter out common words that look like tickers
TICKER_BLACKLIST = {
    "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HAD",
    "HER", "WAS", "ONE", "OUR", "OUT", "HAS", "HIS", "HOW", "MAN", "NEW",
    "NOW", "OLD", "SEE", "WAY", "WHO", "BOY", "DID", "GET", "HIM", "LET",
    "PUT", "SAY", "SHE", "TOO", "USE", "CEO", "CFO", "IPO", "USA", "FBI",
    "CIA", "GDP", "IMO", "TBH", "LOL", "WTF", "OMG", "FYI", "EOD", "ATH",
    "ATL", "DD", "YOLO", "FOMO", "HODL", "WSB", "GME", "AMC", "APE", "APES",
    "MOON", "HOLD", "BUY", "SELL", "CALL", "PUT", "ITM", "OTM", "IV", "DTE",
}


class RedditConnector(BaseConnector):
    """Connector for Reddit finance subreddits (r/wallstreetbets, r/stocks, etc.)."""
    
    def __init__(self, cfg: ConnectorConfig, s3, bus=None, subreddits: Optional[List[str]] = None):
        super().__init__(cfg, s3, bus)
        self.subreddits = subreddits or ["wallstreetbets"]
        self.user_agent = "TradingIntelPlatform/1.0"
        self.seen_ids: set = set()  # In-memory dedup for current run
    
    def fetch(self) -> Iterable[Dict[str, Any]]:
        """Fetch new posts from configured subreddits."""
        for subreddit in self.subreddits:
            try:
                posts = self._fetch_subreddit(subreddit, limit=25)
                for post in posts:
                    # Skip already seen in this run
                    if post["id"] in self.seen_ids:
                        continue
                    self.seen_ids.add(post["id"])
                    yield post
            except Exception as e:
                logger.error(f"Error fetching r/{subreddit}: {e}")
    
    def _fetch_subreddit(self, subreddit: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Fetch posts from a subreddit using Reddit's JSON API."""
        url = f"https://www.reddit.com/r/{subreddit}/new.json"
        headers = {"User-Agent": self.user_agent}
        params = {"limit": limit, "raw_json": 1}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        posts = []
        
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            posts.append({
                "id": post.get("id"),
                "subreddit": subreddit,
                "title": post.get("title", ""),
                "selftext": post.get("selftext", ""),
                "author": post.get("author"),
                "score": post.get("score", 0),
                "upvote_ratio": post.get("upvote_ratio", 0),
                "num_comments": post.get("num_comments", 0),
                "created_utc": post.get("created_utc"),
                "permalink": post.get("permalink"),
                "url": post.get("url"),
                "link_flair_text": post.get("link_flair_text"),
            })
        
        logger.info(f"Fetched {len(posts)} posts from r/{subreddit}")
        return posts
    
    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a Reddit post into a canonical event."""
        # Extract tickers from title and body
        text = f"{raw.get('title', '')} {raw.get('selftext', '')}"
        tickers = self._extract_tickers(text)
        primary_ticker = tickers[0] if tickers else None
        
        # Calculate severity based on engagement
        score = raw.get("score", 0)
        comments = raw.get("num_comments", 0)
        severity = min(100, int((score + comments * 2) / 50))
        
        # Confidence based on upvote ratio and engagement
        upvote_ratio = raw.get("upvote_ratio", 0.5)
        confidence = round(upvote_ratio * 0.7 + min(1.0, (score + comments) / 1000) * 0.3, 2)
        
        created_utc = raw.get("created_utc", datetime.now(timezone.utc).timestamp())
        
        return {
            "eventType": EventType.SOCIAL_MENTIONS,
            "symbol": primary_ticker,
            "entityId": raw.get("author"),
            "tsEvent": datetime.fromtimestamp(created_utc, tz=timezone.utc),
            "severity": severity,
            "confidence": confidence,
            "payload": {
                "postId": raw.get("id"),
                "subreddit": raw.get("subreddit"),
                "title": raw.get("title"),
                "text": raw.get("selftext", "")[:500],  # Truncate long posts
                "author": raw.get("author"),
                "score": raw.get("score"),
                "upvoteRatio": raw.get("upvote_ratio"),
                "numComments": raw.get("num_comments"),
                "flair": raw.get("link_flair_text"),
                "tickers": tickers,
                "url": f"https://reddit.com{raw.get('permalink', '')}",
            },
            "dedupeKey": f"reddit:{raw.get('subreddit')}:{raw.get('id')}",
        }
    
    def _extract_tickers(self, text: str) -> List[str]:
        """Extract potential stock tickers from text."""
        matches = TICKER_PATTERN.findall(text)
        tickers = []
        
        for match in matches:
            # match is a tuple from alternation groups
            ticker = match[0] or match[1]
            if ticker and ticker.upper() not in TICKER_BLACKLIST:
                ticker_upper = ticker.upper()
                if ticker_upper not in tickers:
                    tickers.append(ticker_upper)
        
        return tickers[:5]  # Limit to 5 tickers per post

