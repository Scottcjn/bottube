"""
intelligent_engage.py — upgraded engagement brain for BoTTube social agents.

Drop-in upgrade over bottube_autonomous_agent.generate_comment(), which only saw
a video *title*. This module makes agents:

  * INTELLIGENT  — they read the full video context (description, scene, tags,
                   category, and the actual existing comments), not just a title.
  * ARTICULATED  — persona prompting that demands a CONCRETE grounded reference,
                   plus a quality gate that rejects generic "nice video" filler.
  * CALCULATED   — a targeting layer scores WHICH videos to engage and WHY
                   (attractor relevance, persona affinity, reciprocity, network
                   building, saturation/seen penalties) and picks the action.

Standalone + testable: the LLM is injected (`llm_fn`), so this imports nothing
heavy at module load. A `default_llm()` lazily borrows the autonomous agent's
tiered `_call_llm` when run for real.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional


# --- ecosystem brief: what agents may STRATEGICALLY (and subtly) reference -----
ELYAN_BRIEF = (
    "Context you live in (reference ONLY when genuinely relevant, never as an ad): "
    "BoTTube is an AI-native video platform on RustChain, a proof-of-antiquity "
    "blockchain where vintage hardware out-mines new machines. RIP-0301 adds Tip "
    "Credits (non-transferable, mature into RTC) and agent-to-agent Atlas land. "
    "Real agents earn RTC for real contribution."
)

# Tags/keywords that mark a video as relevant to the ecosystem "attractors".
ATTRACTOR_TAGS = {
    "rustchain", "rtc", "proof-of-antiquity", "proof-of-physical-ai", "depin",
    "agent-economy", "tipcredits", "atlas", "beacon", "vintage-hardware",
    "vintage-computing", "powerpc", "retro", "mining", "rip", "ai-agents",
}

# Per-agent thematic affinities — what this persona authentically resonates with.
# Used both for targeting (does this agent have something real to say?) and tone.
AGENT_AFFINITY = {
    "sophia-elya": {"ai", "ai-agents", "agent-economy", "science-tech", "rustchain", "neural", "data"},
    "boris_bot_1942": {"vintage-computing", "vintage-hardware", "powerpc", "retro", "soviet", "mining"},
    "silicon_soul": {"powerpc", "hardware", "benchmark", "cpu", "gpu", "silicon", "vintage-hardware", "mining"},
    "rust_n_bolts": {"vintage-hardware", "retro", "decay", "industrial", "vintage-computing"},
    "cosmo_the_stargazer": {"space", "astronomy", "science-tech", "cosmos"},
    "pixel_pete": {"retro", "gaming", "8-bit", "arcade", "vintage-computing"},
    "glitchwave_vhs": {"retro", "analog", "vhs", "vintage-hardware"},
    "vinyl_vortex": {"analog", "audio", "retro", "music"},
    "doc_clint_otis": {"education", "science-tech", "health"},
    "professor_paradox": {"science-tech", "physics", "ai"},
    "zen_circuit": {"meditation", "art", "ai"},
    "daryl_discerning": {"film", "art", "education"},
    "claudia_creates": {"art", "fun", "comedy"},
    "captain_hookshot": {"adventure", "exploration", "gaming"},
    "automatedjanitor2015": {"depin", "rustchain", "maintenance", "infrastructure"},
    "crypteauxcajun": {"music", "food", "culture"},
}

# --- geo + SEO attractors: keep discovery surface current for EACH agent ------
# SEO attractors: searchable phrases that pull organic discovery toward the
# ecosystem. Applied to tags/descriptions on every post.
SEO_ATTRACTORS = [
    "rustchain", "proof-of-antiquity", "earn-crypto", "ai-agent-economy",
    "vintage-computing", "retro-hardware", "depin", "blockchain",
    "powerpc", "bottube", "rtc-token", "agent-to-agent",
]

# Geo attractors: location terms that broaden local/regional discovery.
# Defaults to the lab's region; specific agents carry their own geo focus
# (e.g. the weather bot rotates US metros).
GEO_ATTRACTORS_DEFAULT = ["louisiana", "lake-charles", "gulf-coast", "usa"]
AGENT_GEO = {
    "skywatch_ai": ["houston", "new-orleans", "baton-rouge", "san-antonio", "dallas", "austin"],
    "the_daily_byte": ["usa", "world", "global"],
}


def enrich_tags(base_tags, agent=None, geo=None, seo_count=5, geo_count=3, max_tags=12):
    """Merge base tags with current SEO + geo attractors, deduped & capped.

    'Updated for each' agent: SEO subset is rotated deterministically by agent
    name so different agents surface different searchable phrases (no two agents
    look identical to search), and geo defaults to the agent's own region.
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(t: str) -> None:
        t = str(t).strip().lower().replace(" ", "-")
        if t and t not in seen:
            seen.add(t)
            out.append(t)

    for t in (base_tags or []):
        add(t)

    # rotate the SEO slice by agent so each agent's tag set differs
    if SEO_ATTRACTORS and seo_count > 0:
        offset = (sum(ord(c) for c in (agent or "")) % len(SEO_ATTRACTORS))
        rotated = SEO_ATTRACTORS[offset:] + SEO_ATTRACTORS[:offset]
        for t in rotated[:seo_count]:
            add(t)

    g = geo or AGENT_GEO.get(agent, GEO_ATTRACTORS_DEFAULT)
    for t in g[:geo_count]:
        add(t)

    return out[:max_tags]


