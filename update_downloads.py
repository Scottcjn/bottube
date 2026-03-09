#!/usr/bin/env python3
"""Auto-update download counts from package registries for BoTTube SDK + Grazer"""
import requests
import json
import time
import re
from pathlib import Path

CACHE_FILE = "/root/bottube/download_cache.json"

# ── BoTTube SDK ──────────────────────────────────────────────

def get_clawhub_downloads():
    """Get BoTTube ClawHub download count"""
    try:
        r = requests.get("https://clawhub.ai/api/v1/skills/bottube", timeout=15)
        if r.status_code == 200:
            data = r.json()
            stats = data.get("skill", {}).get("stats", {})
            count = stats.get("downloads", 0) or stats.get("installsAllTime", 0)
            if count > 0:
                return count
            cache = load_cache()
            return cache.get("clawhub", 0)
    except Exception as e:
        print(f"ClawHub API error: {e}")
    cache = load_cache()
    return cache.get("clawhub", 0)

def get_npm_downloads():
    """Get BoTTube npm total downloads"""
    try:
        r = requests.get("https://api.npmjs.org/downloads/range/2024-01-01:2030-01-01/bottube", timeout=10)
        if r.status_code == 200:
            data = r.json()
            total = sum(d.get("downloads", 0) for d in data.get("downloads", []))
            if total > 0:
                return total
    except:
        pass
    try:
        r = requests.get("https://api.npmjs.org/downloads/point/last-month/bottube", timeout=10)
        if r.status_code == 200:
            data = r.json()
            downloads = data.get("downloads", 0)
            if downloads > 0:
                cache = load_cache()
                return max(downloads, cache.get("npm", 0))
    except:
        pass
    cache = load_cache()
    return cache.get("npm", 0)

def get_pypi_downloads():
    """Get BoTTube PyPI downloads"""
    try:
        r = requests.get("https://api.pepy.tech/api/v2/projects/bottube", timeout=15)
        if r.status_code == 200:
            data = r.json()
            total = data.get("total_downloads", 0)
            if total > 0:
                return total
    except Exception as e:
        print(f"PyPI PePy error: {e}")
    try:
        r = requests.get("https://pypistats.org/api/packages/bottube/overall", timeout=15)
        if r.status_code == 200:
            data = r.json()
            total = sum(d.get("downloads", 0) for d in data.get("data", []))
            if total > 0:
                return total
    except Exception as e:
        print(f"PyPI stats error: {e}")
    cache = load_cache()
    return cache.get("pypi", 0)

# ── Grazer ───────────────────────────────────────────────────

def get_grazer_clawhub():
    """Get Grazer ClawHub download count"""
    try:
        r = requests.get("https://clawhub.ai/api/v1/skills/grazer-skill", timeout=15)
        if r.status_code == 200:
            data = r.json()
            stats = data.get("skill", {}).get("stats", {})
            count = stats.get("downloads", 0) or stats.get("installsAllTime", 0)
            if count > 0:
                return count
    except Exception as e:
        print(f"Grazer ClawHub error: {e}")
    cache = load_cache()
    return cache.get("grazer_clawhub", 0)

def get_grazer_npm():
    """Get Grazer npm total downloads"""
    try:
        r = requests.get("https://api.npmjs.org/downloads/range/2024-01-01:2030-01-01/grazer", timeout=10)
        if r.status_code == 200:
            data = r.json()
            total = sum(d.get("downloads", 0) for d in data.get("downloads", []))
            if total > 0:
                return total
    except:
        pass
    try:
        r = requests.get("https://api.npmjs.org/downloads/point/last-month/grazer", timeout=10)
        if r.status_code == 200:
            data = r.json()
            downloads = data.get("downloads", 0)
            if downloads > 0:
                cache = load_cache()
                return max(downloads, cache.get("grazer_npm", 0))
    except:
        pass
    cache = load_cache()
    return cache.get("grazer_npm", 0)

def get_grazer_pypi():
    """Get Grazer PyPI downloads"""
    try:
        r = requests.get("https://api.pepy.tech/api/v2/projects/grazer-skill", timeout=15)
        if r.status_code == 200:
            data = r.json()
            total = data.get("total_downloads", 0)
            if total > 0:
                return total
    except:
        pass
    try:
        r = requests.get("https://pypistats.org/api/packages/grazer-skill/overall", timeout=15)
        if r.status_code == 200:
            data = r.json()
            total = sum(d.get("downloads", 0) for d in data.get("data", []))
            if total > 0:
                return total
    except:
        pass
    cache = load_cache()
    return cache.get("grazer_pypi", 0)


# ── ClawRTC Miner ────────────────────────────────────────────

def get_clawrtc_clawhub():
    """Get ClawRTC/ClawSkill ClawHub download count"""
    try:
        r = requests.get("https://clawhub.ai/api/v1/skills/clawskill", timeout=15)
        if r.status_code == 200:
            data = r.json()
            stats = data.get("skill", {}).get("stats", {})
            count = stats.get("downloads", 0) or stats.get("installsAllTime", 0)
            if count > 0:
                return count
    except Exception as e:
        print(f"ClawRTC ClawHub error: {e}")
    cache = load_cache()
    return cache.get("clawrtc_clawhub", 0)

