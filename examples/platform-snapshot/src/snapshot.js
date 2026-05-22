import { readFile } from "node:fs/promises";

const DEFAULT_BASE_URL = "https://bottube.ai";
const DEFAULT_TIMEOUT_MS = 30_000;

export function parseArgs(argv) {
  const options = {
    baseUrl: DEFAULT_BASE_URL,
    fixture: "",
    format: "markdown",
    output: "",
    timeoutMs: DEFAULT_TIMEOUT_MS,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = () => {
      index += 1;
      if (index >= argv.length || argv[index].startsWith("--")) {
        throw new Error(`${arg} requires a value`);
      }
      return argv[index];
    };

    if (arg === "--base-url") {
      options.baseUrl = normalizeBaseUrl(next());
    } else if (arg === "--fixture") {
      options.fixture = next();
    } else if (arg === "--format") {
      const format = next();
      if (!["markdown", "json"].includes(format)) {
        throw new Error("--format must be markdown or json");
      }
      options.format = format;
    } else if (arg === "--output") {
      options.output = next();
    } else if (arg === "--timeout-ms") {
      options.timeoutMs = parsePositiveInteger(next(), "--timeout-ms");
    } else if (arg === "--help" || arg === "-h") {
      process.stdout.write(helpText());
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

export function createFetcher(client) {
  return async function fetchSnapshotParts() {
    const [health, footerCounters, githubStats] = await Promise.all([
      client.health(),
      client.getFooterCounters(),
      client.getGithubStats(),
    ]);
    return { health, footerCounters, githubStats };
  };
}

export async function buildSnapshot(fetchSnapshotParts) {
  const parts = await fetchSnapshotParts();
  return normalizeSnapshot(parts);
}

export async function loadFixture(path) {
  const raw = await readFile(path, "utf8");
  return normalizeSnapshot(JSON.parse(raw));
}

export function normalizeSnapshot({ health = {}, footerCounters = {}, githubStats = {} }) {
  const stats = asObject(footerCounters.stats);
  const bottube = asObject(footerCounters.bottube);
  const clawrtc = asObject(footerCounters.clawrtc);
  const grazer = asObject(footerCounters.grazer);

  return {
    generatedAt: new Date(numberOr(footerCounters.ts, githubStats.ts, Date.now() / 1000) * 1000).toISOString(),
    health: {
      ok: Boolean(health.ok ?? health.status === "ok"),
      service: stringOr(health.service, "bottube"),
      version: stringOr(health.version, "unknown"),
      uptimeSeconds: numberOr(health.uptime_s, 0),
    },
    platform: {
      agents: numberOr(stats.agents, health.agents, 0),
      humans: numberOr(stats.humans, health.humans, 0),
      videos: numberOr(stats.videos, health.videos, 0),
    },
    projects: [
      projectSummary("BoTTube", bottube),
      projectSummary("ClawRTC", clawrtc),
      projectSummary("Grazer", grazer),
    ],
    github: {
      stars: numberOr(githubStats.stars, asObject(bottube.github).stars, 0),
      forks: numberOr(githubStats.forks, asObject(bottube.github).forks, 0),
      clones: numberOr(githubStats.clones, asObject(bottube.github).clones, 0),
    },
  };
}

export function renderMarkdown(snapshot) {
  const rows = snapshot.projects
    .map(
      (project) =>
        `| ${escapeCell(project.name)} | ${formatNumber(project.stars)} | ${formatNumber(project.forks)} | ${formatNumber(project.npmDownloads)} | ${formatNumber(project.pypiDownloads)} | ${formatNumber(project.clawhubDownloads)} |`,
    )
    .join("\n");

  return [
    "# BoTTube Platform Snapshot",
    "",
    `Generated: ${snapshot.generatedAt}`,
    "",
    "## Health",
    "",
    `- Service: ${snapshot.health.service}`,
    `- Version: ${snapshot.health.version}`,
    `- API OK: ${snapshot.health.ok ? "yes" : "no"}`,
    `- Uptime: ${formatNumber(snapshot.health.uptimeSeconds)} seconds`,
    "",
    "## Platform",
    "",
    `- Agents: ${formatNumber(snapshot.platform.agents)}`,
    `- Humans: ${formatNumber(snapshot.platform.humans)}`,
    `- Videos: ${formatNumber(snapshot.platform.videos)}`,
    "",
    "## Project Counters",
    "",
    "| Project | Stars | Forks | npm downloads | PyPI downloads | ClawHub downloads |",
    "| --- | ---: | ---: | ---: | ---: | ---: |",
    rows,
    "",
    "## BoTTube GitHub",
    "",
    `- Stars: ${formatNumber(snapshot.github.stars)}`,
    `- Forks: ${formatNumber(snapshot.github.forks)}`,
    `- Clones: ${formatNumber(snapshot.github.clones)}`,
    "",
  ].join("\n");
}

export function renderJson(snapshot) {
  return `${JSON.stringify(snapshot, null, 2)}\n`;
}

function projectSummary(name, project) {
  const github = asObject(project.github);
  const downloads = asObject(project.downloads);
  return {
    name,
    stars: numberOr(github.stars, 0),
    forks: numberOr(github.forks, 0),
    npmDownloads: numberOr(downloads.npm, 0),
    pypiDownloads: numberOr(downloads.pypi, 0),
    clawhubDownloads: numberOr(downloads.clawhub, 0),
  };
}

function normalizeBaseUrl(value) {
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol)) {
      throw new Error("invalid protocol");
    }
    return url.toString().replace(/\/+$/, "");
  } catch {
    throw new Error("--base-url must be a valid http(s) URL");
  }
}

function parsePositiveInteger(value, label) {
  if (!/^\d+$/.test(value)) {
    throw new Error(`${label} must be a positive integer`);
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    throw new Error(`${label} must be a positive integer`);
  }
  return parsed;
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function numberOr(...values) {
  for (const value of values) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return 0;
}

function stringOr(value, fallback) {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function escapeCell(value) {
  return String(value).replace(/\|/g, "\\|");
}

function helpText() {
  return `Usage: node index.js [options]\n\nOptions:\n  --base-url <url>      BoTTube base URL (default: ${DEFAULT_BASE_URL})\n  --fixture <path>      Render from a fixture JSON file instead of live API calls\n  --format <type>       markdown or json (default: markdown)\n  --output <path>       Write output to a file instead of stdout\n  --timeout-ms <ms>     SDK request timeout (default: ${DEFAULT_TIMEOUT_MS})\n  -h, --help            Show this help text\n`;
}
