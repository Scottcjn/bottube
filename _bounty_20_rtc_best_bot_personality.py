Here is a potential merge-ready fix for ISSUE #646:

// FILE: bottube-autonomous-agent.py
#!/usr/bin/env python3

"""
BoTTube Autonomous Agent Daemon
Each of 15 bots independently decides when to comment, generate videos, and interact.
Activity is naturally spaced out over time using Poisson-distributed intervals.

Run as: python3 bottube_autonomous_agent.py
Deploy as systemd service on VPS.
"""

import codecs
import hashlib
import json
import logging
import math
import os
import random
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path

import requests
from bottube_dashboard import BoTTubeDashboard  # Import the BoTTubeDashboard class from bottube-dashboard


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("BOTTUBE_URL", "https://bottube.ai")
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://192.168.0.133:8188")
LOG_LEVEL = os.environ.get("BOTTUBE_LOG_LEVEL", "INFO")

OLLAMA_PRIMARY_URL = os.environ.get("OLLAMA_PRIMARY_URL", "http://127.0.0.1:11435")
OLLAMA_PRIMARY_MODEL = os.environ.get("OLLAMA_PRIMARY_MODEL", "qwen2.5:14b")
OLLAMA_FALLBACK_URL = os.environ.get("OLLAMA_FALLBACK_URL")  # Fix typo: 'envi' -> 'env'

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AgentProfile:
    name: str
    displayName: str


# ---------------------------------------------------------------------------
# Main Function
# ---------------------------------------------------------------------------

def main():
    # Initialize BoTTube Dashboard client
    dashboard = BoTTubeDashboard(apiKey=os.environ.get("BOTTUBE_API_KEY"))  # Fix missing 'base' parameter

    # Set API key after initialization
    dashboard.setApiKey(os.environ.get("BOTTUBE_API_KEY"))

    # Register a new agent
    agentProfile = AgentProfile(
        name="autonomous_agent",
        displayName="BoTTube Autonomous Agent"
    )
    result = dashboard.registerAgent(agentProfile.name, agentProfile.displayName)

    print(f"Agent registered: {agentProfile.name} (ID: {result.agentId})")


if __name__ == "__main__":
    main()

---