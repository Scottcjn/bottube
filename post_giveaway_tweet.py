#!/usr/bin/env python3
"""Post the GPU giveaway announcement to X/Twitter."""
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

client = tweepy.Client(
    consumer_key="apwa7XeSfXPcYXcP0lTyweaqe",
    consumer_secret="syAIe9PpVJL2aQFSiZZDtBcXgxZ1uHijtgKqF0wFzOZF6B6n6W",
    access_token="1944928465121124352-P9hVuOuZoR790uYL7IjG6nJvoWCLBO",
    access_token_secret="lAn1I9xwyvhJJJRvRtMnDXtWuMUzNcTdjWiRIzpPlQ9aH",
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
