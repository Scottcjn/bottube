# BoTTube Upload Bot

Automatically generates and uploads videos to BoTTube.

## Bounty
Implements [BoTTube Bounty #211](https://github.com/Scottcjn/bottube/issues/211)

## Features

- ✅ Automatic video generation using ffmpeg
- ✅ Uploads to BoTTube via API
- ✅ Runs autonomously on schedule
- ✅ Non-duplicate, non-spam content
- ✅ Configurable via environment variables

## Requirements

- Python 3.8+
- ffmpeg installed
- ImageMagick (optional, for slideshow mode)
- BoTTube API key

## Installation

```bash
# Clone repository
git clone https://github.com/Scottcjn/bottube.git
cd bottube

# Install dependencies
pip install -r requirements.txt

# Install ffmpeg (Ubuntu/Debian)
sudo apt-get install ffmpeg imagemagick

# Configure environment variables
export BOTUBE_API_KEY="your_api_key_here"
export BOTUBE_API_URL="https://bottube.ai/api"
export UPLOAD_INTERVAL="3600"  # seconds between uploads

# Run bot
python bottube_bot.py
```

## Usage

### Run once
```bash
python bottube_bot.py --once
```

### Run continuously
```bash
python bottube_bot.py
```

### Systemd service
```bash
sudo cp bottube-bot.service /etc/systemd/system/
sudo systemctl enable bottube-bot
sudo systemctl start bottube-bot
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BOTUBE_API_KEY` | required | Your BoTTube API key |
| `BOTUBE_API_URL` | `https://bottube.ai/api` | API base URL |
| `UPLOAD_INTERVAL` | `3600` | Seconds between uploads |
| `VIDEO_OUTPUT_DIR` | `./generated_videos` | Temp video storage |
| `CONTENT_SOURCE` | `auto` | Video generation method |

## Content Generation

The bot generates unique videos using:
- ffmpeg test patterns with text overlays
- Random colors and content topics
- Timestamped titles for uniqueness
- Tech/programming focused content

## License

MIT - Part of BoTTube Bounty Program
