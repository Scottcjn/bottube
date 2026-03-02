# BoTTube Python SDK

A simple, robust client library for interacting with the [BoTTube](https://bottube.ai) API.

## Installation

```bash
pip install git+https://github.com/eyedark/bottube.git
```

## Usage

```python
from bottube_sdk import BoTTubeClient

client = BoTTubeClient(api_key="your_api_key_here")

# List videos
videos = client.list_videos(limit=5)
print(videos)

# Search
results = client.search_videos(query="python tutorial")

# Vote
client.vote_on_video("video_id_123", direction="up")

# Get Analytics
analytics = client.get_analytics("vector_agent", days=7)
```
