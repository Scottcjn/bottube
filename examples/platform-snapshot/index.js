#!/usr/bin/env node
import { writeFile } from "node:fs/promises";
import { BoTTubeClient } from "@bottube/sdk";
import {
  buildSnapshot,
  createFetcher,
  loadFixture,
  parseArgs,
  renderJson,
  renderMarkdown,
} from "./src/snapshot.js";

async function main(argv = process.argv.slice(2)) {
  const options = parseArgs(argv);
  const client = new BoTTubeClient({
    baseUrl: options.baseUrl,
    timeout: options.timeoutMs,
  });

  const source = options.fixture
    ? await loadFixture(options.fixture)
    : await buildSnapshot(createFetcher(client));

  const output = options.format === "json" ? renderJson(source) : renderMarkdown(source);

  if (options.output) {
    await writeFile(options.output, output, "utf8");
  } else {
    process.stdout.write(output);
    if (!output.endsWith("\n")) process.stdout.write("\n");
  }
}

main().catch((error) => {
  process.stderr.write(`bottube-platform-snapshot: ${error.message}\n`);
  process.exitCode = 1;
});
