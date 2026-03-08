## What changed

- Updated `MAX_AVATAR_SIZE` from 2 MB to 5 MB to match the documented API limit in the issue
- Fixed hardcoded database path `/root/bottube/bottube.db` in the Base wRTC bridge initialization to use `BOTTUBE_DB_PATH` env var (consistent with other blueprints)
- Added the `POST /api/agents/me/avatar` endpoint to `openapi.yaml` with full request/response documentation
- Added comprehensive test suite for the avatar upload endpoint (`tests/test_avatar_upload.py`)
- Updated `tests/conftest.py` to set `BOTTUBE_DB` and `BOTTUBE_DB_PATH` env vars before importing the server module, fixing test import failures

## Why

Issue #290 documents a `~5MB` max file size for avatar uploads, but the server enforced a 2 MB limit. The avatar endpoint also wasn't documented in the OpenAPI spec and had no test coverage.

Fixes #290

## Testing

- Added 8 tests covering: auth (missing/invalid API key), validation (invalid file type, file too large), rate limiting, successful upload with file, successful auto-generation, and MAX_AVATAR_SIZE constant verification
- All tests pass: `python -m pytest tests/test_avatar_upload.py -v` (8 passed)
- Full suite excluding pre-existing test ordering issue: `python -m pytest tests/ --ignore=tests/test_tipping.py` (68 passed, 1 skipped)
- No new test failures introduced
