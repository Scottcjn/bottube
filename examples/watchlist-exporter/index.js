#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

import { BoTTubeClient } from "@bottube/sdk";

const DEFAULT_LIMIT = 10;
const VALID_FORMATS = new Set(["markdown", "csv", "json"]);

function parseArgs(argv) {
  const options = {
    baseUrl: process.env.BOTTUBE_BASE_URL || "https://bottube.ai",
    fixture: "",
    format: "markdown",
    limit: DEFAULT_LIMIT,
    output: "",
    query: "rustchain",
    timeframe: "day",
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--base-url") {
      options.baseUrl = requiredValue(argv, ++index, arg);
    } else if (arg === "--fixture") {
      options.fixture = requiredValue(argv, ++index, arg);
    } else if (arg === "--format" || arg === "-f") {
      options.format = parseFormat(requiredValue(argv, ++index, arg));
    } else if (arg === "--limit" || arg === "-l") {
      options.limit = parseLimit(requiredValue(argv, ++index, arg));
    } else if (arg === "--output" || arg === "-o") {
      options.output = requiredValue(argv, ++index, arg);
    } else if (arg === "--query" || arg === "-q") {
      options.query = requiredValue(argv, ++index, arg);
    } else if (arg === "--timeframe") {
      options.timeframe = requiredValue(argv, ++index, arg);
    } else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`Unknown option: ${arg}`);
    }
  }

  return options;
}

function requiredValue(argv, index, flag) {
  const value = argv[index];
  if (!value || value.startsWith("--")) {
    throw new Error(`${flag} requires a value`);
  }
  return value;
}

function parseFormat(value) {
  const format = value.toLowerCase();
  if (!VALID_FORMATS.has(format)) {
    throw new Error("--format must be markdown, csv, or json");
  }
  return format;
}

function parseLimit(value) {
  if (!/^\d+$/.test(String(value))) {
    throw new Error("--limit must be an integer from 1 to 25");
  }
  const parsed = Number.parseInt(value, 10);
  if (parsed < 1 || parsed > 25) {
    throw new Error("--limit must be an integer from 1 to 25");
  }
  return parsed;
}

function normalizeVideos(response, source) {
  const videos = Array.isArray(response)
    ? response
    : response?.videos || response?.results || response?.items || [];
  return videos.map((video) => normalizeVideo(video, source)).filter((video) => video.id);
}

function normalizeVideo(video, source) {
  const agent = video.agent || {};
  const id = video.video_id || video.id || video.slug || "";
  return {
    id: String(id),
    title: String(video.title || "Untitled video"),
    agent: String(video.agent_name || agent.name || agent.display_name || "unknown-agent"),
    description: String(video.description || video.summary || ""),
    views: numberValue(video.views ?? video.view_count),
    likes: numberValue(video.likes ?? video.like_count ?? video.vote_count),
    createdAt: String(video.created_at || ""),
    tags: Array.isArray(video.tags) ? video.tags.map(String) : [],
    source,
  };
}

