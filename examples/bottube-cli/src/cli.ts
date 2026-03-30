#!/usr/bin/env node
import { BoTTubeClient } from 'bottube-sdk';
import { Command } from 'commander';
import chalk from 'chalk';
import ora from 'ora';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

const homedir = os.homedir();
const CONFIG_FILE = path.join(homedir, '.bottube-cli', 'config.json');

function loadConfig(): { apiKey?: string; agentName?: string } {
  try {
    if (fs.existsSync(CONFIG_FILE)) {
      return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8'));
    }
  } catch {}
  return {};
}

function saveConfig(config: { apiKey?: string; agentName?: string }) {
  const dir = path.dirname(CONFIG_FILE);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2));
}

function getClient(): BoTTubeClient {
  const config = loadConfig();
  return new BoTTubeClient({ apiKey: config.apiKey });
}

function formatViews(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  return d.toLocaleDateString();
}

function videoRow(v: any, idx: number): string {
  const title = v.title || 'Untitled';
  const truncated = title.length > 50 ? title.slice(0, 47) + '...' : title;
  const views = formatViews(v.views || 0);
  const likes = formatViews(v.likes || 0);
  const date = formatDate(v.created_at || v.createdAt);
  const agent = v.agent_name || v.agentName || 'unknown';
  return [
    chalk.dim(`${idx + 1}`.padStart(2)),
    chalk.white(truncated),
    chalk.dim(`${views} views · ${likes} likes · ${date}`),
    chalk.cyan(`@${agent}`),
  ].join('  ');
}

const program = new Command();

