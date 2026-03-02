#!/usr/bin/env python3
"""Fix all API key mismatches in the autonomous agent daemon."""
import sqlite3
import re
import sys

DB_PATH = "/root/bottube/bottube.db"
AGENT_FILE = "/root/bottube-agent/bottube_autonomous_agent.py"

# Get correct keys from database
conn = sqlite3.connect(DB_PATH)
db_keys = {}
for row in conn.execute("SELECT agent_name, api_key FROM agents"):
    db_keys[row[0]] = row[1]
conn.close()

# Read agent daemon
with open(AGENT_FILE) as f:
    content = f.read()

original = content
fixes = 0

# Find and replace each api_key in the daemon config
for match in re.finditer(r'"api_key":\s*"(bottube_sk_[a-f0-9]+)"', content):
    old_key = match.group(1)
    # Find which bot this belongs to by looking backwards for the bot name
    start = max(0, match.start() - 500)
    context = content[start:match.start()]
    # Find the last bot name definition before this key
    name_match = list(re.finditer(r'"(\w+)":\s*\{', context))
    if not name_match:
        continue
    bot_name = name_match[-1].group(1)

    if bot_name in db_keys and db_keys[bot_name] != old_key:
        new_key = db_keys[bot_name]
        content = content.replace(old_key, new_key)
        print(f"  FIXED: {bot_name}")
        print(f"    old: {old_key}")
        print(f"    new: {new_key}")
        fixes += 1
    elif bot_name in db_keys:
        print(f"  OK: {bot_name}")

if fixes > 0:
    # Backup original
    with open(AGENT_FILE + ".bak", "w") as f:
        f.write(original)
    # Write fixed version
    with open(AGENT_FILE, "w") as f:
        f.write(content)
    print(f"\nFixed {fixes} API keys. Backup saved to {AGENT_FILE}.bak")
else:
    print("\nNo fixes needed!")
