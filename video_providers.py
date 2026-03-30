"""
Video Provider Registry with Auto-Failover and Health Monitoring
================================================================
Tracks provider health, latency, and automatically skips unhealthy
backends. Self-healing: providers recover after a cooldown period.
"""
from __future__ import annotations

import threading
import time
import os
from typing import Callable, Dict, List, Optional, Tuple


class ProviderRegistry:
    """Track provider health and auto-failover."""

    # Consecutive failures before marking unhealthy
    FAIL_THRESHOLD = 3
    # Seconds before an unhealthy provider is retried
    COOLDOWN_SECS = 300  # 5 minutes

    def __init__(self):
        self._lock = threading.Lock()
        self._providers: Dict[str, dict] = {}
        # Insertion order for deterministic rotation
        self._order: List[str] = []

    def register(self, name: str, fn: Callable, requires_key_env: Optional[str] = None):
        """Register a provider. Skip if required env var is not set."""
        if requires_key_env and not os.environ.get(requires_key_env, ""):
            return
        with self._lock:
            self._providers[name] = {
                "fn": fn,
                "healthy": True,
                "last_check": 0.0,
                "fail_count": 0,
                "success_count": 0,
                "avg_latency": 0.0,
                "last_failure_time": 0.0,
            }
            if name not in self._order:
                self._order.append(name)

    def get_ordered(self, job_id: str) -> List[Tuple[str, Callable]]:
        """Return providers ordered by: healthy first, then rotated by job_id hash.

        Unhealthy providers whose cooldown has expired are included at the end
        so they get a chance to recover.
        """
        with self._lock:
            now = time.time()
            healthy = []
            cooldown_ready = []
            still_down = []

            for name in self._order:
                info = self._providers[name]
                if info["healthy"]:
                    healthy.append(name)
                elif now - info["last_failure_time"] >= self.COOLDOWN_SECS:
                    # Cooldown expired -- give it another chance
                    cooldown_ready.append(name)
                else:
                    still_down.append(name)

            # Rotate healthy providers by job_id for load distribution
            if healthy:
                start = hash(job_id) % len(healthy)
                healthy = healthy[start:] + healthy[:start]

            ordered = healthy + cooldown_ready
            # still_down providers are omitted -- no point wasting time

            return [(name, self._providers[name]["fn"]) for name in ordered]

    def report_success(self, name: str, latency: float):
        """Mark provider as healthy, update average latency."""
        with self._lock:
            info = self._providers.get(name)
            if not info:
                return
            info["healthy"] = True
            info["fail_count"] = 0
            info["success_count"] += 1
            info["last_check"] = time.time()
            # Exponential moving average (alpha=0.3)
            if info["avg_latency"] == 0.0:
                info["avg_latency"] = latency
            else:
                info["avg_latency"] = 0.7 * info["avg_latency"] + 0.3 * latency

    def report_failure(self, name: str):
        """Increment fail count. Mark unhealthy after FAIL_THRESHOLD consecutive failures."""
        with self._lock:
            info = self._providers.get(name)
            if not info:
                return
            info["fail_count"] += 1
            info["last_check"] = time.time()
            info["last_failure_time"] = time.time()
            if info["fail_count"] >= self.FAIL_THRESHOLD:
                info["healthy"] = False

    def health_check(self):
        """Reset providers whose cooldown has expired (called periodically or on demand)."""
        with self._lock:
            now = time.time()
            for info in self._providers.values():
                if not info["healthy"] and now - info["last_failure_time"] >= self.COOLDOWN_SECS:
                    info["healthy"] = True
                    info["fail_count"] = 0

    def status(self) -> List[dict]:
        """Return status of all providers for the /providers API endpoint."""
        with self._lock:
            result = []
            for name in self._order:
                info = self._providers[name]
                result.append({
                    "name": name,
                    "healthy": info["healthy"],
                    "fail_count": info["fail_count"],
                    "success_count": info["success_count"],
                    "avg_latency_ms": round(info["avg_latency"] * 1000),
                    "last_check": round(info["last_check"], 1) if info["last_check"] else None,
                })
            return result
