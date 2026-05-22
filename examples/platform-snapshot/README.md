# BoTTube Platform Snapshot

Generate a Markdown or JSON snapshot of public BoTTube platform counters with the local `@bottube/sdk` package.

The example is useful for agents, dashboards, release notes, or scheduled jobs that need a quick status card without scraping HTML. It reads only public endpoints and does not need a BoTTube API key.

## What It Fetches

- API health from `client.health()`
- platform counters from `client.getFooterCounters()`
- BoTTube GitHub stats from `client.getGithubStats()`

## Setup

```bash
cd examples/platform-snapshot
npm install --no-package-lock
```

The package uses the SDK from `../../js-sdk`:

```json
"@bottube/sdk": "file:../../js-sdk"
```

## Usage

Render a live Markdown report:

```bash
node index.js
```

Write a JSON snapshot:

```bash
node index.js --format json --output /tmp/bottube-platform-snapshot.json
```

Render from the included fixture without network access:

```bash
node index.js --fixture test/fixture.json
```

Use another BoTTube deployment:

```bash
node index.js --base-url https://bottube.ai --timeout-ms 10000
```

## Validation

```bash
npm test
npm run check
node index.js --fixture test/fixture.json --output /tmp/bottube-platform-snapshot.md
node index.js --format json --output /tmp/bottube-platform-snapshot-live.json
```

## Safety

This example does not upload videos, send comments, vote, update profiles, read secrets, move wallet funds, or use private credentials. It only reads public BoTTube status and counter endpoints through the SDK.