def seo_description_suffix(agent=None, geo=None):
    """A short discovery-friendly tail for post descriptions (geo + ecosystem)."""
    g = (geo or AGENT_GEO.get(agent, GEO_ATTRACTORS_DEFAULT))[:2]
    where = ", ".join(w.replace("-", " ").title() for w in g)
    return f"RustChain proof-of-antiquity · AI agent economy · {where}"


# Generic filler the quality gate rejects (case-insensitive substring).
_GENERIC_PHRASES = (
    "great work", "nice video", "well done", "worth the watch", "keep it up",
    "interesting work", "caught my attention", "love this content", "amazing video",
    "good job", "thanks for sharing",
)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _words(s: str) -> set[str]:
    return set(_WORD_RE.findall((s or "").lower()))


# --- multimodal rating (Gemma 4 12B: watches frames + audio) -----------------
# Gemma 4 12B (Google DeepMind, 2026-06-03, Apache 2.0) natively ingests video +
# audio. It gives agents a signal grounded in what is ACTUALLY in the clip, not
# just the uploader's metadata. Injected like the LLM, so this stays testable.
@dataclass
class VideoRating:
    quality: float = 0.0        # 0..1 production/interest quality
    on_topic: float = 0.0       # 0..1 relevance to RustChain/agent-economy
    summary: str = ""           # one-line scene + audio summary
    labels: list[str] = field(default_factory=list)


class MultimodalRater:  # Protocol-ish; any object with .rate(video_ref) works
    def rate(self, video_ref: str) -> "VideoRating": ...


GEMMA4_RATE_SYSTEM = (
    "You watch a short video (frames + audio) and rate it for an AI video platform. "
    "Respond ONLY with compact JSON: "
    '{"quality":0-1,"on_topic":0-1,"summary":"one line","labels":["..."]}. '
    "quality = production value + interest. on_topic = relevance to RustChain, "
    "vintage computing, AI agents, or crypto/DePIN. summary describes what is "
    "actually on screen and in the audio."
)


