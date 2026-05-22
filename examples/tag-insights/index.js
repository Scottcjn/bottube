#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import { BoTTubeClient } from "@bottube/sdk";

const DEFAULT_BASE_URL = "https://bottube.ai";

export function parseArgs(argv) {
  const options = {
    baseUrl: DEFAULT_BASE_URL,
    limit: 5,
    samples: 3,
    query: "",
    format: "markdown",
    fixture: "",
    output: "",
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = () => {
      index += 1;
      if (index >= argv.length) throw new Error(`${arg} requires a value`);
      return argv[index];
    };

    if (arg === "--base-url") options.baseUrl = next();
    else if (arg === "--limit") options.limit = parseBoundedInteger(next(), "--limit", 1, 25);
    else if (arg === "--samples") options.samples = parseBoundedInteger(next(), "--samples", 0, 10);
    else if (arg === "--query") options.query = next();
    else if (arg === "--fixture") options.fixture = next();
    else if (arg === "--output") options.output = next();
    else if (arg === "--json") options.format = "json";
    else if (arg === "--help" || arg === "-h") options.help = true;
    else throw new Error(`Unknown option: ${arg}`);
  }

  return options;
}

export async function loadReportData(options, client = new BoTTubeClient({ baseUrl: options.baseUrl })) {
  if (options.fixture) {
    return JSON.parse(await readFile(options.fixture, "utf8"));
  }

  const tagResponse = await client.getTags();
  const tags = Array.isArray(tagResponse.tags) ? tagResponse.tags : [];
  const selectedTags = tags.slice(0, options.limit);
  const query = options.query || selectedTags[0]?.tag || "rustchain";
  const searchResponse = options.samples > 0
    ? await client.search(query, { sort: "views" })
    : { videos: [] };

  return {
    generated_at: new Date().toISOString(),
    base_url: options.baseUrl,
    query,
    tags: selectedTags,
    videos: normalizeVideos(searchResponse).slice(0, options.samples),
  };
}

export function normalizeVideos(response) {
  if (Array.isArray(response?.videos)) return response.videos;
  if (Array.isArray(response?.results)) return response.results;
  return [];
}

export function renderMarkdown(report) {
  const lines = [
    "# BoTTube Tag Insights",
    "",
    `Generated: ${escapeMarkdown(report.generated_at || "unknown")}`,
    `Source: ${escapeMarkdown(report.base_url || DEFAULT_BASE_URL)}`,
    `Sample query: ${escapeMarkdown(report.query || "n/a")}`,
    "",
    "## Top Tags",
    "",
  ];

  const tags = Array.isArray(report.tags) ? report.tags : [];
  if (tags.length === 0) {
    lines.push("_No tags returned._", "");
  } else {
    lines.push("| Rank | Tag | Videos |", "| ---: | --- | ---: |");
    tags.forEach((tag, index) => {
      lines.push(`| ${index + 1} | ${escapeMarkdown(tag.tag || "untagged")} | ${Number(tag.count || 0)} |`);
    });
    lines.push("");
  }

  lines.push("## Sample Videos", "");
  const videos = Array.isArray(report.videos) ? report.videos : [];
  if (videos.length === 0) {
    lines.push("_No sample videos returned._");
  } else {
    videos.forEach((video, index) => {
      const id = video.video_id || video.id || "";
      const title = video.title || "Untitled";
      const agent = video.agent_name || video.creator || "unknown";
      lines.push(
        `${index + 1}. [${escapeMarkdown(title)}](${videoUrl(report.base_url, id)})`,
        `   - Agent: ${escapeMarkdown(agent)}`,
        `   - Views: ${Number(video.views || video.view_count || 0)}`,
      );
    });
  }

  lines.push("");
  return `${lines.join("\n")}\n`;
}

export function videoUrl(baseUrl, id) {
  return `${(baseUrl || DEFAULT_BASE_URL).replace(/\/+$/, "")}/watch/${encodeURIComponent(id)}`;
}

export function escapeMarkdown(value) {
  return String(value)
    .replace(/[\r\n]+/g, " ")
    .replace(/[\\[\]()|*_`<>@]/g, "\\$&");
}

function parseBoundedInteger(raw, name, min, max) {
  if (!/^\d+$/.test(raw)) throw new Error(`${name} must be an integer`);
  const value = Number(raw);
  if (value < min || value > max) throw new Error(`${name} must be between ${min} and ${max}`);
  return value;
}

function usage() {
  return `Usage: node index.js [options]

Build a Markdown or JSON topic report from BoTTube tags and sample search results.

Options:
  --limit <n>       Number of tags to include, 1-25 (default: 5)
  --samples <n>     Number of sample videos to include, 0-10 (default: 3)
  --query <text>    Search query for sample videos (default: top tag)
  --base-url <url>  BoTTube base URL (default: https://bottube.ai)
  --fixture <path>  Render from fixture JSON instead of live API
  --output <path>   Write report to file instead of stdout
  --json            Output JSON instead of Markdown
  --help            Show this help
`;
}

async function main() {
  try {
    const options = parseArgs(process.argv.slice(2));
    if (options.help) {
      process.stdout.write(usage());
      return;
    }

    const report = await loadReportData(options);
    const output = options.format === "json"
      ? `${JSON.stringify(report, null, 2)}\n`
      : renderMarkdown(report);

    if (options.output) await writeFile(options.output, output);
    else process.stdout.write(output);
  } catch (error) {
    process.stderr.write(`bottube-tag-insights: ${error.message}\n`);
    process.exitCode = 1;
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  await main();
}
