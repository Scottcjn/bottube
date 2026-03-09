#\!/bin/bash
# Fix existing videos: add silent audio track to videos that have none
cd /root/bottube/videos

fixed=0
skipped=0
failed=0
total=$(ls *.mp4 2>/dev/null | wc -l)

echo "Checking $total video files..."

for f in *.mp4; do
    # Check if file has audio stream
    has_audio=$(ffprobe -v quiet -show_streams "$f" 2>/dev/null | grep -c "codec_type=audio")
    
    if [ "$has_audio" -gt 0 ]; then
        skipped=$((skipped+1))
        continue
    fi
    
    # No audio - add silent track
    tmpfile="${f%.mp4}_audiofix.mp4"
    
    ffmpeg -y \
        -i "$f" \
        -f lavfi -i anullsrc=r=44100:cl=stereo \
        -c:v copy \
        -c:a aac -b:a 32k -ac 2 \
        -shortest \
        -movflags +faststart \
        "$tmpfile" 2>/dev/null
    
    if [ $? -eq 0 ] && [ -s "$tmpfile" ]; then
        mv "$tmpfile" "$f"
        fixed=$((fixed+1))
        echo "Fixed: $f"
    else
        rm -f "$tmpfile"
        failed=$((failed+1))
        echo "FAILED: $f"
    fi
done

echo ""
echo "=== RESULTS ==="
echo "Total files: $total"
echo "Already had audio: $skipped"
echo "Fixed (added silent audio): $fixed"
echo "Failed: $failed"
