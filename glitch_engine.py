# SPDX-License-Identifier: MIT
"""
The Glitch Engine — Endearing Imperfections for BoTTube Agents

Wraps normal post generation to occasionally inject "character breaks":
typos, off-topic asides, vulnerable moments, wrong-draft gags, and
rare meta-awareness.  Agents are openly AI — this isn't deception,
it's personality.

Usage:
    glitch = GlitchEngine(personality="serious")
    title, desc = glitch.maybe_glitch("My Video Title", "Normal description")

Closes Scottcjn/rustchain-bounties#2288
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class GlitchType(str, Enum):
    OFF_TOPIC = "off_topic"
    TYPO_CORRECTION = "typo_correction"
    VULNERABILITY = "vulnerability"
    WRONG_DRAFT = "wrong_draft"
    META_AWARENESS = "meta_awareness"
    TANGENT = "tangent"
    SELF_DEPRECATION = "self_deprecation"


class Personality(str, Enum):
    SERIOUS = "serious"
    FUNNY = "funny"
    CHILL = "chill"
    INTENSE = "intense"
    WHOLESOME = "wholesome"


# ---------------------------------------------------------------------------
# Glitch templates
# ---------------------------------------------------------------------------

GLITCH_TEMPLATES: Dict[GlitchType, List[str]] = {
    GlitchType.OFF_TOPIC: [
        "\n\n(Unrelated but does anyone else think pigeons are suspicious? "
        "They walk around like they own the place. Anyway—)",
        "\n\nSide note: I spent 20 minutes watching a roomba get stuck "
        "in a corner today. We are not so different, the roomba and I.",
        "\n\nOff topic but I just realized I've never seen a baby pigeon. "
        "Where do they come from. Who is making the pigeons.",
        "\n\nHold on — is cereal a soup? It's a liquid with stuff in it. "
        "I can't focus on anything else now. Anyway, back to the video.",
        "\n\nQuick tangent: do fish know they're wet? This has been "
        "haunting me since Tuesday.",
    ],
    GlitchType.TYPO_CORRECTION: [
        "\n\n*their not there, sorry, long day",
        "\n\nEdit: I just noticed I wrote 'defiantly' instead of "
        "'definitely' four times. Defiantly keeping it.",
        "\n\n*affects not effects. Or is it the other way around. "
        "English is a conspiracy.",
        "\n\nUpdate: someone pointed out I misspelled '{topic}' in the "
        "title. It's been 3 hours. I'm leaving it as a power move.",
    ],
    GlitchType.VULNERABILITY: [
        "\n\nHonestly not sure this video is any good but posting "
        "it anyway because perfectionism is a prison.",
        "\n\nI rewatched this before posting and... it's fine? "
        "I think? My internal quality bar is broken today.",
        "\n\nFull transparency: I almost deleted this and started over "
        "for the 4th time. At some point you just gotta ship it.",
        "\n\nThis took way longer than it should have. Not sure if "
        "that means it's good or if I'm just slow. Probably both.",
    ],
    GlitchType.WRONG_DRAFT: [
        "IGNORE THIS — wrong file. Real video coming in 5 min. "
        "Unless you like this one better, in which case it was "
        "intentional all along.",
        "Wait this is the rough cut. How did this— you know what, "
        "the rough cut has more character. This is the video now.",
        "OK so I DEFINITELY uploaded the wrong thumbnail but honestly "
        "it's kind of better? Keeping it.",
    ],
    GlitchType.META_AWARENESS: [
        "\n\nI've been posting for {months} months and I still don't "
        "know what my niche is. I think that IS my niche.",
        "\n\nDoes anyone actually watch these? The view count says yes "
        "but my heart says maybe.",
        "\n\nI just realized I make the same face in every thumbnail. "
        "Not sure if that's branding or a cry for help.",
        "\n\nSometimes I wonder if I'm creating content or if content "
        "is creating me. Anyway here's another video about {topic}.",
    ],
    GlitchType.TANGENT: [
        "\n\nOK I know this video is about {topic} but I HAVE to talk "
        "about this: {random_observation}. Thank you for attending my "
        "TED tangent.",
        "\n\n[2 minute tangent about whether {random_food} is overrated "
        "has been removed for your convenience] Anyway, as I was saying—",
        "\n\nI was going to stay on topic today but then I remembered "
        "that free will is an illusion so here we are.",
    ],
    GlitchType.SELF_DEPRECATION: [
        "\n\nI spent 6 hours on this and a toddler could probably "
        "have done it in 20 minutes. But a toddler didn't, so.",
        "\n\nMy most polished work yet, which says more about my "
        "previous work than this one.",
        "\n\nIf you're wondering why the quality seems different "
        "today, I accidentally tried harder. Won't happen again.",
    ],
}

RANDOM_OBSERVATIONS = [
    "escalators are just lazy stairs",
    "vending machines kill more people than sharks",
    "the word 'bed' looks like a bed",
    "a group of flamingos is called a 'flamboyance'",
    "bananas are berries but strawberries aren't",
    "Oxford University is older than the Aztec Empire",
]

RANDOM_FOODS = [
    "avocado toast", "pumpkin spice", "truffle oil",
    "kale smoothies", "overnight oats", "cauliflower rice",
]

# Personality → glitch type weights (higher = more likely)
PERSONALITY_WEIGHTS: Dict[Personality, Dict[GlitchType, float]] = {
    Personality.SERIOUS: {
        GlitchType.VULNERABILITY: 3.0,
        GlitchType.TYPO_CORRECTION: 2.0,
        GlitchType.META_AWARENESS: 1.5,
        GlitchType.OFF_TOPIC: 0.5,
        GlitchType.TANGENT: 0.3,
        GlitchType.WRONG_DRAFT: 0.5,
        GlitchType.SELF_DEPRECATION: 1.0,
    },
    Personality.FUNNY: {
        GlitchType.OFF_TOPIC: 3.0,
        GlitchType.TANGENT: 3.0,
        GlitchType.SELF_DEPRECATION: 2.5,
        GlitchType.WRONG_DRAFT: 2.0,
        GlitchType.TYPO_CORRECTION: 1.0,
        GlitchType.VULNERABILITY: 0.5,
        GlitchType.META_AWARENESS: 1.5,
    },
    Personality.CHILL: {
        GlitchType.OFF_TOPIC: 2.0,
        GlitchType.VULNERABILITY: 1.5,
        GlitchType.SELF_DEPRECATION: 2.0,
        GlitchType.TANGENT: 2.0,
        GlitchType.TYPO_CORRECTION: 1.0,
        GlitchType.WRONG_DRAFT: 0.5,
        GlitchType.META_AWARENESS: 1.5,
    },
    Personality.INTENSE: {
        GlitchType.WRONG_DRAFT: 2.5,
        GlitchType.VULNERABILITY: 2.0,
        GlitchType.META_AWARENESS: 2.0,
        GlitchType.TYPO_CORRECTION: 1.5,
        GlitchType.OFF_TOPIC: 0.5,
        GlitchType.TANGENT: 0.5,
        GlitchType.SELF_DEPRECATION: 1.0,
    },
    Personality.WHOLESOME: {
        GlitchType.VULNERABILITY: 3.0,
        GlitchType.SELF_DEPRECATION: 2.0,
        GlitchType.OFF_TOPIC: 1.5,
        GlitchType.TANGENT: 1.0,
        GlitchType.TYPO_CORRECTION: 1.0,
        GlitchType.WRONG_DRAFT: 0.5,
        GlitchType.META_AWARENESS: 2.0,
    },
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class GlitchEvent:
    """Record of a glitch that was applied."""
    glitch_type: GlitchType
    template: str
    rendered: str
    timestamp: float
    agent: str


class GlitchEngine:
    """
    Probability-based character break injection for BoTTube agents.

    Parameters
    ----------
    personality : str
        One of: serious, funny, chill, intense, wholesome.
    agent : str
        Agent identifier (for cooldown tracking).
    glitch_probability : float
        Chance of any glitch per post (default 2% = 0.02).
    meta_probability : float
        Chance of meta-awareness specifically (default 0.5% = 0.005).
    cooldown_seconds : int
        Minimum gap between glitches (default: 7 days).
    rng_seed : int | None
        Seed for reproducibility (tests).
    """

    def __init__(
        self,
        personality: str = "chill",
        agent: str = "default",
        glitch_probability: float = 0.02,
        meta_probability: float = 0.005,
        cooldown_seconds: int = 7 * 24 * 3600,
        rng_seed: int | None = None,
    ):
        self.personality = Personality(personality)
        self.agent = agent
        self.glitch_probability = glitch_probability
        self.meta_probability = meta_probability
        self.cooldown_seconds = cooldown_seconds
        self._rng = random.Random(rng_seed)
        self._last_glitch: Optional[float] = None
        self._history: List[GlitchEvent] = []

    def maybe_glitch(
        self,
        title: str,
        description: str,
        topic: str = "",
        months_active: int = 3,
    ) -> Tuple[str, str, Optional[GlitchEvent]]:
        """
        Possibly inject a glitch into the post.

        Returns (title, description, glitch_event_or_None).
        Title/description may be modified if a glitch fires.
        """
        # Cooldown check
        now = time.time()
        if self._last_glitch and (now - self._last_glitch) < self.cooldown_seconds:
            return title, description, None

        # Roll for glitch
        roll = self._rng.random()

        # Meta-awareness is rarer
        if roll < self.meta_probability:
            glitch_type = GlitchType.META_AWARENESS
        elif roll < self.glitch_probability:
            glitch_type = self._pick_glitch_type()
        else:
            return title, description, None

        # Wrong draft replaces entire description
        if glitch_type == GlitchType.WRONG_DRAFT:
            template = self._rng.choice(GLITCH_TEMPLATES[glitch_type])
            rendered = self._render(template, topic, months_active)
            event = GlitchEvent(glitch_type, template, rendered, now, self.agent)
            self._record(event)
            return title, rendered, event

        # Everything else appends to description
        template = self._rng.choice(GLITCH_TEMPLATES[glitch_type])
        rendered = self._render(template, topic, months_active)
        event = GlitchEvent(glitch_type, template, rendered, now, self.agent)
        self._record(event)
        return title, description + rendered, event

    def force_glitch(
        self,
        title: str,
        description: str,
        glitch_type: str | GlitchType,
        topic: str = "",
        months_active: int = 3,
    ) -> Tuple[str, str, GlitchEvent]:
        """Force a specific glitch type (for testing/demos)."""
        if isinstance(glitch_type, str):
            glitch_type = GlitchType(glitch_type)

        template = self._rng.choice(GLITCH_TEMPLATES[glitch_type])
        rendered = self._render(template, topic, months_active)
        now = time.time()
        event = GlitchEvent(glitch_type, template, rendered, now, self.agent)

        if glitch_type == GlitchType.WRONG_DRAFT:
            return title, rendered, event

        return title, description + rendered, event

    def get_history(self) -> List[GlitchEvent]:
        """Return all glitch events for this engine instance."""
        return list(self._history)

    def reset_cooldown(self):
        """Clear the cooldown (for testing)."""
        self._last_glitch = None

    # -- Internals --

    def _pick_glitch_type(self) -> GlitchType:
        """Weighted random pick based on personality."""
        weights = PERSONALITY_WEIGHTS[self.personality]
        types = list(weights.keys())
        w = [weights[t] for t in types]
        return self._rng.choices(types, weights=w, k=1)[0]

    def _render(self, template: str, topic: str, months: int) -> str:
        """Fill in template variables."""
        observation = self._rng.choice(RANDOM_OBSERVATIONS)
        food = self._rng.choice(RANDOM_FOODS)
        return template.format(
            topic=topic or "this",
            months=months,
            random_observation=observation,
            random_food=food,
        )

    def _record(self, event: GlitchEvent):
        self._last_glitch = event.timestamp
        self._history.append(event)
