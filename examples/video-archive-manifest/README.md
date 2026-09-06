# BoTTube Video Archive Manifest — Bounty #2143

This is the public mirror of the existing @prins1bap-ui submission for `Scottcjn/rustchain-bounties#2143`. It creates no new claim.

The operative submission was delivered by email on 2026-08-30 after Gmail blocked the original ZIP. The plain-text source bundle SHA-256 was `10b206d54bb4aad8afa60513c13304cb8f78fac0bbc0cc423c199a21a3982008`.

## Current bounty accounting

- Live issue title: **3 RTC**
- Issue-body prose still says 5 RTC and is treated as stale unless the maintainer explicitly adjudicates otherwise.
- Canonical requested exposure: **3 RTC**
- Stage: **SUBMITTED** only. No acceptance, queue, pending transfer, or receipt is asserted.

## Current-source verification — 2026-09-02

Rechecked against current `Scottcjn/bottube` main:

- repository-local SDK package remains `bottube-sdk`
- `BoTTubeClient.listVideos(page, perPage)` remains available
- `BoTTubeClient.getVideoStreamUrl(videoId)` remains available
- the `Video` / `VideoListResponse` fields used here remain compatible
- SDK engine requirement remains Node.js 18+

Fresh local QA:

- `npm test` -> 3/3 passed
- `npm run check` -> passed
- fixture JSON render -> passed
- fixture Markdown render -> passed

## What it does

A small, read-only Node.js example using BoTTube's repository-local JavaScript SDK to export public video metadata as a portable JSON archive manifest or a human-readable Markdown inventory.

Live mode imports `BoTTubeClient` from `bottube-sdk` and calls:

- `client.listVideos(page, perPage)`
- `client.getVideoStreamUrl(videoId)`

No API key is required. The tool does not upload, comment, vote, tip, modify profiles, or move funds.

## Intended upstream path

`examples/video-archive-manifest/`

## Setup

When placed inside `Scottcjn/bottube`:

```bash
cd examples/video-archive-manifest
npm install
npm test
npm run check
node index.js --fixture test/fixtures/page.json --format markdown
```
