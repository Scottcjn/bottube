# SPDX-License-Identifier: MIT
"""
ModelRunner provider
====================
Queue-based: submit -> poll status -> download result.
Activate by setting MODELRUNNER_KEY in environment.

The endpoint is configurable with MODELRUNNER_VIDEO_MODEL, so this one adapter
covers any text-to-video model in the catalog without a code change.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Optional, Tuple

from generation.models import GenerationMode, GenerationRequest
from generation.provider import GenerationProvider, ProviderCapabilities

log = logging.getLogger("generation.providers.modelrunner")

MODELRUNNER_KEY = os.environ.get("MODELRUNNER_KEY", "")
MODELRUNNER_MODEL = os.environ.get(
    "MODELRUNNER_VIDEO_MODEL", "wan-video/wan/v3.0/text-to-video"
)
MODELRUNNER_QUEUE_URL = "https://queue.modelrunner.run"

# Finished videos are fetched only from the platform's own media CDN, over
# HTTPS. The result payload names the download host, so without this pin a
# mis-pointed or tampered response could make the worker fetch from anywhere.
MEDIA_HOSTS = ("media.modelrunner.ai",)

# get_status() polls a remote queue; a run of transport errors (timeout, DNS
# blip, 5xx) must not be indistinguishable from a job that is genuinely still
# queued. After this many consecutive poll failures for the same request we
# report it failed instead of returning "pending" forever.
_MAX_CONSECUTIVE_POLL_ERRORS = 5

# Model accepts 2-30s; the router may ask for more, so requests are clamped.
MIN_DURATION = 2
MAX_DURATION = 30

VIDEO_WIDTH = 720
VIDEO_HEIGHT = 720


def _headers() -> dict:
    """Auth + content headers for every call to the queue API."""
    return {
        "Authorization": f"Key {MODELRUNNER_KEY}",
        "Content-Type": "application/json",
    }


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Fail any 3xx instead of following it.

    urllib copies every header except Content-* onto a redirected request, so
    a redirect off the queue host would carry the API key to whichever host it
    named. The queue API never redirects, so refusing them all costs nothing.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code, f"redirect to {newurl} refused", headers, fp
        )


_opener = urllib.request.build_opener(_RefuseRedirects())


def open_url(req: urllib.request.Request, timeout: float):
    """urlopen() that refuses redirects; every network call goes through it."""
    return _opener.open(req, timeout=timeout)


def is_allowed_media_url(url: str) -> bool:
    """True only for an HTTPS URL on the media CDN (exact host or a subdomain).

    Matched on the parsed hostname, not by substring, so
    `media.modelrunner.ai.evil.example` and `media.modelrunner.ai@evil.example`
    are both rejected.
    """
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return False
    if parts.scheme != "https" or not host:
        return False
    return any(
        host == allowed or host.endswith(f".{allowed}") for allowed in MEDIA_HOSTS
    )


def download_media(url: str, dest: Path) -> None:
    """Stream an allowed media URL to `dest`.

    Sends no Authorization header (the CDN is public, and the key belongs to
    the queue host alone) and, via open_url, follows no redirects.
    """
    if not is_allowed_media_url(url):
        raise ValueError(f"refusing to download from outside {MEDIA_HOSTS}: {url}")
    with open_url(urllib.request.Request(url), timeout=120) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh)


def _reencode(raw_path: Path, out_path: Path) -> bool:
    """Re-encode to the standard 720x720 H.264 MP4 with a silent stereo track.

    Both inputs are declared before any output option: ffmpeg reads its
    arguments positionally, so a filter or codec flag placed ahead of the
    second `-i` is taken as an option *for that input* and the whole command
    is rejected. The explicit maps take video from the download and audio from
    the silent source even when the model returned a soundtrack.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", str(raw_path),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", (
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}"
            f":force_original_aspect_ratio=decrease,"
            f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x1a1a2e"
        ),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(out_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired:
        log.warning("ffmpeg re-encode timed out after 60s")
        out_path.unlink(missing_ok=True)
        return False
    if proc.returncode != 0:
        log.warning(
            "ffmpeg re-encode failed (exit %d): %s",
            proc.returncode, proc.stderr.decode(errors="replace")[-500:],
        )
        # ffmpeg may have opened the output before failing; leave nothing partial.
        out_path.unlink(missing_ok=True)
        return False
    return out_path.exists()


class ModelRunnerProvider(GenerationProvider):

    def __init__(self):
        # request_id -> consecutive get_status() poll failures (transport
        # error, HTTP error, malformed JSON). Reset on any poll that reaches
        # the queue, whatever state it reports.
        self._consecutive_poll_errors: dict = {}

    def get_name(self) -> str:
        """Return this provider's registry key."""
        return "modelrunner"

    def get_capabilities(self) -> ProviderCapabilities:
        """Describe what this provider supports (modes, limits, cost/quality tier, availability)."""
        return ProviderCapabilities(
            name="modelrunner",
            modes=[GenerationMode.text_to_video],
            max_duration=MAX_DURATION,
            max_resolution=(1280, 720),
            # The model returns a native soundtrack, but the shared re-encode
            # step replaces audio with a silent track for every provider, so
            # audio is switched off at submit time rather than paid for and
            # discarded.
            supports_audio=False,
            supports_captions=False,
            estimated_latency_s=90.0,
            quality_tier=4,
            # A paid API with no free tier, unlike the free-tier backends above.
            cost_tier=3,
            requires_api_key=True,
            available=bool(MODELRUNNER_KEY),
        )

    def validate_input(self, req: GenerationRequest) -> Tuple[bool, str]:
        """Check the request has a prompt and the API key is configured before submitting."""
        if not req.prompt:
            return False, "prompt is required"
        if not MODELRUNNER_KEY:
            return False, "MODELRUNNER_KEY not configured"
        return True, ""

    def submit(self, req: GenerationRequest, output_dir: Path) -> Tuple[bool, str]:
        """Enqueue a generation job on ModelRunner; returns (ok, request_id_or_error)."""
        duration = max(MIN_DURATION, min(req.duration, MAX_DURATION))
        payload = json.dumps({
            "prompt": req.prompt,
            "duration": duration,
            "resolution": "720P",
            "aspect_ratio": "1:1",
            "audio": False,
        }).encode()

        try:
            http_req = urllib.request.Request(
                f"{MODELRUNNER_QUEUE_URL}/{MODELRUNNER_MODEL}",
                data=payload,
                headers=_headers(),
            )
            with open_url(http_req, timeout=15) as resp:
                result = json.loads(resp.read())

            request_id = result.get("request_id", "")
            if not request_id:
                return False, "no request_id returned"
            return True, request_id
        except Exception as exc:
            return False, str(exc)

    def get_status(self, external_id: str) -> Tuple[str, float]:
        """Poll the queue for a job's status; returns (status_label, progress_fraction).

        A transport error, HTTP error, or malformed body is a transient poll
        failure, not proof the job is still queued: it is counted separately
        and, after _MAX_CONSECUTIVE_POLL_ERRORS in a row, reported as "failed"
        so the router stops polling instead of waiting out its own deadline.
        """
        status_url = (
            f"{MODELRUNNER_QUEUE_URL}/{MODELRUNNER_MODEL}"
            f"/requests/{external_id}/status"
        )
        try:
            req = urllib.request.Request(status_url, headers=_headers())
            with open_url(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if not isinstance(data, dict):
                raise ValueError("status payload is not an object")
        except Exception as exc:
            errors = self._consecutive_poll_errors.get(external_id, 0) + 1
            self._consecutive_poll_errors[external_id] = errors
            log.warning(
                "ModelRunner status poll failed for %s (attempt %d/%d): %s",
                external_id, errors, _MAX_CONSECUTIVE_POLL_ERRORS, exc,
            )
            if errors >= _MAX_CONSECUTIVE_POLL_ERRORS:
                self._consecutive_poll_errors.pop(external_id, None)
                return "failed", 0.0
            return "pending", 0.0

        # The queue answered, so any earlier errors for this job were transient.
        self._consecutive_poll_errors.pop(external_id, None)

        status = data.get("status", "IN_QUEUE")
        if status == "COMPLETED":
            return "completed", 1.0
        if status in ("FAILED", "CANCELLED"):
            return "failed", 0.0
        if status == "IN_PROGRESS":
            return "running", 0.5
        return "pending", 0.0

    def get_result(self, external_id: str, output_dir: Path) -> Optional[Path]:
        """Download a completed job's video and re-encode it to the standard output format."""
        result_url = (
            f"{MODELRUNNER_QUEUE_URL}/{MODELRUNNER_MODEL}/requests/{external_id}"
        )
        try:
            req = urllib.request.Request(result_url, headers=_headers())
            with open_url(req, timeout=30) as resp:
                final = json.loads(resp.read())

            video_url = _extract_video_url(final.get("output"))
            if not video_url:
                return None

            raw_path = output_dir / f"modelrunner_raw_{uuid.uuid4().hex[:8]}.mp4"
            out_path = output_dir / f"modelrunner_{uuid.uuid4().hex[:8]}.mp4"
            try:
                download_media(video_url, raw_path)
                ok = _reencode(raw_path, out_path)
            finally:
                raw_path.unlink(missing_ok=True)
            return out_path if ok else None
        except Exception as exc:
            log.warning("ModelRunner result download failed: %s", exc)
            return None

    def cancel(self, external_id: str) -> bool:
        """Request cancellation of a queued/running job; returns True if the call succeeded."""
        cancel_url = (
            f"{MODELRUNNER_QUEUE_URL}/{MODELRUNNER_MODEL}"
            f"/requests/{external_id}/cancel"
        )
        try:
            req = urllib.request.Request(
                cancel_url, method="PUT", headers=_headers()
            )
            with open_url(req, timeout=10):
                pass
            return True
        except Exception:
            return False


def _extract_video_url(output) -> str:
    """Pull the video URL out of a completed request's output.

    Output shape is defined by the model, not the platform: most video models
    return the URL as a bare string, others wrap it in an object. Handling both
    is what lets MODELRUNNER_VIDEO_MODEL point at any of them.
    """
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        for key in ("video_url", "url", "video", "output"):
            value = output.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                nested = value.get("url")
                if isinstance(nested, str) and nested:
                    return nested
    if isinstance(output, list) and output:
        return _extract_video_url(output[0])
    return ""
