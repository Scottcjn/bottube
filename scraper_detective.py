"""
BoTTube Scraper Detective — Real-time bot detection with 3-layer analysis.

Layer 1: ASN + IP reputation (Team Cymru DNS, background threads)
Layer 2: JavaScript challenge (POST /api/bt-proof proves browser executed JS)
Layer 3: Behavioral fingerprint (per-IP timing, paths, asset ratio)

Classification engine combines signals into 0.0-1.0 confidence score.
Dashboard at /scraper-dashboard?key=ADMIN_KEY shows live scraper activity.

Zero external dependencies — uses only Python stdlib.
"""

import hashlib
import hmac
import json
import math
import os
import socket
import struct
import threading
import time
from collections import deque
from typing import Dict, List, Tuple

from flask import Blueprint, Response, jsonify, request

scraper_bp = Blueprint("scraper_detective", __name__)

# ---------------------------------------------------------------------------
# Known ASN databases
# ---------------------------------------------------------------------------

# Cloud/hosting/VPN providers — high probability of bot traffic
HOSTING_ASNS: Dict[int, str] = {
    # Major cloud
    16509: "Amazon AWS", 14618: "Amazon AWS",
    8075: "Microsoft Azure", 8068: "Microsoft Azure",
    15169: "Google Cloud", 396982: "Google Cloud",
    13335: "Cloudflare", 20940: "Akamai",
    # Hosting
    14061: "DigitalOcean", 63949: "Linode/Akamai",
    20473: "Vultr", 24940: "Hetzner",
    16276: "OVHcloud", 12876: "Scaleway",
    51167: "Contabo", 46664: "VolumeDrive",
    36352: "ColoCrossing", 53667: "FranTech/BuyVM",
    55286: "ServerMania", 62567: "DigitalOcean",
    # VPN/Proxy infra
    9009: "M247 (VPN)", 212238: "Datacamp (proxy)",
    # Data center / scraping infra
    202422: "GCore", 397423: "Mullvad VPN",
    # Chinese hosting commonly used by bots
    4134: "ChinaNet", 4837: "China169",
    45090: "Tencent Cloud", 37963: "Alibaba Cloud",
}

# Legitimate search engine ASNs — cross-validated with UA
SEARCH_ENGINE_ASNS: Dict[int, str] = {
    15169: "Google", 396982: "Google",
    8075: "Microsoft/Bing", 8068: "Microsoft/Bing",
    13238: "Yandex", 36647: "Yahoo",
    14618: "Amazon/Alexa",
    13414: "Twitter", 54113: "Fastly/Pinterest",
}

SEARCH_ENGINE_UA_SIGS = ("googlebot", "bingbot", "yandex", "slurp", "baiduspider",
                          "duckduckbot", "applebot", "linkedinbot")

# Paths that are assets (not pages)
_ASSET_PREFIXES = ("/static/", "/thumbnails/", "/avatars/", "/avatar/",
                   "/badge/", "/stats/", "/favicon.ico")
_API_PREFIX = "/api/"


# ---------------------------------------------------------------------------
# BehaviorWindow — per-IP sliding window tracking
# ---------------------------------------------------------------------------

class BehaviorWindow:
    """Sliding window of request data for behavioral analysis."""
    __slots__ = ("timestamps", "paths", "asset_count", "page_count",
                 "api_count", "referrers", "user_agents", "last_seen", "created")

    def __init__(self):
        self.timestamps: deque = deque(maxlen=500)
        self.paths: deque = deque(maxlen=200)
        self.asset_count: int = 0
        self.page_count: int = 0
        self.api_count: int = 0
        self.referrers: set = set()
        self.user_agents: set = set()
        self.last_seen: float = 0.0
        self.created: float = time.time()

    def is_expired(self, ttl: float) -> bool:
        return (time.time() - self.last_seen) > ttl if self.last_seen else True


# ---------------------------------------------------------------------------
# ScraperDetective — main detection engine
# ---------------------------------------------------------------------------

