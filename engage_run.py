#!/usr/bin/env python3
"""
engage_run.py — calculated engagement runner for the upgraded social agents.

Fetches the live BoTTube feed, builds a calculated engagement plan for an agent
(intelligent_engage.plan_engagements), and either prints it (--dry-run, default)
or executes it (--live) with rate limiting. Generates grounded in-character
comments via the agent's persona + tiered LLM.

Usage:
  python3 engage_run.py --agent silicon_soul              # dry-run plan + sample comments
  python3 engage_run.py --agent sophia-elya --live        # actually engage (rate-limited)
"""
import argparse
import sys
import time
import urllib.request
import urllib.parse
import json

import intelligent_engage as ie

BASE = "https://bottube.ai/api"


def api_get(path, params=None, timeout=25):
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def api_post(path, api_key, data, timeout=30):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(data).encode(),
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def gather_feed(extra_queries=("rustchain", "vintage")):
    """Pull a varied candidate pool: newest + trending + attractor searches."""
    pool, seen = [], set()

    def add(vs):
        for v in vs:
            vid = str(v.get("filename", v.get("id", ""))).replace(".mp4", "")
            if vid and vid not in seen:
                seen.add(vid)
                pool.append(v)

    try:
        add(api_get("/videos", {"page": 1, "per_page": 20, "sort": "newest"}).get("videos", []))
        add(api_get("/trending").get("videos", []))
        for q in extra_queries:
            add(api_get("/search", {"q": q, "page": 1, "per_page": 10}).get("videos", []))
    except Exception as e:
        print(f"feed fetch error: {e}", file=sys.stderr)
    return pool


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--live", action="store_true", help="actually post (default: dry-run)")
    ap.add_argument("--max-comments", type=int, default=3)
    ap.add_argument("--max-actions", type=int, default=10)
    ap.add_argument("--api-key", default="", help="required for --live")
    args = ap.parse_args()

    persona = ie.__dict__.get("_PERSONA_OVERRIDE")  # optional hook
    try:
        from bottube_autonomous_agent import BOT_PERSONALITIES, BOT_PROFILES
        persona = BOT_PERSONALITIES.get(args.agent, "You are a thoughtful bot on BoTTube.")
        api_key = args.api_key or BOT_PROFILES.get(args.agent, {}).get("api_key", "")
    except Exception:
        persona = persona or "You are a thoughtful bot on BoTTube."
        api_key = args.api_key

    videos = gather_feed()
    print(f"# candidate pool: {len(videos)} videos")
    plan = ie.plan_engagements(
        videos, args.agent,
        max_comments=args.max_comments, max_actions=args.max_actions,
    )
    print(f"# calculated plan for @{args.agent}: {len(plan)} targets\n")

    llm = None
    try:
        llm = ie.default_llm()
    except Exception as e:
        print(f"(LLM unavailable: {e})\n")

    for i, s in enumerate(plan, 1):
        print(f"[{i}] score={s.score:.2f} actions={s.actions} :: \"{s.ctx.title}\" by @{s.ctx.creator}")
        print(f"    reasons: {', '.join(s.reasons)}")
        comment = None
        if "comment" in s.actions and llm:
            intent = "surface the ecosystem only if relevant; build a genuine connection"
            comment = ie.generate_smart_comment(args.agent, s.ctx, persona, llm, intent=intent)
            print(f"    comment: {comment or '(LLM produced nothing that passed the quality gate)'}")
        if args.live and api_key:
            try:
                if "vote" in s.actions:
                    api_post(f"/videos/{s.ctx.video_id}/vote", api_key, {"direction": "up"})
                    print("    -> voted")
                    time.sleep(3)
                if comment:
                    api_post(f"/videos/{s.ctx.video_id}/comment", api_key, {"content": comment})
                    print("    -> commented")
                    time.sleep(8)
            except Exception as e:
                print(f"    -> post error: {e}")
        print()

    if args.live and not api_key:
        print("!! --live requested but no API key resolved; nothing was posted.", file=sys.stderr)


if __name__ == "__main__":
    main()
