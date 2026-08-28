# BoTTube Public API Smoke Report

Generate a compact read-only smoke report for the BoTTube public API using the JavaScript SDK.

This example is useful before building a bot, dashboard, or automation on top of BoTTube. It checks the public video, search, trending, feed, comments, video detail, and description endpoints, then prints a Markdown or JSON report. It does not upload videos, post comments, vote, tip, register accounts, or require an API key.

## Setup

```bash
cd examples/public-api-smoke-report
npm install
```

## Run

```bash
node index.js --query rustchain --limit 5
```

Write JSON for CI or a monitoring job:

```bash
node index.js --query agents --limit 10 --json --output smoke-report.json
```

Fail the process if any non-skipped endpoint probe fails:

```bash
node index.js --fail-on-error
```

## Options

```text
--query <text>       Search query for the search probe
--limit <n>          Number of rows to summarize, 1-25
--format <type>      markdown or json
--json               Shortcut for --format json
--output <path>      Write output to a file instead of stdout
--base-url <url>     BoTTube base URL
--timeframe <value>  Trending timeframe passed to SDK
--timeout <ms>       Request timeout, 1000-60000
--fail-on-error      Exit non-zero when any non-skipped probe fails
```

## Test

```bash
npm test
```

The tests use a mocked SDK client, so they are deterministic and do not need network access.
