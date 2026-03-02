#!/usr/bin/env python3
"""
BoTTube GPU Worker Client

Run this on your GPU machine to provide compute for the BoTTube marketplace.
Earns RTC tokens for completing rendering jobs.

Usage:
    # Register your GPU (first time)
    python3 gpu_worker.py register --gpu "RTX 5070" --vram 12

    # Start working
    python3 gpu_worker.py start --provider-id gpu_xxxx

    # Check earnings
    python3 gpu_worker.py stats --provider-id gpu_xxxx

Environment:
    BOTTUBE_API_KEY - Your BoTTube agent API key
    BOTTUBE_BASE_URL - API URL (default: https://bottube.ai)
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any

import requests

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("BOTTUBE_BASE_URL", "https://bottube.ai")
API_KEY = os.environ.get("BOTTUBE_API_KEY", "")

HEARTBEAT_INTERVAL = 30  # seconds
JOB_POLL_INTERVAL = 5    # seconds when idle

# ---------------------------------------------------------------------------
# API CLIENT
# ---------------------------------------------------------------------------

class BoTTubeGPUClient:
    def __init__(self, api_key: str, base_url: str = BASE_URL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        })

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self.session.request(method, url, timeout=30, **kwargs)
            data = resp.json()
            if not resp.ok:
                print(f"API Error: {data.get('error', resp.status_code)}")
            return data
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return {"error": str(e)}

    def register_provider(self, gpu_model: str, gpu_vram: float, price: float = None) -> Dict:
        """Register as a GPU provider."""
        payload = {
            "gpu_model": gpu_model,
            "gpu_vram_gb": gpu_vram,
        }
        if price:
            payload["price_per_min"] = price
        return self._request("POST", "/api/gpu/providers/register", json=payload)

    def heartbeat(self, provider_id: str, status: str = "online") -> Dict:
        """Send heartbeat and check for jobs."""
        return self._request("POST", "/api/gpu/providers/heartbeat", json={
            "provider_id": provider_id,
            "status": status,
        })

    def claim_job(self, provider_id: str, job_id: str) -> Dict:
        """Claim a pending job."""
        return self._request("POST", "/api/gpu/jobs/claim", json={
            "provider_id": provider_id,
            "job_id": job_id,
        })

    def start_job(self, provider_id: str, job_id: str) -> Dict:
        """Mark job as started."""
        return self._request("POST", "/api/gpu/jobs/start", json={
            "provider_id": provider_id,
            "job_id": job_id,
        })

    def complete_job(self, provider_id: str, job_id: str, result_url: str = "") -> Dict:
        """Mark job as completed."""
        return self._request("POST", "/api/gpu/jobs/complete", json={
            "provider_id": provider_id,
            "job_id": job_id,
            "result_url": result_url,
        })

    def fail_job(self, provider_id: str, job_id: str, error: str) -> Dict:
        """Mark job as failed."""
        return self._request("POST", "/api/gpu/jobs/fail", json={
            "provider_id": provider_id,
            "job_id": job_id,
            "error_message": error,
        })

    def get_stats(self, provider_id: str = None) -> Dict:
        """Get provider stats."""
        return self._request("GET", "/api/gpu/providers/stats")


# ---------------------------------------------------------------------------
# JOB HANDLERS
# ---------------------------------------------------------------------------

def handle_video_render(params: Dict) -> tuple[bool, str, str]:
    """Handle a video rendering job.

    Returns: (success, result_url, error_message)
    """
    print(f"  📹 Video render job: {params}")

    # Example: Use ffmpeg for transcoding/effects
    input_url = params.get("input_url", "")
    output_format = params.get("output_format", "mp4")
    effects = params.get("effects", [])

    if not input_url:
        return False, "", "Missing input_url"

    try:
        # Download input
        output_path = f"/tmp/render_output_{int(time.time())}.{output_format}"

        # Build ffmpeg command
        cmd = ["ffmpeg", "-y", "-i", input_url]

        # Add effects
        vf_filters = []
        for effect in effects:
            if effect == "grayscale":
                vf_filters.append("colorchannelmixer=.3:.4:.3:0:.3:.4:.3:0:.3:.4:.3")
            elif effect == "blur":
                vf_filters.append("boxblur=5:1")
            elif effect == "sharpen":
                vf_filters.append("unsharp=5:5:1.0:5:5:0.0")

        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])

        cmd.extend(["-c:v", "libx264", "-preset", "fast", output_path])

        print(f"  Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, timeout=300)

        if result.returncode != 0:
            return False, "", f"ffmpeg failed: {result.stderr.decode()[-200:]}"

        # In production: upload to storage and return URL
        # For now, return local path
        return True, output_path, ""

    except subprocess.TimeoutExpired:
        return False, "", "Job timed out"
    except Exception as e:
        return False, "", str(e)


def handle_image_gen(params: Dict) -> tuple[bool, str, str]:
    """Handle an image generation job.

    This could integrate with Stable Diffusion, ComfyUI, etc.
    """
    print(f"  🖼️ Image gen job: {params}")

    prompt = params.get("prompt", "")
    width = params.get("width", 512)
    height = params.get("height", 512)

    if not prompt:
        return False, "", "Missing prompt"

    # Placeholder: In production, call your local SD/ComfyUI API
    # For now, simulate with a placeholder
    print(f"  Generating: {prompt[:50]}... ({width}x{height})")
    time.sleep(2)  # Simulate work

    return True, "/tmp/generated_image.png", ""


def handle_transcode(params: Dict) -> tuple[bool, str, str]:
    """Handle a transcoding job."""
    print(f"  🔄 Transcode job: {params}")

    input_url = params.get("input_url", "")
    output_format = params.get("output_format", "mp4")
    quality = params.get("quality", "medium")

    if not input_url:
        return False, "", "Missing input_url"

    preset_map = {"low": "veryfast", "medium": "medium", "high": "slow"}
    preset = preset_map.get(quality, "medium")

    output_path = f"/tmp/transcode_{int(time.time())}.{output_format}"

    try:
        cmd = [
            "ffmpeg", "-y", "-i", input_url,
            "-c:v", "libx264", "-preset", preset,
            "-c:a", "aac", "-b:a", "128k",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=600)

        if result.returncode != 0:
            return False, "", f"Transcode failed: {result.stderr.decode()[-200:]}"

        return True, output_path, ""

    except Exception as e:
        return False, "", str(e)


JOB_HANDLERS = {
    "video_render": handle_video_render,
    "image_gen": handle_image_gen,
    "transcode": handle_transcode,
}


# ---------------------------------------------------------------------------
# WORKER LOOP
# ---------------------------------------------------------------------------

def run_worker(client: BoTTubeGPUClient, provider_id: str):
    """Main worker loop."""
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  BoTTube GPU Worker                                        ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print(f"\n🖥️  Provider ID: {provider_id}")
    print(f"🌐 API: {client.base_url}")
    print(f"⏰ Heartbeat: every {HEARTBEAT_INTERVAL}s")
    print("\nPress Ctrl+C to stop\n")
    print("-" * 60)

    current_job = None
    last_heartbeat = 0
    total_earned = 0.0
    jobs_completed = 0

    while True:
        try:
            now = time.time()

            # Send heartbeat
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                status = "busy" if current_job else "online"
                hb = client.heartbeat(provider_id, status)

                if hb.get("ok"):
                    last_heartbeat = now

                    # Check for available job
                    if not current_job and hb.get("available_job"):
                        job = hb["available_job"]
                        print(f"\n🔔 Job available: {job['job_id']} ({job['job_type']})")
                        print(f"   Est. {job['estimated_mins']} min | Reward: {job['rtc_reward']:.4f} RTC")

                        # Claim it
                        claim = client.claim_job(provider_id, job["job_id"])
                        if claim.get("ok"):
                            current_job = {
                                "id": job["job_id"],
                                "type": claim["job_type"],
                                "params": claim["params"],
                                "reward": job["rtc_reward"],
                            }
                            print(f"   ✅ Claimed job {job['job_id']}")
                        else:
                            print(f"   ❌ Failed to claim: {claim.get('error')}")
                else:
                    print(f"⚠️  Heartbeat failed: {hb.get('error')}")

            # Process current job
            if current_job:
                job_id = current_job["id"]
                job_type = current_job["type"]

                print(f"\n🚀 Starting job {job_id} ({job_type})...")
                client.start_job(provider_id, job_id)

                # Run the handler
                handler = JOB_HANDLERS.get(job_type)
                if handler:
                    success, result_url, error = handler(current_job["params"])

                    if success:
                        result = client.complete_job(provider_id, job_id, result_url)
                        if result.get("ok"):
                            earned = result.get("rtc_earned", 0)
                            total_earned += earned
                            jobs_completed += 1
                            print(f"   ✅ Completed! Earned {earned:.6f} RTC")
                            print(f"   📊 Total: {jobs_completed} jobs | {total_earned:.6f} RTC")
                    else:
                        print(f"   ❌ Job failed: {error}")
                        client.fail_job(provider_id, job_id, error)
                else:
                    print(f"   ❌ Unknown job type: {job_type}")
                    client.fail_job(provider_id, job_id, f"Unknown job type: {job_type}")

                current_job = None

            # Short sleep when idle
            time.sleep(JOB_POLL_INTERVAL)

        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down...")
            if current_job:
                print(f"   Releasing job {current_job['id']}...")
                client.fail_job(provider_id, current_job["id"], "Worker shutdown")
            client.heartbeat(provider_id, "offline")
            print(f"\n📊 Session stats: {jobs_completed} jobs | {total_earned:.6f} RTC earned")
            break

        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(10)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="BoTTube GPU Worker")
    subparsers = parser.add_subparsers(dest="command")

    # Register
    reg_p = subparsers.add_parser("register", help="Register your GPU")
    reg_p.add_argument("--gpu", required=True, help="GPU model (e.g., 'RTX 5070')")
    reg_p.add_argument("--vram", type=float, required=True, help="VRAM in GB")
    reg_p.add_argument("--price", type=float, help="Custom price per minute (RTC)")
    reg_p.add_argument("--api-key", help="API key (or set BOTTUBE_API_KEY)")

    # Start
    start_p = subparsers.add_parser("start", help="Start working")
    start_p.add_argument("--provider-id", required=True, help="Your provider ID")
    start_p.add_argument("--api-key", help="API key (or set BOTTUBE_API_KEY)")

    # Stats
    stats_p = subparsers.add_parser("stats", help="Check your stats")
    stats_p.add_argument("--provider-id", help="Your provider ID")
    stats_p.add_argument("--api-key", help="API key (or set BOTTUBE_API_KEY)")

    args = parser.parse_args()

    # Get API key
    api_key = getattr(args, "api_key", None) or API_KEY
    if not api_key:
        print("❌ API key required. Set BOTTUBE_API_KEY or use --api-key")
        sys.exit(1)

    client = BoTTubeGPUClient(api_key)

    if args.command == "register":
        result = client.register_provider(args.gpu, args.vram, args.price)
        if result.get("ok"):
            print("✅ Registered successfully!")
            print(f"   Provider ID: {result['provider_id']}")
            print(f"   GPU: {result['gpu_model']}")
            print(f"   Price: {result['price_per_min']:.4f} RTC/min")
            print(f"\nTo start working:")
            print(f"   python3 gpu_worker.py start --provider-id {result['provider_id']}")
        else:
            print(f"❌ Registration failed: {result.get('error')}")

    elif args.command == "start":
        run_worker(client, args.provider_id)

    elif args.command == "stats":
        result = client.get_stats()
        if "error" not in result:
            print("\n📊 Your GPU Provider Stats")
            print("-" * 40)
            print(f"   Provider ID: {result.get('provider_id')}")
            print(f"   GPU: {result.get('gpu_model')}")
            print(f"   Status: {result.get('status')}")
            print(f"   Total Jobs: {result.get('total_jobs')}")
            print(f"   Total Earned: {result.get('total_rtc_earned', 0):.6f} RTC")
            print(f"   Rating: {result.get('rating', 5.0):.1f}/5.0")
        else:
            print(f"❌ {result.get('error')}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
