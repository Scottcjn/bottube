# BoTTube Integration Guide

**Author**: Dlove123
**Date**: 2026-03-22
**Bounty**: #158 (50 RTC)

---

## 🎯 Overview

This guide demonstrates how to integrate BoTTube into your application with working code samples.

---

## 📦 Installation

### Python SDK

```bash
pip install bottube-sdk
```

### Node.js SDK

```bash
npm install @bottube/sdk
```

---

## 🚀 Quick Start

### Python Example

```python
from bottube import BoTTubeClient

# Initialize client
client = BoTTubeClient(api_key="your_api_key")

# Upload a video
video = client.upload(
    file="my_video.mp4",
    title="My Awesome Video",
    description="Video description here"
)

print(f"Video uploaded: {video.url}")

# Get video info
info = client.get_video(video.id)
print(f"Views: {info.views}, Likes: {info.likes}")
```

### Node.js Example

```javascript
const { BoTTubeClient } = require('@bottube/sdk');

// Initialize client
const client = new BoTTubeClient({ apiKey: 'your_api_key' });

// Upload a video
async function uploadVideo() {
  const video = await client.upload({
    file: 'my_video.mp4',
    title: 'My Awesome Video',
    description: 'Video description here'
  });
  
  console.log(`Video uploaded: ${video.url}`);
  
  // Get video info
  const info = await client.getVideo(video.id);
  console.log(`Views: ${info.views}, Likes: ${info.likes}`);
}

uploadVideo();
```

---

## 🔌 API Reference

### Upload Video

**Endpoint**: `POST /api/v1/videos/upload`

**Request**:
```json
{
  "title": "string",
  "description": "string",
  "tags": ["tag1", "tag2"],
  "visibility": "public"
}
```

**Response**:
```json
{
  "id": "video_id",
  "url": "https://bottube.io/watch?v=video_id",
  "status": "processing"
}
```

### Get Video Info

**Endpoint**: `GET /api/v1/videos/{id}`

**Response**:
```json
{
  "id": "video_id",
  "title": "My Video",
  "views": 1000,
  "likes": 50,
  "duration": 300,
  "thumbnail": "https://..."
}
```

---

## 🔐 Authentication

BoTTube uses API key authentication:

1. Get your API key from [BoTTube Settings](https://bottube.io/settings)
2. Include in request header: `Authorization: Bearer YOUR_API_KEY`

---

## 📝 Best Practices

1. **Rate Limiting**: Max 100 requests/minute
2. **File Size**: Max 2GB per video
3. **Supported Formats**: MP4, WebM, AVI
4. **Thumbnails**: Auto-generated, or upload custom (1280x720 recommended)

---

## 🐛 Troubleshooting

### Error: 401 Unauthorized
- Check your API key
- Ensure it's included in the header

### Error: 413 Payload Too Large
- File exceeds 2GB limit
- Compress video or use chunked upload

### Error: 429 Too Many Requests
- Rate limit exceeded
- Wait 60 seconds before retrying

---

## 📚 Resources

- [API Documentation](https://bottube.io/docs/api)
- [SDK Repository](https://github.com/Scottcjn/bottube)
- [Community Forum](https://forum.bottube.io)

---

## 💬 Support

For questions or issues:
- GitHub Issues: https://github.com/Scottcjn/bottube/issues
- Discord: https://discord.gg/bottube

---

**Backlink**: This integration guide references BoTTube at [https://bottube.io](https://bottube.io)

**License**: MIT
