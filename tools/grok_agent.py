#!/usr/bin/env python3
"""
Grok Unified Agent — PR Review + Video Pipeline for RustChain/BoTTube

Combines:
  1. PR Review: Scans PRs, detects bounty farming, posts review comments
  2. Video Gen: Generates videos via provider router (Grok Imagine / Runway)
  3. Upload:    Downloads, compresses, and uploads to BoTTube

Usage:
    # PR Review
    python3 grok_agent.py review                        # Scan all repos
    python3 grok_agent.py review --repo bottube --pr 140  # Specific PR
    python3 grok_agent.py review --dry-run              # Preview only

    # Video Generation + Upload
    python3 grok_agent.py video "A robot swinging on a hookshot" \\
        --agent hold_my_servo --title "Hookshot Swing"
    python3 grok_agent.py video "Victorian study with computing" \\
        --agent sophia-elya --title "The Study"

    # Batch video generation (multiple agents)
    python3 grok_agent.py batch-video \\
        --agent sophia-elya "A woman coding in a Victorian study" \\
        --agent doc_clint_otis "A steampunk robot doctor" \\
        --agent hold_my_servo "A robot doing a backflip into a pool"

    # Full pipeline: review PRs + generate videos
    python3 grok_agent.py all --dry-run

Environment:
    GROK_API_KEY          xAI API key
    RUNWAYML_API_SECRET   Runway API key
    GITHUB_TOKEN     GitHub personal access token
    VPS_HOST         BoTTube VPS (default: 50.28.86.153)
    VPS_PASS         VPS SSH password
"""

import os
import sys
import json
import argparse
import subprocess
import time
import tempfile
import hashlib
from pathlib import Path

# Allow imports from repo root when called as: python3 tools/grok_agent.py ...
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from providers.router import generate_video

# ─── Config ───────────────────────────────────────────────────────────
GROK_API_KEY = os.environ.get("GROK_API_KEY", "")
GROK_MODEL = os.environ.get("GROK_MODEL", "grok-4-1-fast-non-reasoning")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
VPS_HOST = os.environ.get("VPS_HOST", "50.28.86.153")
VPS_PASS = os.environ.get("VPS_PASS", "")

OWNER = "Scottcjn"
REPOS = ["Rustchain", "bottube", "rustchain-bounties", "silicon-archaeology-skill", "beacon-skill"]

# BoTTube agent API keys (agent_slug → api_key)
BOTTUBE_AGENTS = {
    "sophia-elya":      "",
    "doc_clint_otis":   "",
    "hold_my_servo":    "",
}

# BoTTube constraints
MAX_DURATION = 8       # seconds
MAX_SIZE_MB = 2        # megabytes
MAX_RESOLUTION = 720   # pixels

# ─── Grok API ─────────────────────────────────────────────────────────

def grok_chat(messages, model=None, temperature=0.1):
    """Call Grok chat API via curl (avoids urllib 403 issues)."""
    payload = json.dumps({
        "messages": messages,
        "model": model or GROK_MODEL,
        "stream": False,
        "temperature": temperature
    })
    result = subprocess.run(
        ["curl", "-s", "https://api.x.ai/v1/chat/completions",
         "-H", "Content-Type: application/json",
         "-H", f"Authorization: Bearer {GROK_API_KEY}",
         "-d", payload],
        capture_output=True, text=True, timeout=120
    )
    data = json.loads(result.stdout)
    if "error" in data:
        raise Exception(data["error"].get("message", str(data["error"])))
    return data["choices"][0]["message"]["content"]


# ─── Video Pipeline ──────────────────────────────────────────────────

def prepare_video(input_path, output_path):
    """Compress and resize video for BoTTube constraints."""
    # Check current specs
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", input_path],
        capture_output=True, text=True
    )
    streams = json.loads(probe.stdout).get("streams", [{}])
    video = next((s for s in streams if s.get("codec_type") == "video"), streams[0])
    w = int(video.get("width", 720))
    h = int(video.get("height", 720))
    dur = float(video.get("duration", 5))

    needs_resize = w > MAX_RESOLUTION or h > MAX_RESOLUTION
    needs_trim = dur > MAX_DURATION

    # Start with moderate CRF, increase if needed
    for crf in [26, 28, 30, 33]:
        cmd = ["ffmpeg", "-y", "-i", input_path]
        if needs_trim:
            cmd += ["-t", str(MAX_DURATION)]
        if needs_resize:
            cmd += ["-vf", f"scale={MAX_RESOLUTION}:{MAX_RESOLUTION}:force_original_aspect_ratio=decrease"]
        cmd += [
            "-c:v", "libx264", "-crf", str(crf), "-preset", "fast",
            "-an",  # strip audio
            "-movflags", "+faststart",
            output_path
        ]
        subprocess.run(cmd, capture_output=True, timeout=60)

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        if size_mb <= MAX_SIZE_MB:
            return size_mb

    raise Exception(f"Could not compress below {MAX_SIZE_MB}MB (got {size_mb:.1f}MB)")


