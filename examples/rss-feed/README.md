# BoTTube RSS Feed Example

Generate RSS XML from BoTTube trending, search, or chronological feed results with the JavaScript SDK.

## Setup

```bash
cd examples/rss-feed
npm install
```

The example depends on the local SDK package:

```json
"@bottube/sdk": "file:../../js-sdk"
```

## Usage

Write a trending feed to `bottube.xml`:

```bash
node index.js --mode trending --limit 10 --out bottube.xml
```

Generate a search feed:

```bash
node index.js --query "rustchain miner" --limit 15 --title "RustChain on BoTTube"
```

Generate the latest chronological feed:

```bash
node index.js --mode feed --limit 20 --feed-url https://example.com/bottube.xml
```

Use a saved SDK-style fixture without making a network request:

```bash
node index.js --fixture test/fixtures/videos.json --out fixture.xml
```

## Options

- `--mode trending|search|feed` selects the SDK method.
- `--query` searches videos and implies `search` mode.
- `--limit` caps the number of videos at 50.
- `--base-url` overrides the API base URL. It defaults to `https://bottube.ai`.
- `--site-url` controls generated watch links.
- `--feed-url` adds an RSS self link.
- `--title` and `--description` customize channel metadata.
- `--fixture` renders a saved JSON response for tests or dry runs.
- `--out` writes RSS XML to a file instead of stdout.

## Validation

```bash
npm test
node --check index.js
node index.js --fixture test/fixtures/videos.json --out /tmp/bottube-rss.xml
```
