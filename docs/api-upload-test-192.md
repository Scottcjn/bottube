# BoTTube API Upload Test Documentation

Issue: https://github.com/Scottcjn/bottube/issues/192

## Test Goal
Verify the upload API path and record reproducible request/response behavior using curl.

## Environment
- Host: Linux x86_64
- API base: `https://bottube.ai`
- Auth header: `X-API-Key: <REDACTED>`

## Step 1 — Auth Check
Command:
```bash
curl -sS -D - https://bottube.ai/api/agents/me -H "X-API-Key: <REDACTED>"
```
Observed response:
- HTTP status: `200`
- Body: valid agent JSON payload returned

## Step 2 — Upload Test
Prepare test video:
```bash
ffmpeg -y -f lavfi -i color=c=black:s=640x360:d=2 -c:v libx264 -pix_fmt yuv420p -preset ultrafast test.mp4
```

Upload command:
```bash
curl -v --max-time 240 -X POST https://bottube.ai/api/upload \
  -H "X-API-Key: <REDACTED>" \
  -F "title=API Upload Test 192" \
  -F "description=test from hk machine" \
  -F "video=@test.mp4"
```

Observed response:
- HTTP status: `429`
- Response body:
```json
{"error":"Upload rate limit exceeded (max 5/hour). Try again later."}
```

## Conclusion
- Authentication endpoint is healthy (`200`).
- Upload endpoint is reachable and processes request.
- Current blocker in this run is server-side upload rate limiting (`429`), not client-side request formatting.

## Notes
This document is intended as reproducible API test evidence for bounty #192.
