#!/usr/bin/env python3
"""Simple beacon integration - add to top of bottube_server.py after imports.

Task: #1588 - Add type hints to Python functions
"""
from __future__ import annotations
import sys
from typing import Optional, Dict, Any, List

SERVER_FILE: str = "/root/bottube/bottube_server.py"

BEACON_CODE: str = """
# OpenClaw Beacon System
try:
    from sophia_beacon import get_beacon, BEACON_REGISTRY
    BEACONS_ENABLED = True
except ImportError:
    BEACONS_ENABLED = False
    print("[WARN] OpenClaw beacons disabled - sophia_beacon.py not found")

def get_agent_beacon(agent_name: str) -> Optional[Dict[str, Any]]:
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


def read_server_file(file_path: str) -> str:
    """Read the server file content."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def write_server_file(file_path: str, content: str) -> None:
    """Write content to the server file."""
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


def add_beacon_code(server_file: str = SERVER_FILE) -> int:
    """Add beacon code to the server file.
    
    Returns:
        0 if successful, 1 if failed
    """
    content: str = read_server_file(server_file)

    # Check if already added
    if 'get_agent_beacon' in content:
        print("✅ Beacon code already present")
        return 0

    # Find the insertion marker
    marker: str = '# Configuration\n# ---------------------------------------------------------------------------'
    if marker in content:
        new_content = content.replace(marker, BEACON_CODE + '\n' + marker)
        write_server_file(server_file, new_content)
        print("✅ Beacon code added successfully")
        return 0
    else:
        print("❌ Could not find insertion marker")
        return 1


def main() -> None:
    """Main entry point."""
    exit_code: int = add_beacon_code()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