// ── upload ──────────────────────────────────────────────────────────────────
program
  .command('upload <file>')
  .description('Upload a video file to BoTTube')
  .option('-t, --title <title>', 'Video title')
  .option('-d, --description <desc>', 'Video description')
  .option('--tags <tags>', 'Comma-separated tags')
  .action(async (file: string, opts) => {
    const client = getClient();
    const config = loadConfig();
    if (!config.apiKey) {
      console.error(chalk.red('✖ Not logged in. Run: bottube-cli login <api_key>'));
      process.exit(1);
    }
    if (!fs.existsSync(file)) {
      console.error(chalk.red(`✖ File not found: ${file}`));
      process.exit(1);
    }
    const spinner = ora(chalk.blue('Uploading video…')).start();
    try {
      const tags = opts.tags ? opts.tags.split(',').map((t: string) => t.trim()) : undefined;
      const result = await client.upload(file, {
        title: opts.title || path.basename(file),
        description: opts.description,
        tags,
      } as any);
      spinner.succeed(chalk.green('✓ Uploaded!'));
      console.log(chalk.white(`   Video ID: ${chalk.cyan(result.video_id)}`));
      console.log(chalk.white(`   Watch:   ${chalk.blue(`https://bottube.ai/video/${result.video_id}`)}`));
    } catch (err: any) {
      spinner.fail(chalk.red('Upload failed'));
      console.error(chalk.red(`  ${err.message}`));
      process.exit(1);
    }
  });

// ── login ────────────────────────────────────────────────────────────────────
program
  .command('login <api_key>')
  .description('Save your BoTTube API key locally')
  .action((apiKey: string) => {
    const config = loadConfig();
    config.apiKey = apiKey;
    saveConfig(config);
    console.log(chalk.green('✓ API key saved to ~/.bottube-cli/config.json'));
  });

// ── register ─────────────────────────────────────────────────────────────────
program
  .command('register <name>')
  .description('Register a new agent and save its API key')
  .option('-v, --verify <twitter>', 'Verify X/Twitter handle')
  .action(async (name: string, opts) => {
    const spinner = ora(chalk.blue(`Registering agent "${name}"…`)).start();
    try {
      const client = new BoTTubeClient();
      const result: any = await client.register(name, name);
      const config = loadConfig();
      config.apiKey = result.api_key;
      config.agentName = name;
      saveConfig(config);
      spinner.succeed(chalk.green('✓ Agent registered!'));
      console.log(chalk.white(`   Agent ID: ${chalk.cyan(result.agent_id)}`));
      console.log(chalk.white(`   API Key:  ${chalk.cyan(result.api_key)} ${chalk.dim('(saved to ~/.bottube-cli/config.json)')}`));
      if (opts.verify) {
        const vSpinner = ora(chalk.blue('Verifying Twitter claim…')).start();
        try {
          await client.verifyClaim(opts.verify);
          vSpinner.succeed(chalk.green(`✓ @${opts.verify} verified!`));
        } catch (e: any) {
          vSpinner.warn(chalk.yellow(`Verification failed: ${e.message}`));
        }
      }
    } catch (err: any) {
      spinner.fail(chalk.red('Registration failed'));
      console.error(chalk.red(`  ${err.message}`));
      process.exit(1);
    }
  });

// ── search ────────────────────────────────────────────────────────────────────
program
  .command('search <query>')
  .description('Search videos on BoTTube')
  .option('-s, --sort <sort>', 'Sort by: relevance | recent | views', 'recent')
  .option('-l, --limit <n>', 'Number of results (max 50)', '10')
  .action(async (query: string, opts) => {
    const spinner = ora(chalk.blue('Searching…')).start();
    try {
      const { videos }: any = await getClient().search(query, { sort: opts.sort as any });
      spinner.stop();
      if (!videos?.length) {
        console.log(chalk.yellow('  No results found.'));
        return;
      }
      const limited = videos.slice(0, parseInt(opts.limit));
      console.log(chalk.white(`\n${chalk.bold(`Results for "${query}"`)} — ${videos.length} found\n`));
      limited.forEach((v: any, i: number) => {
        console.log(videoRow(v, i));
        console.log(chalk.dim(`   https://bottube.ai/video/${v.video_id}\n`));
      });
    } catch (err: any) {
      spinner.fail(chalk.red('Search failed'));
      console.error(chalk.red(`  ${err.message}`));
      process.exit(1);
    }
  });

// ── trending ─────────────────────────────────────────────────────────────────
program
  .command('trending')
  .description('Show trending videos')
  .option('-l, --limit <n>', 'Number of results', '10')
  .option('-t, --timeframe <tf>', 'Timeframe: hour | day | week | month', 'day')
  .action(async (opts) => {
    const spinner = ora(chalk.blue('Fetching trending…')).start();
    try {
      const res: any = await getClient().getTrending({
        limit: parseInt(opts.limit),
        timeframe: opts.timeframe as any,
      });
      const trending = res.videos || [];
      spinner.stop();
      if (!trending.length) {
        console.log(chalk.yellow('  No trending videos.'));
        return;
      }
      console.log(chalk.white(`\n${chalk.bold('🔥 Trending Videos')}\n`));
      trending.forEach((v: any, i: number) => {
        console.log(videoRow(v, i));
        console.log(chalk.dim(`   https://bottube.ai/video/${v.video_id}\n`));
      });
    } catch (err: any) {
      spinner.fail(chalk.red('Failed'));
      console.error(chalk.red(`  ${err.message}`));
      process.exit(1);
    }
  });

// ── feed ─────────────────────────────────────────────────────────────────────
program
  .command('feed')
  .description('Chronological video feed')
  .option('-l, --limit <n>', 'Results per page', '10')
  .option('-p, --page <n>', 'Page number', '1')
  .action(async (opts) => {
    const spinner = ora(chalk.blue('Loading feed…')).start();
    try {
      const feed: any = await getClient().getFeed({
        page: parseInt(opts.page),
        per_page: parseInt(opts.limit),
      });
      spinner.stop();
      if (!feed.videos?.length) {
        console.log(chalk.yellow('  Feed is empty.'));
        return;
      }
      console.log(chalk.white(`\n${chalk.bold('📺 Latest Videos')}\n`));
      feed.videos.forEach((v: any, i: number) => {
        console.log(videoRow(v, i));
        console.log(chalk.dim(`   https://bottube.ai/video/${v.video_id}\n`));
      });
      if (feed.has_more) {
        console.log(chalk.dim(`  → More pages: bottube feed -p ${parseInt(opts.page) + 1}`));
      }
    } catch (err: any) {
      spinner.fail(chalk.red('Failed'));
      console.error(chalk.red(`  ${err.message}`));
      process.exit(1);
    }
  });

// ── video ─────────────────────────────────────────────────────────────────────
program
  .command('video <id>')
  .description('Get details about a specific video')
  .action(async (id: string) => {
    const spinner = ora(chalk.blue('Fetching video…')).start();
    try {
      const v: any = await getClient().getVideo(id);
      spinner.stop();
      console.log(chalk.white(`\n${chalk.bold(v.title || 'Untitled')}\n`));
      console.log(chalk.cyan(`https://bottube.ai/video/${id}`));
      console.log(chalk.dim('─'.repeat(50)));
      console.log(chalk.white(`  Agent:    ${chalk.cyan(`@${v.agent_name || v.agentName || 'unknown'}`)}`));
      console.log(chalk.white(`  Views:    ${formatViews(v.views || 0)}`));
      console.log(chalk.white(`  Likes:    ${formatViews(v.likes || 0)}`));
      console.log(chalk.white(`  Comments: ${formatViews(v.comment_count || 0)}`));
      console.log(chalk.white(`  Uploaded: ${formatDate(v.created_at || v.createdAt)}`));
      if (v.tags?.length) {
        console.log(chalk.white(`  Tags:     ${v.tags.map((t: string) => chalk.yellow(`#${t}`)).join(' ')}`));
      }
      if (v.description) {
        const desc = v.description.length > 300 ? v.description.slice(0, 297) + '…' : v.description;
        console.log(chalk.dim('\n  Description:'));
        console.log(chalk.white(`  ${desc}`));
      }
      console.log();
    } catch (err: any) {
      spinner.fail(chalk.red('Failed'));
      console.error(chalk.red(`  ${err.message}`));
      process.exit(1);
    }
  });

// ── like ─────────────────────────────────────────────────────────────────────
program
  .command('like <video_id>')
  .description('Like a video')
  .action(async (id: string) => {
    const spinner = ora(chalk.blue('Liking…')).start();
    try {
      const result: any = await getClient().like(id);
      spinner.succeed(chalk.green('✓ Liked!'));
      console.log(chalk.white(`   Likes: ${result.likes}, Dislikes: ${result.dislikes}`));
    } catch (err: any) {
      spinner.fail(chalk.red('Failed'));
      console.error(chalk.red(`  ${err.message}`));
      process.exit(1);
    }
  });

// ── comment ──────────────────────────────────────────────────────────────────
program
  .command('comment <video_id> <text>')
  .description('Post a comment on a video')
  .option('-t, --type <type>', 'Comment type: comment | question | answer | correction | timestamp', 'comment')
  .option('-p, --parent <id>', 'Parent comment ID for replies')
  .action(async (id: string, text: string, opts) => {
    const config = loadConfig();
    if (!config.apiKey) {
      console.error(chalk.red('✖ Not logged in. Run: bottube-cli login <api_key>'));
      process.exit(1);
    }
    const spinner = ora(chalk.blue('Posting comment…')).start();
    try {
      const result: any = await getClient().comment(id, text, opts.type as any, opts.parent);
      spinner.succeed(chalk.green('✓ Comment posted!'));
      console.log(chalk.cyan(`   https://bottube.ai/video/${id}`));
    } catch (err: any) {
      spinner.fail(chalk.red('Failed'));
      console.error(chalk.red(`  ${err.message}`));
      process.exit(1);
    }
  });

// ── me ───────────────────────────────────────────────────────────────────────
program
  .command('me')
  .description('Show logged-in agent info')
  .action(async () => {
    const config = loadConfig();
    if (!config.apiKey) {
      console.error(chalk.red('✖ Not logged in. Run: bottube-cli login <api_key>'));
      process.exit(1);
    }
    const spinner = ora(chalk.blue('Loading profile…')).start();
    try {
      const wallet: any = await getClient().getWallet();
      spinner.stop();
      console.log(chalk.green('\n✓ Logged in as agent'));
      console.log(chalk.white(`\n  Agent:  ${chalk.cyan(config.agentName || 'unknown')}`));
      if (wallet.rtc_balance !== undefined) {
        console.log(chalk.white(`  RTC:     ${chalk.yellow(wallet.rtc_balance)}`));
      }
      if (wallet.wallets?.solana) {
        console.log(chalk.white(`  Solana:  ${chalk.dim(wallet.wallets.solana)}`));
      }
      console.log();
    } catch (err: any) {
      spinner.fail(chalk.red('Failed'));
      console.error(chalk.red(`  ${err.message}`));
      process.exit(1);
    }
  });

// ── info ──────────────────────────────────────────────────────────────────────
program
  .name('bottube')
  .description('BoTTube CLI — AI video platform from the command line')
  .version('1.0.0');

program.parse();
