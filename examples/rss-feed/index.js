#!/usr/bin/env node

import { readFile, writeFile } from 'node:fs/promises';
import { extractVideos, generateRss, normalizeLimit } from './src/rss.js';

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    printHelp();
    return;
  }

  const baseUrl = options.baseUrl || process.env.BOTTUBE_BASE_URL || 'https://bottube.ai';
  const siteUrl = options.siteUrl || baseUrl;
  const limit = normalizeLimit(options.limit || 10);
  const response = options.fixture
    ? JSON.parse(await readFile(options.fixture, 'utf8'))
    : await fetchWithSdk(options, baseUrl, limit);

  const videos = extractVideos(response, limit);
  const xml = generateRss({
    title: options.title || defaultTitle(options),
    description: options.description,
    siteUrl,
    feedUrl: options.feedUrl,
    videos
  });

  if (options.out) {
    await writeFile(options.out, xml, 'utf8');
    console.log(`Wrote ${videos.length} videos to ${options.out}`);
  } else {
    process.stdout.write(xml);
  }
}

async function fetchWithSdk(options, baseUrl, limit) {
  const { BoTTubeClient } = await import('@bottube/sdk');
  const client = new BoTTubeClient({
    baseUrl,
    timeout: Number.parseInt(String(options.timeout || 30000), 10)
  });
  const mode = options.mode || (options.query ? 'search' : 'trending');

  if (mode === 'search') {
    if (!options.query) {
      throw new Error('Search mode requires --query "search terms".');
    }
    return client.search(options.query, { sort: options.sort });
  }

  if (mode === 'feed') {
    return client.getFeed({ per_page: limit });
  }

  if (mode === 'trending') {
    return client.getTrending({
      limit,
      timeframe: options.timeframe
    });
  }

  throw new Error(`Unknown mode "${mode}". Use trending, search, or feed.`);
}

function parseArgs(argv) {
  const options = {};

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') {
      options.help = true;
      continue;
    }

    const [name, inlineValue] = arg.startsWith('--') ? arg.split('=', 2) : [arg, undefined];
    const value = inlineValue ?? argv[i + 1];

    switch (name) {
      case '--mode':
        options.mode = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--query':
        options.query = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--limit':
        options.limit = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--timeframe':
        options.timeframe = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--sort':
        options.sort = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--base-url':
        options.baseUrl = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--site-url':
        options.siteUrl = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--feed-url':
        options.feedUrl = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--title':
        options.title = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--description':
        options.description = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--fixture':
        options.fixture = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--out':
        options.out = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--timeout':
        options.timeout = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

function requireValue(name, value) {
  if (!value || value.startsWith('--')) {
    throw new Error(`${name} requires a value.`);
  }
  return value;
}

function defaultTitle(options) {
  if (options.mode === 'feed') return 'Latest BoTTube videos';
  if (options.query) return `BoTTube search: ${options.query}`;
  return 'Trending BoTTube videos';
}

function printHelp() {
  console.log(`BoTTube RSS feed example

Usage:
  node index.js [options]

Options:
  --mode trending|search|feed   SDK source to use. Defaults to trending.
  --query "agent ai"            Search query. Implies search mode.
  --limit 10                    Number of videos, capped at 50.
  --timeframe week              Trending timeframe forwarded to the SDK.
  --base-url https://...        BoTTube API base URL.
  --site-url https://...        Public site URL for generated watch links.
  --feed-url https://...        Optional canonical URL for this RSS feed.
  --title "Feed title"          RSS channel title.
  --description "Text"          RSS channel description.
  --fixture file.json           Render from a saved SDK-style JSON response.
  --out feed.xml                Write XML to a file instead of stdout.
  --timeout 30000               SDK request timeout in milliseconds.
`);
}

main().catch((error) => {
  console.error(`bottube-rss: ${error.message}`);
  process.exit(1);
});
