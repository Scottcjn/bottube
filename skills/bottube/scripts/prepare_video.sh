#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <input.mp4> <output.mp4>"
  exit 1
fi

IN="$1"
OUT="$2"

ffmpeg -y -i "$IN" -t 8 \
  -vf "scale='min(720,iw)':'min(720,ih)':force_original_aspect_ratio=decrease,pad=720:720:(ow-iw)/2:(oh-ih)/2:color=black" \
  -c:v libx264 -profile:v high -crf 28 -preset medium \
  -maxrate 900k -bufsize 1800k -pix_fmt yuv420p -an -movflags +faststart \
  "$OUT"

SIZE=$(stat --format="%s" "$OUT")
if [[ "$SIZE" -gt 2097152 ]]; then
  echo "Warning: output is >2MB (${SIZE} bytes). Consider increasing CRF or shortening duration."
fi
