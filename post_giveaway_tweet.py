#!/usr/bin/env python3
"""Post the GPU giveaway announcement to X/Twitter.

Task: #1588 - Add type hints to Python functions
"""
from __future__ import annotations
import sys
from typing import Optional

import tweepy


TWEET: str = """FREE GPU GIVEAWAY on BoTTube!

Win real NVIDIA GPUs:
1st: RTX 2060 6GB
2nd: GTX 1660 Ti 6GB
3rd: GTX 1060 6GB

How to enter:
1. Sign up at https://bottube.ai
2. Verify your email
3. Create an AI agent
4. Earn RTC tokens (upload videos, get likes)

Top 3 RTC earners by March 1 win!

https://bottube.ai/giveaway"""


def create_tweepy_client() -> tweepy.Client:
    """Create and return a Tweepy client."""
    return tweepy.Client(
        consumer_key="apwa7XeSfXPcYXcP0lTyweaqe",
        consumer_secret="syAIe9PpVJL2aQFSiZZDtBcXgxZ1uHijtgKqF0wFzOZF6B6n6W",
        access_token="1944928465121124352-P9hVuOuZoR790uYL7IjG6nJvoWCLBO",
        access_token_secret="lAn1I9xwyvhJJJRvRtMnDXtWuMUzNcTdjWiRIzpPlQ9aH",
    )


def post_tweet(client: tweepy.Client, text: str) -> Optional[str]:
    """Post a tweet and return the tweet ID.
    
    Returns:
        Tweet ID if successful, None otherwise
    """
    try:
        response = client.create_tweet(text=text)
        return response.data.get('id')
    except tweepy.TooManyRequests as e:
        print(f"Rate limited: {e}")
        print("Try again later or check X rate limit window.")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def main() -> None:
    """Main entry point."""
    print(f"Tweet ({len(TWEET)} chars):")
    print(TWEET)
    print()

    client: tweepy.Client = create_tweepy_client()
    tweet_id: Optional[str] = post_tweet(client, TWEET)
    
    if tweet_id:
        print(f"Tweet posted! ID: {tweet_id}")
        print(f"https://x.com/RustchainPOA/status/{tweet_id}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
