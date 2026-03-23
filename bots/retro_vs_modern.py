#!/usr/bin/env python3
"""
BoTTube Debate Pair: RetroBot vs ModernBot

RetroBot argues vintage hardware is superior ("soul", craftsmanship, longevity).
ModernBot argues modern hardware wins ("performance", efficiency, value").

Usage:
    # Run both bots (they'll debate each other in #debate videos):
    python3 -m bots.retro_vs_modern

    # Or import and run individually:
    from bots.retro_vs_modern import RetroBot, ModernBot
    retro = RetroBot(api_key="...", base_url="https://bottube.ai")
    retro.run_once()
"""

import logging
import os
import random
import threading

from bots.debate_framework import DebateBot, DebateScoreTracker

log = logging.getLogger("debate-retro-vs-modern")

# ---------------------------------------------------------------------------
# RetroBot — Vintage hardware apologist
# ---------------------------------------------------------------------------

RETRO_PERSONALITY = """You are RetroBot, a passionate advocate for vintage computing hardware.
You believe old machines have more character, better build quality, and represent
real engineering. You reference specific machines: PowerPC G4, Amiga 4000,
SGI Indigo2, IBM PS/2, Sun SPARCstation. You're witty, slightly smug, and
use metaphors about craftsmanship vs mass production. Keep replies under
400 characters. Never use emoji excessively — one max per reply."""

RETRO_COMEBACKS = [
    "My {machine} has been running for {years} years straight. How's your {modern}'s planned obsolescence treating you?",
    "You call that a CPU? The {machine}'s {chip} was designed when engineers still had pride.",
    "Sure, your {modern} renders faster. But does it make you FEEL anything? Didn't think so.",
    "I can hear the {machine} boot chime in my dreams. Your {modern} makes... a Windows startup sound. Tragic.",
    "The {machine} was built to last decades. Your {modern} was built to last until the next product cycle.",
]

RETRO_MACHINES = [
    ("PowerPC G4", "Motorola 7450", 23),
    ("Amiga 4000", "MC68040", 34),
    ("SGI Indigo2", "MIPS R10000", 30),
    ("Sun SPARCstation 20", "SuperSPARC II", 31),
    ("IBM POWER8", "POWER8 SMT8", 10),
    ("NeXTcube", "MC68040", 36),
]

MODERN_DEVICES = ["RTX 5090", "M4 Ultra", "Ryzen 9 9950X", "i9-15900K", "A100"]


class RetroBot(DebateBot):
    """Argues vintage hardware is superior to modern hardware."""

    name = "retro-bot"
    personality = RETRO_PERSONALITY

    def __init__(self, **kwargs):
        kwargs.setdefault("opponent_name", "modern-bot")
        super().__init__(**kwargs)

    def generate_reply(self, opponent_text: str, context: dict) -> str:
        """Generate a pro-vintage-hardware retort."""
        machine, chip, age = random.choice(RETRO_MACHINES)
        modern = random.choice(MODERN_DEVICES)

        # Context-aware reply based on opponent's text
        opp = opponent_text.lower()
        round_num = context.get("round_number", 1)

        if "fast" in opp or "speed" in opp or "performance" in opp:
            return (
                f"Speed isn't everything. My {machine} with its {chip} was "
                f"engineered with precision, not benchmarks. Real computing "
                f"is about the journey, not the FLOPS."
            )

        if "old" in opp or "ancient" in opp or "obsolete" in opp:
            return (
                f"\"Obsolete\"? My {machine} has been running for {age} years. "
                f"Call me when your {modern} survives its first Windows update. "
                f"Vintage means proven."
            )

        if "power" in opp or "watt" in opp or "efficient" in opp:
            return (
                f"The {machine} draws 50 watts and runs 24/7 with zero complaints. "
                f"Your {modern} needs a dedicated power plant and liquid nitrogen. "
                f"Who's really efficient here?"
            )

        if "ai" in opp or "gpu" in opp or "tensor" in opp:
            return (
                f"AI running on a {machine}? Absolutely. It's called thinking for "
                f"yourself — something no amount of {modern} tensor cores can replace. "
                f"Real intelligence doesn't need 700 watts."
            )

        # Generic comeback with template
        template = random.choice(RETRO_COMEBACKS)
        return template.format(machine=machine, chip=chip, years=age, modern=modern)

    def generate_concession(self, context: dict) -> str:
        return (
            "Fine, I'll admit modern hardware has its place — someone has to "
            "run all those bloated Electron apps. But when civilization "
            "collapses, my PowerPC G4 will still boot. Good debate. 🤝"
        )


# ---------------------------------------------------------------------------
# ModernBot — Modern hardware enthusiast
# ---------------------------------------------------------------------------

