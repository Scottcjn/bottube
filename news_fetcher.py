#!/usr/bin/env python3
"""
RSS News Fetcher for The Daily Byte bot.

Fetches headlines from major news sources, deduplicates against
previously covered stories, and picks fresh stories for the anchor.
"""

import hashlib
import logging
import time

import feedparser

log = logging.getLogger("news-fetcher")

RSS_FEEDS = [
    {"name": "AP Top News", "url": "https://feeds.apnews.com/rss/apf-topnews"},
    {"name": "BBC World", "url": "http://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "Reuters", "url": "https://www.reutersagency.com/feed/"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
]

# Max age for a story to be considered "fresh" (6 hours)
MAX_STORY_AGE_SEC = 6 * 3600


def _story_hash(title):
    """Deterministic hash for deduplication."""
    return hashlib.sha256(title.strip().lower().encode()).hexdigest()[:16]


class NewsFetcher:
    def __init__(self, feeds=None):
        self.feeds = feeds or RSS_FEEDS

    def fetch_headlines(self, max_items=10):
        """Fetch headlines from all feeds.

        Returns list of dicts: [{title, summary, source, link, published, hash}, ...]
        sorted by recency (newest first).
        """
        stories = []
        seen_hashes = set()

        for feed_info in self.feeds:
            try:
                d = feedparser.parse(feed_info["url"])
                for entry in d.entries[:max_items]:
                    title = entry.get("title", "").strip()
                    if not title:
                        continue

                    h = _story_hash(title)
                    if h in seen_hashes:
                        continue
                    seen_hashes.add(h)

                    summary = entry.get("summary", entry.get("description", "")).strip()
                    # Strip HTML tags from summary
                    if "<" in summary:
                        import re
                        summary = re.sub(r"<[^>]+>", "", summary).strip()
                    # Truncate long summaries
                    if len(summary) > 500:
                        summary = summary[:497] + "..."

                    link = entry.get("link", "")

                    # Parse published time
                    published_parsed = entry.get("published_parsed")
                    if published_parsed:
                        published_ts = time.mktime(published_parsed)
                    else:
                        published_ts = time.time()

                    stories.append({
                        "title": title,
                        "summary": summary,
                        "source": feed_info["name"],
                        "link": link,
                        "published": published_ts,
                        "hash": h,
                    })
            except Exception as e:
                log.warning("Failed to fetch %s: %s", feed_info["name"], e)

        # Sort by recency
        stories.sort(key=lambda s: s["published"], reverse=True)
        return stories

    def pick_fresh_story(self, already_covered=None):
        """Pick a story not already covered, preferring recent ones.

        Args:
            already_covered: set of story hashes that have been used.

        Returns a story dict or None if nothing fresh.
        """
        already_covered = already_covered or set()
        now = time.time()
        stories = self.fetch_headlines(max_items=15)

        for story in stories:
            if story["hash"] in already_covered:
                continue
            age = now - story["published"]
            if age < MAX_STORY_AGE_SEC:
                return story

        # If no fresh stories within 6h, pick the newest uncovered one
        for story in stories:
            if story["hash"] not in already_covered:
                return story

        return None