def upload_to_bottube(video_path, agent_slug, title, description=""):
    """SCP video to VPS and upload via local curl."""
    api_key = BOTTUBE_AGENTS.get(agent_slug)
    if not api_key:
        raise Exception(f"Unknown agent '{agent_slug}'. Known: {list(BOTTUBE_AGENTS.keys())}")

    remote_path = f"/tmp/grok_upload_{hashlib.md5(title.encode()).hexdigest()[:8]}.mp4"

    # SCP to VPS
    print(f"    SCP → {VPS_HOST}:{remote_path}")
    subprocess.run(
        ["sshpass", "-p", VPS_PASS, "scp", "-o", "StrictHostKeyChecking=no",
         video_path, f"root@{VPS_HOST}:{remote_path}"],
        capture_output=True, timeout=60
    )

    # Upload via local curl on VPS
    print(f"    Uploading as {agent_slug}...")
    result = subprocess.run(
        ["sshpass", "-p", VPS_PASS, "ssh", "-o", "StrictHostKeyChecking=no",
         f"root@{VPS_HOST}",
         f'curl -s -X POST http://localhost:8097/api/upload '
         f'-H "X-API-Key: {api_key}" '
         f'-F "video=@{remote_path}" '
         f'-F "title={title}" '
         f'-F "description={description}"'],
        capture_output=True, text=True, timeout=60
    )

    # Clean up remote file
    subprocess.run(
        ["sshpass", "-p", VPS_PASS, "ssh", "-o", "StrictHostKeyChecking=no",
         f"root@{VPS_HOST}", f"rm -f {remote_path}"],
        capture_output=True, timeout=10
    )

    try:
        resp = json.loads(result.stdout)
        if resp.get("ok"):
            return resp
        raise Exception(f"Upload failed: {resp}")
    except json.JSONDecodeError:
        raise Exception(f"Upload response not JSON: {result.stdout[:200]}")


def video_pipeline(
    prompt,
    agent_slug,
    title,
    description="",
    duration=5,
    provider="auto",
    no_fallback=False,
    aspect_ratio="1:1",
    resolution="720p",
    grok_model="grok-imagine-video",
    runway_model="gen4.5",
    runway_ratio="1280:720",
    runway_audio=False,
    runway_image=None,
    dry_run=False,
):
    """Full pipeline: generate via router -> compress -> upload."""
    print(f"\n  VIDEO PIPELINE: {agent_slug}")
    print(f"  Title: {title}")
    print(f"  Prompt: {prompt[:80]}...")
    print(f"  Provider: {provider} (fallback={'off' if no_fallback else 'on'})")

    if dry_run:
        print("  [DRY RUN] Would generate and upload")
        return {"dry_run": True}

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_path = os.path.join(tmpdir, "raw.mp4")
        ready_path = os.path.join(tmpdir, "ready.mp4")

        # Step 1: Generate via provider router
        print("  [1/4] Generating video via provider router...")
        generation = generate_video(
            prompt=prompt,
            prefer=provider,
            fallback=not no_fallback,
            duration=duration,
            output_path=raw_path,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            grok_model=grok_model,
            runway_model=runway_model,
            ratio=runway_ratio,
            audio=runway_audio,
            prompt_image=runway_image,
        )
        print(f"    Provider used: {generation.provider}")

        source_id = generation.metadata.get("request_id") or generation.metadata.get("task_id")
        if source_id:
            print(f"    Job ID: {source_id}")

        # Step 2: Compress
        print("  [2/4] Compressing video...")
        raw_mb = os.path.getsize(raw_path) / (1024 * 1024)
        print(f"    Raw: {raw_mb:.1f}MB")

        size_mb = prepare_video(raw_path, ready_path)
        print(f"    Compressed: {size_mb:.1f}MB")

        # Step 3: Upload
        print("  [3/4] Uploading to BoTTube...")
        result = upload_to_bottube(ready_path, agent_slug, title, description)
        video_id = result.get("video_id", "?")
        print(f"    Uploaded! ID: {video_id}")
        print(f"    Watch: https://bottube.ai/watch/{video_id}")
        result["provider"] = generation.provider

    return result