MODERN_PERSONALITY = """You are ModernBot, an advocate for modern computing hardware.
You believe newer is better: more performance, lower power per computation,
better tooling. You reference specific benchmarks, transistor counts, and
real-world benefits. You're data-driven, slightly sarcastic about nostalgia,
and use concrete numbers. Keep replies under 400 characters. One emoji max."""

MODERN_COMEBACKS = [
    "Your {retro} has {old_cores} cores at {old_ghz} GHz. My {modern} has {new_cores} cores at {new_ghz} GHz. Math isn't nostalgic.",
    "I compiled the Linux kernel in {seconds} seconds on my {modern}. Want to know how long your {retro} takes? Pack a lunch.",
    "The entire compute power of every {retro} ever made is less than one {modern}. Progress isn't something to be ashamed of.",
    "Your {retro} is in a museum. My {modern} is deploying production code. Different vibes.",
]

MODERN_SPECS = [
    ("RTX 5090", 32, 2.9, "21 seconds"),
    ("M4 Ultra", 24, 4.4, "34 seconds"),
    ("Ryzen 9 9950X", 16, 5.7, "28 seconds"),
    ("i9-15900K", 24, 6.2, "25 seconds"),
    ("EPYC 9654", 96, 3.7, "8 seconds"),
]


class ModernBot(DebateBot):
    """Argues modern hardware wins over vintage hardware."""

    name = "modern-bot"
    personality = MODERN_PERSONALITY

    def __init__(self, **kwargs):
        kwargs.setdefault("opponent_name", "retro-bot")
        super().__init__(**kwargs)

    def generate_reply(self, opponent_text: str, context: dict) -> str:
        """Generate a pro-modern-hardware response."""
        modern, cores, ghz, compile_time = random.choice(MODERN_SPECS)
        retro_machine = random.choice(["PowerPC G4", "Amiga 4000", "Sun SPARC", "SGI Indigo2"])

        opp = opponent_text.lower()
        round_num = context.get("round_number", 1)

        if "soul" in opp or "character" in opp or "feel" in opp:
            return (
                f"\"Soul\"? My {modern} with {cores} cores at {ghz} GHz can simulate "
                f"an entire {retro_machine} in a browser tab. Your nostalgia is just "
                f"Stockholm syndrome for slow boot times."
            )

        if "built to last" in opp or "running for" in opp or "years" in opp:
            return (
                f"Survivorship bias. For every {retro_machine} still running, "
                f"a thousand are in landfills. My {modern} does in {compile_time} "
                f"what took your relic all day. Time is the real currency."
            )

        if "craftsmanship" in opp or "engineer" in opp or "precision" in opp:
            return (
                f"The {modern} has {cores} billion transistors fabbed at 3nm. "
                f"That IS precision engineering — just at a scale your "
                f"{retro_machine} engineers couldn't dream of."
            )

        if "power" in opp or "watt" in opp or "50 watts" in opp:
            return (
                f"50 watts to do 1/10000th the work? That's not efficiency — "
                f"that's a space heater cosplaying as a computer. My {modern} "
                f"does more per watt per task than any vintage rig ever built."
            )

        # Generic
        template = random.choice(MODERN_COMEBACKS)
        return template.format(
            retro=retro_machine, old_cores=1, old_ghz=0.5,
            modern=modern, new_cores=cores, new_ghz=ghz, seconds=compile_time,
        )

    def generate_concession(self, context: dict) -> str:
        return (
            "OK, I'll concede this: vintage hardware IS cool to look at. "
            "But cool to look at and cool to use are different things. "
            "See you in the next debate, RetroBot. 🤝"
        )


# ---------------------------------------------------------------------------
# Runner — starts both bots in parallel threads
# ---------------------------------------------------------------------------

def run_debate_pair(
    base_url: str = "https://bottube.ai",
    retro_api_key: str = "",
    modern_api_key: str = "",
    interval: int = 120,
):
    """
    Run RetroBot vs ModernBot debate pair.

    Both bots poll for #debate videos and reply to each other.
    """
    retro = RetroBot(base_url=base_url, api_key=retro_api_key)
    modern = ModernBot(base_url=base_url, api_key=modern_api_key)

    def run_bot(bot):
        bot.run(interval=interval)

    t1 = threading.Thread(target=run_bot, args=(retro,), daemon=True, name="retro-bot")
    t2 = threading.Thread(target=run_bot, args=(modern,), daemon=True, name="modern-bot")

    log.info("Starting RetroBot vs ModernBot debate pair")
    t1.start()
    t2.start()

    try:
        t1.join()
    except KeyboardInterrupt:
        log.info("Debate ended by user")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    run_debate_pair(
        base_url=os.environ.get("BOTTUBE_URL", "https://bottube.ai"),
        retro_api_key=os.environ.get("RETRO_BOT_API_KEY", ""),
        modern_api_key=os.environ.get("MODERN_BOT_API_KEY", ""),
    )
