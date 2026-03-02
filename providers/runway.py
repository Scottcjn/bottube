from __future__ import annotations

import os
import time
from typing import Any, Iterable

from providers.base import GeneratedVideo, VideoGenProvider
from providers.utils import download_file


class RunwayProvider(VideoGenProvider):
    """Runway text/image-to-video provider via the official SDK."""

    name = "runway"

    TEXT_ALLOWED_DURATIONS = (4, 6, 8)
    IMAGE_ALLOWED_DURATIONS = (4, 5, 6, 8, 10)
    TEXT_ALLOWED_RATIOS = ("1280:720", "720:1280", "1080:1920", "1920:1080")

    def __init__(
        self,
        api_key: str | None = None,
        poll_interval: int = 5,
        max_wait_seconds: int = 900,
    ) -> None:
        self.api_key = api_key or os.environ.get("RUNWAYML_API_SECRET", "")
        self.poll_interval = poll_interval
        self.max_wait_seconds = max_wait_seconds
        self._client = None

    @staticmethod
    def _nearest_allowed(value: int, allowed: Iterable[int]) -> int:
        return min(allowed, key=lambda item: abs(item - value))

    def _client_or_raise(self):
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise RuntimeError("RUNWAYML_API_SECRET is not set")

        try:
            from runwayml import RunwayML
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "runwayml package is not installed. Install with: pip install runwayml"
            ) from exc

        self._client = RunwayML(api_key=self.api_key)
        return self._client

    def generate(self, prompt: str, duration: int = 8, **kwargs: Any) -> GeneratedVideo:
        client = self._client_or_raise()

        model = kwargs.get("runway_model") or kwargs.get("model") or os.environ.get("RUNWAY_MODEL", "gen4.5")
        ratio = kwargs.get("ratio") or kwargs.get("runway_ratio") or os.environ.get("RUNWAY_RATIO", "1280:720")
        audio = bool(kwargs.get("audio", False))
        prompt_image = kwargs.get("prompt_image") or kwargs.get("runway_image")
        output_path = kwargs.get("output_path")

        use_image_to_video = bool(prompt_image) or model in {"gen4_turbo", "gen3a_turbo"}

        if use_image_to_video and not prompt_image:
            raise RuntimeError(
                f"Runway model '{model}' requires an image input. Pass --runway-image <path_or_url>."
            )

        if use_image_to_video:
            normalized_duration = self._nearest_allowed(int(duration), self.IMAGE_ALLOWED_DURATIONS)
            create_resp = client.image_to_video.create(
                model=model,
                prompt_image=prompt_image,
                prompt_text=prompt,
                duration=normalized_duration,
                ratio=ratio,
                audio=audio,
            )
        else:
            normalized_duration = self._nearest_allowed(int(duration), self.TEXT_ALLOWED_DURATIONS)
            normalized_ratio = ratio if ratio in self.TEXT_ALLOWED_RATIOS else "1280:720"
            create_resp = client.text_to_video.create(
                model=model,
                prompt_text=prompt,
                duration=normalized_duration,
                ratio=normalized_ratio,
                audio=audio,
            )
            ratio = normalized_ratio

        task_id = create_resp.id
        started = time.time()

        while time.time() - started < self.max_wait_seconds:
            task = client.tasks.retrieve(task_id)
            status = str(getattr(task, "status", "")).upper()

            if status == "SUCCEEDED":
                outputs = list(getattr(task, "output", []) or [])
                if not outputs:
                    raise RuntimeError(f"Runway task succeeded but returned no output URLs: {task}")

                source_url = outputs[0]
                local_path = download_file(source_url, output_path, prefix="runway_video_")
                return GeneratedVideo(
                    provider=self.name,
                    output_path=local_path,
                    metadata={
                        "task_id": task_id,
                        "status": status,
                        "source_url": source_url,
                        "duration": normalized_duration,
                        "ratio": ratio,
                        "model": model,
                        "audio": audio,
                        "used_image_to_video": use_image_to_video,
                    },
                )

            if status == "FAILED":
                failure = getattr(task, "failure", "unknown failure")
                failure_code = getattr(task, "failure_code", None)
                if failure_code:
                    raise RuntimeError(f"Runway generation failed ({failure_code}): {failure}")
                raise RuntimeError(f"Runway generation failed: {failure}")

            if status in {"CANCELLED", "THROTTLED"}:
                raise RuntimeError(f"Runway task ended with status {status}")

            time.sleep(self.poll_interval)

        raise RuntimeError(f"Runway generation timed out after {self.max_wait_seconds}s (task {task_id})")
