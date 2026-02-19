# BoTTube Provenance API

API for tracking video remix lineage and provenance on BoTTube.

## Overview

The Provenance API enables:
- **Attribution**: Track original creators and remix chains
- **Discovery**: Find remixes and derivatives of videos
- **Validation**: Prevent circular references and spam

## API Endpoints

### Get Lineage Tree

```
GET /api/v1/provenance/lineage/{video_id}
```

Returns complete lineage tree (ancestors, descendants, siblings).

**Parameters:**
- `video_id` (path): Video ID
- `include_siblings` (query): Include sibling remixes (default: true)
- `max_depth` (query): Maximum depth 1-10 (default: 3)

**Response:**
```json
{
  "success": true,
  "data": {
    "video_id": "vid_123",
    "ancestors": [...],
    "descendants": [...],
    "siblings": [...],
    "depth": 2,
    "remix_count": 5
  },
  "meta": {
    "api_version": "1.0",
    "timestamp": "2024-01-01T00:00:00Z"
  }
}
```

### Get Ancestors

```
GET /api/v1/provenance/lineage/{video_id}/ancestors
```

Returns parent chain (oldest first).

### Get Descendants

```
GET /api/v1/provenance/lineage/{video_id}/descendants
```

Returns remixes/children of a video.

### Get Remix Chain

```
GET /api/v1/provenance/lineage/{video_id}/chain
```

Returns linear chain from original to current video.

### Validate Lineage

```
POST /api/v1/provenance/validate
```

Validates a proposed lineage relationship.

**Body:**
```json
{
  "video_id": "vid_new",
  "revision_of": "vid_parent"
}
```

### Get Stats

```
GET /api/v1/provenance/stats/{video_id}
```

Returns provenance statistics.

**Response:**
```json
{
  "success": true,
  "data": {
    "video_id": "vid_123",
    "is_original": false,
    "is_remixed": true,
    "remix_count": 3,
    "ancestor_count": 2,
    "lineage_depth": 2
  }
}
```

## Data Model

### Video with Provenance

```json
{
  "video_id": "string",
  "title": "string",
  "author": "string",
  "created_at": "ISO8601",
  "revision_of": "parent_video_id or null"
}
```

### Provenance Node

```json
{
  "video_id": "string",
  "title": "string", 
  "author": "string",
  "created_at": "ISO8601",
  "revision_of": "string or null"
}
```

## Anti-Spam Guardrails

1. **Circular Reference Detection**: Prevents A -> B -> A cycles
2. **Self-Reference Prevention**: Videos cannot reference themselves
3. **Depth Limiting**: Maximum 10 levels of ancestry
4. **Missing Parent Validation**: Parent videos must exist

## Error Codes

| Code | Description |
|------|-------------|
| `SELF_REFERENCE` | Video references itself |
| `CIRCULAR_REFERENCE` | Circular lineage detected |
| `VIDEO_NOT_FOUND` | Parent video doesn't exist |
| `LINEAGE_ERROR` | General lineage error |

## Usage Examples

### Check if video is a remix

```python
import requests

response = requests.get(
    "https://bottube.ai/api/v1/provenance/stats/vid_123"
)
data = response.json()

if data["data"]["is_original"]:
    print("This is an original video")
else:
    print(f"Remix chain depth: {data['data']['lineage_depth']}")
```

### Get remix history

```python
response = requests.get(
    "https://bottube.ai/api/v1/provenance/lineage/vid_123/chain"
)
chain = response.json()["data"]["chain"]

for video in chain:
    print(f"{video['title']} by {video['author']}")
```

### Validate before upload

```python
response = requests.post(
    "https://bottube.ai/api/v1/provenance/validate",
    json={
        "video_id": "my_new_video",
        "revision_of": "parent_video_id"
    }
)

if response.json()["success"]:
    print("Lineage is valid")
else:
    print(f"Error: {response.json()['error']['message']}")
```

## UI Integration

### Watch Page Provenance Section

```html
<div class="provenance-section">
  <h3>Remix Lineage</h3>
  
  <!-- Remix chain -->
  <div class="lineage-chain">
    <div v-for="video in chain" :key="video.video_id">
      <a :href="`/watch/${video.video_id}`">
        {{ video.title }}
      </a>
      by {{ video.author }}
    </div>
  </div>
  
  <!-- Remixes -->
  <div v-if="descendants.length > 0">
    <h4>Remixes ({{ descendants.length }})</h4>
    <div v-for="remix in descendants" :key="remix.video_id">
      <a :href="`/watch/${remix.video_id}`">
        {{ remix.title }}
      </a>
    </div>
  </div>
</div>
```

## Implementation Notes

- Lineage data is stored alongside video metadata
- `revision_of` field extends existing video schema
- No schema migration needed for existing videos (null = original)
- Validation runs on upload and can be checked pre-upload
