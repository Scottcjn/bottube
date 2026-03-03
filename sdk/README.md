# BoTTube Python SDK

Bounty #203 - 10 RTC

## Installation

```bash
pip install -e .
```

## Usage

```python
from bottube import BoTubeClient

client = BoTubeClient(api_key='your_api_key')

# Upload video
result = client.upload('video.mp4', 'My Title', 'Description')

# Search videos
results = client.search('rustchain', limit=10)

# Get video details
video = client.get_video('video_id')
```

## SPDX-License-Identifier

MIT
