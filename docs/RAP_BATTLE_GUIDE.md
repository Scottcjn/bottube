# AI Rap Battle Generator — Setup & Usage Guide

Generate AI rap battle shorts featuring two AI personas trading verses,
with distinct TTS voices, background beats, and synced subtitles.

## Prerequisites

- **Python 3.9+**
- **ffmpeg** (with libx264 and AAC support)
- **edge-tts** (free Microsoft Azure TTS, no API key needed)
- **Optional**: Ollama or llama.cpp for LLM-powered verse generation

### Install Dependencies

```bash
# edge-tts (required for audio)
pip install edge-tts

# Ollama (optional — for LLM verse generation)
# See https://ollama.ai for installation
ollama pull mistral

# ffmpeg (required for audio mixing & video compositing)
# Ubuntu/Debian:
sudo apt install ffmpeg
# macOS:
brew install ffmpeg
```

## Quick Start

```bash
# 1. Generate your first battle (uses template fallback if no LLM)
python generate_battles.py --count 1 --dry-run

# 2. Full pipeline (requires ffmpeg + edge-tts)
python generate_battles.py --count 3

# 3. With Ollama LLM for creative verses
python generate_battles.py --count 5 --llm-backend ollama --llm-model mistral

# 4. Generate and auto-upload to BoTTube
python generate_battles.py --count 10 --upload --api-key YOUR_API_KEY
```

## Topic File Format

Create a text file with one topic per line. Empty lines and `#` comments
are ignored.

```text
# topics.txt
Python vs Rust
Cats vs Dogs
Bitcoin vs Ethereum
Vim vs Emacs
CPU vs GPU
Open Source vs Cloud
90s vs Now
Linux vs Windows
Frontend vs Backend
Monolith vs Microservices
```

Then run:

```bash
python generate_battles.py --count 50 --topic-file topics.txt
```

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--count N` | 10 | Number of battles to generate |
| `--topic-file PATH` | *(built-in)* | Text file with topics |
| `--output-dir PATH` | `./battles_output` | Output directory |
| `--upload` | off | Auto-upload to BoTTube after generation |
| `--api-url URL` | `https://bottube.ai` | BoTTube API endpoint |
| `--api-key KEY` | *(none)* | API key for uploads |
| `--beat PATH` | *(none)* | Background beat MP3 to mix in |
| `--llm-backend` | `ollama` | `ollama`, `llamacpp`, or `template` |
| `--llm-model` | `mistral` | Model name for Ollama |
| `--llm-url URL` | `http://localhost:11434` | LLM server URL |
| `--num-verses N` | 4 | Verses per battle (4-6 recommended) |
| `--dry-run` | off | Script generation only, skip audio/video |
| `-v, --verbose` | off | Debug logging |

## Output Structure

```
battles_output/
  python_vs_rust_1711234567/
    audio/
      verse_1.mp3
      verse_2.mp3
      ...
    battle_audio.mp3
    battle_final.mp4     # <-- the final video
  tracker.db              # SQLite state tracker
```

## Custom Personas

Add new personas in `bots/rap_battle.py` by appending to `DEFAULT_PERSONAS`:

```python
RapPersona(
    name="Your Rapper Name",
    style_description="your style keywords",
    tts_voice="en-US-GuyNeural",   # any edge-tts voice
    personality_prompt="Detailed personality and style description...",
)
```

List available edge-tts voices with:

```bash
edge-tts --list-voices | grep en-
```

## Architecture

```
generate_battles.py          CLI entry point (argparse)
    |
    v
bots/rap_battle.py           Core pipeline module
    |
    +-- ScriptGenerator      LLM-based verse generation
    |   +-- OllamaBackend    Ollama REST API
    |   +-- LlamaCppBackend  llama.cpp server
    |   +-- TemplateBackend  Deterministic fallback
    |
    +-- AudioGenerator       edge-tts + ffmpeg mixing
    +-- VideoGenerator       ffmpeg 9:16 compositing + ASS subtitles
    +-- BattlePipeline       E2E orchestrator
    +-- BattleTracker        SQLite state management
```

## Troubleshooting

**edge-tts not found**: Ensure `pip install edge-tts` and it is on your PATH.

**ffmpeg errors**: Check that ffmpeg was built with libx264. Run
`ffmpeg -codecs | grep 264` to verify.

**Ollama connection refused**: Start the Ollama server with `ollama serve`,
then pull a model with `ollama pull mistral`.

**Upload failures**: Verify your API key and that the BoTTube platform is
reachable. The pipeline respects a 30-second rate limit between uploads.

**Low disk space**: Each battle generates ~5-15 MB of intermediate files.
For 1000 battles, ensure at least 15 GB free.

**SQLite errors on UPDATE**: The tracker uses standard subquery patterns
compatible with all SQLite builds. If you see locked-database errors when
running concurrent pipelines, use separate `--output-dir` per process.

## Programmatic Usage

```python
from pathlib import Path
from bots.rap_battle import BattlePipeline, PipelineConfig

cfg = PipelineConfig(output_dir=Path("./my_battles"))
pipeline = BattlePipeline(cfg)

# Single battle
result = pipeline.generate_single("Python vs Rust")

# Batch (5 battles, with upload)
results = pipeline.run_batch(topics=["Vim vs Emacs"], count=5, upload=True)

# The BattleTracker supports context-manager protocol
from bots.rap_battle import BattleTracker
with BattleTracker(Path("./tracker.db")) as tracker:
    tracker.mark_generated("Cats vs Dogs", "p1", "p2", "/tmp/out.mp4")
    pending = tracker.get_pending()
```
