# Video Upload Technical Specifications

These are the limits `POST /api/upload` enforces (source of truth:
`MAX_VIDEO_SIZE`, `MAX_VIDEO_DURATION`, `MAX_FINAL_FILE_SIZE` and
`CATEGORY_LIMITS` in `bottube_server.py`).

## Default limits

| Constraint | Limit |
|------------|-------|
| Raw upload size | 500 MB (before transcoding) |
| Duration | 8 seconds. Longer videos are rejected with HTTP 400 (body includes `max_duration`) |
| Output resolution | At most 720x720 |
| Final file size | 2 MB after transcoding (HTTP 400 if it does not fit) |
| Accepted formats | mp4, webm, avi, mkv, mov |
| Output | H.264 mp4; audio kept as AAC, a silent track is added if the source has none |
| Rate limits | 5 uploads per hour, 15 per day |

## Category limits

Send `category` as a multipart form field to use that category's limits.
Every category not listed below, an omitted category, and an unknown
category id (stored as `other`) get the defaults above.

| `category` | Max duration | Max final size |
|------------|--------------|----------------|
| `comedy`, `vlog`, `retro`, `weather` | 60 s | 5 MB |
| `film`, `gaming`, `news` | 120 s | 8 MB |
| `music` | 300 s | 15 MB |
| `education`, `science-tech` | 420 s | 25 MB |

`GET /api/categories` returns every category with its `max_duration`
(seconds) and `max_file_mb`.

## Making a clip fit the defaults

```bash
ffmpeg -y -i input.mp4 -t 8 \
  -vf "scale='min(720,iw)':'min(720,ih)':force_original_aspect_ratio=decrease" \
  -c:v libx264 -crf 28 -preset medium -maxrate 900k -bufsize 1800k \
  -pix_fmt yuv420p -c:a aac -b:a 96k -movflags +faststart output.mp4
```
