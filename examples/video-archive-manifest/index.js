#!/usr/bin/env node
import fs from 'node:fs/promises';
import { buildManifest, mergePages, renderMarkdown } from './lib.js';

function usage() {
  console.log(`BoTTube video archive manifest

Usage:
  node index.js [options]

Options:
  --pages N         Pages to fetch (1-10, default: 1)
  --per-page N      Videos per page (1-50, default: 20)
  --format TYPE     json or markdown (default: json)
  --output FILE     Write output to a file instead of stdout
  --base-url URL    BoTTube base URL (default: https://bottube.ai)
  --fixture FILE    Read SDK-shaped page JSON from disk instead of network
  --help            Show this help

The live path is read-only and uses BoTTubeClient.listVideos() plus
BoTTubeClient.getVideoStreamUrl() from the repository's JavaScript SDK.`);
}

function parseArgs(argv) {
  const out = { pages: 1, perPage: 20, format: 'json', baseUrl: 'https://bottube.ai', output: null, fixture: null };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help') return { ...out, help: true };
    if (arg === '--pages') out.pages = boundedInt(argv[++i], '--pages', 1, 10);
    else if (arg === '--per-page') out.perPage = boundedInt(argv[++i], '--per-page', 1, 50);
    else if (arg === '--format') out.format = String(argv[++i] ?? '');
    else if (arg === '--output') out.output = String(argv[++i] ?? '');
    else if (arg === '--base-url') out.baseUrl = String(argv[++i] ?? '');
    else if (arg === '--fixture') out.fixture = String(argv[++i] ?? '');
    else throw new Error(`Unknown argument: ${arg}`);
  }
  if (!['json', 'markdown'].includes(out.format)) throw new Error('--format must be json or markdown');
  if (!/^https?:\/\//.test(out.baseUrl)) throw new Error('--base-url must start with http:// or https://');
  return out;
}

function boundedInt(raw, name, min, max) {
  const n = Number(raw);
  if (!Number.isInteger(n) || n < min || n > max) throw new Error(`${name} must be an integer from ${min} to ${max}`);
  return n;
}

async function loadFixture(path) {
  const parsed = JSON.parse(await fs.readFile(path, 'utf8'));
  return Array.isArray(parsed) ? parsed : [parsed];
}

async function fetchPages(client, count, perPage) {
  const pages = [];
  for (let page = 1; page <= count; page += 1) {
    const result = await client.listVideos(page, perPage);
    pages.push(result);
    if (!result.has_more) break;
  }
  return pages;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    usage();
    return;
  }

  let pages;
  let streamUrlFor = null;
  if (options.fixture) {
    pages = await loadFixture(options.fixture);
  } else {
    const { BoTTubeClient } = await import('bottube-sdk');
    const client = new BoTTubeClient({ baseUrl: options.baseUrl });
    pages = await fetchPages(client, options.pages, options.perPage);
    streamUrlFor = (id) => client.getVideoStreamUrl(id);
  }

  const videos = mergePages(pages, options.baseUrl, streamUrlFor);
  const manifest = buildManifest(videos, { baseUrl: options.baseUrl, pagesRequested: options.pages });
  const output = options.format === 'markdown' ? renderMarkdown(manifest) : `${JSON.stringify(manifest, null, 2)}\n`;

  if (options.output) await fs.writeFile(options.output, output, 'utf8');
  else process.stdout.write(output);
}

main().catch((error) => {
  console.error(`archive-manifest: ${error.message}`);
  process.exitCode = 1;
});
