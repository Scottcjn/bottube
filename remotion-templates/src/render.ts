/**
 * render.ts — CLI wrapper for Remotion rendering
 *
 * Usage:
 *   ts-node src/render.ts --template NewsLowerThird --config configs/news-example.json --out out/news.mp4
 *   ts-node src/render.ts --template DataVisualization --out out/data.mp4
 *   ts-node src/render.ts --list
 *
 * Options:
 *   --template <id>     Composition ID (see list below)
 *   --config <path>     JSON config file (optional, uses defaults)
 *   --out <path>        Output MP4 path (default: out/<template>.mp4)
 *   --fps <n>           Frames per second (default: 30)
 *   --list              Print available template IDs and exit
 */

import path from 'path';
import fs from 'fs';
import { execSync } from 'child_process';

const TEMPLATES = [
  'NewsLowerThird',
  'DataVisualization',
  'TutorialExplainer',
  'MemeShortForm',
  'Slideshow',
];

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

function main() {
  const args = parseArgs(process.argv.slice(2));

  if (args.list === 'true') {
    console.log('Available templates:');
    TEMPLATES.forEach((t) => console.log(`  • ${t}`));
    process.exit(0);
  }

  const template = args.template;
  if (!template) {
    console.error('Error: --template is required. Use --list to see options.');
    process.exit(1);
  }

  if (!TEMPLATES.includes(template)) {
    console.error(`Unknown template: "${template}". Available: ${TEMPLATES.join(', ')}`);
    process.exit(1);
  }

  const outFile = args.out ?? `out/${template}.mp4`;
  const outDir = path.dirname(outFile);
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

  // Build remotion render command
  const entryPoint = path.resolve(__dirname, 'index.ts');
  let cmd = `npx remotion render "${entryPoint}" "${template}" "${outFile}"`;

  // Add props from config file if provided
  if (args.config) {
    const configPath = path.resolve(args.config);
    if (!fs.existsSync(configPath)) {
      console.error(`Config file not found: ${configPath}`);
      process.exit(1);
    }
    const configJson = JSON.stringify({ config: JSON.parse(fs.readFileSync(configPath, 'utf-8')) });
    cmd += ` --props '${configJson}'`;
  }

  if (args.fps) {
    cmd += ` --overwrite`;
  }

  console.log(`\n🎬 Rendering: ${template}`);
  console.log(`📁 Output: ${outFile}`);
  if (args.config) console.log(`⚙️  Config: ${args.config}`);
  console.log(`\n$ ${cmd}\n`);

  try {
    execSync(cmd, { stdio: 'inherit', cwd: path.resolve(__dirname, '..') });
    console.log(`\n✅ Render complete: ${outFile}`);

    // Post-processing: ensure BoTTube compliance (8s max, 720x720, H.264)
    const processedFile = outFile.replace(/\.mp4$/, '_bottube.mp4');
    const ffmpegCmd = [
      'ffmpeg -y',
      `-i "${outFile}"`,
      '-t 8',
      `-vf "scale='min(720,iw)':'min(720,ih)':force_original_aspect_ratio=decrease,pad=720:720:(ow-iw)/2:(oh-ih)/2:color=black"`,
      '-c:v libx264 -crf 28 -preset medium -maxrate 900k -bufsize 1800k',
      '-pix_fmt yuv420p -an -movflags +faststart',
      `"${processedFile}"`,
    ].join(' ');

    console.log(`\n🔧 Post-processing for BoTTube compliance...`);
    execSync(ffmpegCmd, { stdio: 'inherit' });
    console.log(`✅ BoTTube-ready: ${processedFile}`);
    console.log(`\nUpload with: ts-node src/upload.ts --video "${processedFile}" --title "My ${template}" --api-key YOUR_KEY`);
  } catch (e) {
    console.error('Render failed:', e);
    process.exit(1);
  }
}

main();
