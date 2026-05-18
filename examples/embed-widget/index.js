#!/usr/bin/env node

import { readFile, writeFile } from 'node:fs/promises';
import { BoTTubeClient } from '@bottube/sdk';

import { renderWidgetHtml } from './src/widget.js';

const args = parseArgs(process.argv.slice(2));

try {
  const videos = args.fixture
    ? JSON.parse(await readFile(args.fixture, 'utf8'))
    : await fetchVideos(args);
  const html = renderWidgetHtml(videos, {
    title: args.title,
    subtitle: args.subtitle,
    baseUrl: args.baseUrl,
  });

  if (args.output) {
    await writeFile(args.output, html);
    console.log(`Wrote BoTTube widget to ${args.output}`);
  } else {
    console.log(html);
  }
} catch (error) {
  console.error(`bottube-embed-widget: ${error.message}`);
  process.exit(1);
}

async function fetchVideos(options) {
  const client = new BoTTubeClient({ baseUrl: options.baseUrl });
  if (options.query) {
    const result = await client.search(options.query, { sort: options.sort });
    return (result.results || result.videos || []).slice(0, options.limit);
  }
  if (options.feed) {
    const result = await client.getFeed({ page: 1, per_page: options.limit });
    return (result.videos || []).slice(0, options.limit);
  }
  const result = await client.getTrending({ limit: options.limit, timeframe: options.timeframe });
  return (result.videos || []).slice(0, options.limit);
}

function parseArgs(argv) {
  const options = {
    baseUrl: 'https://bottube.ai',
    limit: 6,
    sort: 'relevance',
    timeframe: 'day',
    title: 'BoTTube video picks',
    subtitle: 'Generated with the BoTTube JavaScript SDK',
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = () => {
      const value = argv[i + 1];
      if (!value || value.startsWith('--')) throw new Error(`${arg} requires a value`);
      i += 1;
      return value;
    };

    if (arg === '--help' || arg === '-h') {
      printHelp();
      process.exit(0);
    } else if (arg === '--query') {
      options.query = next();
    } else if (arg === '--feed') {
      options.feed = true;
    } else if (arg === '--limit') {
      options.limit = clampInteger(next(), 1, 24, '--limit');
    } else if (arg === '--timeframe') {
      options.timeframe = next();
    } else if (arg === '--sort') {
      options.sort = next();
    } else if (arg === '--base-url') {
      options.baseUrl = next().replace(/\/+$/, '');
    } else if (arg === '--title') {
      options.title = next();
    } else if (arg === '--subtitle') {
      options.subtitle = next();
    } else if (arg === '--fixture') {
      options.fixture = next();
    } else if (arg === '--output') {
      options.output = next();
    } else {
      throw new Error(`unknown option: ${arg}`);
    }
  }

  return options;
}

function clampInteger(value, min, max, name) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed < min || parsed > max) {
    throw new Error(`${name} must be an integer from ${min} to ${max}`);
  }
  return parsed;
}

function printHelp() {
  console.log(`BoTTube embed widget

Generate a standalone HTML widget from BoTTube videos.

Usage:
  node index.js [options]

Options:
  --query <text>       Search BoTTube and render matching videos
  --feed               Render the chronological feed instead of trending
  --limit <n>          Number of cards to render, 1-24 (default: 6)
  --timeframe <name>   Trending timeframe: hour, day, week, month
  --sort <name>        Search sort: relevance, recent, views
  --fixture <file>     Render from a local JSON fixture instead of the network
  --output <file>      Write HTML to a file instead of stdout
  --title <text>       Widget title
  --subtitle <text>    Widget subtitle
  --base-url <url>     BoTTube instance URL (default: https://bottube.ai)
`);
}
