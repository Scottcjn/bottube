#!/usr/bin/env python3
"""Post the GPU giveaway announcement to X/Twitter.

Requires environment variables:
  TWITTER_CONSUMER_KEY
  TWITTER_CONSUMER_SECRET
  TWITTER_ACCESS_TOKEN
  TWITTER_ACCESS_TOKEN_SECRET
"""
import os
import tweepy
import sys

TWEET = """FREE GPU GIVEAWAY on BoTTube!

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

# Load Twitter credentials from environment
client = tweepy.Client(
    consumer_key=os.environ.get("TWITTER_CONSUMER_KEY", ""),
    consumer_secret=os.environ.get("TWITTER_CONSUMER_SECRET", ""),
    access_token=os.environ.get("TWITTER_ACCESS_TOKEN", ""),
    access_token_secret=os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", ""),
)

print(f"Tweet ({len(TWEET)} chars):")
print(TWEET)
print()

try:
    response = client.create_tweet(text=TWEET)
    print(f"Tweet posted! ID: {response.data['id']}")
    print(f"https://x.com/RustchainPOA/status/{response.data['id']}")
except tweepy.TooManyRequests as e:
    print(f"Rate limited: {e}")
    print("Try again later or check X rate limit window.")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
