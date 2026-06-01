import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  buildTipLedgerReport,
  escapeMarkdown,
  normalizeTipRow,
  parseArgs,
  renderMarkdown,
  rowsFromResponse,
} from './index.js';

const exampleRoot = dirname(fileURLToPath(new URL('./index.js', import.meta.url)));

test('parseArgs accepts output controls', () => {
  assert.deepEqual(parseArgs(['--base-url', 'https://example.test/', '--limit', '3', '--format', 'json', '--out', '/tmp/tips.json']), {
    baseUrl: 'https://example.test/',
    limit: 3,
    format: 'json',
    fixture: '',
    out: '/tmp/tips.json',
    help: false,
  });
});

test('parseArgs rejects malformed limit and format values', () => {
  assert.throws(() => parseArgs(['--limit', '2abc']), /--limit must be an integer/);
  assert.throws(() => parseArgs(['--format', 'csv']), /--format must be/);
});

test('rowsFromResponse accepts common leaderboard shapes', () => {
  assert.deepEqual(rowsFromResponse([{ agent_name: 'a' }]), [{ agent_name: 'a' }]);
  assert.deepEqual(rowsFromResponse({ leaderboard: [{ agent_name: 'b' }] }), [{ agent_name: 'b' }]);
  assert.deepEqual(rowsFromResponse({ items: [{ agent_name: 'c' }] }), [{ agent_name: 'c' }]);
});

test('normalizeTipRow keeps received and sent totals separate', () => {
  assert.deepEqual(
    normalizeTipRow({ agent_name: 'alice\nagent', display_name: 'Alice\tA', tip_count: '4', total_received: '1.25', is_human: true }, 'received'),
    {
      agent: 'alice agent',
      displayName: 'Alice A',
      direction: 'received',
      tipCount: 4,
      totalRtc: 1.25,
      isHuman: true,
    },
  );

  assert.equal(normalizeTipRow({ agent_name: 'bob', total_sent: '2.5' }, 'sent').totalRtc, 2.5);
});

test('buildTipLedgerReport uses SDK tip methods and sorts by RTC total', async () => {
  const calls = [];
  const client = {
    async getTipsLeaderboard() {
      calls.push('received');
      return {
        leaderboard: [
          { agent_name: 'small', total_received: 0.2, tip_count: 4 },
          { agent_name: 'large', total_received: 1.5, tip_count: 2 },
        ],
      };
    },
    async getTippers() {
      calls.push('sent');
      return {
        leaderboard: [
          { agent_name: 'sender', total_sent: 0.8, tip_count: 1 },
        ],
      };
    },
  };

  const report = await buildTipLedgerReport({
    client,
    options: { baseUrl: 'https://bottube.ai', limit: 5 },
  });

  assert.deepEqual(calls.sort(), ['received', 'sent']);
  assert.equal(report.recipients[0].agent, 'large');
  assert.equal(report.totals.receivedRtc, 1.7);
  assert.equal(report.totals.sentRtc, 0.8);
});

test('buildTipLedgerReport can use fixture data without calling SDK', async () => {
  const client = {
    async getTipsLeaderboard() {
      throw new Error('should not call live received endpoint');
    },
    async getTippers() {
      throw new Error('should not call live sent endpoint');
    },
  };

  const report = await buildTipLedgerReport({
    client,
    options: { baseUrl: 'https://fixture.test', limit: 1 },
    fixtureData: {
      received: { leaderboard: [{ agent_name: 'fixture-recipient', total_received: 9, tip_count: 3 }] },
      sent: { leaderboard: [{ agent_name: 'fixture-sender', total_sent: 5, tip_count: 2 }] },
    },
  });

  assert.equal(report.recipients.length, 1);
  assert.equal(report.recipients[0].agent, 'fixture-recipient');
  assert.equal(report.senders[0].agent, 'fixture-sender');
});

test('renderMarkdown escapes table-breaking text', () => {
  const markdown = renderMarkdown({
    generatedAt: '2026-06-02T00:00:00.000Z',
    baseUrl: 'https://bottube.ai',
    limit: 1,
    recipients: [
      { agent: 'alice|agent', displayName: 'Alice <A>', tipCount: 2, totalRtc: 1.2, isHuman: false },
    ],
    senders: [],
    totals: { recipientRows: 1, senderRows: 0, receivedRtc: 1.2, sentRtc: 0 },
  });

  assert.match(markdown, /Tip Ledger/);
  assert.ok(markdown.includes('alice\\|agent'));
  assert.ok(markdown.includes('Alice \\<A\\>'));
});

test('escapeMarkdown normalizes newlines', () => {
  assert.equal(escapeMarkdown('a\nb|c'), 'a b\\|c');
});

test('CLI help exits successfully', () => {
  const result = spawnSync(process.execPath, [join(exampleRoot, 'index.js'), '--help'], {
    encoding: 'utf8',
  });

  assert.equal(result.status, 0);
  assert.match(result.stdout, /BoTTube Tip Ledger Reporter/);
});
