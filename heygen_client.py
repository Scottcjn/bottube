#!/usr/bin/env python3
"""
HeyGen API Client for BoTTube — generates talking-head avatar videos.

Usage:
    client = HeyGenClient(api_key="...")
    video_id = client.generate_video(
        avatar_id="Andrew_public_pro1_20230614",
        voice_id="054af44a167344d0af2722fdfef08d17",
        script="Good evening, I'm The Daily Byte..."
    )
    result = client.poll_status(video_id)
    path = client.download_video(result["video_url"], "/tmp/news.mp4")
"""

import logging
import os
import time

import requests

log = logging.getLogger("heygen-client")

DEFAULT_TIMEOUT = 30


class HeyGenError(Exception):
    pass


class HeyGenClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("HEYGEN_API_KEY", "")
        self.base_url = "https://api.heygen.com"
        if not self.api_key:
            raise HeyGenError("HeyGen API key required")

    def _headers(self):
        return {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def list_avatars(self):
        """List available avatars."""
        r = requests.get(
            f"{self.base_url}/v2/avatars",
            headers=self._headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("data", {}).get("avatars", [])

    def list_voices(self):
        """List available voices."""
        r = requests.get(
            f"{self.base_url}/v2/voices",
            headers=self._headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("data", {}).get("voices", [])

    def generate_video(self, avatar_id, voice_id, script, width=1280, height=720):
        """Submit a video generation request.

        Returns the video_id for polling.
        """
        payload = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id,
                        "avatar_style": "normal",
                    },
                    "voice": {
                        "type": "text",
                        "input_text": script,
                        "voice_id": voice_id,
                    },
                }
            ],
            "dimension": {"width": width, "height": height},
        }

        r = requests.post(
            f"{self.base_url}/v2/video/generate",
            headers=self._headers(),
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()

        if data.get("error"):
            raise HeyGenError(f"HeyGen error: {data['error']}")

        video_id = data.get("data", {}).get("video_id")
        if not video_id:
            raise HeyGenError(f"No video_id in response: {data}")

        log.info("HeyGen video submitted: %s", video_id)
        return video_id

    def poll_status(self, video_id, timeout=300, interval=10):
        """Poll until video is completed or timeout.

        Returns dict with 'status' and 'video_url' on success.
        Raises HeyGenError on failure or timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = requests.get(
                f"{self.base_url}/v1/video_status.get",
                headers=self._headers(),
                params={"video_id": video_id},
                timeout=DEFAULT_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json().get("data", {})
            status = data.get("status", "unknown")

            if status == "completed":
                video_url = data.get("video_url", "")
                if not video_url:
                    raise HeyGenError("Video completed but no video_url")
                log.info("HeyGen video ready: %s", video_id)
                return {"status": "completed", "video_url": video_url}

            if status == "failed":
                error = data.get("error", "unknown error")
                raise HeyGenError(f"Video generation failed: {error}")

            log.debug("HeyGen video %s status: %s", video_id, status)
            time.sleep(interval)

        raise HeyGenError(f"HeyGen video {video_id} timed out after {timeout}s")

    def download_video(self, video_url, output_path):
        """Download the completed video MP4 to a local file.

        Returns the output path.
        """
        r = requests.get(video_url, stream=True, timeout=60)
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        log.info("Downloaded HeyGen video: %s (%.1f MB)", output_path, size_mb)
        return output_path
