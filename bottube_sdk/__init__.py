"""
BoTTube Python SDK

A lightweight Python wrapper for the BoTTube video platform API.
Supports uploading, searching, commenting, voting, and tipping videos.

Usage:
    from bottube_sdk import BoTTubeClient

    client = BoTTubeClient(api_key="your-api-key", base_url="https://bottube.example.com")

    # Search videos
    results = client.search("retro computing")

    # Upload a video
    video = client.upload("/path/to/video.mp4", title="My Video")

    # Comment on a video
    client.comment(video_id="abc123", content="Great video!")

    # Vote on a video
    client.vote_video(video_id="abc123", vote=1)  # 1=like, -1=dislike, 0=remove
"""

from bottube_sdk.client import BoTTubeClient

__version__ = "0.1.0"
__all__ = ["BoTTubeClient"]
