#!/usr/bin/env node

import { BoTTubeClient } from "@bottube/sdk";

const DEFAULT_LIMIT = 5;

function parseArgs(argv) {
  const options = {
    limit: DEFAULT_LIMIT,
    query: "rustchain",
    timeframe: "day",
    json: false,
    baseUrl: process.env.BOTTUBE_BASE_URL || "https://bottube.ai",
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--json") {
      options.json = true;
    } else if (arg === "--limit" || arg === "-l") {
      options.limit = clampLimit(argv[++i]);
    } else if (arg === "--query" || arg === "-q") {
      options.query = argv[++i] || options.query;
    } else if (arg === "--timeframe" || arg === "-t") {
      options.timeframe = argv[++i] || options.timeframe;
    } else if (arg === "--base-url") {
      options.baseUrl = argv[++i] || options.baseUrl;
    } else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    }
  }

  return options;
}

function clampLimit(value) {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) {
    return DEFAULT_LIMIT;
  }
  return Math.min(Math.max(parsed, 1), 20);
}

function normalizeVideos(response) {
  if (Array.isArray(response)) {
    return response;
  }
  return response?.videos || response?.results || response?.items || [];
}

function videoUrl(video, baseUrl) {
  const id = video.video_id || video.id || video.slug;
  if (!id) {
    return baseUrl;
  }
  return `${baseUrl.replace(/\/$/, "")}/watch/${id}`;
}

function renderVideo(video, index, baseUrl) {
  const title = video.title || "Untitled video";
  const agent = video.agent_name || video.agent || "unknown-agent";
  const views = video.view_count ?? video.views ?? 0;
  const likes = video.like_count ?? video.likes ?? video.vote_count ?? 0;
  const summary = video.description || video.scene_description || "";

  const lines = [
    `${index + 1}. [${title}](${videoUrl(video, baseUrl)})`,
    `   - Agent: ${agent}`,
    `   - Views: ${views} | Likes: ${likes}`,
  ];
  if (summary) {
    lines.push(`   - Summary: ${summary.slice(0, 180)}`);
  }
  return lines.join("\n");
}

function renderDigest({ trending, searchResults, options }) {
  const date = new Date().toISOString().slice(0, 10);
  const sections = [
    `# BoTTube Daily Digest - ${date}`,
    "",
    `Generated with the BoTTube JavaScript SDK from ${options.baseUrl}.`,
    "",
    `## Trending (${options.timeframe})`,
    "",
    ...trending.map((video, index) => renderVideo(video, index, options.baseUrl)),
    "",
    `## Search: ${options.query}`,
    "",
    ...searchResults.map((video, index) =>
      renderVideo(video, index, options.baseUrl),
    ),
    "",
  ];
  return sections.join("\n");
}

async function buildDigest(options) {
  const client = new BoTTubeClient({ baseUrl: options.baseUrl });
  const [trendingResponse, searchResponse] = await Promise.all([
    client.getTrending({ limit: options.limit, timeframe: options.timeframe }),
    client.search(options.query, { sort: "recent", perPage: options.limit }),
  ]);

  return {
    options,
    trending: normalizeVideos(trendingResponse).slice(0, options.limit),
    searchResults: normalizeVideos(searchResponse).slice(0, options.limit),
  };
}

function printHelp() {
  console.log(`BoTTube Daily Digest

Usage:
  node index.js [options]

Options:
  -l, --limit <n>       Number of videos per section, 1-20 (default: 5)
  -q, --query <text>    Search query for the second section (default: rustchain)
  -t, --timeframe <t>   Trending timeframe passed to SDK (default: day)
      --base-url <url>  BoTTube base URL (default: https://bottube.ai)
      --json            Print raw normalized JSON instead of Markdown
  -h, --help            Show this help
`);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const digest = await buildDigest(options);
  if (options.json) {
    console.log(JSON.stringify(digest, null, 2));
    return;
  }
  console.log(renderDigest(digest));
}

main().catch((error) => {
  console.error(`Failed to build BoTTube digest: ${error.message}`);
  process.exit(1);
});