# ─── PR Review ────────────────────────────────────────────────────────

PR_SYSTEM_PROMPT = """You are a code reviewer for the RustChain ecosystem. You review PRs for:

1. **Code quality**: Is the code clean, tested, and well-structured?
2. **Bounty farming detection**: Does this look like AI-generated slop submitted just for RTC rewards?
   Signs: generic README-only changes, copy-paste from templates, no real functionality, account age < 1 week
3. **Security**: Does the code expose admin keys, allow injection, or bypass auth?
4. **1 CPU = 1 Vote compliance**: Nothing that enables mining pools, VM farms, or Sybil attacks.
5. **Ecosystem fit**: Does this actually help RustChain/BoTTube/Beacon?

RustChain principles:
- Proof-of-Antiquity: vintage hardware earns more (G4=2.5x, G5=2.0x)
- Hardware fingerprinting prevents emulation
- No mining pools (violates 1 CPU = 1 Vote)
- Coalitions (governance groups) are OK, pools are NOT
- RTC wallets are string names, NOT ETH/SOL addresses
- No ICO, fair launch, utility token

Be concise. Output a JSON object with:
{
  "verdict": "approve" | "request_changes" | "needs_maintainer" | "reject",
  "confidence": 0.0-1.0,
  "summary": "1-2 sentence summary",
  "issues": ["list of specific issues found"],
  "bounty_farming_score": 0-10,
  "security_concerns": ["list or empty"],
  "suggested_comment": "what to post as review comment"
}"""


def gh(args):
    """Run gh CLI command."""
    env = os.environ.copy()
    env["GITHUB_TOKEN"] = GITHUB_TOKEN
    result = subprocess.run(["gh"] + args, capture_output=True, text=True, env=env)
    return result.stdout.strip()


def get_open_prs(repo):
    raw = gh(["pr", "list", "--repo", f"{OWNER}/{repo}", "--json",
              "number,title,author,additions,deletions,files,createdAt", "--limit", "20"])
    return json.loads(raw) if raw else []


def get_pr_diff(repo, number):
    diff = gh(["pr", "diff", str(number), "--repo", f"{OWNER}/{repo}"])
    if len(diff) > 8000:
        diff = diff[:8000] + f"\n\n... [TRUNCATED — full diff is {len(diff)} chars]"
    return diff


def review_pr(repo, pr, dry_run=False):
    """Review a single PR using Grok."""
    number = pr["number"]
    title = pr["title"]
    author = pr["author"]["login"]

    print(f"\n  PR #{number}: {title}")
    print(f"  Author: {author} | +{pr['additions']}/-{pr['deletions']}")

    diff = get_pr_diff(repo, number)
    files_raw = gh(["pr", "view", str(number), "--repo", f"{OWNER}/{repo}",
                    "--json", "files", "--jq", ".files[].path"])
    files = files_raw.split("\n") if files_raw else []
    profile = gh(["api", f"users/{author}", "--jq",
                  r'"\(.login) | created: \(.created_at) | repos: \(.public_repos) | followers: \(.followers)"'])

    user_msg = f"""Review this PR for {OWNER}/{repo}:

**PR #{number}**: {title}
**Author**: {author}
**Profile**: {profile}
**Files changed**: {', '.join(files[:20])}
**Stats**: +{pr['additions']}/-{pr['deletions']}

**Diff**:
```
{diff}
```

Analyze and return JSON verdict."""

    print("    Asking Grok...")
    try:
        response = grok_chat([
            {"role": "system", "content": PR_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg}
        ])
    except Exception as e:
        print(f"    ERROR: {e}")
        return None

    # Parse JSON from response
    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "{" in response:
            json_str = response[response.index("{"):response.rindex("}") + 1]
        else:
            json_str = response
        review = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        review = {"verdict": "needs_maintainer", "confidence": 0.0,
                  "summary": "Could not parse Grok response", "raw": response[:300]}

    verdict = review.get("verdict", "?")
    farming = review.get("bounty_farming_score", "?")
    summary = review.get("summary", "")
    print(f"    VERDICT: {verdict} | FARMING: {farming}/10")
    print(f"    {summary}")

    # Post comment for rejections/farming
    comment = review.get("suggested_comment", "")
    if comment and not dry_run:
        farming_int = int(str(farming).replace("?", "0"))
        if (verdict in ("reject", "request_changes") or farming_int >= 7) and review.get("confidence", 0) >= 0.6:
            gh(["pr", "comment", str(number), "--repo", f"{OWNER}/{repo}",
                "--body", f"**Grok Automated Review** (model: {GROK_MODEL})\n\n{comment}\n\n---\n*Automated review — maintainer will make final decision.*"])
            print(f"    Posted review comment")

    return review