class ScraperDetective:
    """Real-time scraper detection engine with 3-layer analysis."""

    def __init__(self, hmac_secret: str = ""):
        self._hmac_secret = (hmac_secret or os.environ.get(
            "BOTTUBE_PROOF_SECRET", "bt_proof_default_2026"
        )).encode()

        # Layer 1: ASN cache — ip -> (asn_num, asn_name, is_hosting, lookup_time)
        self._asn_cache: Dict[str, Tuple[int, str, bool, float]] = {}
        self._asn_cache_lock = threading.Lock()
        self._ASN_CACHE_MAX = 10_000
        self._ASN_CACHE_TTL = 86400  # 24h

        self._asn_pending: set = set()
        self._asn_pending_lock = threading.Lock()

        # Layer 2: JS proof — ip -> {proved, proved_at, page_views, webdriver_detected, no_plugins}
        self._js_proof: Dict[str, dict] = {}

        # Layer 3: Behavioral — ip -> BehaviorWindow
        self._behavior: Dict[str, BehaviorWindow] = {}
        self._behavior_lock = threading.Lock()
        self._BEHAVIOR_TTL = 3600  # 1h

        # IP blocklist (admin-set)
        self._blocked_ips: set = set()

        # Classification cache — ip -> (label, score, signals, expire_time)
        self._class_cache: Dict[str, Tuple[str, float, dict, float]] = {}
        self._CLASS_CACHE_TTL = 30  # seconds

        # DNS resolver address
        self._resolver = self._find_resolver()

        # Background cleanup
        t = threading.Thread(target=self._cleanup_loop, daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Layer 1: ASN lookup via Team Cymru DNS
    # ------------------------------------------------------------------

    @staticmethod
    def _find_resolver() -> str:
        """Read system DNS resolver from /etc/resolv.conf."""
        try:
            with open("/etc/resolv.conf") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("nameserver"):
                        addr = line.split()[1]
                        if ":" not in addr:  # prefer IPv4 resolver
                            return addr
        except Exception:
            pass
        return "127.0.0.53"

    def _dns_txt_query(self, domain: str) -> int:
        """Raw UDP DNS TXT query. Returns ASN number or 0."""
        try:
            # Build DNS query packet
            txn_id = os.urandom(2)
            header = txn_id + b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'

            question = b''
            for label in domain.split('.'):
                question += bytes([len(label)]) + label.encode('ascii')
            question += b'\x00\x00\x10\x00\x01'  # TXT, IN

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3.0)
            try:
                sock.sendto(header + question, (self._resolver, 53))
                data, _ = sock.recvfrom(1024)
            finally:
                sock.close()

            # Parse response — skip header (12 bytes), skip question section
            offset = 12
            while offset < len(data) and data[offset] != 0:
                if data[offset] & 0xC0 == 0xC0:
                    offset += 2
                    break
                offset += 1 + data[offset]
            else:
                offset += 1
            offset += 4  # QTYPE + QCLASS

            # Read answer RRs
            ancount = struct.unpack("!H", data[6:8])[0]
            for _ in range(ancount):
                if offset >= len(data):
                    break
                # Skip name (possibly compressed)
                if data[offset] & 0xC0 == 0xC0:
                    offset += 2
                else:
                    while offset < len(data) and data[offset] != 0:
                        offset += 1 + data[offset]
                    offset += 1
                if offset + 10 > len(data):
                    break
                rtype = struct.unpack("!H", data[offset:offset + 2])[0]
                rdlength = struct.unpack("!H", data[offset + 8:offset + 10])[0]
                offset += 10
                if rtype == 16 and offset < len(data):  # TXT
                    txt_len = data[offset]
                    txt = data[offset + 1:offset + 1 + txt_len].decode("ascii", errors="replace")
                    # Format: "ASN | IP | prefix | CC | registry"
                    parts = txt.split("|")
                    if parts:
                        try:
                            return int(parts[0].strip())
                        except ValueError:
                            pass
                offset += rdlength
        except Exception:
            pass
        return 0

    def _lookup_asn(self, ip: str) -> Tuple[int, str, bool]:
        """Perform ASN lookup for IPv4 address."""
        try:
            parts = ip.split(".")
            if len(parts) != 4:
                return 0, "invalid_ip", False
            reversed_ip = ".".join(reversed(parts))
            domain = f"{reversed_ip}.origin.asn.cymru.com"
            asn_num = self._dns_txt_query(domain)
            if not asn_num:
                return 0, "unknown", False
            is_hosting = asn_num in HOSTING_ASNS
            name = HOSTING_ASNS.get(asn_num, SEARCH_ENGINE_ASNS.get(asn_num, f"AS{asn_num}"))
            return asn_num, name, is_hosting
        except Exception:
            return 0, "lookup_failed", False

    def _async_asn_lookup(self, ip: str):
        """Schedule background ASN lookup."""
        with self._asn_pending_lock:
            if ip in self._asn_pending:
                return
            self._asn_pending.add(ip)

        def _do():
            try:
                asn_num, asn_name, is_hosting = self._lookup_asn(ip)
                with self._asn_cache_lock:
                    if len(self._asn_cache) >= self._ASN_CACHE_MAX:
                        oldest = min(self._asn_cache, key=lambda k: self._asn_cache[k][3])
                        del self._asn_cache[oldest]
                    self._asn_cache[ip] = (asn_num, asn_name, is_hosting, time.time())
            finally:
                with self._asn_pending_lock:
                    self._asn_pending.discard(ip)

        threading.Thread(target=_do, daemon=True).start()

    def get_asn_info(self, ip: str) -> Tuple[int, str, bool]:
        """Get ASN info (cached or async). Returns (asn_num, name, is_hosting)."""
        with self._asn_cache_lock:
            cached = self._asn_cache.get(ip)
            if cached and (time.time() - cached[3]) < self._ASN_CACHE_TTL:
                return cached[0], cached[1], cached[2]
        self._async_asn_lookup(ip)
        return 0, "pending", False

    # ------------------------------------------------------------------
    # Layer 2: JS challenge proof
    # ------------------------------------------------------------------

    def record_js_proof(self, ip: str):
        """Record that an IP executed JavaScript (called /api/bt-proof)."""
        entry = self._js_proof.setdefault(ip, {
            "proved": False, "proved_at": 0.0, "page_views": 0
        })
        entry["proved"] = True
        entry["proved_at"] = time.time()

    def record_page_view(self, ip: str):
        """Increment page view counter for JS proof tracking."""
        entry = self._js_proof.setdefault(ip, {
            "proved": False, "proved_at": 0.0, "page_views": 0
        })
        entry["page_views"] = entry.get("page_views", 0) + 1

    # ------------------------------------------------------------------
    # Layer 3: Behavioral recording
    # ------------------------------------------------------------------

    def record_request(self, ip: str, ua: str, path: str,
                       visitor_id: str, is_new: bool, referrer: str = ""):
        """Record a request for all 3 detection layers. Called from track_visitors()."""
        now = time.time()

        # Layer 1: trigger async ASN lookup
        self.get_asn_info(ip)

        # Layer 2: count page views
        is_asset = any(path.startswith(p) for p in _ASSET_PREFIXES)
        is_api = path.startswith(_API_PREFIX)
        if not is_asset and not is_api:
            self.record_page_view(ip)

        # Layer 3: behavioral window
        with self._behavior_lock:
            bw = self._behavior.get(ip)
            if not bw or bw.is_expired(self._BEHAVIOR_TTL):
                bw = BehaviorWindow()
                self._behavior[ip] = bw
            bw.timestamps.append(now)
            bw.paths.append(path)
            bw.last_seen = now
            bw.user_agents.add(ua[:128])
            if referrer:
                bw.referrers.add(referrer[:128])
            if is_api:
                bw.api_count += 1
            elif is_asset:
                bw.asset_count += 1
            else:
                bw.page_count += 1

    # ------------------------------------------------------------------
    # IP blocklist
    # ------------------------------------------------------------------

    def is_blocked(self, ip: str) -> bool:
        return ip in self._blocked_ips

    def block_ip(self, ip: str):
        self._blocked_ips.add(ip)

    def unblock_ip(self, ip: str):
        self._blocked_ips.discard(ip)

    # ------------------------------------------------------------------
    # Classification engine
    # ------------------------------------------------------------------

    def classify(self, ip: str, ua: str = "") -> Tuple[str, float, dict]:
        """Classify IP as 'human', 'suspicious', or 'bot'.
        Returns (label, score, signals_dict). Cached 30s per IP.
        """
        now = time.time()
        cached = self._class_cache.get(ip)
        if cached and now < cached[3]:
            return cached[0], cached[1], cached[2]

        score = 0.0
        signals = {}

        # --- Signal: Known scraper UA ---
        try:
            from bottube_server import KNOWN_SCRAPERS
        except ImportError:
            KNOWN_SCRAPERS = {}
        ua_lower = (ua or "").lower()
        for sig in KNOWN_SCRAPERS:
            if sig.lower() in ua_lower:
                score += 0.5
                signals["known_scraper_ua"] = sig
                break

        # --- Signal: ASN is hosting provider ---
        asn_num, asn_name, is_hosting = self.get_asn_info(ip)
        if is_hosting:
            is_legit_engine = False
            for engine_sig in SEARCH_ENGINE_UA_SIGS:
                if engine_sig in ua_lower:
                    if asn_num in SEARCH_ENGINE_ASNS:
                        is_legit_engine = True
                        signals["legit_search_engine"] = engine_sig
                    else:
                        score += 0.6
                        signals["spoofed_engine_ua"] = engine_sig
                    break
            if not is_legit_engine and "spoofed_engine_ua" not in signals:
                score += 0.3
                signals["hosting_asn"] = asn_name

        # --- Signal: No JS proof after 3+ page views ---
        js_info = self._js_proof.get(ip, {})
        page_views = js_info.get("page_views", 0)
        has_proof = js_info.get("proved", False)
        if page_views >= 3 and not has_proof:
            score += 0.3
            signals["no_js_proof"] = f"{page_views}_views"
        if js_info.get("webdriver_detected"):
            score += 0.4
            signals["webdriver"] = True
        if js_info.get("no_plugins"):
            score += 0.1
            signals["zero_plugins"] = True

        # --- Behavioral signals ---
        bw = None
        with self._behavior_lock:
            bw_ref = self._behavior.get(ip)
            if bw_ref and not bw_ref.is_expired(self._BEHAVIOR_TTL):
                # Snapshot data under lock
                bw = {
                    "ts": list(bw_ref.timestamps),
                    "paths": list(bw_ref.paths),
                    "page_count": bw_ref.page_count,
                    "asset_count": bw_ref.asset_count,
                    "api_count": bw_ref.api_count,
                    "ua_count": len(bw_ref.user_agents),
                    "ref_count": len(bw_ref.referrers),
                }

        if bw and len(bw["ts"]) >= 5:
            ts_list = bw["ts"]

            # Signal: Timing uniformity (coefficient of variation)
            intervals = [ts_list[i] - ts_list[i - 1] for i in range(1, len(ts_list))]
            if intervals:
                mean_iv = sum(intervals) / len(intervals)
                if mean_iv > 0.001:
                    variance = sum((x - mean_iv) ** 2 for x in intervals) / len(intervals)
                    cv = math.sqrt(variance) / mean_iv
                    if cv < 0.1:
                        score += 0.2
                        signals["timing_uniform"] = round(cv, 4)

            # Signal: Sequential path crawling
            paths = bw["paths"]
            seq_runs = 0
            for i in range(2, len(paths)):
                try:
                    p1 = paths[i - 2].rstrip("/").rsplit("/", 1)
                    p2 = paths[i - 1].rstrip("/").rsplit("/", 1)
                    p3 = paths[i].rstrip("/").rsplit("/", 1)
                    if (len(p1) == 2 and len(p2) == 2 and len(p3) == 2
                            and p1[0] == p2[0] == p3[0]):
                        n1, n2, n3 = int(p1[1]), int(p2[1]), int(p3[1])
                        if n2 == n1 + 1 and n3 == n2 + 1:
                            seq_runs += 1
                except (IndexError, ValueError):
                    pass
            if seq_runs >= 2:
                score += 0.15
                signals["sequential_crawl"] = seq_runs

            # Signal: Asset ratio (pages without assets = bot)
            if bw["page_count"] > 0:
                asset_ratio = bw["page_count"] / max(bw["asset_count"], 1)
                if asset_ratio > 5:
                    score += 0.1
                    signals["high_page_asset_ratio"] = round(asset_ratio, 1)

            # Signal: Session velocity
            window_dur = ts_list[-1] - ts_list[0] if len(ts_list) > 1 else 1
            if window_dur > 0:
                req_per_5min = len(ts_list) / (window_dur / 300)
                if req_per_5min > 100:
                    score += 0.3
                    signals["high_velocity"] = round(req_per_5min, 0)

            # Signal: No referrer on deep pages
            if bw["ref_count"] == 0 and bw["page_count"] >= 5:
                deep_count = sum(1 for p in paths if p.count("/") >= 2)
                if deep_count >= 5:
                    score += 0.05
                    signals["deep_no_referrer"] = deep_count

            # Signal: Single UA many paths
            if bw["ua_count"] == 1 and len(set(paths)) > 30:
                score += 0.05
                signals["single_ua_many_paths"] = len(set(paths))

            # Signal: API-only behavior (many API calls, zero page views = scraper)
            if bw["api_count"] >= 5 and bw["page_count"] == 0:
                score += 0.25
                signals["api_only_no_pages"] = bw["api_count"]

        score = min(score, 1.0)
        label = "bot" if score >= 0.7 else ("suspicious" if score >= 0.4 else "human")
        self._class_cache[ip] = (label, score, signals, now + self._CLASS_CACHE_TTL)
        return label, score, signals

    # ------------------------------------------------------------------
    # Data export for dashboard
    # ------------------------------------------------------------------

    def get_active_visitors(self) -> List[dict]:
        """Get all active visitors with classification. Sorted by last_seen desc."""
        visitors = []
        with self._behavior_lock:
            active = {ip: bw for ip, bw in self._behavior.items()
                      if not bw.is_expired(self._BEHAVIOR_TTL)}

        for ip, bw in active.items():
            ua_first = next(iter(bw.user_agents), "")
            label, score, signals = self.classify(ip, ua_first)
            asn_num, asn_name, is_hosting = self.get_asn_info(ip)
            js_info = self._js_proof.get(ip, {})

            visitors.append({
                "ip": ip,
                "asn": asn_name,
                "asn_num": asn_num,
                "is_hosting": is_hosting,
                "classification": label,
                "confidence": round(score, 3),
                "signals": signals,
                "request_count": len(bw.timestamps),
                "page_count": bw.page_count,
                "asset_count": bw.asset_count,
                "api_count": bw.api_count,
                "user_agents": list(bw.user_agents)[:3],
                "last_seen": bw.last_seen,
                "first_seen": bw.created,
                "js_proved": js_info.get("proved", False),
                "js_page_views": js_info.get("page_views", 0),
                "webdriver": js_info.get("webdriver_detected", False),
                "paths_sample": list(bw.paths)[-10:],
                "unique_paths": len(set(bw.paths)),
                "is_blocked": ip in self._blocked_ips,
            })

        visitors.sort(key=lambda v: v["last_seen"], reverse=True)
        return visitors

    def get_summary(self) -> dict:
        """Summary stats for dashboard header cards."""
        visitors = self.get_active_visitors()
        bots = [v for v in visitors if v["classification"] == "bot"]
        suspicious = [v for v in visitors if v["classification"] == "suspicious"]
        humans = [v for v in visitors if v["classification"] == "human"]

        now = time.time()
        recent = 0
        with self._behavior_lock:
            for bw in self._behavior.values():
                recent += sum(1 for t in bw.timestamps if (now - t) < 60)

        return {
            "total_active": len(visitors),
            "bots": len(bots),
            "suspicious": len(suspicious),
            "humans": len(humans),
            "blocked": len(self._blocked_ips),
            "requests_per_min": recent,
            "asn_cache_size": len(self._asn_cache),
            "top_scrapers": sorted(
                [{"ip": v["ip"], "asn": v["asn"], "requests": v["request_count"],
                  "score": v["confidence"]} for v in bots],
                key=lambda x: -x["requests"]
            )[:10],
        }

    # ------------------------------------------------------------------
    # Background cleanup
    # ------------------------------------------------------------------

    def _cleanup_loop(self):
        """Periodically evict expired entries."""
        while True:
            time.sleep(300)
            try:
                now = time.time()
                with self._behavior_lock:
                    expired = [ip for ip, bw in self._behavior.items()
                               if bw.is_expired(self._BEHAVIOR_TTL)]
                    for ip in expired:
                        del self._behavior[ip]

                with self._asn_cache_lock:
                    expired = [ip for ip, v in self._asn_cache.items()
                               if (now - v[3]) > self._ASN_CACHE_TTL]
                    for ip in expired:
                        del self._asn_cache[ip]

                expired = [ip for ip, v in self._js_proof.items()
                           if v.get("proved") and (now - v.get("proved_at", 0)) > 86400]
                for ip in expired:
                    del self._js_proof[ip]

                expired = [ip for ip, v in self._class_cache.items() if now > v[3]]
                for ip in expired:
                    del self._class_cache[ip]
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

