import random
from typing import List

def generate_rap_battle(topic: str, personas: List[dict]) -> dict:
    """
    Generate 4-6 rap verses alternating between two personas.

    Args:
        topic (str): Theme of the rap battle (e.g., "Python vs Rust").
        personas (List[dict]): List of persona details, where each persona has "name" and "style".

    Returns:
        dict: A structured dictionary containing the topic, personas, and generated verse exchanges.
    """
    if len(personas) != 2:
        raise ValueError("Exactly two personas are required.")

    verses = []
    themes = topic.split(" vs ") if " vs " in topic else [topic, topic]

    for i in range(random.randint(4, 6)):  # Randomize 4-6 verses
        persona = personas[i % 2]
        style = persona.get("style", "")

        verse = (
            f"{persona['name']} ({style}) spits:\n            '{generate_line(themes[i % 2], style)}'"
        )
        verses.append(verse)

    return {
        "topic": topic,
        "personas": [persona["name"] for persona in personas],
        "battle": verses,
    }

def generate_line(theme: str, style: str) -> str:
    """Generate a single line mimicking a persona's style based on the theme."""
    templates = [
        f"Straight from the heart — {theme}, that's my art.",
        f"Old-school hitting hard, like a {theme} shard.",
        f"Mumble rap vibes on {theme}, we all survive.",
        f"{theme}'s my domain, better check my campaign.",
    ]
    return random.choice(templates)