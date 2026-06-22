# SPDX-License-Identifier: Apache-2.0
# Author: @Scottcjn (Elyan Labs)
"""
Forge3D provider layer — the SWAPPABLE 3D backend behind Studio's 3D mode.

Phase-0 wraps Meshy's public text-to-3D API. The whole point (design §0.1): the
model is a swappable backend, not the product. To add/replace a backend (TRELLIS
or Tripo on our own fleet, etc.), add a `_provider_*` function and list it in
PROVIDERS — the billing/job/refund rails in forge3d_blueprint never change.

Each provider returns (glb_bytes, meta_dict) on success or raises on failure.
Raising is the contract that triggers the RTC refund upstream.
"""
import os
import time

import requests

MESHY_ROOT = "https://api.meshy.ai/openapi"
_TIMEOUT = float(os.environ.get("FORGE3D_TIMEOUT", "300"))   # total wait for a task
_POLL = float(os.environ.get("FORGE3D_POLL", "5"))
# Local TRELLIS backend (our V100 fleet). Internal host -> env, not repo. Empty = disabled.
TRELLIS_URL = os.environ.get("TRELLIS_URL", "").strip()
_TRELLIS_TIMEOUT = float(os.environ.get("FORGE3D_TRELLIS_TIMEOUT", "600"))


class Forge3DError(Exception):
    """Generation failed — upstream refunds the RTC."""


class Forge3DNoCredits(Forge3DError):
    """Backend is out of credits/quota (HTTP 402) — distinct so the UI can say so."""


def _provider_meshy(prompt: str, art_style: str = "realistic"):
    key = os.environ.get("MESHY_API_KEY", "").strip()
    if not key:
        raise Forge3DError("no_backend_configured")
    h = {"Authorization": f"Bearer {key}"}

    r = requests.post(
        f"{MESHY_ROOT}/v2/text-to-3d",
        json={"mode": "preview", "prompt": prompt[:600],
              "art_style": art_style, "should_remesh": True},
        headers=h, timeout=30)
    if r.status_code == 402:
        raise Forge3DNoCredits("backend_out_of_credits")
    r.raise_for_status()
    task_id = (r.json() or {}).get("result")
    if not task_id:
        raise Forge3DError("no_task_id")

    deadline = time.time() + _TIMEOUT
    while time.time() < deadline:
        time.sleep(_POLL)
        s = requests.get(f"{MESHY_ROOT}/v2/text-to-3d/{task_id}", headers=h, timeout=30)
        s.raise_for_status()
        d = s.json() or {}
        st = d.get("status")
        if st == "SUCCEEDED":
            urls = d.get("model_urls") or {}
            glb = urls.get("glb")
            if not glb:
                raise Forge3DError("no_glb_in_result")
            g = requests.get(glb, timeout=180)
            g.raise_for_status()
            return g.content, {"backend": "meshy", "task_id": task_id,
                               "formats": sorted(urls.keys())}
        if st in ("FAILED", "EXPIRED", "CANCELED"):
            raise Forge3DError(f"backend_task_{str(st).lower()}")
    raise Forge3DError("backend_timeout")


def _provider_trellis(prompt: str, art_style: str = "realistic"):
    """Local TRELLIS (our V100): text -> image (local SDXL) -> image-to-3D -> GLB.

    The TRELLIS box does the whole text->image->3D pipeline on-GPU (no external
    image API, no quota, zero per-job COGS). We just hand it the prompt."""
    if not TRELLIS_URL:
        raise Forge3DError("trellis_not_configured")
    r = requests.post(
        TRELLIS_URL.rstrip("/") + "/generate",
        data={"prompt": prompt[:600], "seed": "1"}, timeout=_TRELLIS_TIMEOUT)
    if r.status_code != 200:
        raise Forge3DError(f"trellis_http_{r.status_code}")
    if not r.content or len(r.content) < 256:
        raise Forge3DError("trellis_empty")
    return r.content, {"backend": "trellis-v100", "formats": ["glb"]}


def generate_3d(prompt: str, art_style: str = "realistic"):
    """Cascade: local TRELLIS first (free, our hardware), Meshy as fallback.
    Returns (glb_bytes, meta). Raises Forge3DError if all backends fail (-> refund)."""
    providers = []
    if TRELLIS_URL:
        providers.append(_provider_trellis)
    providers.append(_provider_meshy)
    last = None
    for prov in providers:
        try:
            return prov(prompt, art_style=art_style)
        except Forge3DNoCredits as e:
            last = e  # try next backend if any; preserve the no-credits signal
        except Exception as e:  # noqa: BLE001 - any backend failure -> try next
            last = e
    raise last if last is not None else Forge3DError("no_providers")
