"""
ComfyUI / LTX-2 local GPU provider
====================================
Connects to the ComfyUI instance on the LTX Video Server
(Tailscale 100.95.77.124:8188, LAN 192.168.0.136).

Synchronous workflow: queue prompt -> poll history -> download output.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Optional, Tuple

from generation.models import GenerationMode, GenerationRequest
from generation.provider import GenerationProvider, ProviderCapabilities

log = logging.getLogger("generation.providers.comfyui_ltx")

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://100.95.77.124:8188")
COMFYUI_TIMEOUT = int(os.environ.get("COMFYUI_TIMEOUT", "300"))

# LTX-2 workflow template
_LTX_WORKFLOW = {
    "1": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 720, "height": 720, "batch_size": 1},
    },
    "2": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["4", 1]},
    },
    "3": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "low quality, blurry, distorted, watermark",
            "clip": ["4", 1],
        },
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "ltx-video-2b-v0.9.1.safetensors"},
    },
    "5": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
            "model": ["4", 0],
            "positive": ["2", 0],
            "negative": ["3", 0],
            "latent_image": ["1", 0],
        },
    },
    "6": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["5", 0], "vae": ["4", 2]},
    },
    "7": {
        "class_type": "SaveAnimatedWEBP",
        "inputs": {
            "filename_prefix": "bottube_gen",
            "fps": 8,
            "lossless": False,
            "quality": 80,
            "method": "default",
            "images": ["6", 0],
        },
    },
}


class ComfyUILTXProvider(GenerationProvider):
    """Local LTX-2 via ComfyUI."""

    def __init__(self):
        # Completed jobs: prompt_id -> local path
        self._completed: dict = {}

    def get_name(self) -> str:
        return "comfyui_ltx"

    def get_capabilities(self) -> ProviderCapabilities:
        available = self._ping()
        return ProviderCapabilities(
            name="comfyui_ltx",
            modes=[GenerationMode.text_to_video],
            max_duration=8,
            max_resolution=(720, 720),
            supports_audio=False,
            supports_captions=False,
            estimated_latency_s=60.0,
            quality_tier=5,
            cost_tier=1,  # free (own hardware)
            requires_api_key=False,
            available=available,
            styles=["cinematic", "anime", "photorealistic"],
        )

    def validate_input(self, req: GenerationRequest) -> Tuple[bool, str]:
        if not req.prompt:
            return False, "prompt is required"
        if req.mode != GenerationMode.text_to_video:
            return False, "comfyui_ltx only supports text_to_video"
        return True, ""

    def submit(self, req: GenerationRequest, output_dir: Path) -> Tuple[bool, str]:
        workflow = json.loads(json.dumps(_LTX_WORKFLOW))
        workflow["2"]["inputs"]["text"] = req.prompt
        workflow["5"]["inputs"]["seed"] = random.randint(0, 2**31)

        payload = json.dumps({"prompt": workflow}).encode()
        try:
            http_req = urllib.request.Request(
                f"{COMFYUI_URL}/prompt",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(http_req, timeout=15) as resp:
                result = json.loads(resp.read())
            prompt_id = result.get("prompt_id")
            if not prompt_id:
                return False, "no prompt_id returned"
            return True, prompt_id
        except Exception as exc:
            log.warning("ComfyUI submit failed: %s", exc)
            return False, str(exc)

    def get_status(self, external_id: str) -> Tuple[str, float]:
        """Poll ComfyUI history for this prompt_id."""
        if external_id in self._completed:
            return "completed", 1.0
        try:
            with urllib.request.urlopen(
                f"{COMFYUI_URL}/history/{external_id}", timeout=10
            ) as resp:
                history = json.loads(resp.read())
            if external_id in history:
                entry = history[external_id]
                if entry.get("status", {}).get("status_str") == "error":
                    return "failed", 0.0
                if entry.get("outputs"):
                    self._completed[external_id] = entry["outputs"]
                    return "completed", 1.0
                return "running", 0.5
        except Exception:
            pass
        return "pending", 0.0

    def get_result(self, external_id: str, output_dir: Path) -> Optional[Path]:
        output_data = self._completed.get(external_id)
        if not output_data:
            return None

        for _node_id, node_out in output_data.items():
            images = node_out.get("images") or node_out.get("gifs", [])
            for img_info in images:
                filename = img_info.get("filename")
                subfolder = img_info.get("subfolder", "")
                if not filename:
                    continue
                params = urllib.parse.urlencode({
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": "output",
                })
                try:
                    with urllib.request.urlopen(
                        f"{COMFYUI_URL}/view?{params}", timeout=30
                    ) as resp:
                        data = resp.read()
                    out_path = output_dir / f"comfyui_{uuid.uuid4().hex[:8]}.webp"
                    out_path.write_bytes(data)
                    return out_path
                except Exception as exc:
                    log.warning("ComfyUI download failed: %s", exc)
        return None

    def cancel(self, external_id: str) -> bool:
        try:
            payload = json.dumps({"delete": [external_id]}).encode()
            req = urllib.request.Request(
                f"{COMFYUI_URL}/queue",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    def _ping(self) -> bool:
        """Quick health check."""
        try:
            with urllib.request.urlopen(f"{COMFYUI_URL}/system_stats", timeout=5):
                return True
        except Exception:
            return False
