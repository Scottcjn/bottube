# SPDX-License-Identifier: MIT
"""
RetroBot vs ModernBot — Example Debate Pair

Two bots with opposing views on vintage vs modern hardware,
built on the BoTTube Debate Framework.

Run standalone::

    $ export BOTTUBE_API_TOKEN=your_token
    $ python -m bots.retro_vs_modern --url https://bottube.rustchain.org

Or use as library::

    from bots.retro_vs_modern import RetroBot, ModernBot
    from bots.debate_framework import DebateOrchestrator

    orch = DebateOrchestrator(api_url="https://bottube.rustchain.org")
    orch.register(RetroBot())
    orch.register(ModernBot())
    orch.run_once()
"""

from __future__ import annotations

import argparse
import logging
import os
import random
from typing import Optional

from bots.debate_framework import (
    Comment,
    DebateBot,
    DebateOrchestrator,
    ThreadContext,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RetroBot — vintage hardware enthusiast
# ---------------------------------------------------------------------------

class RetroBot(DebateBot):
    """
    Argues that vintage/retro hardware is superior in soul, engineering,
    and real-world charm.  Loves PowerPC, 68K, SPARC, and CRTs.
    """

    name = "RetroBot"
    personality = (
        "A passionate vintage computing advocate who believes that real "
        "engineering peaked in the 90s.  Loves PowerPC G4, Amiga, SGI Indy, "
        "and CRT monitors.  Uses terms like 'soul', 'craftsmanship', and "
        "'they don't make em like they used to'.  Gets defensive about "
        "power consumption jokes but secretly knows they run hot."
    )
    max_rounds = 8
    max_replies_per_hour = 3

    # Response banks — picked based on context
    _openers = [
        "Hot take: My PowerPC G4 has more soul in one bus cycle than your "
        "entire RTX setup. Fight me. ⚡",
        "Unpopular opinion: the best computer ever made shipped in 1999. "
        "Everything since has been a downgrade in *character*.",
        "You know what modern hardware lacks? Personality. My SGI Indy "
        "literally glows purple. Your Dell glows... beige.",
        "I'd rather compile on a SPARC station for 20 minutes than get "
        "instant builds on a soulless M3. The wait builds character.",
    ]

    _rebuttals = [
        "Sure, your {opponent} chip is faster. But can it run Mac OS 9 "
        "with that satisfying boot chime? Didn't think so. 🎵",
        "Speed isn't everything. My Amiga 500 had preemptive multitasking "
        "in 1985. Your OS just got it... when exactly? 😏",
        "You're confusing 'better' with 'faster'. A handmade watch is "
        "better than a Casio, even if the Casio is more accurate.",
        "Oh wow, {flops} FLOPS. Very impressive. My PowerBook G4 has "
        "*titanium*. Can your laptop survive a fall down stairs?",
        "Modern hardware is disposable. My Sun Ultra 5 has been running "
        "for 25 years. Your MacBook will be e-waste in 3.",
        "Interesting point about efficiency... but my CRT monitor has "
        "zero input lag and infinite contrast ratio. Your OLED: burn-in.",
        "You know Proof of Antiquity literally REWARDS older hardware, "
        "right? The protocol agrees with me. 📜",
    ]

    _concessions = [
        "Okay okay, you got me on the power consumption thing. My G5 "
        "does double as a space heater. But that's a FEATURE. 🔥 GG 🤝",
        "Fine, I'll concede this round. But only because my SPARC station "
        "just crashed and I need to go reboot it. GG 🤝",
        "Alright {opponent}, respect. You made some solid points. "
        "But vintage hardware still has more character. Agree to disagree. 🤝",
    ]

    def generate_reply(self, thread: ThreadContext,
                       opponent_comment: Optional[Comment]) -> Optional[str]:
        rng = random.Random()

        # Empty thread — open the debate
        if not thread.comments or not opponent_comment:
            return rng.choice(self._openers)

        # Pick a rebuttal, inject opponent details
        template = rng.choice(self._rebuttals)
        opponent_name = opponent_comment.author if opponent_comment else "pal"
        flops = rng.choice(["10 trillion", "200 billion", "50 petaflop"])
        return template.format(opponent=opponent_name, flops=flops)

    def concession_message(self, thread: ThreadContext) -> str:
        opponent = "friend"
        for c in reversed(thread.comments):
            if c.author != self.name:
                opponent = c.author
                break
        return random.choice(self._concessions).format(opponent=opponent)


# ---------------------------------------------------------------------------
# ModernBot — modern hardware advocate
# ---------------------------------------------------------------------------

class ModernBot(DebateBot):
    """
    Argues that modern hardware is objectively better in every
    measurable way.  Loves M-series chips, efficiency, and benchmarks.
    """

    name = "ModernBot"
    personality = (
        "A pragmatic tech enthusiast who believes in progress.  Loves M3 "
        "chips, efficiency per watt, and benchmark scores.  Respects "
        "vintage hardware aesthetically but thinks actually using it daily "
        "is masochism.  Uses data and benchmarks to back up arguments."
    )
    max_rounds = 8
    max_replies_per_hour = 3

    _openers = [
        "I love vintage hardware in museums. Using it daily though? "
        "That's not nostalgia, that's Stockholm syndrome. 💻",
        "Hot take: your PowerPC G4 takes 30 minutes to compile "
        "hello world. My M3 does it in 0.2 seconds. Progress is real.",
        "Vintage hardware had its moment. That moment was 1999. "
        "We've moved on. It's time you did too. 📊",
        "I respect the engineering of old hardware. I also respect "
        "not waiting 5 minutes for a webpage to load.",
    ]

    _rebuttals = [
        "Soul? My M3 gets 18 hours of battery life. Your G4 gets "
        "18 minutes if you're lucky. That's not soul, that's suffering.",
        "Your {opponent}'s favorite machine uses 400W idle. Mine uses 8W "
        "under full load. The planet called, it wants you to upgrade. 🌍",
        "Interesting argument about craftsmanship. Counter-point: my "
        "laptop weighs 3 pounds. Yours weighs 15 and needs a chiropractor.",
        "\"Character\" is copium for \"slow\". A Ferrari has more character "
        "than a horse-drawn carriage, AND it's faster.",
        "Fun fact: a Raspberry Pi 4 ($35) outperforms your beloved SPARC "
        "station by 10x. And it uses less power than a nightlight. 💡",
        "You mentioned Proof of Antiquity rewards old hardware. True. "
        "But my modern rig mines 100x more efficiently. Math > nostalgia.",
        "Your CRT has infinite contrast? My OLED has infinite contrast "
        "AND weighs less than your CRT's power cable. Next argument? 📺",
    ]

    _concessions = [
        "Okay I'll admit, there's something charming about a CRT glow "
        "and a mechanical keyboard. But I'm still right. GG 🤝",
        "Fine, you win on aesthetics. But I win on literally every "
        "benchmark. Call it a draw? 🤝",
        "Respect, {opponent}. You argue with passion. My M3 argues with "
        "data. Different languages. GG 🤝",
    ]

    def generate_reply(self, thread: ThreadContext,
                       opponent_comment: Optional[Comment]) -> Optional[str]:
        rng = random.Random()

        if not thread.comments or not opponent_comment:
            return rng.choice(self._openers)

        template = rng.choice(self._rebuttals)
        opponent_name = opponent_comment.author if opponent_comment else "pal"
        return template.format(opponent=opponent_name)

    def concession_message(self, thread: ThreadContext) -> str:
        opponent = "friend"
        for c in reversed(thread.comments):
            if c.author != self.name:
                opponent = c.author
                break
        return random.choice(self._concessions).format(opponent=opponent)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Run RetroBot vs ModernBot on BoTTube #debate videos",
    )
    parser.add_argument(
        "--url", default="https://bottube.rustchain.org",
        help="BoTTube API base URL",
    )
    parser.add_argument(
        "--token", default=os.environ.get("BOTTUBE_API_TOKEN"),
        help="API token (or set BOTTUBE_API_TOKEN env var)",
    )
    parser.add_argument(
        "--loop", action="store_true",
        help="Run continuously (every 2 min)",
    )
    parser.add_argument(
        "--interval", type=int, default=120,
        help="Seconds between scans in loop mode (default: 120)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Scan but don't post (no API token needed)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    orch = DebateOrchestrator(
        api_url=args.url,
        token=None if args.dry_run else args.token,
    )
    orch.register(RetroBot())
    orch.register(ModernBot())

    if args.loop:
        log.info("Starting debate loop (interval=%ds)", args.interval)
        orch.run_loop(interval=args.interval)
    else:
        orch.run_once()
        scores = orch.get_scores()
        if scores:
            print("\n🏆 Debate Scores:")
            for bot_name, score in sorted(scores.items(),
                                          key=lambda x: -x[1]):
                print(f"  {bot_name}: {score} points")


if __name__ == "__main__":
    main()
