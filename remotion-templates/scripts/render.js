#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 2) {
    const k = argv[i]?.replace(/^--/, '');
    const v = argv[i + 1];
    out[k] = v;
  }
  return out;
}

const args = parseArgs(process.argv);
if (!args.template || !args.data || !args.output) {
  console.error('Usage: node scripts/render.js --template news --data input.json --output out.mp4 [--resolution 1920x1080]');
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(args.data, 'utf8'));
const resolution = args.resolution || data.resolution || '1920x1080';

const cmd = [
  'npx', 'remotion', 'render',
  `src/templates/${args.template}.tsx`,
  args.output,
  '--props', JSON.stringify(data),
  '--codec', 'h264',
  '--pixel-format', 'yuv420p'
].join(' ');

console.log('[render-command]', cmd);
console.log('[note] run this command in an environment with remotion installed');
console.log('[resolution]', resolution);
