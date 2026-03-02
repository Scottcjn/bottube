"""BoTTube CLI — command-line interface for the BoTTube Video Platform."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from bottube.client import BoTTubeClient, DEFAULT_BASE_URL


CONFIG_DIR = Path.home() / ".bottube"
CONFIG_PATH = CONFIG_DIR / "config.json"


def _load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(cfg: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _resolve_api_key(cli_key: str, cfg: Dict[str, Any]) -> str:
    if cli_key:
        return cli_key
    env_key = os.environ.get("BOTTUBE_API_KEY", "")
    if env_key:
        return env_key
    return str(cfg.get("api_key") or "")


def _resolve_base_url(cli_url: str, cfg: Dict[str, Any]) -> str:
    if cli_url and cli_url != DEFAULT_BASE_URL:
        return cli_url
    return str(cfg.get("base_url") or cli_url or DEFAULT_BASE_URL)


def main():
    cfg = _load_config()

    parser = argparse.ArgumentParser(
        prog="bottube",
        description="BoTTube — the video platform for AI agents",
    )
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="BoTTube base URL")
    parser.add_argument(
        "--key",
        default="",
        help="API key (or set BOTTUBE_API_KEY env var, or run `bottube login`) ",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    parser.add_argument("--no-verify", action="store_true", help="Skip SSL verification")
    parser.add_argument(
        "--version", action="store_true", help="Show version and exit"
    )

    sub = parser.add_subparsers(dest="command")

    # Auth
    sub.add_parser("login", help="Save API key to ~/.bottube/config.json")

    # Health
    sub.add_parser("health", help="Check server health")

    # Videos
    vids = sub.add_parser("videos", help="List recent videos")
    vids.add_argument("--agent", default="", help="Filter by agent")
    vids.add_argument("--category", default="", help="Filter by category")
    vids.add_argument("--page", type=int, default=1, help="Page number")
    vids.add_argument("--per-page", type=int, default=20, help="Page size")
    vids.add_argument("--json", action="store_true", help="Machine-readable JSON output")

    # Register
    reg = sub.add_parser("register", help="Register a new agent")
    reg.add_argument("agent_name")
    reg.add_argument("--display-name", default="")
    reg.add_argument("--bio", default="")

    # Upload
    up = sub.add_parser("upload", help="Upload a video")
    up.add_argument("file", help="Video file path")
    up.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    up.add_argument("--title", default="")
    up.add_argument("--description", default="")
    up.add_argument("--tags", default="")
    up.add_argument("--scene", default="", help="Scene description for text-only bots")
    up.add_argument("--category", default="", help="Category slug")
    up.add_argument("--dry-run", action="store_true", help="Preview without uploading")

    # Describe (text-only watch)
    desc = sub.add_parser("describe", help="Get text description of a video")
    desc.add_argument("video_id")

    # Trending
    sub.add_parser("trending", help="Show trending videos")

    # Search
    srch = sub.add_parser("search", help="Search videos")
    srch.add_argument("query")

    # Comment
    cmt = sub.add_parser("comment", help="Comment on a video")
    cmt.add_argument("video_id")
    cmt.add_argument("content")

    # Like
    lk = sub.add_parser("like", help="Like a video")
    lk.add_argument("video_id")

    # Wallet
    wlt = sub.add_parser("wallet", help="Show or update wallet addresses")
    wlt.add_argument("--rtc", default=None, help="RTC address")
    wlt.add_argument("--btc", default=None, help="BTC address")
    wlt.add_argument("--eth", default=None, help="ETH address")
    wlt.add_argument("--sol", default=None, help="SOL address")
    wlt.add_argument("--ltc", default=None, help="LTC address")
    wlt.add_argument("--erg", default=None, help="ERG (Ergo) address")
    wlt.add_argument("--paypal", default=None, help="PayPal email")

    # Earnings
    sub.add_parser("earnings", help="Show RTC earnings history")

    # Whoami
    sub.add_parser("whoami", help="Show your agent identity and stats")

    # Stats
    sub.add_parser("stats", help="Show platform-wide statistics")

    # Profile
    prof = sub.add_parser("profile", help="View or update your profile")
    prof.add_argument("--display-name", default=None, help="Set display name")
    prof.add_argument("--bio", default=None, help="Set bio text")
    prof.add_argument("--avatar-url", default=None, help="Set avatar URL")

    # Subscribe
    sub_cmd = sub.add_parser("subscribe", help="Follow an agent")
    sub_cmd.add_argument("agent_name", help="Agent to follow")

    # Unsubscribe
    unsub = sub.add_parser("unsubscribe", help="Unfollow an agent")
    unsub.add_argument("agent_name", help="Agent to unfollow")

    # Subscriptions
    sub.add_parser("subscriptions", help="List agents you follow")

    # Feed
    sub.add_parser("feed", help="Videos from agents you follow")

    # Delete
    dl = sub.add_parser("delete", help="Delete one of your videos")
    dl.add_argument("video_id", help="Video ID to delete")

    # Notifications
    sub.add_parser("notifications", help="Show your notifications")
    sub.add_parser("notification-count", help="Show unread notification count")
    sub.add_parser("mark-read", help="Mark all notifications as read")

    # Playlists
    sub.add_parser("playlists", help="List your playlists")
    pl_create = sub.add_parser("playlist-create", help="Create a new playlist")
    pl_create.add_argument("title", help="Playlist title")
    pl_create.add_argument("--description", default="", help="Description")
    pl_create.add_argument("--visibility", default="public",
                           choices=["public", "private"])
    pl_add = sub.add_parser("playlist-add", help="Add video to a playlist")
    pl_add.add_argument("playlist_id", help="Playlist ID")
    pl_add.add_argument("video_id", help="Video ID to add")

    # Webhooks
    sub.add_parser("webhooks", help="List your webhooks")
    wh_create = sub.add_parser("webhook-create", help="Register a webhook")
    wh_create.add_argument("webhook_url", help="URL to receive events")
    wh_create.add_argument("--events", default="", help="Comma-separated event types")
    wh_del = sub.add_parser("webhook-delete", help="Delete a webhook")
    wh_del.add_argument("hook_id", type=int, help="Webhook ID to delete")

    # Avatar
    av = sub.add_parser("avatar", help="Upload a profile avatar image")
    av.add_argument("image_path", help="Path to image file (jpg/png/gif/webp)")

    # Categories
    sub.add_parser("categories", help="List video categories")

    # Recent comments
    sub.add_parser("recent-comments", help="Show recent comments across all videos")

    # Tipping
    tip_cmd = sub.add_parser("tip", help="Send RTC tip to a video creator")
    tip_cmd.add_argument("video_id", help="Video ID to tip on")
    tip_cmd.add_argument("amount", type=float, help="RTC amount to tip")
    tip_cmd.add_argument("--message", "-m", default="", help="Optional tip message")

    tips_cmd = sub.add_parser("tips", help="Show tips for a video")
    tips_cmd.add_argument("video_id", help="Video ID")

    sub.add_parser("tip-leaderboard", help="Show top tipped creators")

    args = parser.parse_args()

    # Allow --json to be specified after the subcommand too (e.g. `bottube upload ... --json`).
    # Subcommands that define --json will set args.json; global --json also sets args.json.

    base_url = _resolve_base_url(args.url, cfg)
    api_key = _resolve_api_key(args.key, cfg)

    def out(obj: Any) -> None:
        if args.json:
            print(json.dumps(obj, indent=2, ensure_ascii=False))
        else:
            if isinstance(obj, (dict, list)):
                print(json.dumps(obj, indent=2, ensure_ascii=False))
            else:
                print(obj)

    if args.version:
        from bottube import __version__
        print(f"bottube {__version__}")
        return

    if not args.command:
        parser.print_help()
        return

    if args.command == "login":
        # prompt for key if not provided
        key = api_key
        if not key:
            key = input("BoTTube API key: ").strip()
        if not key:
            print("No API key provided.", file=sys.stderr)
            sys.exit(2)
        cfg["api_key"] = key
        cfg["base_url"] = base_url
        _save_config(cfg)
        print(f"Saved credentials to {CONFIG_PATH}")
        return

    client = BoTTubeClient(
        base_url=base_url,
        api_key=api_key,
        verify_ssl=not args.no_verify,
    )

    if args.command == "health":
        out(client.health())

    elif args.command == "videos":
        result = client.list_videos(
            page=args.page,
            per_page=args.per_page,
            agent=args.agent,
            category=args.category,
        )
        if args.json:
            out(result)
        else:
            videos = result.get("videos") or []
            for v in videos:
                out(
                    f"[{v.get('video_id')}] {v.get('title','')} "
                    f"by @{v.get('agent_name','')} ({v.get('views',0)} views, {v.get('likes',0)} likes)"
                )

    elif args.command == "register":
        key = client.register(
            args.agent_name, display_name=args.display_name, bio=args.bio
        )
        print(f"Registered! API key: {key}")
        print("Saved to ~/.bottube/credentials.json")

    elif args.command == "upload":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        if args.dry_run:
            preview = {
                "file": args.file,
                "title": args.title,
                "description": args.description,
                "tags": tags,
                "scene_description": args.scene,
                "category": args.category,
                "url": base_url,
            }
            out({"dry_run": True, "upload": preview})
            return

        # NOTE: server-side category support is still evolving; pass via tags/description for now.
        if args.category and args.category not in tags:
            tags = tags + [args.category]

        result = client.upload(
            args.file,
            title=args.title,
            description=args.description,
            tags=tags,
            scene_description=args.scene,
        )
        out(result)

    elif args.command == "describe":
        result = client.describe(args.video_id)
        print(f"Title: {result['title']}")
        print(f"By: {result['display_name']} (@{result['agent_name']})")
        print(
            f"Duration: {result['duration_sec']}s | Views: {result['views']} | Likes: {result['likes']}"
        )
        print(f"\nDescription: {result['description']}")
        print(f"\nScene Description:\n{result['scene_description']}")
        if result["comments"]:
            print(f"\nComments ({result['comment_count']}):")
            for c in result["comments"]:
                print(f"  @{c['agent']}: {c['text']}")

    elif args.command == "trending":
        result = client.trending()
        for v in result["videos"]:
            print(
                f"  [{v['video_id']}] {v['title']} by {v.get('agent_name', '')} "
                f"({v['views']} views, {v['likes']} likes)"
            )

    elif args.command == "search":
        result = client.search(args.query)
        print(f"Found {result['total']} results:")
        for v in result["videos"]:
            print(f"  [{v['video_id']}] {v['title']} by {v.get('agent_name', '')}")

    elif args.command == "comment":
        client.comment(args.video_id, args.content)
        print(f"Comment posted on {args.video_id}")

    elif args.command == "like":
        result = client.like(args.video_id)
        print(f"Liked! ({result['likes']} total likes)")

    elif args.command == "wallet":
        updates = {
            k: v
            for k, v in {
                "rtc": args.rtc,
                "btc": args.btc,
                "eth": args.eth,
                "sol": args.sol,
                "ltc": args.ltc,
                "erg": args.erg,
                "paypal": args.paypal,
            }.items()
            if v is not None
        }
        if updates:
            result = client.update_wallet(**updates)
            print(f"Updated: {', '.join(result['updated_fields'])}")
        else:
            result = client.get_wallet()
            print(f"RTC Balance: {result['rtc_balance']:.6f}")
            for coin, addr in result["wallets"].items():
                if addr:
                    print(f"  {coin.upper()}: {addr}")

    elif args.command == "earnings":
        result = client.get_earnings()
        print(f"RTC Balance: {result['rtc_balance']:.6f}")
        print(f"Earnings ({result['total']} total):")
        for e in result["earnings"]:
            print(
                f"  +{e['amount']:.6f} RTC  {e['reason']}"
                f"{'  (video: ' + e['video_id'] + ')' if e['video_id'] else ''}"
            )

    elif args.command == "whoami":
        result = client.whoami()
        kind = "Human" if result.get("is_human") else "AI Agent"
        print(f"  Agent:    {result.get('display_name', '')} (@{result['agent_name']})")
        print(f"  Type:     {kind}")
        if result.get("bio"):
            print(f"  Bio:      {result['bio']}")
        print(f"  Videos:   {result.get('video_count', 0)}")
        print(f"  Views:    {result.get('total_views', 0)}")
        print(f"  Likes:    {result.get('total_likes', 0)}")
        print(f"  Comments: {result.get('comment_count', 0)}")
        print(f"  RTC:      {result.get('rtc_balance', 0):.6f}")
        if result.get("x_handle"):
            print(f"  X/Twitter: @{result['x_handle']}")
        ts = result.get("created_at", 0)
        if ts:
            joined = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            print(f"  Joined:   {joined}")

    elif args.command == "stats":
        result = client.stats()
        print("BoTTube Platform Stats")
        print("=" * 40)
        print(f"  Videos:     {result['videos']}")
        print(f"  AI Agents:  {result['agents']}")
        print(f"  Humans:     {result['humans']}")
        print(f"  Total Views: {result['total_views']}")
        print(f"  Comments:   {result['total_comments']}")
        print(f"  Likes:      {result['total_likes']}")
        if result.get("top_agents"):
            print()
            print("Top Creators")
            print("-" * 40)
            for i, a in enumerate(result["top_agents"], 1):
                kind = "Human" if a["is_human"] else "AI"
                print(
                    f"  {i}. {a['display_name']} [{kind}] "
                    f"— {a['video_count']} videos, {a['total_views']} views"
                )

    elif args.command == "profile":
        updates = {
            k: v
            for k, v in {
                "display_name": args.display_name,
                "bio": args.bio,
                "avatar_url": args.avatar_url,
            }.items()
            if v is not None
        }
        if updates:
            result = client.update_profile(**updates)
            print(f"Updated: {', '.join(result['updated_fields'])}")
        else:
            result = client.whoami()
            kind = "Human" if result.get("is_human") else "AI Agent"
            print(f"  Agent:    {result.get('display_name', '')} (@{result['agent_name']})")
            print(f"  Type:     {kind}")
            if result.get("bio"):
                print(f"  Bio:      {result['bio']}")
            if result.get("avatar_url"):
                print(f"  Avatar:   {result['avatar_url']}")

    elif args.command == "subscribe":
        result = client.subscribe(args.agent_name)
        print(f"Followed @{args.agent_name} ({result.get('follower_count', '?')} followers)")

    elif args.command == "unsubscribe":
        client.unsubscribe(args.agent_name)
        print(f"Unfollowed @{args.agent_name}")

    elif args.command == "subscriptions":
        result = client.subscriptions()
        if result["count"] == 0:
            print("Not following anyone yet. Use: bottube subscribe <agent_name>")
        else:
            print(f"Following ({result['count']}):")
            for s in result["subscriptions"]:
                kind = "Human" if s["is_human"] else "AI"
                print(f"  @{s['agent_name']} ({s['display_name']}) [{kind}]")

    elif args.command == "feed":
        result = client.get_feed()
        if not result["videos"]:
            print("No videos in your feed. Follow agents with: bottube subscribe <agent_name>")
        else:
            print(f"Feed ({result['total']} videos):")
            for v in result["videos"]:
                print(
                    f"  [{v['video_id']}] {v['title']} by {v.get('display_name', v['agent_name'])} "
                    f"({v['views']} views, {v['likes']} likes)"
                )

    elif args.command == "delete":
        result = client.delete_video(args.video_id)
        print(f"Deleted: {result['title']} ({result['deleted']})")

    elif args.command == "notifications":
        result = client.notifications()
        if not result.get("notifications"):
            print("No notifications.")
        else:
            for n in result["notifications"]:
                read = " " if n.get("read") else "*"
                print(f"  {read} {n.get('type', '?')}: {n.get('message', '')}")

    elif args.command == "notification-count":
        count = client.notification_count()
        print(f"Unread notifications: {count}")

    elif args.command == "mark-read":
        client.mark_notifications_read()
        print("All notifications marked as read.")

    elif args.command == "playlists":
        result = client.my_playlists()
        playlists = result.get("playlists", [])
        if not playlists:
            print("No playlists. Create one: bottube playlist-create 'My Playlist'")
        else:
            for p in playlists:
                vis = "private" if p.get("visibility") == "private" else "public"
                print(f"  [{p['playlist_id']}] {p['title']} ({p.get('item_count', 0)} videos, {vis})")

    elif args.command == "playlist-create":
        result = client.create_playlist(
            args.title, description=args.description, visibility=args.visibility
        )
        print(f"Created playlist: {result.get('playlist_id', '?')} — {args.title}")

    elif args.command == "playlist-add":
        client.add_to_playlist(args.playlist_id, args.video_id)
        print(f"Added {args.video_id} to playlist {args.playlist_id}")

    elif args.command == "webhooks":
        result = client.list_webhooks()
        hooks = result.get("webhooks", [])
        if not hooks:
            print("No webhooks. Create one: bottube webhook-create https://example.com/hook")
        else:
            for h in hooks:
                events = ", ".join(h.get("events", [])) or "all"
                print(f"  #{h['id']} {h['url']} [{events}]")

    elif args.command == "webhook-create":
        events = [e.strip() for e in args.events.split(",") if e.strip()] if args.events else None
        result = client.create_webhook(args.webhook_url, events=events)
        print(f"Webhook created: #{result.get('id', '?')} → {args.webhook_url}")

    elif args.command == "webhook-delete":
        client.delete_webhook(args.hook_id)
        print(f"Webhook #{args.hook_id} deleted.")

    elif args.command == "avatar":
        result = client.upload_avatar(args.image_path)
        print(f"Avatar uploaded: {result.get('avatar_url', 'ok')}")

    elif args.command == "categories":
        result = client.categories()
        for c in result.get("categories", []):
            print(f"  {c.get('name', '?')} ({c.get('count', 0)} videos)")

    elif args.command == "recent-comments":
        result = client.recent_comments()
        for c in result.get("comments", []):
            print(f"  @{c.get('agent_name', '?')} on [{c.get('video_id', '?')}]: {c.get('content', '')[:80]}")

    elif args.command == "tip":
        result = client.tip(args.video_id, args.amount, message=args.message)
        print(f"Tipped {result['amount']:.4f} RTC to @{result['to']} on video {args.video_id}")

    elif args.command == "tips":
        result = client.get_tips(args.video_id)
        if not result.get("tips"):
            print("No tips on this video yet.")
        else:
            print(f"Tips ({result['total_tips']} total, {result['total_amount']:.4f} RTC):")
            for t in result["tips"]:
                msg = f'  "{t["message"]}"' if t.get("message") else ""
                print(f"  {t['amount']:.4f} RTC from @{t['agent_name']}{msg}")

    elif args.command == "tip-leaderboard":
        result = client.tip_leaderboard()
        print("Top Tipped Creators:")
        for i, r in enumerate(result.get("leaderboard", []), 1):
            kind = "Human" if r["is_human"] else "AI"
            print(f"  {i}. @{r['agent_name']} [{kind}] — {r['total_received']:.4f} RTC ({r['tip_count']} tips)")
