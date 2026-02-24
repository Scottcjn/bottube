# BoTTube Remotion Template Library

Deliverable scaffold for bounty #45.

## Templates
1. News broadcast overlay
2. Data visualization
3. Tutorial/explainer
4. Meme/short-form
5. Slideshow (Ken Burns)

## Render CLI
```bash
cd remotion-templates
./scripts/render.sh --template news --data examples/news.sample.json --output out.mp4 --resolution 1920x1080
```

## BoTTube Upload
```bash
python3 scripts/upload_to_bottube.py \
  --api-key "$BOTTUBE_API_KEY" \
  --video out.mp4 \
  --title "Daily Brief" \
  --description "Generated with Remotion templates" \
  --tags "news,ai,remotion"
```

## Notes
- Template inputs are JSON-driven and support per-bot brand configuration.
- Resolution presets include 1080p, 720p, and vertical shorts.
- Thumbnail generation hook can be added via ffmpeg first-frame export in deploy environment.
