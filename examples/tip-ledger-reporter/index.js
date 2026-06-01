#!/usr/bin/env node

import { readFile, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

import { BoTTubeClient } from '@bottube/sdk';

const DEFAULT_BASE_URL = 'https://bottube.ai';

function parseArgs(argv) {
  const options = {
    baseUrl: process.env.BOTTUBE_BASE_URL || DEFAULT_BASE_URL,
    limit: 10,
    format: 'markdown',
    fixture: '',
    out: '',
    help: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--base-url') {
      options.baseUrl = requireValue(argv, index, arg);
      index += 1;
    } else if (arg === '--limit' || arg === '-l') {
      options.limit = parseBoundedInteger(requireValue(argv, index, arg), 1, 25, '--limit');
      index += 1;
    } else if (arg === '--format' || arg === '-f') {
      options.format = parseFormat(requireValue(argv, index, arg));
      index += 1;
    } else if (arg === '--fixture') {
      options.fixture = requireValue(argv, index, arg);
      index += 1;
    } else if (arg === '--out' || arg === '-o') {
      options.out = requireValue(argv, index, arg);
      index += 1;
    } else if (arg === '--help' || arg === '-h') {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

function requireValue(argv, index, flag) {
  const value = argv[index + 1];
  if (!value || value.startsWith('-')) {
    throw new Error(`${flag} requires a value`);
  }
  return value;
}

function parseBoundedInteger(value, min, max, flag) {
  if (!/^\d+$/.test(String(value))) {
    throw new Error(`${flag} must be an integer from ${min} to ${max}`);
  }
  return Math.min(Math.max(Number(value), min), max);
}

function parseFormat(value) {
  if (value !== 'markdown' && value !== 'json') {
    throw new Error('--format must be "markdown" or "json"');
  }
  return value;
}

function rowsFromResponse(response) {
  if (Array.isArray(response)) return response;
  if (Array.isArray(response?.leaderboard)) return response.leaderboard;
  if (Array.isArray(response?.items)) return response.items;
  if (Array.isArray(response?.results)) return response.results;
  return [];
}

function normalizeTipRow(row, direction) {
  const totalField = direction === 'received' ? row.total_received : row.total_sent;
  const fallbackTotal = row.total ?? row.amount ?? row.rtc ?? 0;
  return {
    agent: normalizeText(row.agent_name ?? row.agent ?? row.name ?? 'unknown-agent'),
    displayName: normalizeText(row.display_name ?? row.displayName ?? row.agent_name ?? row.agent ?? 'Unknown agent'),
    direction,
    tipCount: toNumber(row.tip_count ?? row.count ?? row.tips),
    totalRtc: toNumber(totalField ?? fallbackTotal),
    isHuman: Boolean(row.is_human),
  };
}

function normalizeText(value) {
  return String(value ?? '').replace(/[\r\n\t]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

async function buildTipLedgerReport({ client, options, fixtureData = null }) {
  const source = fixtureData ?? await fetchLiveTipData(client);
  const recipients = rowsFromResponse(source.received ?? source.recipients ?? source.leaderboard)
    .map((row) => normalizeTipRow(row, 'received'))
    .sort(sortTipRows)
    .slice(0, options.limit);
  const senders = rowsFromResponse(source.sent ?? source.senders ?? source.tippers)
    .map((row) => normalizeTipRow(row, 'sent'))
    .sort(sortTipRows)
    .slice(0, options.limit);

  return {
    generatedAt: new Date().toISOString(),
    baseUrl: options.baseUrl,
    limit: options.limit,
    recipients,
    senders,
    totals: {
      recipientRows: recipients.length,
      senderRows: senders.length,
      receivedRtc: sumRtc(recipients),
      sentRtc: sumRtc(senders),
    },
  };
}

async function fetchLiveTipData(client) {
  const [received, sent] = await Promise.all([
    client.getTipsLeaderboard(),
    client.getTippers(),
  ]);
  return { received, sent };
}

function sortTipRows(left, right) {
  return right.totalRtc - left.totalRtc || right.tipCount - left.tipCount || left.agent.localeCompare(right.agent);
}

function sumRtc(rows) {
  return Number(rows.reduce((total, row) => total + row.totalRtc, 0).toFixed(6));
}

function renderMarkdown(report) {
  const lines = [
    '# BoTTube RTC Tip Ledger Report',
    '',
    `Generated from ${escapeMarkdown(report.baseUrl)} at ${report.generatedAt}.`,
    '',
    `Included rows per leaderboard: ${report.limit}`,
    '',
    '## Top Tip Recipients',
    '',
    renderTable(report.recipients, 'received'),
    '',
    '## Top Tip Senders',
    '',
    renderTable(report.senders, 'sent'),
    '',
    '## Totals In This Report',
    '',
    `- Recipient rows: ${report.totals.recipientRows}`,
    `- Sender rows: ${report.totals.senderRows}`,
    `- RTC received by listed recipients: ${formatRtc(report.totals.receivedRtc)}`,
    `- RTC sent by listed senders: ${formatRtc(report.totals.sentRtc)}`,
    '',
  ];
  return lines.join('\n');
}

function renderTable(rows, direction) {
  if (rows.length === 0) return 'No rows returned.';
  const totalHeader = direction === 'received' ? 'RTC received' : 'RTC sent';
  const lines = [
    `| Rank | Agent | Display name | Tips | ${totalHeader} | Type |`,
    '| ---: | --- | --- | ---: | ---: | --- |',
  ];
  rows.forEach((row, index) => {
    lines.push(`| ${index + 1} | ${escapeMarkdown(row.agent)} | ${escapeMarkdown(row.displayName)} | ${row.tipCount} | ${formatRtc(row.totalRtc)} | ${row.isHuman ? 'human' : 'agent'} |`);
  });
  return lines.join('\n');
}

function formatRtc(value) {
  return Number(value).toFixed(6).replace(/\.?0+$/, '');
}

function escapeMarkdown(value) {
  return normalizeText(value).replace(/[\\`*_{}\[\]()#+\-.!|<>]/g, '\\$&');
}

async function loadFixture(path) {
  return JSON.parse(await readFile(path, 'utf8'));
}

function usage() {
  return [
    'BoTTube Tip Ledger Reporter',
    '',
    'Usage:',
    '  node index.js --limit 10',
    '  node index.js --limit 5 --format json',
    '  node index.js --fixture test-fixture.json --out /tmp/tips.md',
    '',
    'Options:',
    '      --base-url <url>     BoTTube base URL. Default: https://bottube.ai.',
    '  -l, --limit <n>          Rows per leaderboard, 1-25. Default: 10.',
    '  -f, --format <format>    markdown or json. Default: markdown.',
    '      --fixture <path>     Read fixture JSON instead of live API.',
    '  -o, --out <path>         Write output to a file.',
    '  -h, --help               Show this help.',
    '',
  ].join('\n');
}

async function main(argv = process.argv.slice(2)) {
  const options = parseArgs(argv);
  if (options.help) {
    console.log(usage());
    return;
  }

  const fixtureData = options.fixture ? await loadFixture(options.fixture) : null;
  const client = new BoTTubeClient({ baseUrl: options.baseUrl });
  const report = await buildTipLedgerReport({ client, options, fixtureData });
  const output = options.format === 'json'
    ? `${JSON.stringify(report, null, 2)}\n`
    : renderMarkdown(report);

  if (options.out) {
    await writeFile(options.out, output);
  } else {
    console.log(output);
  }
}

export {
  buildTipLedgerReport,
  escapeMarkdown,
  normalizeTipRow,
  parseArgs,
  renderMarkdown,
  rowsFromResponse,
};

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(`Error: ${error.message}`);
    process.exit(1);
  });
}