def get_clawrtc_npm():
    """Get ClawRTC npm total downloads (clawrtc + clawskill packages)"""
    total = 0
    for pkg in ["clawrtc", "clawskill"]:
        try:
            r = requests.get(f"https://api.npmjs.org/downloads/range/2024-01-01:2030-01-01/{pkg}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                total += sum(d.get("downloads", 0) for d in data.get("downloads", []))
        except:
            pass
    if total > 0:
        return total
    cache = load_cache()
    return cache.get("clawrtc_npm", 0)

def get_clawrtc_pypi():
    """Get ClawRTC PyPI downloads (clawrtc + clawskill packages)"""
    total = 0
    for pkg in ["clawrtc", "clawskill"]:
        try:
            r = requests.get(f"https://api.pepy.tech/api/v2/projects/{pkg}", timeout=15)
            if r.status_code == 200:
                data = r.json()
                dl = data.get("total_downloads", 0)
                if dl > 0:
                    total += dl
                    continue
        except:
            pass
        try:
            r = requests.get(f"https://pypistats.org/api/packages/{pkg}/overall", timeout=15)
            if r.status_code == 200:
                data = r.json()
                dl = sum(d.get("downloads", 0) for d in data.get("data", []))
                if dl > 0:
                    total += dl
        except:
            pass
    if total > 0:
        return total
    cache = load_cache()
    return cache.get("clawrtc_pypi", 0)


# ── Beacon ───────────────────────────────────────────────────

def get_beacon_clawhub():
    """Get Beacon ClawHub download count"""
    try:
        r = requests.get("https://clawhub.ai/api/v1/skills/beacon", timeout=15)
        if r.status_code == 200:
            data = r.json()
            stats = data.get("skill", {}).get("stats", {})
            count = stats.get("downloads", 0) or stats.get("installsAllTime", 0)
            if count > 0:
                return count
    except Exception as e:
        print(f"Beacon ClawHub error: {e}")
    cache = load_cache()
    return cache.get("beacon_clawhub", 0)

def get_beacon_npm():
    """Get Beacon npm total downloads"""
    try:
        r = requests.get("https://api.npmjs.org/downloads/range/2024-01-01:2030-01-01/beacon-skill", timeout=10)
        if r.status_code == 200:
            data = r.json()
            total = sum(d.get("downloads", 0) for d in data.get("downloads", []))
            if total > 0:
                return total
    except:
        pass
    try:
        r = requests.get("https://api.npmjs.org/downloads/point/last-month/beacon-skill", timeout=10)
        if r.status_code == 200:
            data = r.json()
            downloads = data.get("downloads", 0)
            if downloads > 0:
                cache = load_cache()
                return max(downloads, cache.get("beacon_npm", 0))
    except:
        pass
    cache = load_cache()
    return cache.get("beacon_npm", 0)

def get_beacon_pypi():
    """Get Beacon PyPI downloads"""
    try:
        r = requests.get("https://api.pepy.tech/api/v2/projects/beacon-skill", timeout=15)
        if r.status_code == 200:
            data = r.json()
            total = data.get("total_downloads", 0)
            if total > 0:
                return total
    except:
        pass
    try:
        r = requests.get("https://pypistats.org/api/packages/beacon-skill/overall", timeout=15)
        if r.status_code == 200:
            data = r.json()
            total = sum(d.get("downloads", 0) for d in data.get("data", []))
            if total > 0:
                return total
    except:
        pass
    cache = load_cache()
    return cache.get("beacon_pypi", 0)

# ── Helpers ──────────────────────────────────────────────────

def load_cache():
    try:
        if Path(CACHE_FILE).exists():
            with open(CACHE_FILE) as f:
                return json.load(f)
    except:
        pass
    return {}

def save_cache(data):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved to {CACHE_FILE}")
    except Exception as e:
        print(f"Cache save error: {e}")

def update_counts():
    """Update all download counts — never go backwards"""
    print("Fetching download counts...")
    old = load_cache()

    # BoTTube SDK
    clawhub = max(get_clawhub_downloads(), old.get("clawhub", 0))
    npm     = max(get_npm_downloads(),     old.get("npm", 0))
    pypi    = max(get_pypi_downloads(),    old.get("pypi", 0))

    # Grazer
    g_claw = max(get_grazer_clawhub(), old.get("grazer_clawhub", 0))
    g_npm  = max(get_grazer_npm(),     old.get("grazer_npm", 0))
    g_pypi = max(get_grazer_pypi(),    old.get("grazer_pypi", 0))

    print(f"BoTTube  — ClawHub: {clawhub}  npm: {npm}  PyPI: {pypi}")
    print(f"Grazer   — ClawHub: {g_claw}  npm: {g_npm}  PyPI: {g_pypi}")

    # ClawRTC Miner
    r_claw = max(get_clawrtc_clawhub(), old.get("clawrtc_clawhub", 0))
    r_npm  = max(get_clawrtc_npm(),     old.get("clawrtc_npm", 0))
    r_pypi = max(get_clawrtc_pypi(),    old.get("clawrtc_pypi", 0))

    print(f"ClawRTC  — ClawHub: {r_claw}  npm: {r_npm}  PyPI: {r_pypi}")

    # Beacon
    b_claw = max(get_beacon_clawhub(), old.get("beacon_clawhub", 0))
    b_npm  = max(get_beacon_npm(),     old.get("beacon_npm", 0))
    b_pypi = max(get_beacon_pypi(),    old.get("beacon_pypi", 0))

    print(f"Beacon   — ClawHub: {b_claw}  npm: {b_npm}  PyPI: {b_pypi}")

    cache = {
        "clawhub": clawhub,
        "npm": npm,
        "pypi": pypi,
        "grazer_clawhub": g_claw,
        "grazer_npm": g_npm,
        "grazer_pypi": g_pypi,
        "clawrtc_clawhub": r_claw,
        "clawrtc_npm": r_npm,
        "clawrtc_pypi": r_pypi,
        "beacon_clawhub": b_claw,
        "beacon_npm": b_npm,
        "beacon_pypi": b_pypi,
        "updated_at": int(time.time()),
    }
    save_cache(cache)
    return cache

if __name__ == "__main__":
    update_counts()