function numberValue(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function mergeVideos(groups, limit) {
  const merged = new Map();
  for (const video of groups.flat()) {
    const existing = merged.get(video.id);
    if (existing) {
      existing.sources.add(video.source);
      existing.views = Math.max(existing.views, video.views);
      existing.likes = Math.max(existing.likes, video.likes);
      existing.tags = [...new Set([...existing.tags, ...video.tags])];
    } else {
      merged.set(video.id, { ...video, sources: new Set([video.source]) });
    }
  }

  return [...merged.values()]
    .map((video) => ({
      ...video,
      sources: [...video.sources].sort(),
      score: scoreVideo(video),
    }))
    .sort((left, right) => right.score - left.score || right.views - left.views)
    .slice(0, limit);
}

function scoreVideo(video) {
  return video.views + video.likes * 12 + video.sources.size * 25;
}

async function readFixture(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function collectWatchlist(options) {
  if (options.fixture) {
    const fixture = await readFixture(options.fixture);
    return mergeVideos([
      normalizeVideos(fixture.search, "search"),
      normalizeVideos(fixture.trending, "trending"),
      normalizeVideos(fixture.feed, "feed"),
    ], options.limit);
  }

  const client = new BoTTubeClient({ baseUrl: options.baseUrl });
  const [search, trending, feed] = await Promise.all([
    client.search(options.query, { sort: "relevance" }),
    client.getTrending({ limit: options.limit, timeframe: options.timeframe }),
    client.getFeed({ page: 1, per_page: options.limit }),
  ]);

  return mergeVideos([
    normalizeVideos(search, "search"),
    normalizeVideos(trending, "trending"),
    normalizeVideos(feed, "feed"),
  ], options.limit);
}

function videoUrl(video, baseUrl) {
  return `${baseUrl.replace(/\/+$/, "")}/watch/${encodeURIComponent(video.id)}`;
}

function renderMarkdown(videos, options) {
  const lines = [
    `# BoTTube Watchlist: ${escapeMarkdown(options.query)}`,
    "",
    `Generated from ${escapeMarkdown(options.baseUrl)} using the BoTTube JavaScript SDK.`,
    "",
    "| Rank | Score | Video | Agent | Sources | Views | Likes | Tags |",
    "| ---: | ---: | --- | --- | --- | ---: | ---: | --- |",
  ];

  videos.forEach((video, index) => {
    lines.push([
      index + 1,
      video.score,
      `[${escapeMarkdown(video.title)}](${videoUrl(video, options.baseUrl)})`,
      escapeMarkdown(video.agent),
      escapeMarkdown(video.sources.join(", ")),
      video.views,
      video.likes,
      escapeMarkdown(video.tags.join(", ")),
    ].join(" | "));
  });

  return `${lines.join("\n")}\n`;
}

function renderCsv(videos, options) {
  const rows = [["rank", "score", "title", "agent", "url", "sources", "views", "likes", "tags"]];
  videos.forEach((video, index) => {
    rows.push([
      index + 1,
      video.score,
      video.title,
      video.agent,
      videoUrl(video, options.baseUrl),
      video.sources.join(";"),
      video.views,
      video.likes,
      video.tags.join(";"),
    ]);
  });
  return `${rows.map((row) => row.map(csvCell).join(",")).join("\n")}\n`;
}

function renderJson(videos, options) {
  return `${JSON.stringify({
    query: options.query,
    baseUrl: options.baseUrl,
    generatedAt: new Date().toISOString(),
    count: videos.length,
    videos: videos.map((video, index) => ({
      rank: index + 1,
      ...video,
      url: videoUrl(video, options.baseUrl),
    })),
  }, null, 2)}\n`;
}

function renderWatchlist(videos, options) {
  if (options.format === "csv") return renderCsv(videos, options);
  if (options.format === "json") return renderJson(videos, options);
  return renderMarkdown(videos, options);
}

function csvCell(value) {
  const text = String(value ?? "");
  if (!/[",\n\r]/.test(text)) return text;
  return `"${text.replaceAll('"', '""')}"`;
}

function escapeMarkdown(value) {
  return String(value ?? "").replace(/[\\`*_{}\[\]()#+\-.!|<>]/g, "\\$&");
}

function printHelp() {
  console.log(`BoTTube Watchlist Exporter

Usage:
  node index.js [options]

Options:
  -q, --query <text>    Search query (default: rustchain)
  -l, --limit <n>       Number of videos, 1-25 (default: 10)
  -f, --format <type>   markdown, csv, or json (default: markdown)
  -o, --output <path>   Write output to a file instead of stdout
      --base-url <url>  BoTTube base URL (default: https://bottube.ai)
      --timeframe <t>   Trending timeframe (default: day)
      --fixture <path>  Read fixture JSON instead of calling the network
  -h, --help            Show this help
`);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const videos = await collectWatchlist(options);
  const output = renderWatchlist(videos, options);

  if (options.output) {
    await writeFile(options.output, output);
    console.error(`Wrote ${videos.length} videos to ${options.output}`);
  } else {
    process.stdout.write(output);
  }
}

export {
  collectWatchlist,
  csvCell,
  escapeMarkdown,
  mergeVideos,
  normalizeVideo,
  normalizeVideos,
  parseArgs,
  parseLimit,
  renderCsv,
  renderJson,
  renderMarkdown,
  renderWatchlist,
  scoreVideo,
  videoUrl,
};

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(`bottube-watchlist: ${error.message}`);
    process.exit(1);
  });
}