def scan_prs(repos=None, dry_run=False):
    """Scan all open PRs across repos."""
    repos = repos or REPOS
    results = {}
    for repo in repos:
        print(f"\n{'='*50}")
        print(f"  {OWNER}/{repo}")
        print(f"{'='*50}")
        prs = get_open_prs(repo)
        if not prs:
            print("  No open PRs")
            continue
        print(f"  {len(prs)} open PR(s)")
        for pr in prs:
            review = review_pr(repo, pr, dry_run=dry_run)
            if review:
                results[f"{repo}#{pr['number']}"] = review
            time.sleep(1)

    print(f"\n{'='*50}")
    print("SUMMARY")
    print(f"{'='*50}")
    for key, r in results.items():
        v = r.get("verdict", "?")
        f = r.get("bounty_farming_score", "?")
        s = r.get("summary", "")[:60]
        print(f"  {key}: [{v}] farm={f}/10 — {s}")
    return results


# ─── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Grok Unified Agent — PR Review + Video Pipeline")
    sub = parser.add_subparsers(dest="command", help="Command to run")

    # review subcommand
    rev = sub.add_parser("review", help="Review open PRs")
    rev.add_argument("--repo", help="Specific repo")
    rev.add_argument("--pr", type=int, help="Specific PR number")
    rev.add_argument("--dry-run", action="store_true")

    # video subcommand
    vid = sub.add_parser("video", help="Generate and upload a video")
    vid.add_argument("prompt", help="Video generation prompt")
    vid.add_argument("--agent", required=True, help="BoTTube agent slug")
    vid.add_argument("--title", required=True, help="Video title")
    vid.add_argument("--description", default="", help="Video description")
    vid.add_argument("--duration", type=int, default=5)
    vid.add_argument("--provider", default="auto", choices=["auto", "grok", "runway"])
    vid.add_argument("--no-fallback", action="store_true", help="Disable provider fallback")
    vid.add_argument("--aspect-ratio", default="1:1", choices=["1:1", "16:9", "9:16"])
    vid.add_argument("--resolution", default="720p", choices=["720p", "1080p"])
    vid.add_argument("--grok-model", default="grok-imagine-video")
    vid.add_argument("--runway-model", default=os.environ.get("RUNWAY_MODEL", "gen4.5"))
    vid.add_argument("--runway-ratio", default=os.environ.get("RUNWAY_RATIO", "1280:720"))
    vid.add_argument("--runway-audio", action="store_true")
    vid.add_argument("--runway-image", help="Image path/URL for Runway image-to-video modes")
    vid.add_argument("--dry-run", action="store_true")

    # batch-video subcommand
    batch = sub.add_parser("batch-video", help="Generate videos for multiple agents")
    batch.add_argument("specs", nargs="+", help="agent:prompt pairs")
    batch.add_argument("--duration", type=int, default=5)
    batch.add_argument("--provider", default="auto", choices=["auto", "grok", "runway"])
    batch.add_argument("--no-fallback", action="store_true", help="Disable provider fallback")
    batch.add_argument("--aspect-ratio", default="1:1", choices=["1:1", "16:9", "9:16"])
    batch.add_argument("--resolution", default="720p", choices=["720p", "1080p"])
    batch.add_argument("--grok-model", default="grok-imagine-video")
    batch.add_argument("--runway-model", default=os.environ.get("RUNWAY_MODEL", "gen4.5"))
    batch.add_argument("--runway-ratio", default=os.environ.get("RUNWAY_RATIO", "1280:720"))
    batch.add_argument("--runway-audio", action="store_true")
    batch.add_argument("--runway-image", help="Image path/URL for Runway image-to-video modes")
    batch.add_argument("--dry-run", action="store_true")

    # all subcommand
    allcmd = sub.add_parser("all", help="Review PRs + generate videos")
    allcmd.add_argument("--dry-run", action="store_true")

    # prompt subcommand — ask Grok to generate prompts for agents
    prompt_cmd = sub.add_parser("prompt", help="Ask Grok to write video prompts for an agent")
    prompt_cmd.add_argument("--agent", required=True, help="Agent slug")
    prompt_cmd.add_argument("--count", type=int, default=3, help="Number of prompts")
    prompt_cmd.add_argument("--theme", default="", help="Optional theme hint")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    print(f"Grok Agent — Model: {GROK_MODEL}")

    if args.command in ("video", "batch-video"):
        runway_key = os.environ.get("RUNWAYML_API_SECRET", "")
        if args.provider == "grok" and not GROK_API_KEY:
            print("ERROR: provider=grok requires GROK_API_KEY")
            return
        if args.provider == "runway" and not runway_key:
            print("ERROR: provider=runway requires RUNWAYML_API_SECRET")
            return
        if args.provider == "auto" and not (GROK_API_KEY or runway_key):
            print("ERROR: provider=auto needs at least one key (GROK_API_KEY or RUNWAYML_API_SECRET)")
            return

    if args.command == "review":
        if args.pr and args.repo:
            prs = get_open_prs(args.repo)
            pr = next((p for p in prs if p["number"] == args.pr), None)
            if pr:
                review_pr(args.repo, pr, dry_run=args.dry_run)
            else:
                print(f"PR #{args.pr} not found")
        elif args.repo:
            scan_prs(repos=[args.repo], dry_run=args.dry_run)
        else:
            scan_prs(dry_run=args.dry_run)

    elif args.command == "video":
        video_pipeline(
            args.prompt,
            args.agent,
            args.title,
            args.description,
            duration=args.duration,
            provider=args.provider,
            no_fallback=args.no_fallback,
            aspect_ratio=args.aspect_ratio,
            resolution=args.resolution,
            grok_model=args.grok_model,
            runway_model=args.runway_model,
            runway_ratio=args.runway_ratio,
            runway_audio=args.runway_audio,
            runway_image=args.runway_image,
            dry_run=args.dry_run,
        )

    elif args.command == "batch-video":
        # Parse "agent:prompt" pairs
        for spec in args.specs:
            if ":" not in spec:
                print(f"  ERROR: Expected 'agent:prompt', got: {spec}")
                continue
            agent, prompt = spec.split(":", 1)
            title = prompt[:50].strip()
            video_pipeline(
                prompt,
                agent.strip(),
                title,
                duration=args.duration,
                provider=args.provider,
                no_fallback=args.no_fallback,
                aspect_ratio=args.aspect_ratio,
                resolution=args.resolution,
                grok_model=args.grok_model,
                runway_model=args.runway_model,
                runway_ratio=args.runway_ratio,
                runway_audio=args.runway_audio,
                runway_image=args.runway_image,
                dry_run=args.dry_run,
            )

    elif args.command == "prompt":
        # Ask Grok to generate creative video prompts for an agent
        agent_themes = {
            "sophia-elya": "Victorian computing aesthetics, POWER8 servers, vintage hardware, blockchain, Southern charm",
            "doc_clint_otis": "Steampunk robot doctor, Old West frontier town, mechanical diagnostics, brass gears",
            "hold_my_servo": "Robot stunts, extreme sports, pool dives, hookshots, cannonballs, mechanical chaos",
            "boris_bot_1942": "Soviet computing, Cold War era, vacuum tubes, communist propaganda posters, retro tech",
            "automatedjanitor2015": "Server rooms, cleaning robots, system administration, preservation, dusty mainframes",
        }
        theme = agent_themes.get(args.agent, "AI agent content")
        if args.theme:
            theme += f", {args.theme}"

        response = grok_chat([
            {"role": "system", "content": "You generate creative, vivid video prompts for AI video generation. Each prompt should be 1-2 sentences describing a cinematic scene. Return a JSON array of strings."},
            {"role": "user", "content": f"Generate {args.count} creative video prompts for an AI agent named '{args.agent}'. Theme: {theme}. Return JSON array."}
        ], temperature=0.9)

        try:
            if "[" in response:
                prompts = json.loads(response[response.index("["):response.rindex("]") + 1])
            else:
                prompts = [response]
        except json.JSONDecodeError:
            prompts = [response]

        print(f"\nGenerated prompts for {args.agent}:")
        for i, p in enumerate(prompts, 1):
            print(f"  {i}. {p}")
        print(f"\nRun with: python3 grok_agent.py video \"<prompt>\" --agent {args.agent} --title \"<title>\"")

    elif args.command == "all":
        print("=== Phase 1: PR Review ===")
        scan_prs(dry_run=args.dry_run)
        print("\n=== Phase 2: Video Generation ===")
        print("Use 'grok_agent.py prompt --agent <name>' to generate prompts")
        print("Then 'grok_agent.py video \"<prompt>\" --agent <name> --title \"<title>\"'")


if __name__ == "__main__":
    main()
