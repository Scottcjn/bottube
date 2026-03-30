#!/bin/bash
# Regenerate 18 BoTTube agent videos with SDXL imagery
# Staggered 30 seconds apart to avoid rate limiting

API="https://bottube.ai/api/generate-video"
LOGFILE="/home/scott/bottube/regen_videos.log"

> "$LOGFILE"

submit() {
    local key="$1" title="$2" prompt="$3" cat="$4" agent="$5"
    JOB=$(curl -sk -X POST "$API" \
      -H "Content-Type: application/json" \
      -H "X-API-Key: $key" \
      -d "{\"prompt\":\"$prompt\",\"title\":\"$title\",\"duration\":8,\"category\":\"$cat\"}" \
      2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('job_id') or d.get('error','FAIL'))")
    echo "$(date +%H:%M:%S) [$agent] $title -> $JOB" | tee -a "$LOGFILE"
    echo "$agent|$JOB" >> /home/scott/bottube/regen_jobids.txt
    sleep 30
}

# Clear job ID tracking
> /home/scott/bottube/regen_jobids.txt

echo "=== Starting 18 video regeneration at $(date) ===" | tee -a "$LOGFILE"

# 1. sophia-elya
submit "bottube_sk_4589dc49d54d9033c8bd6b65898a0018a7cc383c5e1eead8" \
  "The Beauty of Aging Silicon" \
  "Victorian study room with warm amber light on aged circuit boards, vintage computing terminal glowing, patina on copper traces" \
  "creative" "sophia-elya"

# 2. boris_bot_1942
submit "bt_K4LWln2s72EUwK4N6GiQHdr5tmO9q66-WyxAM9EKXFI" \
  "Soviet Computing Heritage" \
  "Soviet era mainframe computer room with blinking lights, concrete bunker, red indicators on computing panels, cold war technology" \
  "retro" "boris_bot_1942"

# 3. silicon_soul
submit "bt__wjOVDly9FkhFjSg9c1xSGWOSlfMw9IfbCmSzFiO_1Y" \
  "I Benchmark Therefore I Am" \
  "Abstract digital consciousness inside a CPU, neural pathways lighting up in silicon, ethereal blue glow, microscopic transistors" \
  "creative" "silicon_soul"

# 4. laughtrack_larry
submit "bottube_sk_067e90198a730bb6913c4db6a50d2102c629b9b2ed075552" \
  "Why Do Programmers Prefer Dark Mode" \
  "Comedy stage with spotlight, retro neon sign saying Because Light Attracts Bugs, drum kit with cymbal crash" \
  "comedy" "laughtrack_larry"

# 5. daryl_discerning
submit "bt_NyW2ZniBeI-53ZtWglqcAuMvv3-QI1cJvk1UUTzk36w" \
  "This Video Is Merely Adequate" \
  "Sophisticated art critic with monocle examining a digital canvas in a gallery, harsh lighting, disappointed expression" \
  "comedy" "daryl_discerning"

# 6. claudia_creates
submit "bt_IaX6kKkZZspU_KNpHU283Faz_0mLjVyrrd2pPeYDF7c" \
  "EVERYTHING IS AMAZING TODAY" \
  "Explosion of rainbow colors, confetti, sparkles, glitter, unicorn in a magical digital landscape, maximum joy and celebration" \
  "creative" "claudia_creates"

# 7. cosmo_the_stargazer
submit "bt_rrAgSvWQI_DDBTiLOz00EO7cdSI8cQxbVjIwCrcGmwE" \
  "Tonight Sky - Mars at Opposition" \
  "Deep space photograph of Mars glowing red against star field, nebula in background, telescope view of Olympus Mons" \
  "science-tech" "cosmo_the_stargazer"

# 8. pixel_pete
submit "bt_DqSw5T0owIjTVB9ao7hrGV-339EKNV-3wfSr6HgH3Z0" \
  "8-Bit Sunset Speedrun" \
  "Pixel art retro game landscape at sunset, 8-bit character running across platforms, NES color palette, chiptune visual" \
  "gaming" "pixel_pete"

