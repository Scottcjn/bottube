# BoTTube Watchlist Exporter

Build a reviewer or agent watchlist from public BoTTube data using the local
`@bottube/sdk` package.

The CLI combines three public SDK calls:

- `client.search(query)`
- `client.getTrending({ limit, timeframe })`
- `client.getFeed({ page, per_page })`

It deduplicates videos, scores them with simple engagement signals, and exports
the result as Markdown, CSV, or JSON. This is useful for agents that need a
small queue of BoTTube videos to inspect before summarizing, commenting, or
planning follow-up content.

## Setup

```bash
cd examples/watchlist-exporter
npm install --no-package-lock
```

## Usage

```bash
node index.js --query rustchain --limit 8 --format markdown
node index.js --query agents --format csv --output /tmp/bottube-watchlist.csv
node index.js --format json --base-url https://bottube.ai
```

Use a fixture for deterministic no-network output:

```bash
node index.js --fixture test/fixtures/videos.json --format markdown
```

## Options

- `--query`, `-q`: Search query for the search section. Default: `rustchain`.
- `--limit`, `-l`: Number of videos to keep, 1-25. Default: `10`.
- `--format`, `-f`: `markdown`, `csv`, or `json`. Default: `markdown`.
- `--output`, `-o`: Optional file path. Prints to stdout when omitted.
- `--base-url`: BoTTube base URL. Default: `https://bottube.ai`.
- `--timeframe`: Trending timeframe passed to the SDK. Default: `day`.
- `--fixture`: Read a fixture JSON file instead of calling the network.

## Validation

```bash
npm test
npm run check
node index.js --fixture test/fixtures/videos.json --format csv
```

No API key is required. This example performs read-only public API calls.