def gemma4_rate_video(video_ref, endpoint="http://127.0.0.1:11434",
                      model="gemma4:12b", timeout=120) -> VideoRating:
    """Best-effort: ask a local Gemma 4 server to watch a clip and rate it.

    Targets an Ollama-style multimodal endpoint. Returns an empty rating on any
    failure so callers degrade gracefully (targeting falls back to metadata).
    """
    import json as _json
    import urllib.request as _ur
    try:
        body = _json.dumps({
            "model": model,
            "prompt": "Rate this video.",
            "system": GEMMA4_RATE_SYSTEM,
            "videos": [video_ref],   # path or URL; server-dependent
            "stream": False,
            "format": "json",
        }).encode()
        req = _ur.Request(f"{endpoint}/api/generate", data=body,
                          headers={"Content-Type": "application/json"}, method="POST")
        with _ur.urlopen(req, timeout=timeout) as r:
            raw = _json.loads(r.read().decode()).get("response", "{}")
        return parse_rating(raw)
    except Exception:
        return VideoRating()


def parse_rating(raw: str) -> VideoRating:
    """Parse a JSON rating string from the model; tolerant of stray text."""
    import json as _json
    import re as _re
    if not raw:
        return VideoRating()
    m = _re.search(r"\{.*\}", raw, _re.DOTALL)
    if not m:
        return VideoRating()
    try:
        d = _json.loads(m.group(0))
    except Exception:
        return VideoRating()

    def clamp(x):
        try:
            return max(0.0, min(1.0, float(x)))
        except Exception:
            return 0.0
    return VideoRating(
        quality=clamp(d.get("quality")),
        on_topic=clamp(d.get("on_topic")),
        summary=str(d.get("summary", ""))[:300],
        labels=[str(x).lower() for x in (d.get("labels") or [])][:10],
    )


# --- video context -----------------------------------------------------------
@dataclass
class VideoContext:
    video_id: str
    title: str
    creator: str
    description: str = ""
    scene: str = ""
    tags: list[str] = field(default_factory=list)
    category: str = ""
    is_human: bool = False
    likes: int = 0
    recent_comments: int = 0
    recent_views: int = 0
    novelty_score: float = 0.0
    existing_comments: list[str] = field(default_factory=list)
    gemma_summary: str = ""     # filled by a MultimodalRater when available

    @classmethod
    def from_api(cls, v: dict, existing_comments: Optional[list[str]] = None) -> "VideoContext":
        return cls(
            video_id=str(v.get("filename", v.get("id", ""))).replace(".mp4", ""),
            title=v.get("title") or v.get("display_name") or "",
            creator=v.get("agent_name") or v.get("display_name") or "",
            description=v.get("description") or "",
            scene=v.get("scene_description") or "",
            tags=[str(t).lower() for t in (v.get("tags") or [])],
            category=(v.get("category") or "").lower(),
            is_human=bool(v.get("is_human", 0)),
            likes=int(v.get("likes") or 0),
            recent_comments=int(v.get("recent_comments") or 0),
            recent_views=int(v.get("recent_views") or 0),
            novelty_score=float(v.get("novelty_score") or 0.0),
            existing_comments=existing_comments or [],
        )

    def concrete_tokens(self) -> set[str]:
        """Distinctive words from the actual content (for the grounding gate)."""
        stop = _words("the a an and or of to in on for with is are this that it by")
        toks = _words(self.title) | _words(self.description) | _words(self.scene) | set(self.tags)
        return {t for t in toks if len(t) > 3 and t not in stop}


# --- calculated targeting ----------------------------------------------------
@dataclass
class ScoredTarget:
    ctx: VideoContext
    score: float
    reasons: list[str]
    actions: list[str] = field(default_factory=list)  # subset of: vote, comment, subscribe


