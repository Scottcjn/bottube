#!/usr/bin/env python3
"""Optimized X/Twitter posting script based on open-source algorithm insights.

Key optimizations:
- Links go in FIRST REPLY (avoids -30-50% penalty)
- Engagement question in SECOND REPLY (drives 75x weighted replies)
- Supports threads for longer content
- Auto-replies to boost author engagement signals

Usage:
    python3 x_optimized_post.py "Your main tweet text" --link "https://bottube.ai" --question "What do you think?"
    python3 x_optimized_post.py --interactive

Environment variables (or use --env-file):
    TWITTER_CONSUMER_KEY
    TWITTER_CONSUMER_SECRET
    TWITTER_ACCESS_TOKEN
    TWITTER_ACCESS_TOKEN_SECRET
"""
import argparse
import os
import sys
import time
import tweepy

# Credentials from environment variables
# Set these in your shell or .env file:
#   TWITTER_CONSUMER_KEY
#   TWITTER_CONSUMER_SECRET
#   TWITTER_ACCESS_TOKEN
#   TWITTER_ACCESS_TOKEN_SECRET

# Algorithm-based best practices
ALGORITHM_TIPS = """
╔══════════════════════════════════════════════════════════════╗
║  X Algorithm Optimization Guide (from open-source code)      ║
╠══════════════════════════════════════════════════════════════╣
║  BOOST FACTORS:                                              ║
║    • Author replies to comments     = 75x weight             ║
║    • Profile visit + engagement     = 12x weight             ║
║    • 2+ min conversation dwell      = 10x weight             ║
║    • Retweets                       = 1x weight              ║
║    • Likes                          = 0.5x weight            ║
║                                                              ║
║  PENALTIES:                                                  ║
║    • Links in main tweet            = -30-50% reach          ║
║    • "Offensive" content            = -80% reach             ║
║    • Low Tweepcred (<0.65)          = only 3 tweets shown    ║
║                                                              ║
║  TIMING:                                                     ║
║    • First 30 mins are CRITICAL for distribution             ║
║    • Engage heavily immediately after posting                ║
╚══════════════════════════════════════════════════════════════╝
"""

def get_client():
    """Initialize Twitter client with credentials from environment."""
    consumer_key = os.environ.get("TWITTER_CONSUMER_KEY")
    consumer_secret = os.environ.get("TWITTER_CONSUMER_SECRET")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
    access_token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

    if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
        print("❌ Missing Twitter credentials. Set environment variables:")
        print("   TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET")
        print("   TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET")
        sys.exit(1)

    return tweepy.Client(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
    )


