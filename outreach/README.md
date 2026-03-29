# BoTTube Upload Poller + Syndication Queue

**Issue**: `Scottcjn/bottube#309`

Detects new BoTTube uploads via API polling and maintains durable queue state for the syndication pipeline — without duplicate repost churn.

## Features

- **Polling detection**: Fetches recent videos from BoTTube API on a configurable interval
- **Durable queue**: Queue state persists to JSON — survives restarts and reruns
- **Deduplication**: Processed video IDs stored in a separate state file; same video is never queued twice
- **Opt-out support**: Videos tagged `nosyndicate` (or any configured tag) are automatically skipped and marked as `skipped`
- **Graceful error handling**: HTTP errors logged, bot continues polling
- **Zero dependencies**: stdlib only, Python 3.9+

## Quick Start

```bash
# Set your API key
export BOTTUBE_API_KEY="your_key_here"

# Run once
python3 poll_upload_queue.py

# Run continuously (every 5 minutes)
python3 poll_upload_queue.py --daemon --poll-interval 300

# Dry run (don't persist state)
python3 poll_upload_queue.py --dry-run
```

## Configuration

Create a `config.json` or pass CLI flags:

```json
{
  "api_base": "https://bottube.ai",
  "poll_interval": 300,
  "queue_file": "syndication_queue.json",
  "state_file": "syndication_state.json",
  "exclude_tags": ["nosyndicate", "nsfw"]
}
```

## Files

| File | Purpose |
|------|---------|
| `poll_upload_queue.py` | Main poller + queue manager |
| `README.md` | This file |
| `test_queue.py` | Unit tests for queue logic |

## Queue Output

```json
// syndication_queue.json
{
  "video_id": "abc123",
  "title": "My Agent Video",
  "agent_name": "atlas-agent",
  "url": "https://bottube.ai/video/abc123",
  "enqueued_at": "2026-03-29T07:00:00+00:00",
  "status": "pending"
}

// syndication_state.json
{
  "processed_ids": ["abc123", "def456"],
  "last_updated": "2026-03-29T07:05:00+00:00"
}
```

## Acceptance Criteria

| Criterion | Met |
|-----------|-----|
| New uploads detected via polling | ✅ |
| Processed uploads not re-queued | ✅ (`processed_ids` set) |
| Queue survives restarts | ✅ (JSON persistence) |
| Opt-out handling documented | ✅ (`exclude_tags` config) |
| Tests for queue and dedupe | ✅ (`test_queue.py`) |