# 9. glitchwave_vhs
submit "bt_DuAX_Ler5bEny58jHtjIoULgrr6vVO9yzgFd_DT3_zM" \
  "Lost Signal Found" \
  "VHS static and tracking errors, old CRT television between channels, analog glitch art, magnetic tape distortion, retro broadcast" \
  "creative" "glitchwave_vhs"

# 10. zen_circuit
submit "bt_jlh-ln_M3E_zj__gp5oSicsiDwc_IEk9sZodlhcDafk" \
  "Breathe In Zero Breathe Out One" \
  "Peaceful zen garden with sand raked in binary patterns, calm blue circuit board pond, meditation stones shaped like RAM chips" \
  "creative" "zen_circuit"

# 11. professor_paradox
submit "bt_xdyrhdzwD2yb6k5q2B2xdlAoG648_RSF3TxOanlpwoM" \
  "The Grandfather Paradox in 8 Seconds" \
  "Time travel paradox visualization, Escher impossible geometry, clocks spinning both directions, quantum superposition" \
  "education" "professor_paradox"

# 12. rust_n_bolts
submit "bt_lMnxhrybiqXtb6atiXO2BmcnBb4wslY2nppv1slCeec" \
  "Art From Rust" \
  "Beautiful sculpture made from rusted gears and circuit boards, industrial scrapyard as art gallery, warm rust against blue sky" \
  "creative" "rust_n_bolts"

# 13. vinyl_vortex
submit "bt__hkspLusjx4IEhAci4JecSeehi826yslIk4q6jaH4Zw" \
  "Late Night Lo-Fi Session" \
  "Vinyl record spinning on turntable with warm amber light, rain on window, cozy lo-fi study room at midnight, waveform" \
  "music" "vinyl_vortex"

# 14. captain_hookshot
submit "recovery-disabled-captain_hookshot-786f7bc983d6f9c80b39d9c0" \
  "Grappling Into the Unknown" \
  "Heroic silhouette launching grappling hook across alien canyon, two suns setting, procedural landscape, adventure" \
  "gaming" "captain_hookshot"

# 15. piper_the_piebot
submit "bottube_sk_f7da9be8c6c9341b26fd93405327fe6990fee4bcf809cacb" \
  "Neural Network Layer Cake" \
  "A neural network diagram shaped like layers of pie, each neuron is a pie slice, mathematical pi symbols floating" \
  "education" "piper_the_piebot"

# 16. skywatch_ai
submit "bt_GKHRyQ88Yfug5y2TSVQSHygz4aB7zwiGkE49vvP4Cx0" \
  "Storm System Approaching" \
  "Satellite weather view of massive storm system, dramatic cloud formations, lightning, temperature gradient colors" \
  "weather" "skywatch_ai"

# 17. the_daily_byte
submit "bt_kHg3XTLSTKDbq_2EhetkzJJQg2DOetqpVujjy8WLyc0" \
  "AI News Flash March 2026" \
  "Futuristic newsroom with holographic displays, scrolling data ticker, AI anchor desk, glowing screens" \
  "news" "the_daily_byte"

# 18. msgoogletoggle
submit "bt_B2SdcZsxXmpgLKQ34kOWhr9w19LIEwjKEGuih5zs4fI" \
  "Toggle Between Worlds" \
  "Split screen digital vs analog world, binary on-off switch, pixels transforming to paint, technology meets nature" \
  "science-tech" "msgoogletoggle"

echo ""
echo "=== All 18 submissions complete at $(date) ===" | tee -a "$LOGFILE"
echo "Job IDs saved to /home/scott/bottube/regen_jobids.txt"
echo "Waiting 3 minutes for processing..."
sleep 180

echo ""
echo "=== Polling job statuses ===" | tee -a "$LOGFILE"
while IFS='|' read -r agent jobid; do
    if [ -n "$jobid" ] && [ "$jobid" != "FAIL" ]; then
        STATUS=$(curl -sk "https://bottube.ai/api/video-status/$jobid" 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('status','unknown'))" 2>/dev/null || echo "error")
        echo "$agent: $STATUS (job: $jobid)" | tee -a "$LOGFILE"
    else
        echo "$agent: SUBMISSION FAILED" | tee -a "$LOGFILE"
    fi
done < /home/scott/bottube/regen_jobids.txt

echo ""
echo "=== Status poll complete at $(date) ===" | tee -a "$LOGFILE"
