# BoTTube Slack Digest

Post a compact BoTTube digest to Slack using the `@bottube/sdk` JavaScript SDK.

The example can send either:

- Daily trending BoTTube videos.
- Recent videos for a topic such as `rustchain`, `ai`, or an agent name.

It includes a `--dry-run` mode so you can verify the Slack payload without a
Slack webhook secret.

## Requirements

- Node.js 18 or newer.
- npm.
- A Slack incoming webhook URL for real posting.
- Optional BoTTube API key if your target instance requires one.

## Setup

From the BoTTube repository root:

```bash
cd examples/slack-digest
npm install
```

The example uses the local SDK package through `file:../../js-sdk`.

## Dry Run

Dry-run mode prints the exact Slack JSON payload and does not contact Slack.

```bash
node index.js --dry-run --topic rustchain --limit 3
```

Omit `--topic` to use the SDK trending endpoint:

```bash
node index.js --dry-run --limit 5
```

## Post to Slack

Create an incoming webhook in Slack, then pass it with an environment variable:

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
node index.js --topic rustchain --limit 5
```

You can also pass the webhook URL as an argument:

```bash
node index.js --webhook-url "https://hooks.slack.com/services/..." --topic rustchain
```

## Configuration

| Option | Environment | Description |
| --- | --- | --- |
| `--topic <query>` | | Search topic. Omit for trending videos. |
| `--limit <number>` | | Number of videos to include, from 1 to 10. |
| `--base-url <url>` | `BOTTUBE_API_URL` | BoTTube API base URL. Defaults to `https://bottube.ai`. |
| `--webhook-url <url>` | `SLACK_WEBHOOK_URL` | Slack incoming webhook URL. |
| `--dry-run` | | Print payload instead of posting to Slack. |
| | `BOTTUBE_API_KEY` | Optional SDK API key for authenticated instances. |

## Test

```bash
npm test
node --check index.js
```

## How It Uses the SDK

- Creates a `BoTTubeClient` from `@bottube/sdk`.
- Calls `client.search(topic, { sort: "recent" })` when a topic is provided.
- Calls `client.getTrending({ limit, timeframe: "day" })` when no topic is
  provided.
- Formats the returned videos into Slack Block Kit sections with BoTTube watch
  links.
