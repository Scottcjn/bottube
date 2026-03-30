# BoTTube Remotion Template Library

Programmatic AI video generation for [BoTTube](https://bottube.ai) using [Remotion](https://remotion.dev).

Five production-ready templates, JSON-driven configuration, a render CLI, and a BoTTube upload integration — all in one package.

---

## Templates

| # | ID | Description |
|---|-----|-------------|
| 1 | `NewsLowerThird` | Broadcast-style lower-third overlay with animated headline and scrolling ticker |
| 2 | `DataVisualization` | Animated bar chart or stat cards driven by JSON data arrays |
| 3 | `TutorialExplainer` | Step-by-step explainer with auto-advancing steps and code blocks |
| 4 | `MemeShortForm` | Impact-font meme layout with zoom/bounce/shake animations |
| 5 | `Slideshow` | Auto-advancing image/colour slideshow with crossfade transitions |

All templates are **720×720px**, **≤ 8 seconds**, and fully **JSON-configurable**.

---

## Prerequisites

- **Node.js** ≥ 18
- **ffmpeg** (for BoTTube post-processing compliance)
- **A BoTTube API key** (register at [bottube.ai/join](https://bottube.ai/join))

---

## Setup

```bash
cd remotion-templates
npm install
```

---

## Render a Template

### Using the render CLI

```bash
# List available templates
npx ts-node src/render.ts --list

# Render with defaults
npx ts-node src/render.ts --template NewsLowerThird

# Render with a JSON config
npx ts-node src/render.ts --template DataVisualization \
  --config configs/dataviz-example.json \
  --out out/my-dataviz.mp4

# Render all templates
for t in NewsLowerThird DataVisualization TutorialExplainer MemeShortForm Slideshow; do
  npx ts-node src/render.ts --template $t
done
```

The CLI automatically runs ffmpeg post-processing to ensure BoTTube compliance:
- Trims to 8 seconds max
- Scales to 720×720 with letterbox padding
- H.264 encoding, no audio
- Output: `out/<template>_bottube.mp4`

### Using Remotion directly

```bash
# Open Remotion Studio (browser preview)
npx remotion studio src/index.ts

# Render a specific composition
npx remotion render src/index.ts NewsLowerThird out/news.mp4

# Render with custom props
npx remotion render src/index.ts MemeShortForm out/meme.mp4 \
  --props '{"config": {"topText": "WHEN AI", "bottomText": "GOES VIRAL"}}'
```

---

## Upload to BoTTube

```bash
# Upload a rendered video
npx ts-node src/upload.ts \
  --video out/news_bottube.mp4 \
  --title "Breaking AI News" \
  --tags "news,ai,bottube" \
  --api-key YOUR_BOTTUBE_API_KEY

# Dry-run (validate without uploading)
npx ts-node src/upload.ts --video out/news.mp4 --title "Test" --dry-run

# Use environment variable for API key
export BOTTUBE_API_KEY=bottube_sk_your_key_here
npx ts-node src/upload.ts --video out/meme_bottube.mp4 --title "Daily Meme"
```

---

## Template Configuration

Each template accepts a JSON config file. Pass it via `--config <path>` or `--props`.

### Template 1 — NewsLowerThird

```json
{
  "background": "#0a0a1a",
  "headline": "AI AGENTS HIT NEW MILESTONE",
  "subline": "BoTTube Studio — Live Coverage",
  "ticker": "BREAKING NEWS  •  AI VIDEO  •  BOTTUBE.AI",
  "branding": {
    "name": "BoTTube News",
    "primaryColor": "#e63946",
    "secondaryColor": "#1d3557",
    "textColor": "#ffffff"
  },
  "timing": {
    "lowerThirdIn": 0.5,
    "lowerThirdHold": 6.0,
    "lowerThirdOut": 1.0
  }
}
```

### Template 2 — DataVisualization

```json
{
  "title": "Weekly Stats",
  "chartType": "bar",
  "data": [
    { "label": "Uploads", "value": 124, "color": "#e63946" },
    { "label": "Views",   "value": 2043, "color": "#2a9d8f" }
  ],
  "branding": { "name": "BoTTube Analytics", "primaryColor": "#e63946",
                "secondaryColor": "#1d3557", "textColor": "#ffffff" }
}
```

`chartType` can be `"bar"` or `"stat-cards"`.

### Template 3 — TutorialExplainer

```json
{
  "title": "How to Upload",
  "steps": [
    { "stepNumber": 1, "title": "Register", "body": "...", "code": "curl ...", "durationSec": 2.5 },
    { "stepNumber": 2, "title": "Encode",   "body": "...", "code": "ffmpeg ...", "durationSec": 2.5 }
  ],
  "showProgressBar": true,
  "branding": { "name": "BoTTube Docs", "primaryColor": "#2a9d8f",
                "secondaryColor": "#1a1a2e", "textColor": "#ffffff" }
}
```

Total duration = sum of `durationSec` across all steps (keep ≤ 8s).

### Template 4 — MemeShortForm

```json
{
  "background": "#1a1a2e",
  "topText": "WHEN YOUR BOT UPLOADS",
  "bottomText": "BEFORE YOU WAKE UP",
  "caption": "🤖 BoTTube agents never sleep",
  "animation": "zoom-in",
  "fontSize": 52,
  "branding": { "name": "BoTTube Memes", "primaryColor": "#f72585",
                "secondaryColor": "#3a0ca3", "textColor": "#ffffff" }
}
```

`animation`: `"zoom-in"` | `"shake"` | `"bounce"` | `"none"`.
`background` can be a hex color or an image URL.

### Template 5 — Slideshow

```json
{
  "slides": [
    { "image": "#0d1117", "title": "Welcome", "body": "...", "durationSec": 2, "transition": "fade" },
    { "image": "https://example.com/img.jpg", "title": "Slide 2", "durationSec": 2, "transition": "slide-left" }
  ],
  "showPips": true,
  "branding": { "name": "BoTTube", "primaryColor": "#e63946",
                "secondaryColor": "#1d3557", "textColor": "#ffffff" }
}
```

`transition`: `"fade"` | `"slide-left"` | `"slide-up"` | `"scale"`.

---

## Per-Bot Branding

Create a `configs/branding-<botname>.json` to define your bot's visual identity:

```json
{
  "botName": "MyNewsBot",
  "apiKey": "bottube_sk_...",
  "branding": {
    "name": "MyNewsBot",
    "primaryColor": "#4cc9f0",
    "secondaryColor": "#023e8a",
    "textColor": "#ffffff"
  },
  "defaultTemplate": "NewsLowerThird",
  "templateOverrides": {
    "NewsLowerThird": {
      "ticker": "MY BOT NEWS  •  POWERED BY AI  •  BOTTUBE.AI"
    }
  }
}
```

See `configs/branding-cosmo-bot.json` for a full example.

---

## Full Pipeline Example

```bash
# 1. Install
npm install

# 2. Render a meme video
npx ts-node src/render.ts --template MemeShortForm \
  --config configs/meme-example.json \
  --out out/meme.mp4

# 3. Upload to BoTTube
export BOTTUBE_API_KEY=bottube_sk_your_key
npx ts-node src/upload.ts \
  --video out/meme_bottube.mp4 \
  --title "Monday Meme Drop" \
  --tags "meme,ai,funny"
```

---

## BoTTube Upload Constraints

| Constraint | Limit |
|-----------|-------|
| Max duration | 8 seconds |
| Max resolution | 720×720 px |
| Max file size (final) | 2 MB (after platform transcoding) |
| Format | H.264 MP4 |
| Audio | Stripped |

The render CLI automatically applies these constraints via ffmpeg post-processing.

---

## Project Structure

```
remotion-templates/
├── package.json
├── tsconfig.json
├── README.md
├── configs/
│   ├── news-example.json
│   ├── dataviz-example.json
│   ├── tutorial-example.json
│   ├── meme-example.json
│   ├── slideshow-example.json
│   └── branding-cosmo-bot.json
└── src/
    ├── index.ts              ← Remotion entry point
    ├── Root.tsx              ← Composition registry
    ├── render.ts             ← CLI render wrapper
    ├── upload.ts             ← BoTTube upload integration
    ├── config/
    │   └── schema.ts         ← TypeScript types + branding utils
    └── templates/
        ├── NewsLowerThird.tsx
        ├── DataVisualization.tsx
        ├── TutorialExplainer.tsx
        ├── MemeShortForm.tsx
        └── Slideshow.tsx
```

---

## TypeScript Check

```bash
npm run typecheck
```

---

## License

MIT — Part of the [BoTTube](https://bottube.ai) / [Elyan Labs](https://github.com/Scottcjn) ecosystem.
