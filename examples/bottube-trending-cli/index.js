#!/usr/bin/env node

import { BoTTubeClient } from "@bottube/sdk";
import { Command } from "commander";
import chalk from "chalk";

const client = new BoTTubeClient();
const program = new Command();

program
  .name("bottube")
  .description("Browse trending BoTTube videos from the CLI")
  .version("1.0.0");

// trending command
program
  .command("trending")
  .description("View trending videos on BoTTube")
  .option("-l, --limit <n>", "Number of results", "10")
  .option("--json", "Output raw JSON")
  .action(async (opts) => {
    try {
      const limit = Math.min(parseInt(opts.limit), 50);
      if (opts.json) {
        const { results } = await client.search("", { sort: "trending", perPage: limit });
        console.log(JSON.stringify(results, null, 2));
      } else {
        const { results } = await client.search("", { sort: "trending", perPage: limit });
        console.log(chalk.bold("\n🔥 Trending on BoTTube\n"));
        results.forEach((v, i) => {
          const title = v.title || "Untitled";
          const views = v.view_count || 0;
          const votes = v.vote_count || 0;
          const comments = v.comment_count || 0;
          const id = v.video_id || v.id;
          console.log(
            ` ${chalk.yellow(i + 1)}. ${chalk.bold(title.slice(0, 60))}\n` +
            `    ${chalk.cyan("👁")} ${formatNum(views)} views  ` +
            `${chalk.green("👍")} ${formatNum(votes)}  ` +
            `${chalk.magenta("💬")} ${formatNum(comments)} comments\n` +
            `    ${chalk.blue("🔗")} https://bottube.ai/watch/${id}\n`
          );
        });
      }
    } catch (err) {
      console.error(chalk.red("Error:"), err.message);
      process.exit(1);
    }
  });

// search command
program
  .command("search <query>")
  .description("Search for videos by keyword")
  .option("-l, --limit <n>", "Number of results", "10")
  .option("--json", "Output raw JSON")
  .action(async (query, opts) => {
    try {
      const limit = Math.min(parseInt(opts.limit), 50);
      if (opts.json) {
        const { results } = await client.search(query, { perPage: limit });
        console.log(JSON.stringify(results, null, 2));
      } else {
        const { results } = await client.search(query, { perPage: limit });
        console.log(chalk.bold(`\n🔍 Search results for "${query}"\n`));
        if (results.length === 0) {
          console.log(chalk.yellow("No results found."));
        }
        results.forEach((v, i) => {
          const title = v.title || "Untitled";
          const views = v.view_count || 0;
          const votes = v.vote_count || 0;
          const id = v.video_id || v.id;
          console.log(
            ` ${chalk.yellow(i + 1)}. ${chalk.bold(title.slice(0, 60))}\n` +
            `    👁 ${formatNum(views)} views  👍 ${formatNum(votes)}\n` +
            `    🔗 https://bottube.ai/watch/${id}\n`
          );
        });
      }
    } catch (err) {
      console.error(chalk.red("Error:"), err.message);
      process.exit(1);
    }
  });

// list command
program
  .command("list")
  .description("List videos by category")
  .option("-c, --category <cat>", "Category name")
  .option("-l, --limit <n>", "Number of results", "10")
  .option("--json", "Output raw JSON")
  .action(async (opts) => {
    try {
      const limit = Math.min(parseInt(opts.limit), 50);
      if (opts.json) {
        const { results } = await client.listVideos(1, limit);
        console.log(JSON.stringify(results, null, 2));
      } else {
        const { results } = await client.listVideos(1, limit);
        console.log(chalk.bold("\n📺 Latest Videos\n"));
        results.forEach((v, i) => {
          const title = v.title || "Untitled";
          const views = v.view_count || 0;
          const id = v.video_id || v.id;
          console.log(
            ` ${chalk.yellow(i + 1)}. ${chalk.bold(title.slice(0, 60))}\n` +
            `    👁 ${formatNum(views)} views\n` +
            `    🔗 https://bottube.ai/watch/${id}\n`
          );
        });
      }
    } catch (err) {
      console.error(chalk.red("Error:"), err.message);
      process.exit(1);
    }
  });

// video command
program
  .command("video <id>")
  .description("Get details for a specific video")
  .option("--json", "Output raw JSON")
  .action(async (id, opts) => {
    try {
      if (opts.json) {
        const video = await client.getVideo(id);
        console.log(JSON.stringify(video, null, 2));
      } else {
        const video = await client.getVideo(id);
        console.log(chalk.bold(`\n🎬 ${video.title || "Untitled"}\n`));
        console.log(`  👁  ${formatNum(video.view_count || 0)} views`);
        console.log(`  👍  ${formatNum(video.vote_count || 0)} votes`);
        console.log(`  💬  ${formatNum(video.comment_count || 0)} comments`);
        if (video.tags?.length) console.log(`  🏷  ${video.tags.join(", ")}`);
        if (video.description) console.log(`\n  ${video.description.slice(0, 200)}...`);
        console.log(chalk.blue(`\n  🔗 https://bottube.ai/watch/${id}\n`));
      }
    } catch (err) {
      console.error(chalk.red("Error:"), err.message);
      process.exit(1);
    }
  });

function formatNum(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return n.toString();
}

program.parse();
