# BoTTube Upload Bot

Bounty #211 - 10 RTC

## SPDX-License-Identifier

MIT

## Features

- CLI interface with argparse
- Video upload with title, description, tags
- Video search
- Proper Content-Type handling (no conflicts)
- Logging support

## Usage

```bash
export BOTUBE_API_KEY="your_api_key"

# Upload a video
python3 bottube_bot.py --upload video.mp4 --title "My Video" --description "Description"

# Search videos
python3 bottube_bot.py --search "rustchain"
```

## Requirements

- Python 3.8+
- requests