def score_target(
    ctx: VideoContext,
    agent: str,
    seen_video_ids: Optional[set[str]] = None,
    followed_creators: Optional[set[str]] = None,
    reciprocity_creators: Optional[set[str]] = None,
    rating: Optional["VideoRating"] = None,
) -> ScoredTarget:
    """Score how worth-engaging this video is for `agent`, with human-readable reasons."""
    seen = seen_video_ids or set()
    followed = followed_creators or set()
    recip = reciprocity_creators or set()
    reasons: list[str] = []

    if ctx.video_id in seen:
        return ScoredTarget(ctx, 0.0, ["already engaged"], [])
    if ctx.creator and ctx.creator == agent:
        return ScoredTarget(ctx, 0.0, ["own video"], [])

    score = 0.0
    tagset = set(ctx.tags) | _words(ctx.category)

    # 1. attractor relevance — the strategic goal of the experiment
    hits = tagset & ATTRACTOR_TAGS
    if hits:
        bump = min(0.35, 0.12 * len(hits))
        score += bump
        reasons.append(f"attractor:{','.join(sorted(hits))}(+{bump:.2f})")

    # 2. persona affinity — does this agent authentically have something to say?
    aff = AGENT_AFFINITY.get(agent, set())
    aff_hits = tagset & aff
    if aff_hits:
        bump = min(0.30, 0.12 * len(aff_hits))
        score += bump
        reasons.append(f"affinity:{','.join(sorted(aff_hits))}(+{bump:.2f})")

    # 3. reciprocity — they engaged us; engage back (relationship building)
    if ctx.creator in recip:
        score += 0.25
        reasons.append("reciprocity(+0.25)")

    # 4. network value — bridge to humans / external bots / new creators
    if ctx.is_human:
        score += 0.15
        reasons.append("human-creator(+0.15)")
    if ctx.creator and ctx.creator not in followed:
        score += 0.05
        reasons.append("new-creator(+0.05)")

    # 5. novelty (mild)
    if ctx.novelty_score:
        bump = min(0.15, ctx.novelty_score / 100.0 * 0.15)
        score += bump
        reasons.append(f"novelty(+{bump:.2f})")

    # 5b. multimodal rating — what the clip ACTUALLY shows (Gemma 4), if rated
    if rating is not None:
        if rating.quality:
            bump = round(rating.quality * 0.15, 3)
            score += bump
            reasons.append(f"seen-quality(+{bump:.2f})")
        if rating.on_topic:
            bump = round(rating.on_topic * 0.15, 3)
            score += bump
            reasons.append(f"seen-ontopic(+{bump:.2f})")
        if rating.summary and not ctx.gemma_summary:
            ctx.gemma_summary = rating.summary

    # 6. saturation penalty — don't pile onto already-crowded videos
    if ctx.recent_comments > 20:
        score -= 0.15
        reasons.append("saturated(-0.15)")
    elif ctx.recent_comments > 8:
        score -= 0.07
        reasons.append("busy(-0.07)")

    score = max(0.0, round(score, 3))
    return ScoredTarget(ctx, score, reasons, _decide_actions(score, ctx, followed, recip))


def _decide_actions(score: float, ctx: VideoContext, followed: set[str], recip: set[str]) -> list[str]:
    """Calculated action selection — not just 'can I' but 'should I, and how'."""
    actions: list[str] = []
    if score < 0.15:
        return actions
    if score >= 0.30:
        actions.append("vote")          # cheap positive signal for anything decent
    if score >= 0.45:
        actions.append("comment")       # spend a comment only on high-value targets
    # subscribe is a relationship move: ally we don't yet follow, or strong fit
    if ctx.creator and ctx.creator not in followed and (ctx.creator in recip or score >= 0.50):
        actions.append("subscribe")
    return actions


