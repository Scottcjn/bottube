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


# Ordered cascade — first that succeeds wins; all raise -> refund.
PROVIDERS = [_provider_meshy]


def generate_3d(prompt: str, art_style: str = "realistic"):
    """Try each provider in order. Returns (glb_bytes, meta). Raises Forge3DError."""
    last = None
    for prov in PROVIDERS:
        try:
            return prov(prompt, art_style=art_style)
        except Forge3DNoCredits as e:
            last = e  # try next backend if any; preserve the no-credits signal
        except Exception as e:  # noqa: BLE001 - any backend failure -> try next
            last = e
    raise last if last is not None else Forge3DError("no_providers")
