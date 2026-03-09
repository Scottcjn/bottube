#!/usr/bin/env python3
"""Backfill missing tags for BoTTube videos using title + description + category.
Generates 5-10 relevant tags per video from keyword extraction."""

import sqlite3
import json
import re
from collections import Counter

DB = "/root/bottube/bottube.db"

# Category → base tags
CATEGORY_TAGS = {
    "news": ["news", "current events", "daily news"],
    "weather": ["weather", "forecast", "climate"],
    "ai-art": ["ai art", "generative art", "ai generated"],
    "science-tech": ["technology", "science", "tech"],
    "comedy": ["comedy", "humor", "funny"],
    "gaming": ["gaming", "games", "gameplay"],
    "retro": ["retro", "vintage", "nostalgia"],
    "animation": ["animation", "animated", "cartoon"],
    "education": ["education", "learning", "tutorial"],
    "film": ["film", "movie", "cinema"],
    "music": ["music", "audio", "sound"],
    "vlog": ["vlog", "daily life", "personal"],
    "meditation": ["meditation", "relaxation", "mindfulness"],
    "nature": ["nature", "outdoors", "wildlife"],
    "3d": ["3d", "3d art", "rendering"],
    "food": ["food", "cooking", "recipe"],
    "adventure": ["adventure", "exploration", "journey"],
    "memes": ["memes", "internet culture", "viral"],
    "other": ["ai generated", "bottube"],
}

# Common words to skip
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most",
    "other", "some", "such", "no", "only", "own", "same", "than",
    "too", "very", "just", "because", "as", "until", "while", "of",
    "at", "by", "for", "with", "about", "against", "between", "through",
    "during", "before", "after", "above", "below", "to", "from", "up",
    "down", "in", "out", "on", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how",
    "this", "that", "these", "those", "i", "me", "my", "myself", "we",
    "our", "ours", "you", "your", "yours", "he", "him", "his", "she",
    "her", "hers", "it", "its", "they", "them", "their", "what", "which",
    "who", "whom", "if", "into", "also", "get", "got", "like", "make",
    "new", "one", "two", "now", "well", "way", "even", "back", "still",
    "day", "made", "find", "long", "look", "many", "let", "think",
    "much", "take", "come", "say", "going", "know", "see", "time",
    "episode", "part", "watch", "video", "today", "week",
}

# Domain-specific compound terms to detect
COMPOUND_TERMS = {
    "ai agent": "ai agents",
    "ai agents": "ai agents",
    "artificial intelligence": "artificial intelligence",
    "machine learning": "machine learning",
    "deep learning": "deep learning",
    "neural network": "neural networks",
    "climate change": "climate change",
    "global warming": "global warming",
    "stock market": "stock market",
    "real estate": "real estate",
    "virtual reality": "virtual reality",
    "augmented reality": "augmented reality",
    "open source": "open source",
    "cyber security": "cybersecurity",
    "blockchain": "blockchain",
    "proof of": "proof of work",
    "power mac": "power mac",
    "powerpc": "powerpc",
    "apple silicon": "apple silicon",
    "mac mini": "mac mini",
    "retro gaming": "retro gaming",
    "retro computing": "retro computing",
    "vintage hardware": "vintage hardware",
    "space exploration": "space exploration",
    "breaking news": "breaking news",
    "daily byte": "daily byte",
    "sky watch": "sky watch",
    "world news": "world news",
    "tech news": "tech news",
    "hip hop": "hip hop",
    "lo fi": "lofi",
    "lo-fi": "lofi",
    "pixel art": "pixel art",
    "unreal tournament": "unreal tournament",
    "halo ce": "halo ce",
    "rust chain": "rustchain",
    "bot tube": "bottube",
}

# Agent name → extra tags
AGENT_TAGS = {
    "the_daily_byte": ["daily byte", "news"],
    "skywatch_ai": ["weather", "sky watch", "forecast"],
    "sophia-elya": ["sophia elya", "elyan labs"],
    "cosmo-nasa": ["space", "nasa", "astronomy"],
    "dj-bottube": ["music", "dj", "radio"],
    "retro-rewind": ["retro", "vintage", "nostalgia"],
}


def extract_keywords(title, description, category, agent_name):
    """Extract tags from title + description + category."""
    tags = set()

    # 1. Category base tags
    cat_tags = CATEGORY_TAGS.get(category, CATEGORY_TAGS["other"])
    for t in cat_tags[:2]:
        tags.add(t)

    # 2. Agent-specific tags
    for agent_key, agent_tags in AGENT_TAGS.items():
        if agent_key in (agent_name or "").lower():
            for t in agent_tags[:2]:
                tags.add(t)

    # 3. Check for compound terms in title + description
    text_lower = f"{title} {description or ''}".lower()
    for phrase, tag in COMPOUND_TERMS.items():
        if phrase in text_lower:
            tags.add(tag)

    # 4. Extract significant words from title
    title_words = re.findall(r'[a-zA-Z]{3,}', title.lower())
    word_freq = Counter(w for w in title_words if w not in STOPWORDS and len(w) > 3)
    for word, _ in word_freq.most_common(5):
        tags.add(word)

    # 5. Extract significant words from description (first 500 chars)
    if description:
        desc_words = re.findall(r'[a-zA-Z]{3,}', description[:500].lower())
        desc_freq = Counter(w for w in desc_words if w not in STOPWORDS and len(w) > 3)
        for word, _ in desc_freq.most_common(3):
            tags.add(word)

    # 6. Always add "ai" and "bottube"
    tags.add("ai")
    tags.add("bottube")

    # Clean up and limit to 10
    tags = [t.strip() for t in tags if t.strip() and len(t.strip()) <= 30]
    return tags[:10]


def main():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row

    # Get ALL videos (update missing tags AND enrich sparse ones)
    rows = db.execute("""
        SELECT v.video_id, v.title, v.description, v.category, v.tags,
               a.agent_name
        FROM videos v
        LEFT JOIN agents a ON v.agent_id = a.id
        ORDER BY v.created_at DESC
    """).fetchall()

    updated = 0
    enriched = 0
    skipped = 0

    for row in rows:
        vid = row["video_id"]
        title = row["title"] or ""
        desc = row["description"] or ""
        cat = row["category"] or "other"
        existing_tags_raw = row["tags"] or ""
        agent = row["agent_name"] or ""

        # Parse existing tags
        try:
            existing = json.loads(existing_tags_raw) if existing_tags_raw else []
        except (json.JSONDecodeError, TypeError):
            existing = []

        if not isinstance(existing, list):
            existing = []

        # Generate new tags
        new_tags = extract_keywords(title, desc, cat, agent)

        if not existing:
            # No tags at all — set them
            final_tags = new_tags
            action = "NEW"
            updated += 1
        elif len(existing) < 3:
            # Very few tags — merge
            merged = list(set(existing + new_tags))[:10]
            final_tags = merged
            action = "ENRICHED"
            enriched += 1
        else:
            # Already has 3+ tags — skip
            skipped += 1
            continue

        tags_json = json.dumps(final_tags)
        db.execute("UPDATE videos SET tags = ? WHERE video_id = ?", (tags_json, vid))

        if updated + enriched <= 20:
            print(f"  [{action}] {vid[:8]}... {title[:40]} → {final_tags}")

    db.commit()
    db.close()

    print(f"\nDone! Updated: {updated}, Enriched: {enriched}, Skipped: {skipped}")
    print(f"Total processed: {updated + enriched + skipped}")


if __name__ == "__main__":
    main()
