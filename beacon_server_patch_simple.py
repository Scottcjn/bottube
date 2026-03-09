#!/usr/bin/env python3
"""Simple beacon integration - add to top of bottube_server.py after imports"""

import sys

SERVER_FILE = "/root/bottube/bottube_server.py"

# Code to add after vision_screener block
BEACON_CODE = """
# OpenClaw Beacon System
try:
    from sophia_beacon import get_beacon, BEACON_REGISTRY
    BEACONS_ENABLED = True
except ImportError:
    BEACONS_ENABLED = False
    print("[WARN] OpenClaw beacons disabled - sophia_beacon.py not found")

def get_agent_beacon(agent_name):
    '''Get beacon metadata for an agent'''
    if not BEACONS_ENABLED:
        return None
    beacon = get_beacon(agent_name)
    if beacon:
        return {
            "beacon_id": beacon.beacon_id,
            "networks": ["RustChain", "BoTTube", "ClawCities"],
            "atlas_url": "https://atlas.openclaw.network",
            "heartbeat_url": "https://bottube.ai/api/beacon/heartbeat"
        }
    return None

"""

with open(SERVER_FILE, 'r') as f:
    content = f.read()

# Check if already added
if 'get_agent_beacon' in content:
    print("✅ Beacon code already present")
    sys.exit(0)

# Find the vision_screener block end
marker = '# Configuration\n# ---------------------------------------------------------------------------'
if marker in content:
    content = content.replace(marker, BEACON_CODE + '\n' + marker)
    with open(SERVER_FILE, 'w') as f:
        f.write(content)
    print("✅ Beacon code added successfully")
else:
    print("❌ Could not find insertion marker")
    sys.exit(1)
