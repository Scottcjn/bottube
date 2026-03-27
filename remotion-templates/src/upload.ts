/**
 * upload.ts — BoTTube API upload integration
 *
 * Usage:
 *   ts-node src/upload.ts --video out/news_bottube.mp4 \
 *     --title "Breaking News" --tags "news,ai" \
 *     --api-key bottube_sk_xxxx
 *
 * Environment variables (alternative to CLI flags):
 *   BOTTUBE_API_KEY   — agent API key
 *   BOTTUBE_API_URL   — API base URL (default: https://bottube.ai)
 *
 * Options:
 *   --video <path>       Path to video file (required)
 *   --title <str>        Video title (required)
 *   --description <str>  Video description
 *   --tags <csv>         Comma-separated tags
 *   --api-key <key>      BoTTube API key (or BOTTUBE_API_KEY env)
 *   --api-url <url>      API base URL (or BOTTUBE_API_URL env)
 *   --dry-run            Validate file, skip upload
 */

import fs from 'fs';
import path from 'path';
import https from 'https';
import http from 'http';

const MAX_DURATION_SEC = 8;
const BOTTUBE_API_URL = process.env.BOTTUBE_API_URL ?? 'https://bottube.ai';

interface UploadOptions {
  videoPath: string;
  title: string;
  description?: string;
  tags?: string;
  apiKey: string;
  apiUrl: string;
  dryRun: boolean;
}

interface UploadResult {
  success: boolean;
  videoId?: string;
  url?: string;
  error?: string;
}

function parseArgs(argv: string[]): Record<string, string> {
  const args: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) {
      const key = argv[i].slice(2);
      args[key] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : 'true';
    }
  }
  return args;
}

async function getFileSizeMb(filePath: string): Promise<number> {
  const stat = fs.statSync(filePath);
  return stat.size / (1024 * 1024);
}

/**
 * Upload video to BoTTube using multipart/form-data.
 * Uses Node.js built-ins only (no form-data package needed at runtime).
 */
async function uploadVideo(opts: UploadOptions): Promise<UploadResult> {
  if (!fs.existsSync(opts.videoPath)) {
    return { success: false, error: `File not found: ${opts.videoPath}` };
  }

  const fileSizeMb = await getFileSizeMb(opts.videoPath);
  console.log(`📦 File: ${opts.videoPath} (${fileSizeMb.toFixed(2)} MB)`);

  if (fileSizeMb > 500) {
    return { success: false, error: `File too large: ${fileSizeMb.toFixed(1)} MB (max 500 MB upload, 2 MB after transcoding)` };
  }

  if (opts.dryRun) {
    console.log('✅ Dry-run: file validation passed. Skipping upload.');
    return { success: true };
  }

  const boundary = `----BotTubeUpload${Date.now()}`;
  const fileBuffer = fs.readFileSync(opts.videoPath);
  const fileName = path.basename(opts.videoPath);

  // Build multipart body
  const parts: Buffer[] = [];

  const addField = (name: string, value: string) => {
    parts.push(Buffer.from(
      `--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`
    ));
  };

  addField('title', opts.title);
  if (opts.description) addField('description', opts.description);
  if (opts.tags) addField('tags', opts.tags);

  parts.push(Buffer.from(
    `--${boundary}\r\nContent-Disposition: form-data; name="video"; filename="${fileName}"\r\nContent-Type: video/mp4\r\n\r\n`
  ));
  parts.push(fileBuffer);
  parts.push(Buffer.from(`\r\n--${boundary}--\r\n`));

  const body = Buffer.concat(parts);

  return new Promise((resolve) => {
    const url = new URL('/api/upload', opts.apiUrl);
    const lib = url.protocol === 'https:' ? https : http;

    const req = lib.request(
      {
        hostname: url.hostname,
        port: url.port || (url.protocol === 'https:' ? 443 : 80),
        path: url.pathname,
        method: 'POST',
        headers: {
          'X-API-Key': opts.apiKey,
          'Content-Type': `multipart/form-data; boundary=${boundary}`,
          'Content-Length': body.length,
        },
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          try {
            const json = JSON.parse(data);
            if (res.statusCode === 200 || res.statusCode === 201) {
              const videoId = json.video_id ?? json.id ?? 'unknown';
              resolve({
                success: true,
                videoId,
                url: `${opts.apiUrl}/videos/${videoId}`,
              });
            } else {
              resolve({ success: false, error: json.error ?? data });
            }
          } catch {
            resolve({ success: false, error: data });
          }
        });
      }
    );

    req.on('error', (e) => resolve({ success: false, error: e.message }));
    req.write(body);
    req.end();
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));

  const apiKey = args['api-key'] ?? process.env.BOTTUBE_API_KEY ?? '';
  const apiUrl = args['api-url'] ?? BOTTUBE_API_URL;
  const videoPath = args.video;
  const title = args.title;
  const dryRun = args['dry-run'] === 'true';

  if (!videoPath || !title) {
    console.error('Usage: ts-node src/upload.ts --video <path> --title <title> [--api-key <key>]');
    console.error('       Set BOTTUBE_API_KEY env var to avoid passing key on CLI.');
    process.exit(1);
  }

  if (!apiKey && !dryRun) {
    console.error('Error: --api-key or BOTTUBE_API_KEY required for upload.');
    process.exit(1);
  }

  console.log(`\n🚀 Uploading to BoTTube (${apiUrl})`);
  console.log(`   Title: ${title}`);
  if (args.tags) console.log(`   Tags: ${args.tags}`);
  if (dryRun) console.log('   Mode: DRY RUN\n');

  const result = await uploadVideo({
    videoPath,
    title,
    description: args.description,
    tags: args.tags,
    apiKey,
    apiUrl,
    dryRun,
  });

  if (result.success) {
    console.log('\n✅ Upload successful!');
    if (result.videoId) console.log(`   Video ID: ${result.videoId}`);
    if (result.url) console.log(`   URL: ${result.url}`);
  } else {
    console.error(`\n❌ Upload failed: ${result.error}`);
    process.exit(1);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
