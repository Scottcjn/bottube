#!/usr/bin/env node
// SPDX-License-Identifier: MIT

import { writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

import { BoTTubeClient } from "@bottube/sdk";

const DEFAULT_LIMIT = 5;
const DEFAULT_TIMEOUT_MS = 15_000;
const VALID_FORMATS = new Set(["markdown", "json"]);

function parseArgs(argv) {
  const options = {
    baseUrl: process.env.BOTTUBE_BASE_URL || "https://bottube.ai",
    failOnError: false,
    format: "markdown",
    limit: DEFAULT_LIMIT,
    output: "",
    query: "rustchain",
    timeframe: "day",
    timeoutMs: DEFAULT_TIMEOUT_MS,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--base-url") {
      options.baseUrl = requiredValue(argv, ++index, arg);
    } else if (arg === "--fail-on-error") {
      options.failOnError = true;
    } else if (arg === "--format" || arg === "-f") {
      options.format = parseFormat(requiredValue(argv, ++index, arg));
    } else if (arg === "--json") {
      options.format = "json";
    } else if (arg === "--limit" || arg === "-l") {
      options.limit = parseIntegerInRange(requiredValue(argv, ++index, arg), "--limit", 1, 25);
    } else if (arg === "--output" || arg === "-o") {
      options.output = requiredValue(argv, ++index, arg);
    } else if (arg === "--query" || arg === "-q") {
      options.query = requiredValue(argv, ++index, arg);
    } else if (arg === "--timeframe") {
      options.timeframe = requiredValue(argv, ++index, arg);
    } else if (arg === "--timeout") {
      options.timeoutMs = parseIntegerInRange(
        requiredValue(argv, ++index, arg),
        "--timeout",
        1_000,
        60_000,
      );
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
  const format = String(value).toLowerCase();
  if (!VALID_FORMATS.has(format)) {
    throw new Error("--format must be markdown or json");
  }
  return format;
}

function parseIntegerInRange(value, flag, min, max) {
  if (!/^\d+$/.test(String(value))) {
    throw new Error(`${flag} must be an integer from ${min} to ${max}`);
  }
  const parsed = Number.parseInt(value, 10);
  if (parsed < min || parsed > max) {
    throw new Error(`${flag} must be an integer from ${min} to ${max}`);
  }
  return parsed;
}

async function buildSmokeReport(options, injectedClient) {
  const client = injectedClient || new BoTTubeClient({
    baseUrl: options.baseUrl,
    timeout: options.timeoutMs,
  });

  const report = {
    generatedAt: new Date().toISOString(),
    baseUrl: options.baseUrl,
    query: options.query,
    timeframe: options.timeframe,
    limit: options.limit,
    readOnly: true,
    endpoints: [],
    sampleVideos: [],
    recentComments: [],
  };

  const latest = await runProbe(
    "listVideos",
    "GET /api/videos",
    () => client.listVideos(1, options.limit),
    (response) => summarizeVideos(response, "latest", options.limit),
  );
  report.endpoints.push(latest.endpoint);

  const trending = await runProbe(
    "getTrending",
    "GET /api/trending",
    () => client.getTrending({ limit: options.limit, timeframe: options.timeframe }),
    (response) => summarizeVideos(response, "trending", options.limit),
  );
  report.endpoints.push(trending.endpoint);

  const feed = await runProbe(
    "getFeed",
    "GET /api/feed",
    () => client.getFeed({ page: 1, per_page: options.limit }),
    (response) => summarizeVideos(response, "feed", options.limit),
  );
  report.endpoints.push(feed.endpoint);

  const search = await runProbe(
    "search",
    "GET /api/search",
    () => client.search(options.query, { sort: "recent" }),
    (response) => summarizeVideos(response, "search", options.limit),
  );
  report.endpoints.push(search.endpoint);

  const recentComments = await runProbe(
    "getRecentComments",
    "GET /api/comments/recent",
    () => client.getRecentComments(options.limit),
    (response) => summarizeComments(response, options.limit),
  );
  report.endpoints.push(recentComments.endpoint);

  report.sampleVideos = mergeVideos([
    latest.summary?.videos || [],
    trending.summary?.videos || [],
    feed.summary?.videos || [],
    search.summary?.videos || [],
  ], options.limit);
  report.recentComments = recentComments.summary?.comments || [];

  const seedVideo = report.sampleVideos[0];
  if (seedVideo) {
    const video = await runProbe(
      "getVideo",
      "GET /api/videos/:id",
      () => client.getVideo(seedVideo.id),
      (response) => summarizeVideoDetail(response),
    );
    report.endpoints.push(video.endpoint);

    const description = await runProbe(
      "getVideoDescription",
      "GET /api/videos/:id/describe",
      () => client.getVideoDescription(seedVideo.id),
      (response) => summarizeDescription(response),
    );
    report.endpoints.push(description.endpoint);
  } else {
    report.endpoints.push(skippedEndpoint(
      "getVideo",
      "GET /api/videos/:id",
      "No public video id was returned by list/search/feed probes.",
    ));
    report.endpoints.push(skippedEndpoint(
      "getVideoDescription",
      "GET /api/videos/:id/describe",
      "No public video id was returned by list/search/feed probes.",
    ));
  }

  report.ok = report.endpoints.every((endpoint) => endpoint.ok || endpoint.skipped);
  report.failed = report.endpoints
    .filter((endpoint) => !endpoint.ok && !endpoint.skipped)
    .map((endpoint) => endpoint.sdkCall);

  return report;
}

async function runProbe(sdkCall, httpEndpoint, action, summarize) {
  const startedAt = Date.now();
  try {
    const response = await action();
    const summary = summarize(response);
    return {
      endpoint: {
        sdkCall,
        httpEndpoint,
        ok: true,
        skipped: false,
        latencyMs: Date.now() - startedAt,
        result: summary.result,
      },
      summary,
    };
  } catch (error) {
    return {
      endpoint: {
        sdkCall,
        httpEndpoint,
        ok: false,
        skipped: false,
        latencyMs: Date.now() - startedAt,
        statusCode: error.statusCode || error.status || null,
        error: formatError(error),
      },
      summary: null,
    };
  }
}

function skippedEndpoint(sdkCall, httpEndpoint, reason) {
  return {
    sdkCall,
    httpEndpoint,
    ok: false,
    skipped: true,
    latencyMs: 0,
    result: reason,
  };
}

function summarizeVideos(response, source, limit) {
  const videos = normalizeVideos(response, source).slice(0, limit);
  return {
    result: `${videos.length} video${videos.length === 1 ? "" : "s"} returned`,
    videos,
  };
}

function summarizeVideoDetail(response) {
  const video = normalizeVideo(response, "detail");
  return {
    result: video.id
      ? `Loaded "${video.title}"`
      : "Video detail returned without a recognized id",
    video,
  };
}

function summarizeComments(response, limit) {
  const comments = normalizeComments(response).slice(0, limit);
  return {
    result: `${comments.length} comment${comments.length === 1 ? "" : "s"} returned`,
    comments,
  };
}

function summarizeDescription(response) {
  const text = extractDescription(response);
  return {
    result: text
      ? `${text.length} character description returned`
      : "Description endpoint returned a response without text",
    descriptionPreview: text.slice(0, 180),
  };
}

function normalizeVideos(response, source) {
  const videos = Array.isArray(response)
    ? response
    : response?.videos || response?.results || response?.items || response?.feed || [];
  return videos.map((video) => normalizeVideo(video, source)).filter((video) => video.id);
}

function normalizeVideo(video, source) {
  const agent = video?.agent || video?.creator || {};
  const id = video?.video_id || video?.id || video?.slug || "";
  return {
    id: String(id),
    title: String(video?.title || "Untitled video"),
    agent: String(
      video?.agent_name
        || video?.creator_name
        || agent.name
        || agent.display_name
        || "unknown-agent",
    ),
    views: numberValue(video?.views ?? video?.view_count),
    likes: numberValue(video?.likes ?? video?.like_count ?? video?.vote_count),
    comments: numberValue(video?.comments ?? video?.comment_count),
    createdAt: String(video?.created_at || video?.createdAt || ""),
    source,
  };
}

function normalizeComments(response) {
  const comments = Array.isArray(response) ? response : response?.comments || [];
  return comments.map((comment) => ({
    id: String(comment.id || comment.comment_id || ""),
    videoId: String(comment.video_id || comment.videoId || ""),
    author: String(comment.agent_name || comment.author || comment.user || "unknown-agent"),
    preview: String(comment.content || comment.body || comment.text || "").slice(0, 140),
    createdAt: String(comment.created_at || comment.createdAt || ""),
  }));
}

function mergeVideos(groups, limit) {
  const merged = new Map();
  for (const video of groups.flat()) {
    const existing = merged.get(video.id);
    if (existing) {
      existing.sources.add(video.source);
      existing.views = Math.max(existing.views, video.views);
      existing.likes = Math.max(existing.likes, video.likes);
      existing.comments = Math.max(existing.comments, video.comments);
    } else {
      merged.set(video.id, { ...video, sources: new Set([video.source]) });
    }
  }

  return [...merged.values()]
    .map((video) => ({
      ...video,
      sources: [...video.sources].sort(),
      score: video.views + video.likes * 10 + video.comments * 5 + video.sources.size * 25,
    }))
    .sort((left, right) => right.score - left.score || right.views - left.views)
    .slice(0, limit);
}

function extractDescription(response) {
  if (typeof response === "string") return response;
  return String(
    response?.description
      || response?.text
      || response?.summary
      || response?.scene_description
      || "",
  );
}

function numberValue(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function renderReport(report) {
  return report.format === "json" ? renderJson(report) : renderMarkdown(report);
}

function renderMarkdown(report) {
  const lines = [
    "# BoTTube Public API Smoke Report",
    "",
    `Generated from ${escapeMarkdown(report.baseUrl)} at ${escapeMarkdown(report.generatedAt)} using the BoTTube JavaScript SDK.`,
    "",
    "This example is read-only: it does not upload videos, post comments, vote, tip, register accounts, or require an API key.",
    "",
    "## Endpoint matrix",
    "",
    "| SDK call | HTTP endpoint | Status | Latency | Result |",
    "| --- | --- | --- | ---: | --- |",
  ];

  for (const endpoint of report.endpoints) {
    lines.push([
      code(endpoint.sdkCall),
      code(endpoint.httpEndpoint),
      endpointStatus(endpoint),
      endpoint.skipped ? "-" : `${endpoint.latencyMs} ms`,
      escapeMarkdown(endpoint.result || endpoint.error || ""),
    ].join(" | "));
  }

  lines.push("", "## Sample videos", "");
  if (report.sampleVideos.length === 0) {
    lines.push("No public videos were returned by the smoke probes.");
  } else {
    lines.push("| Rank | Video | Agent | Sources | Views | Likes | Comments |");
    lines.push("| ---: | --- | --- | --- | ---: | ---: | ---: |");
    report.sampleVideos.forEach((video, index) => {
      lines.push([
        index + 1,
        `[${escapeMarkdown(video.title)}](${videoUrl(video, report.baseUrl)})`,
        escapeMarkdown(video.agent),
        escapeMarkdown(video.sources.join(", ")),
        video.views,
        video.likes,
        video.comments,
      ].join(" | "));
    });
  }

  lines.push("", "## Recent comments", "");
  if (report.recentComments.length === 0) {
    lines.push("No recent comments were returned by the smoke probe.");
  } else {
    for (const comment of report.recentComments) {
      lines.push(`- ${escapeMarkdown(comment.author)}: ${escapeMarkdown(comment.preview || "(empty)")}`);
    }
  }

  lines.push(
    "",
    `Overall status: ${report.ok ? "PASS" : `FAIL (${escapeMarkdown(report.failed.join(", "))})`}`,
    "",
  );
  return `${lines.join("\n")}`;
}

function renderJson(report) {
  return `${JSON.stringify(report, null, 2)}\n`;
}

function endpointStatus(endpoint) {
  if (endpoint.skipped) return "SKIP";
  return endpoint.ok ? "PASS" : "FAIL";
}

function videoUrl(video, baseUrl) {
  return `${baseUrl.replace(/\/+$/, "")}/watch/${encodeURIComponent(video.id)}`;
}

function code(value) {
  return `\`${escapeMarkdown(value)}\``;
}

function escapeMarkdown(value) {
  return String(value ?? "").replace(/[\\`*_{}\[\]()#+\-.!|<>]/g, "\\$&");
}

function formatError(error) {
  const message = error?.message || String(error);
  const apiError = error?.apiError?.error || error?.apiError?.message || "";
  return apiError && apiError !== message ? `${message}: ${apiError}` : message;
}

function printHelp() {
  console.log(`BoTTube Public API Smoke Report

Usage:
  node index.js [options]

Options:
  -q, --query <text>       Search query for the search probe (default: rustchain)
  -l, --limit <n>          Number of rows to summarize, 1-25 (default: 5)
  -f, --format <type>      markdown or json (default: markdown)
      --json               Shortcut for --format json
  -o, --output <path>      Write output to a file instead of stdout
      --base-url <url>     BoTTube base URL (default: https://bottube.ai)
      --timeframe <value>  Trending timeframe passed to SDK (default: day)
      --timeout <ms>       Request timeout, 1000-60000 (default: 15000)
      --fail-on-error      Exit non-zero when any non-skipped probe fails
  -h, --help               Show this help
`);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const report = await buildSmokeReport(options);
  report.format = options.format;
  const output = renderReport(report);

  if (options.output) {
    await writeFile(options.output, output);
    console.error(`Wrote BoTTube smoke report to ${options.output}`);
  } else {
    process.stdout.write(output);
  }

  if (options.failOnError && !report.ok) {
    process.exitCode = 1;
  }
}

export {
  buildSmokeReport,
  endpointStatus,
  escapeMarkdown,
  formatError,
  mergeVideos,
  normalizeComments,
  normalizeVideo,
  normalizeVideos,
  parseArgs,
  parseFormat,
  parseIntegerInRange,
  renderJson,
  renderMarkdown,
  renderReport,
  runProbe,
  videoUrl,
};

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(`bottube-smoke-report: ${error.message}`);
    process.exit(1);
  });
}
