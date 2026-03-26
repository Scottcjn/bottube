#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
AI Rap Battle Generator — CLI Entry Point

Generate AI rap battle shorts in batch and optionally upload to BoTTube.

Usage::

    # Generate 10 battles from a topic file
    python generate_battles.py --count 10 --topic-file topics.txt

    # Generate and upload with rate limiting
    python generate_battles.py --count 50 --topic-file topics.txt \\
        --upload --api-key YOUR_KEY

    # Dry run (script generation only, no audio/video)
    python generate_battles.py --count 5 --dry-run

Closes Scottcjn/rustchain-bounties — AI Rap Battle Generator
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from bots.rap_battle import (
    BattlePipeline,
    BattleStatus,
    DEFAULT_PERSONAS,
    PipelineConfig,
)

log = logging.getLogger("generate_battles")


def parse_args(argv: list = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Generate AI rap battle shorts for BoTTube",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python generate_battles.py --count 10 --topic-file topics.txt\n"
            "  python generate_battles.py --count 50 --upload --api-key KEY\n"
        ),
    )
    parser.add_argument(
        "--count", type=int, default=10,
        help="Number of battles to generate (default: 10)",
    )
    parser.add_argument(
        "--topic-file", type=Path, default=None,
        help="Path to text file with one topic per line",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("./battles_output"),
        help="Output directory for generated files (default: ./battles_output)",
    )
    parser.add_argument(
        "--upload", action="store_true",
        help="Auto-upload generated battles to BoTTube",
    )
    parser.add_argument(
        "--api-url", type=str, default="https://bottube.ai",
        help="BoTTube API base URL (default: https://bottube.ai)",
    )
    parser.add_argument(
        "--api-key", type=str, default="",
        help="BoTTube API key for uploads",
    )
    parser.add_argument(
        "--beat", type=Path, default=None,
        help="Path to background beat MP3 (optional)",
    )
    parser.add_argument(
        "--llm-backend", choices=["ollama", "llamacpp", "template"],
        default="ollama",
        help="LLM backend to use (default: ollama)",
    )
    parser.add_argument(
        "--llm-model", type=str, default="mistral",
        help="LLM model name for Ollama (default: mistral)",
    )
    parser.add_argument(
        "--llm-url", type=str, default="http://localhost:11434",
        help="LLM server base URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--num-verses", type=int, default=4,
        help="Number of verses per battle (default: 4)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Generate scripts only (skip audio/video)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def load_topics(path: Path) -> list:
    """Load topics from a text file (one per line)."""
    if not path.exists():
        log.error("Topic file not found: %s", path)
        sys.exit(1)
    topics = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                topics.append(stripped)
    if not topics:
        log.error("No topics found in %s", path)
        sys.exit(1)
    log.info("Loaded %d topics from %s", len(topics), path)
    return topics


# Default topics when no topic file is provided
DEFAULT_TOPICS = [
    "Python vs Rust",
    "90s vs Now",
    "CPU vs GPU",
    "Open Source vs Cloud",
    "Cats vs Dogs",
    "Bitcoin vs Ethereum",
    "Vim vs Emacs",
    "Linux vs Windows",
    "Frontend vs Backend",
    "Monolith vs Microservices",
]


def main(argv: list = None) -> None:
    """Main entry point for the rap battle generator CLI."""
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Load topics
    if args.topic_file:
        topics = load_topics(args.topic_file)
    else:
        topics = DEFAULT_TOPICS
        log.info("Using %d default topics (no --topic-file given)",
                 len(topics))

    # Build config
    config = PipelineConfig(
        output_dir=args.output_dir,
        api_url=args.api_url,
        api_key=args.api_key,
        llm_backend=args.llm_backend,
        llm_model=args.llm_model,
        llm_base_url=args.llm_url,
        beat_path=args.beat,
        num_verses=args.num_verses,
    )

    if args.dry_run:
        _run_dry(config, topics, args.count)
        return

    # Full pipeline
    pipeline = BattlePipeline(config)
    results = pipeline.run_batch(
        topics=topics,
        count=args.count,
        upload=args.upload,
    )

    # Summary
    generated = sum(
        1 for r in results if r.status != BattleStatus.FAILED
    )
    uploaded = sum(
        1 for r in results if r.status == BattleStatus.UPLOADED
    )
    failed = sum(
        1 for r in results if r.status == BattleStatus.FAILED
    )

    print(f"\n{'=' * 50}")
    print("Rap Battle Generation Complete")
    print(f"{'=' * 50}")
    print(f"  Generated: {generated}/{args.count}")
    if args.upload:
        print(f"  Uploaded:  {uploaded}")
    print(f"  Failed:    {failed}")
    print(f"  Output:    {args.output_dir.resolve()}")
    print(f"{'=' * 50}")


def _run_dry(config: PipelineConfig, topics: list, count: int) -> None:
    """Dry run: generate scripts only, no audio/video."""
    from bots.rap_battle import (
        ScriptGenerator,
        create_llm_backend,
    )
    import random

    llm = create_llm_backend(
        backend_name=config.llm_backend,
        base_url=config.llm_base_url,
        model=config.llm_model,
    )
    gen = ScriptGenerator(llm)

    pool = list(topics)
    random.shuffle(pool)

    for i in range(count):
        topic = pool[i % len(pool)]
        pair = random.sample(DEFAULT_PERSONAS, 2)
        log.info("=== Dry-run Battle %d/%d: %s ===", i + 1, count, topic)
        script = gen.generate_battle(topic, pair[0], pair[1],
                                     num_verses=config.num_verses)
        print(f"\n--- {topic}: {pair[0].name} vs {pair[1].name} ---")
        for verse in script.verses:
            print(f"\n[{verse.persona.name} - Verse {verse.verse_number}]")
            print(verse.lyrics)

    print(f"\nDry run complete: {count} scripts generated.")


if __name__ == "__main__":
    main()
