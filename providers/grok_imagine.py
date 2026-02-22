from __future__ import annotations

import os
import time
from typing import Any, Dict

import requests

from providers.base import GeneratedVideo, VideoGenProvider
from providers.utils import download_file


class GrokImagineProvider(VideoGenProvider):
    """xAI Grok Imagine video provider."""

    name = "grok"

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        poll_interval: int = 5,
        max_wait_seconds: int = 300,
    ) -> None:
        self.api_key = api_key or os.environ.get("GROK_API_KEY", "")
        self.api_base = (api_base or os.environ.get("GROK_API_BASE", "https://api.x.ai/v1")).rstrip("/")
        self.poll_interval = poll_interval
        self.max_wait_seconds = max_wait_seconds

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise RuntimeError("GROK_API_KEY is not set")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, prompt: str, duration: int = 5, **kwargs: Any) -> GeneratedVideo:
        aspect_ratio = kwargs.get("aspect_ratio", "1:1")
        resolution = kwargs.get("resolution", "720p")
        model = kwargs.get("grok_model") or kwargs.get("model") or "grok-imagine-video"
        output_path = kwargs.get("output_path")

        payload = {
            "model": model,
            "prompt": prompt,
            "duration": int(duration),
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        }

        create_resp = requests.post(
            f"{self.api_base}/videos/generations",
            json=payload,
            headers=self._headers(),
            timeout=30,
        )
        create_resp.raise_for_status()
        create_data = create_resp.json()

        if create_data.get("error"):
            raise RuntimeError(f"Grok API error: {create_data['error']}")

        request_id = create_data.get("request_id")
        if not request_id:
            raise RuntimeError(f"Missing request_id from Grok response: {create_data}")

        started = time.time()
        while time.time() - started < self.max_wait_seconds:
            poll_resp = requests.get(
                f"{self.api_base}/videos/{request_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30,
            )
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()

            if poll_data.get("error"):
                raise RuntimeError(f"Grok generation failed: {poll_data['error']}")

            url = (
                (poll_data.get("video") or {}).get("url")
                or poll_data.get("video_url")
                or poll_data.get("url")
            )
            status = str(poll_data.get("status", "")).lower()

            if url:
                local_path = download_file(url, output_path, prefix="grok_video_")
                return GeneratedVideo(
                    provider=self.name,
                    output_path=local_path,
                    metadata={
                        "request_id": request_id,
                        "status": status or "completed",
                        "source_url": url,
                        "duration": int(duration),
                        "aspect_ratio": aspect_ratio,
                        "resolution": resolution,
                        "model": model,
                    },
                )

            if status in {"failed", "error", "cancelled"}:
                raise RuntimeError(f"Grok generation ended with status '{status}': {poll_data}")

            time.sleep(self.poll_interval)

        raise RuntimeError(f"Grok generation timed out after {self.max_wait_seconds}s")