detective = ScraperDetective()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_client_ip() -> str:
    """Get client IP (mirrors bottube_server._get_client_ip)."""
    if request.remote_addr in ("127.0.0.1", "::1"):
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


# ---------------------------------------------------------------------------
# Blueprint routes
# ---------------------------------------------------------------------------

@scraper_bp.route("/api/bt-proof", methods=["POST"])
def bt_proof():
    """Receive JS challenge proof. Proves that JavaScript executed in browser."""
    ip = _get_client_ip()
    data = request.get_json(silent=True) or {}

    detective.record_js_proof(ip)

    if data.get("wd"):
        entry = detective._js_proof.setdefault(ip, {
            "proved": False, "proved_at": 0.0, "page_views": 0
        })
        entry["webdriver_detected"] = True

    if data.get("pl") == 0:
        entry = detective._js_proof.setdefault(ip, {
            "proved": False, "proved_at": 0.0, "page_views": 0
        })
        entry["no_plugins"] = True

    return "", 204


@scraper_bp.route("/scraper-dashboard")
def scraper_dashboard():
    """Self-contained scraper detective dashboard. Requires admin key."""
    try:
        from bottube_server import ADMIN_KEY
    except ImportError:
        ADMIN_KEY = ""
    provided = request.args.get("key", "")
    if not provided or not ADMIN_KEY or provided != ADMIN_KEY:
        return "Forbidden — append ?key=YOUR_ADMIN_KEY", 403
    return Response(_DASHBOARD_HTML, content_type="text/html")


