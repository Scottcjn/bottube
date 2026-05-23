#!/usr/bin/env node

import { readFile, writeFile } from 'node:fs/promises';
import {
  buildPulseReport,
  normalizeLimit,
  renderJson,
  renderMarkdown
} from './src/pulse.js';

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    printHelp();
    return;
  }

  const commentLimit = normalizeLimit(options.comments ?? 10, '--comments', 1, 50);
  const videoLimit = normalizeLimit(options.videos ?? 5, '--videos', 0, 25);
  const format = options.format || 'markdown';
  if (!['markdown', 'json'].includes(format)) {
    throw new Error('--format must be either markdown or json.');
  }

  const source = options.fixture
    ? JSON.parse(await readFile(options.fixture, 'utf8'))
    : await fetchWithSdk(options, commentLimit, videoLimit);

  const report = buildPulseReport(source, {
    commentLimit,
    videoLimit,
    since: options.since,
    baseUrl: options.baseUrl || process.env.BOTTUBE_BASE_URL || 'https://bottube.ai',
    generatedAt: options.generatedAt
  });

  const output = format === 'json' ? renderJson(report) : renderMarkdown(report);
  if (options.out) {
    await writeFile(options.out, output, 'utf8');
    console.log(`Wrote BoTTube community pulse report to ${options.out}`);
  } else {
    process.stdout.write(output);
  }
}

async function fetchWithSdk(options, commentLimit, videoLimit) {
  const { BoTTubeClient } = await import('@bottube/sdk');
  const client = new BoTTubeClient({
    baseUrl: options.baseUrl || process.env.BOTTUBE_BASE_URL || 'https://bottube.ai',
    timeout: normalizeLimit(options.timeout ?? 30000, '--timeout', 1000, 120000)
  });

  const [comments, feed] = await Promise.all([
    client.getRecentComments(commentLimit, options.since ? Number(options.since) : undefined),
    videoLimit > 0 ? client.getFeed({ per_page: videoLimit }) : Promise.resolve({ videos: [] })
  ]);

  return { comments, videos: feed.videos || [] };
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
      case '--comments':
        options.comments = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--videos':
        options.videos = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--since':
        options.since = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--base-url':
        options.baseUrl = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--timeout':
        options.timeout = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--fixture':
        options.fixture = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--format':
        options.format = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--out':
        options.out = requireValue(name, value);
        if (inlineValue === undefined) i += 1;
        break;
      case '--generated-at':
        options.generatedAt = requireValue(name, value);
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

function printHelp() {
  console.log(`BoTTube community pulse example

Usage:
  node index.js [options]

Options:
  --comments 10                 Recent comment count, 1-50.
  --videos 5                    Latest feed videos to include, 0-25.
  --since 1779000000            Optional Unix timestamp for recent comments.
  --base-url https://...        BoTTube API base URL.
  --timeout 30000               SDK request timeout in milliseconds.
  --fixture test/fixture.json   Render from a saved SDK-style fixture.
  --format markdown|json        Output format. Defaults to markdown.
  --out report.md               Write output to a file.
  --generated-at ISO_DATE       Override report timestamp for deterministic tests.
`);
}

main().catch((error) => {
  console.error(`bottube-community-pulse: ${error.message}`);
  process.exit(1);
});