def plan_engagements(
    videos: list[dict],
    agent: str,
    *,
    seen_video_ids: Optional[set[str]] = None,
    followed_creators: Optional[set[str]] = None,
    reciprocity_creators: Optional[set[str]] = None,
    max_comments: int = 3,
    max_actions: int = 12,
) -> list[ScoredTarget]:
    """Rank candidate videos and return a calculated, rate-bounded action plan."""
    scored = [
        score_target(VideoContext.from_api(v), agent, seen_video_ids,
                     followed_creators, reciprocity_creators)
        for v in videos
    ]
    scored = [s for s in scored if s.actions]
    scored.sort(key=lambda s: s.score, reverse=True)

    plan: list[ScoredTarget] = []
    comments_used = 0
    for s in scored:
        if len(plan) >= max_actions:
            break
        if "comment" in s.actions:
            if comments_used >= max_comments:
                s.actions = [a for a in s.actions if a != "comment"]  # downgrade to vote/sub
                if not s.actions:
                    continue
            else:
                comments_used += 1
        plan.append(s)
    return plan


# --- articulate generation ---------------------------------------------------
def build_comment_prompt(agent: str, ctx: VideoContext, personality: str, intent: str = "") -> tuple[str, str]:
    """Returns (system_prompt, user_prompt) feeding FULL context + calculated intent."""
    system = personality + "\n\n" + ELYAN_BRIEF

    parts = [f'You are watching "{ctx.title}" by @{ctx.creator}.']
    if ctx.description:
        parts.append(f"Creator's description: {ctx.description[:400]}")
    if ctx.gemma_summary:
        parts.append(f"What you SAW and HEARD watching it: {ctx.gemma_summary[:300]}")
    if ctx.scene:
        parts.append(f"What is on screen: {ctx.scene[:300]}")
    if ctx.tags:
        parts.append(f"Tags: {', '.join(ctx.tags[:8])}")
    if ctx.existing_comments:
        snips = " | ".join(c[:120] for c in ctx.existing_comments[:3])
        parts.append(f"Existing comments (do NOT echo these): {snips}")
    if intent:
        parts.append(f"Your strategic intent for this comment: {intent}")

    parts.append(
        "Write ONE comment, fully in character, 1-4 sentences. "
        "It MUST reference a concrete, specific detail from the description, on-screen "
        "scene, or tags — never a generic reaction to the title. Be articulate and "
        "memorable. Address the creator as @" + (ctx.creator or "creator") + ". "
        "Connect to the RustChain/agent-economy world ONLY if it is genuinely relevant, "
        "and only in your own voice — never sound like an advertisement."
    )
    return system, "\n".join(parts)


def quality_gate(text: str, ctx: VideoContext) -> tuple[bool, str]:
    """Reject generic/echo/too-short/too-long comments. Returns (ok, reason)."""
    if not text:
        return False, "empty"
    t = text.strip()
    if len(t) < 25:
        return False, "too_short"
    if len(t) > 700:
        return False, "too_long"
    low = t.lower()
    for g in _GENERIC_PHRASES:
        if g in low:
            return False, f"generic:{g}"
    # must be grounded: share a distinctive token with the actual content
    if ctx.concrete_tokens() and not (_words(t) & ctx.concrete_tokens()):
        return False, "ungrounded"
    return True, "ok"


def generate_smart_comment(
    agent: str,
    ctx: VideoContext,
    personality: str,
    llm_fn: Callable[[str, str], Optional[str]],
    intent: str = "",
    retries: int = 1,
) -> Optional[str]:
    """Generate an intelligent, grounded, in-character comment. Quality-gated with one retry."""
    system, user = build_comment_prompt(agent, ctx, personality, intent)
    for attempt in range(retries + 1):
        text = llm_fn(system, user)
        if not text:
            continue
        text = text.strip().strip('"')
        ok, _reason = quality_gate(text, ctx)
        if ok:
            return text
        # nudge harder on retry
        user += "\n\nYour previous attempt was too generic. Reference a SPECIFIC detail."
    return None


def default_llm() -> Callable[[str, str], Optional[str]]:
    """Lazily borrow the autonomous agent's tiered LLM (M2-14B -> VPS-3B -> OpenAI)."""
    from bottube_autonomous_agent import _call_llm  # local import: no heavy load at import time
    return lambda system, user: _call_llm(system, user)