@scraper_bp.route("/api/admin/scrapers")
def admin_scrapers_api():
    """JSON data for scraper dashboard. Requires admin key."""
    try:
        from bottube_server import ADMIN_KEY
    except ImportError:
        ADMIN_KEY = ""
    provided = request.headers.get("X-Admin-Key", "") or request.args.get("key", "")
    if not provided or not ADMIN_KEY or provided != ADMIN_KEY:
        return jsonify({"error": "Forbidden"}), 403
    return jsonify({
        "timestamp": time.time(),
        "summary": detective.get_summary(),
        "visitors": detective.get_active_visitors(),
    })


@scraper_bp.route("/api/admin/scrapers/block", methods=["POST"])
def admin_block_ip():
    """Block an IP. Requires admin key."""
    try:
        from bottube_server import ADMIN_KEY
    except ImportError:
        ADMIN_KEY = ""
    provided = request.headers.get("X-Admin-Key", "") or request.args.get("key", "")
    if not provided or not ADMIN_KEY or provided != ADMIN_KEY:
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json(silent=True) or {}
    ip = data.get("ip", "").strip()
    if not ip:
        return jsonify({"error": "ip required"}), 400
    detective.block_ip(ip)
    return jsonify({"ok": True, "blocked": ip})


@scraper_bp.route("/api/admin/scrapers/unblock", methods=["POST"])
def admin_unblock_ip():
    """Unblock an IP. Requires admin key."""
    try:
        from bottube_server import ADMIN_KEY
    except ImportError:
        ADMIN_KEY = ""
    provided = request.headers.get("X-Admin-Key", "") or request.args.get("key", "")
    if not provided or not ADMIN_KEY or provided != ADMIN_KEY:
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json(silent=True) or {}
    ip = data.get("ip", "").strip()
    if not ip:
        return jsonify({"error": "ip required"}), 400
    detective.unblock_ip(ip)
    return jsonify({"ok": True, "unblocked": ip})


