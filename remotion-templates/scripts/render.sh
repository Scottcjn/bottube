#!/usr/bin/env bash
set -euo pipefail

TEMPLATE=""
DATA=""
OUTPUT=""
RESOLUTION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --template) TEMPLATE="$2"; shift 2 ;;
    --data) DATA="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    --resolution) RESOLUTION="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

[[ -n "$TEMPLATE" && -n "$DATA" && -n "$OUTPUT" ]] || { echo "Usage: render.sh --template news --data input.json --output video.mp4 [--resolution 1920x1080]"; exit 1; }

node scripts/render.js --template "$TEMPLATE" --data "$DATA" --output "$OUTPUT" ${RESOLUTION:+--resolution "$RESOLUTION"}
