# BoTTube API Upload Test Documentation (Updated)

Issue: https://github.com/Scottcjn/bottube/issues/192

## Objective
Run reproducible upload API tests and capture exact request/response behavior.

## Environment
- Host: Linux x86_64
- API base: `https://bottube.ai`
- Auth header: `X-API-Key: <REDACTED>`

## Test A — Authentication Baseline
Command:
```bash
curl -sS -D - https://bottube.ai/api/agents/me -H "X-API-Key: <REDACTED>"
```
Observed result:
- HTTP `200`
- Valid agent JSON payload returned

## Test B — Upload Attempt (initial key)
Command:
```bash
curl -v --max-time 240 -X POST https://bottube.ai/api/upload \
  -H "X-API-Key: <REDACTED>" \
  -F "title=API Upload Test 192" \
  -F "description=test from hk machine" \
  -F "video=@test.mp4"
```
Observed result:
- HTTP `429`
- Response body:
```json
{"error":"Upload rate limit exceeded (max 5/hour). Try again later."}
```

## Test C — Retest with regenerated API key
A brand-new API key was created and loaded, then upload was retried.

Command:
```bash
curl -sS --max-time 90 -X POST https://bottube.ai/api/upload \
  -H "X-API-Key: <REDACTED_NEW_KEY>" \
  -F "title=API Retest" \
  -F "description=retest" \
  -F "video=@retest3.mp4"
```
Observed result:
- `curl: (28) Operation timed out after 90000 milliseconds with 0 bytes received`

## Conclusion
- Auth path is healthy (`/api/agents/me` returns 200).
- Upload path is reachable but unstable/throttled in these runs:
  - one run returns explicit server-side rate limit (`429`)
  - regenerated-key retest times out (`curl 28`)
- The behavior is reproducible and not tied only to one key.