def post_optimized(main_text: str, link: str = None, question: str = None,
                   thread: list = None, dry_run: bool = False) -> dict:
    """
    Post an optimized tweet with link in reply (not main tweet).

    Args:
        main_text: The main tweet content (NO LINKS - they go in reply)
        link: URL to include in first reply (avoids algorithm penalty)
        question: Engagement question for second reply (drives comments)
        thread: Additional tweets to chain as a thread
        dry_run: If True, just preview without posting

    Returns:
        dict with tweet IDs and URLs
    """
    results = {"main": None, "link_reply": None, "question_reply": None, "thread": []}

    # Validate main tweet doesn't have links
    if "http://" in main_text or "https://" in main_text:
        print("⚠️  WARNING: Link detected in main tweet!")
        print("   This will reduce reach by 30-50%.")
        print("   Move the link to --link parameter instead.")
        print()

    if len(main_text) > 280:
        print(f"❌ Main tweet too long ({len(main_text)}/280 chars)")
        return results

    print("═" * 60)
    print("OPTIMIZED POST PREVIEW")
    print("═" * 60)
    print(f"\n📝 MAIN TWEET ({len(main_text)}/280 chars):")
    print(f"   {main_text}")

    if link:
        link_text = f"🔗 {link}"
        print(f"\n↳ REPLY 1 - Link ({len(link_text)}/280 chars):")
        print(f"   {link_text}")

    if question:
        print(f"\n↳ REPLY 2 - Engagement ({len(question)}/280 chars):")
        print(f"   {question}")

    if thread:
        for i, tweet in enumerate(thread):
            print(f"\n↳ THREAD {i+3} ({len(tweet)}/280 chars):")
            print(f"   {tweet}")

    print("\n" + "═" * 60)

    if dry_run:
        print("🔍 DRY RUN - No tweets posted")
        return results

    client = get_client()

    try:
        # 1. Post main tweet
        print("\n🚀 Posting main tweet...")
        response = client.create_tweet(text=main_text)
        main_id = response.data['id']
        results["main"] = {
            "id": main_id,
            "url": f"https://x.com/i/status/{main_id}"
        }
        print(f"   ✅ Posted: {results['main']['url']}")

        time.sleep(1)  # Small delay between tweets

        # 2. Post link as first reply (avoids penalty!)
        if link:
            print("\n🔗 Posting link reply...")
            link_text = f"🔗 {link}"
            response = client.create_tweet(text=link_text, in_reply_to_tweet_id=main_id)
            link_id = response.data['id']
            results["link_reply"] = {
                "id": link_id,
                "url": f"https://x.com/i/status/{link_id}"
            }
            print(f"   ✅ Posted: {results['link_reply']['url']}")
            time.sleep(1)

        # 3. Post engagement question as second reply
        if question:
            print("\n💬 Posting engagement question...")
            response = client.create_tweet(text=question, in_reply_to_tweet_id=main_id)
            q_id = response.data['id']
            results["question_reply"] = {
                "id": q_id,
                "url": f"https://x.com/i/status/{q_id}"
            }
            print(f"   ✅ Posted: {results['question_reply']['url']}")
            time.sleep(1)

        # 4. Post thread continuation
        last_id = main_id
        if thread:
            for i, tweet_text in enumerate(thread):
                print(f"\n📎 Posting thread [{i+1}/{len(thread)}]...")
                response = client.create_tweet(text=tweet_text, in_reply_to_tweet_id=last_id)
                t_id = response.data['id']
                results["thread"].append({
                    "id": t_id,
                    "url": f"https://x.com/i/status/{t_id}"
                })
                last_id = t_id
                print(f"   ✅ Posted: {results['thread'][-1]['url']}")
                time.sleep(1)

        print("\n" + "═" * 60)
        print("✅ ALL POSTS COMPLETE!")
        print("═" * 60)
        print("\n⏰ CRITICAL: Engage heavily in the next 30 minutes!")
        print("   Reply to any comments for 75x algorithm boost.")

    except tweepy.TooManyRequests as e:
        print(f"\n❌ Rate limited: {e}")
        print("   Wait 15 minutes and try again.")
    except Exception as e:
        print(f"\n❌ Error: {e}")

    return results


def interactive_mode():
    """Interactive posting wizard."""
    print(ALGORITHM_TIPS)
    print("\n🎯 INTERACTIVE POSTING MODE\n")

    main_text = input("📝 Main tweet (no links!): ").strip()
    if not main_text:
        print("❌ Main tweet required")
        return

    link = input("🔗 Link for reply (or Enter to skip): ").strip() or None
    question = input("💬 Engagement question (or Enter to skip): ").strip() or None

    thread = []
    print("\n📎 Add thread tweets (empty line to finish):")
    while True:
        t = input(f"   Thread [{len(thread)+1}]: ").strip()
        if not t:
            break
        thread.append(t)

    print("\n" + "-" * 40)
    confirm = input("Post this? [y/N/dry-run]: ").strip().lower()

    if confirm == 'y':
        post_optimized(main_text, link, question, thread if thread else None)
    elif confirm == 'dry-run' or confirm == 'd':
        post_optimized(main_text, link, question, thread if thread else None, dry_run=True)
    else:
        print("❌ Cancelled")


def main():
    parser = argparse.ArgumentParser(
        description="Post optimized tweets based on X's open-source algorithm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=ALGORITHM_TIPS
    )

    parser.add_argument("main_text", nargs="?", help="Main tweet text (no links)")
    parser.add_argument("--link", "-l", help="URL for first reply (avoids penalty)")
    parser.add_argument("--question", "-q", help="Engagement question for second reply")
    parser.add_argument("--thread", "-t", nargs="+", help="Additional thread tweets")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Preview without posting")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--tips", action="store_true", help="Show algorithm tips")
    parser.add_argument("--env-file", help="Load credentials from .env file")

    args = parser.parse_args()

    # Load env file if specified
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)

    if args.tips:
        print(ALGORITHM_TIPS)
        return

    if args.interactive or not args.main_text:
        interactive_mode()
        return

    post_optimized(
        main_text=args.main_text,
        link=args.link,
        question=args.question,
        thread=args.thread,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
