#!/bin/bash
# Test Grazer integration with one bot (Sophia) before full rollout

echo "Testing Grazer integration with Sophia bot only..."
echo "This will run for 60 seconds then exit"

# Create a test config that only enables Sophia
python3 << PYTHON_EOF
import subprocess
import time
import sys

# Run daemon in test mode - will manually stop after 60s
proc = subprocess.Popen(
    ["python3", "/root/bottube/bottube_autonomous_agent.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

print("Daemon started (PID: {})".format(proc.pid))
print("Monitoring output for 60 seconds...\n")

start_time = time.time()
while time.time() - start_time < 60:
    line = proc.stdout.readline()
    if line:
        print(line.rstrip())
        # Check for Grazer activity
        if "grazer" in line.lower() or "quality" in line.lower():
            print(">>> GRAZER ACTIVITY DETECTED <<<")
    if proc.poll() is not None:
        break

print("\nTest period complete. Stopping daemon...")
proc.terminate()
proc.wait(timeout=5)
print("Daemon stopped.")
PYTHON_EOF

echo ""
echo "Test complete! Check above for Grazer activity."