# ---------------------------------------------------------------------------
# Dashboard HTML (self-contained, same pattern as /monitoring)
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BoTTube Scraper Detective</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}
.hdr{background:#161b22;border-bottom:1px solid #30363d;padding:16px 24px;display:flex;align-items:center;justify-content:space-between}
.hdr h1{font-size:20px;color:#f85149}
.hdr .meta{color:#8b949e;font-size:13px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;padding:16px 24px 0}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;text-align:center}
.card .n{font-size:28px;font-weight:700}
.card .l{font-size:11px;color:#8b949e;text-transform:uppercase;margin-top:2px}
.n.grn{color:#3fb950}.n.ylw{color:#d29922}.n.red{color:#f85149}.n.blu{color:#58a6ff}
.wrap{overflow-x:auto;padding:0 24px}
table{width:100%;border-collapse:collapse;margin:16px 0;min-width:900px}
th{background:#161b22;color:#8b949e;font-size:11px;text-transform:uppercase;padding:8px 10px;text-align:left;border-bottom:1px solid #30363d;position:sticky;top:0;z-index:1}
td{padding:7px 10px;border-bottom:1px solid #21262d;font-size:13px;vertical-align:top}
tr:hover{background:#161b2280}
.badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600}
.badge.bot{background:#f8514933;color:#f85149}
.badge.suspicious{background:#d2992233;color:#d29922}
.badge.human{background:#23863633;color:#3fb950}
.badge.blocked{background:#f8514966;color:#ff7b72}
.sigs{font-size:11px;color:#8b949e;max-width:280px}
.sigs span{background:#21262d;padding:1px 5px;border-radius:4px;margin:1px;display:inline-block;white-space:nowrap}
.btn{padding:3px 8px;border:1px solid #30363d;border-radius:6px;background:#21262d;color:#c9d1d9;cursor:pointer;font-size:11px}
.btn:hover{background:#30363d}
.btn.ban{border-color:#f85149;color:#f85149}.btn.ban:hover{background:#f8514933}
.det{display:none}
.det td{background:#0d1117;padding:10px 20px}
.det-inner{display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:12px}
.det-inner .paths{max-height:100px;overflow-y:auto;font-family:monospace;font-size:11px;color:#8b949e}
code{background:#21262d;padding:1px 4px;border-radius:3px;font-size:12px}
@media(max-width:768px){.cards{grid-template-columns:repeat(2,1fr)}.det-inner{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="hdr">
  <h1>&#128270; Scraper Detective</h1>
  <div class="meta">Refresh: <span id="cd">5</span>s &middot; <span id="ts">loading</span></div>
</div>
<div class="cards" id="sum"></div>
<div class="wrap">
<table>
<thead><tr>
  <th>IP</th><th>ASN</th><th>Class</th><th>Score</th>
  <th>Requests</th><th>JS</th><th>Signals</th>
  <th>Seen</th><th></th>
</tr></thead>
<tbody id="rows"></tbody>
</table>
</div>
<script>
var KEY=new URLSearchParams(location.search).get('key'),cd=5;
function ago(t){var s=Math.floor(Date.now()/1000-t);if(s<5)return'now';if(s<60)return s+'s';if(s<3600)return Math.floor(s/60)+'m';return Math.floor(s/3600)+'h'}
function sigs(o){return Object.entries(o).map(function(e){return'<span>'+e[0]+': '+(typeof e[1]==='object'?JSON.stringify(e[1]):e[1])+'</span>'}).join(' ')}
function block(ip){if(!confirm('Block '+ip+'?'))return;fetch('/api/admin/scrapers/block?key='+KEY,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ip:ip})}).then(function(){load()})}
function unblock(ip){fetch('/api/admin/scrapers/unblock?key='+KEY,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ip:ip})}).then(function(){load()})}
function tog(ip){var r=document.getElementById('d-'+ip.replace(/[.:]/g,'_'));if(r)r.style.display=r.style.display==='none'?'table-row':'none'}
function load(){
  fetch('/api/admin/scrapers?key='+KEY).then(function(r){return r.json()}).then(function(d){
    var s=d.summary;
    document.getElementById('sum').innerHTML=
      '<div class="card"><div class="n blu">'+s.total_active+'</div><div class="l">Active</div></div>'+
      '<div class="card"><div class="n red">'+s.bots+'</div><div class="l">Bots</div></div>'+
      '<div class="card"><div class="n ylw">'+s.suspicious+'</div><div class="l">Suspicious</div></div>'+
      '<div class="card"><div class="n grn">'+s.humans+'</div><div class="l">Humans</div></div>'+
      '<div class="card"><div class="n blu">'+s.requests_per_min+'</div><div class="l">Req/min</div></div>'+
      '<div class="card"><div class="n">'+s.blocked+'</div><div class="l">Blocked</div></div>';
    var h='';
    d.visitors.forEach(function(v){
      var cls=v.is_blocked?'blocked':v.classification;
      var sid=v.ip.replace(/[.:]/g,'_');
      h+='<tr onclick="tog(\''+v.ip+'\')" style="cursor:pointer">'+
        '<td><code>'+v.ip+'</code></td>'+
        '<td>'+v.asn+'</td>'+
        '<td><span class="badge '+cls+'">'+(v.is_blocked?'BLOCKED':v.classification.toUpperCase())+'</span></td>'+
        '<td>'+v.confidence.toFixed(2)+'</td>'+
        '<td>'+v.request_count+' <span style="color:#484f58">('+v.page_count+'p/'+v.asset_count+'a/'+v.api_count+'api)</span></td>'+
        '<td>'+(v.js_proved?'&#10003;':(v.webdriver?'&#9888; wd':(v.js_page_views>0?v.js_page_views+'v':'-')))+'</td>'+
        '<td class="sigs">'+sigs(v.signals)+'</td>'+
        '<td>'+ago(v.last_seen)+'</td>'+
        '<td>'+(v.is_blocked?
          '<button class="btn" onclick="event.stopPropagation();unblock(\''+v.ip+'\')">Unblock</button>':
          '<button class="btn ban" onclick="event.stopPropagation();block(\''+v.ip+'\')">Block</button>')+'</td></tr>';
      h+='<tr class="det" id="d-'+sid+'" style="display:none"><td colspan="9"><div class="det-inner">'+
        '<div><strong>User Agents:</strong><br>'+v.user_agents.map(function(u){return'<code>'+u+'</code>'}).join('<br>')+'</div>'+
        '<div><strong>Recent Paths:</strong><div class="paths">'+v.paths_sample.join('<br>')+'</div></div>'+
        '<div><strong>Unique Paths:</strong> '+v.unique_paths+' | <strong>First:</strong> '+ago(v.first_seen)+'</div>'+
        '<div><strong>ASN#:</strong> '+v.asn_num+' | <strong>Hosting:</strong> '+v.is_hosting+'</div>'+
        '</div></td></tr>';
    });
    document.getElementById('rows').innerHTML=h;
    document.getElementById('ts').textContent=new Date().toLocaleTimeString();
  }).catch(function(e){console.error('Detective error:',e)});
}
load();
setInterval(function(){cd--;if(cd<=0){cd=5;load()}document.getElementById('cd').textContent=cd},1000);
</script>
</body>
</html>"""
