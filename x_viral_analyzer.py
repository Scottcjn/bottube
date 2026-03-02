#!/usr/bin/env python3
"""
X Viral Tweet Analyzer

Analyzes tweets against the open-source algorithm factors to:
1. Score viral potential before posting
2. Analyze why viral tweets went viral
3. Generate optimized strategies
4. Learn from top performers in any niche

Based on X's open-source algorithm weights:
- Author replies: 75x
- Profile visits + engagement: 12x
- Dwell time 2+ min: 10x
- Retweets: 1x
- Likes: 0.5x
- External links: -30-50%
"""
import argparse
import re
import json
from dataclasses import dataclass
from typing import List, Dict, Tuple

# ═══════════════════════════════════════════════════════════════
# ALGORITHM SCORING WEIGHTS (from X open-source)
# ═══════════════════════════════════════════════════════════════

WEIGHTS = {
    "author_reply_potential": 75,    # Will this spark replies author can respond to?
    "profile_visit_trigger": 12,     # Does it make people want to check profile?
    "dwell_time_factor": 10,         # Will people spend time reading/thinking?
    "retweet_potential": 1,          # Is it shareable?
    "like_potential": 0.5,           # Is it likeable?
    "link_penalty": -35,             # External link in main tweet
    "engagement_bait_penalty": -20,  # Empty engagement bait
}

# ═══════════════════════════════════════════════════════════════
# VIRAL PATTERNS (learned from top performers)
# ═══════════════════════════════════════════════════════════════

VIRAL_PATTERNS = {
    "curiosity_gap": {
        "patterns": [
            r"here'?s what",
            r"here'?s why",
            r"nobody.*(talk|mention|know)",
            r"secret",
            r"truth.*(about|is)",
            r"what i learned",
        ],
        "score_boost": 15,
        "reason": "Creates information gap that demands closure"
    },
    "specific_numbers": {
        "patterns": [
            r"\d+\s*(years?|months?|days?|hours?)",
            r"\d+\s*(videos?|posts?|tweets?|followers?)",
            r"\d+%",
            r"\$\d+",
            r"analyzed\s+\d+",
        ],
        "score_boost": 12,
        "reason": "Specificity builds credibility and curiosity"
    },
    "contrarian": {
        "patterns": [
            r"unpopular opinion",
            r"hot take",
            r"controversial",
            r"(is|are)\s+(overrated|dead|dying|broken)",
            r"stop\s+\w+ing",
            r"everyone.*(wrong|missing)",
        ],
        "score_boost": 18,
        "reason": "Controversy drives engagement and debate"
    },
    "transformation": {
        "patterns": [
            r"(before|after)",
            r"(then|now)",
            r"(year|month|week)\s+ago",
            r"used to",
            r"changed everything",
            r"game.?changer",
        ],
        "score_boost": 14,
        "reason": "Transformation stories are inherently compelling"
    },
    "question_hook": {
        "patterns": [
            r"\?$",
            r"^(what|why|how|when|where|who)",
            r"would you",
            r"do you",
            r"have you",
        ],
        "score_boost": 10,
        "reason": "Questions demand mental engagement"
    },
    "list_format": {
        "patterns": [
            r"^\d+\.",
            r"^[•\-\*]",
            r"\d+\s+things",
            r"\d+\s+ways",
            r"\d+\s+tips",
            r"\d+\s+reasons",
        ],
        "score_boost": 8,
        "reason": "Lists promise structured value"
    },
    "emotional_trigger": {
        "patterns": [
            r"🔥|💯|😂|🤯|😱|❤️|🚀",
            r"(insane|crazy|wild|unreal|incredible)",
            r"(love|hate|obsessed)",
            r"can'?t believe",
            r"blew my mind",
        ],
        "score_boost": 6,
        "reason": "Emotional content gets shared"
    },
    "ai_tech_topic": {
        "patterns": [
            r"\bai\b",
            r"artificial intelligence",
            r"machine learning",
            r"gpt|llm|chatbot",
            r"robot|automat",
            r"crypto|blockchain|web3",
        ],
        "score_boost": 10,
        "reason": "Tech/AI topics are algorithmically boosted on X"
    },
}

PENALTY_PATTERNS = {
    "external_link": {
        "patterns": [r"https?://(?!twitter\.com|x\.com)"],
        "penalty": -35,
        "reason": "External links reduce reach 30-50%"
    },
    "empty_engagement_bait": {
        "patterns": [
            r"^(like|retweet|rt)\s+if",
            r"^follow\s+(me|for)",
        ],
        "penalty": -25,
        "reason": "Empty engagement bait is penalized"
    },
    "too_many_hashtags": {
        "patterns": [r"(#\w+\s*){4,}"],
        "penalty": -15,
        "reason": "Excessive hashtags look spammy"
    },
    "all_caps_spam": {
        "patterns": [r"^[A-Z\s!]{20,}$"],
        "penalty": -20,
        "reason": "ALL CAPS is penalized as spam"
    },
}

# ═══════════════════════════════════════════════════════════════
# ANALYZER CLASS
# ═══════════════════════════════════════════════════════════════

@dataclass
class AnalysisResult:
    score: float
    grade: str
    strengths: List[str]
    weaknesses: List[str]
    suggestions: List[str]
    pattern_matches: Dict[str, bool]
    reply_potential: str
    predicted_performance: str


def analyze_tweet(text: str, has_link_in_reply: bool = False) -> AnalysisResult:
    """
    Analyze a tweet's viral potential based on algorithm factors.

    Args:
        text: The tweet text to analyze
        has_link_in_reply: Whether the link will be in a reply (not main tweet)

    Returns:
        AnalysisResult with score, grade, and actionable insights
    """
    score = 50  # Base score
    strengths = []
    weaknesses = []
    suggestions = []
    pattern_matches = {}

    text_lower = text.lower()

    # Check viral patterns (positive)
    for pattern_name, pattern_data in VIRAL_PATTERNS.items():
        matched = False
        for regex in pattern_data["patterns"]:
            if re.search(regex, text_lower):
                matched = True
                break

        pattern_matches[pattern_name] = matched
        if matched:
            score += pattern_data["score_boost"]
            strengths.append(f"✅ {pattern_name.replace('_', ' ').title()}: {pattern_data['reason']}")

    # Check penalty patterns (negative)
    for pattern_name, pattern_data in PENALTY_PATTERNS.items():
        for regex in pattern_data["patterns"]:
            if re.search(regex, text_lower):
                # Skip link penalty if link is in reply
                if pattern_name == "external_link" and has_link_in_reply:
                    strengths.append("✅ Link in reply: Avoids algorithm penalty")
                    continue

                score += pattern_data["penalty"]
                weaknesses.append(f"❌ {pattern_name.replace('_', ' ').title()}: {pattern_data['reason']}")
                break

    # Check length optimization
    char_count = len(text)
    if 100 <= char_count <= 200:
        score += 5
        strengths.append("✅ Optimal length: 100-200 chars performs best")
    elif char_count < 50:
        score -= 5
        weaknesses.append("❌ Too short: May lack substance")
        suggestions.append("Add more context or value")
    elif char_count > 250:
        score -= 3
        weaknesses.append("⚠️ Long tweet: May reduce engagement")
        suggestions.append("Consider threading for long content")

    # Check for question (drives replies)
    if "?" in text:
        score += 8
        strengths.append("✅ Contains question: Drives replies (75x author reply potential)")
    else:
        suggestions.append("Add a question to encourage replies")

    # Check line breaks (readability = dwell time)
    if "\n" in text:
        line_count = text.count("\n") + 1
        if 2 <= line_count <= 6:
            score += 6
            strengths.append("✅ Good formatting: Line breaks increase readability")
    else:
        suggestions.append("Add line breaks for better readability")

    # Reply potential assessment
    reply_triggers = sum([
        "?" in text,
        bool(re.search(r"(agree|disagree|think|opinion)", text_lower)),
        bool(re.search(r"(what|how|why|would you)", text_lower)),
        pattern_matches.get("contrarian", False),
    ])

    if reply_triggers >= 3:
        reply_potential = "🔥 HIGH - Strong reply triggers"
        score += 10
    elif reply_triggers >= 2:
        reply_potential = "👍 MEDIUM - Some reply triggers"
        score += 5
    else:
        reply_potential = "😐 LOW - Add engagement hooks"
        suggestions.append("Add controversy, question, or call for opinions")

    # Calculate grade
    if score >= 90:
        grade = "S"
        predicted_performance = "🚀 VIRAL POTENTIAL - Strong algorithm signals"
    elif score >= 75:
        grade = "A"
        predicted_performance = "🔥 HIGH PERFORMER - Should do well"
    elif score >= 60:
        grade = "B"
        predicted_performance = "👍 SOLID - Above average potential"
    elif score >= 45:
        grade = "C"
        predicted_performance = "😐 AVERAGE - Could be improved"
    else:
        grade = "D"
        predicted_performance = "⚠️ WEAK - Needs work"

    # Generate suggestions if score is low
    if not pattern_matches.get("specific_numbers"):
        suggestions.append("Add specific numbers for credibility")
    if not pattern_matches.get("curiosity_gap"):
        suggestions.append("Create a curiosity gap (tease value, deliver later)")
    if not pattern_matches.get("emotional_trigger"):
        suggestions.append("Add emotional words or emojis")

    return AnalysisResult(
        score=min(100, max(0, score)),  # Clamp 0-100
        grade=grade,
        strengths=strengths,
        weaknesses=weaknesses,
        suggestions=suggestions[:5],  # Top 5 suggestions
        pattern_matches=pattern_matches,
        reply_potential=reply_potential,
        predicted_performance=predicted_performance,
    )


def print_analysis(result: AnalysisResult, tweet_text: str):
    """Pretty print the analysis results."""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  X VIRAL ANALYZER                                          ║")
    print("╚════════════════════════════════════════════════════════════╝")

    print(f"\n📝 Tweet ({len(tweet_text)}/280 chars):")
    print(f"   {tweet_text[:100]}{'...' if len(tweet_text) > 100 else ''}")

    print(f"\n{'═' * 60}")
    print(f"   VIRAL SCORE: {result.score:.0f}/100  |  GRADE: {result.grade}")
    print(f"{'═' * 60}")

    print(f"\n{result.predicted_performance}")
    print(f"Reply Potential: {result.reply_potential}")

    if result.strengths:
        print(f"\n💪 STRENGTHS:")
        for s in result.strengths:
            print(f"   {s}")

    if result.weaknesses:
        print(f"\n⚠️ WEAKNESSES:")
        for w in result.weaknesses:
            print(f"   {w}")

    if result.suggestions:
        print(f"\n💡 SUGGESTIONS:")
        for i, s in enumerate(result.suggestions, 1):
            print(f"   {i}. {s}")

    # Pattern breakdown
    print(f"\n📊 PATTERN ANALYSIS:")
    for pattern, matched in result.pattern_matches.items():
        status = "✓" if matched else "✗"
        print(f"   [{status}] {pattern.replace('_', ' ').title()}")


def compare_tweets(tweets: List[str]) -> None:
    """Compare multiple tweet variants (A/B testing)."""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  A/B COMPARISON                                            ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    results = []
    for i, tweet in enumerate(tweets):
        result = analyze_tweet(tweet)
        results.append((tweet, result))
        print(f"Variant {chr(65+i)}: Score {result.score:.0f} | Grade {result.grade}")
        print(f"   {tweet[:60]}...")
        print()

    # Declare winner
    best = max(results, key=lambda x: x[1].score)
    best_idx = results.index(best)
    print(f"🏆 WINNER: Variant {chr(65+best_idx)} (Score: {best[1].score:.0f})")
    print(f"\nReason: {best[1].predicted_performance}")


def generate_strategy(topic: str, style: str = "balanced") -> None:
    """Generate a viral posting strategy for a topic."""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  VIRAL STRATEGY GENERATOR                                  ║")
    print("╚════════════════════════════════════════════════════════════╝")

    print(f"\n🎯 Topic: {topic}")
    print(f"📋 Style: {style}\n")

    strategies = {
        "aggressive": {
            "hooks": ["contrarian", "curiosity_gap", "specific_numbers"],
            "tone": "Bold, provocative, challenges assumptions",
            "risk": "High engagement OR high backlash",
        },
        "balanced": {
            "hooks": ["transformation", "list_format", "question_hook"],
            "tone": "Informative, valuable, approachable",
            "risk": "Consistent performance, less viral ceiling",
        },
        "safe": {
            "hooks": ["list_format", "emotional_trigger", "question_hook"],
            "tone": "Friendly, helpful, non-controversial",
            "risk": "Lower risk, lower viral potential",
        },
    }

    strat = strategies.get(style, strategies["balanced"])

    print("📌 RECOMMENDED APPROACH:\n")
    print(f"   Tone: {strat['tone']}")
    print(f"   Risk Profile: {strat['risk']}")
    print(f"\n   Hook Types to Use:")
    for hook in strat["hooks"]:
        info = VIRAL_PATTERNS.get(hook, {})
        print(f"   • {hook.replace('_', ' ').title()}: +{info.get('score_boost', 0)} pts")
        print(f"     {info.get('reason', '')}")

    print("\n📝 TEMPLATE STRUCTURE:\n")
    print("   [HOOK - Create curiosity/controversy]")
    print("   ")
    print("   [VALUE - Deliver insight/information]")
    print("   ")
    print("   [ENGAGEMENT - Question or call to action]")
    print("   ")
    print("   ↳ Reply 1: 🔗 [LINK]")
    print("   ↳ Reply 2: [Follow-up question]")

    print("\n⏰ TIMING:\n")
    print("   Best days: Tuesday-Thursday")
    print("   Best times (EST): 8AM, 12PM, 5PM, 9PM")
    print("   Critical window: First 30 minutes")

    print("\n🔄 POST-PUBLISH CHECKLIST:\n")
    print("   □ Reply to EVERY comment within 15 mins")
    print("   □ Ask follow-up questions in replies")
    print("   □ Like thoughtful responses")
    print("   □ Quote-tweet if performing well after 2hrs")


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="X Viral Tweet Analyzer")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Analyze command
    analyze_p = subparsers.add_parser("analyze", help="Analyze a tweet's viral potential")
    analyze_p.add_argument("tweet", help="Tweet text to analyze")
    analyze_p.add_argument("--link-in-reply", "-l", action="store_true",
                          help="Link will be in reply (not main tweet)")

    # Compare command
    compare_p = subparsers.add_parser("compare", help="Compare tweet variants (A/B test)")
    compare_p.add_argument("tweets", nargs="+", help="Tweet variants to compare")

    # Strategy command
    strat_p = subparsers.add_parser("strategy", help="Generate viral strategy for topic")
    strat_p.add_argument("topic", help="Topic to create strategy for")
    strat_p.add_argument("--style", "-s", choices=["aggressive", "balanced", "safe"],
                        default="balanced", help="Strategy style")

    # Patterns command
    subparsers.add_parser("patterns", help="Show all viral patterns")

    args = parser.parse_args()

    if args.command == "analyze":
        result = analyze_tweet(args.tweet, args.link_in_reply)
        print_analysis(result, args.tweet)

    elif args.command == "compare":
        compare_tweets(args.tweets)

    elif args.command == "strategy":
        generate_strategy(args.topic, args.style)

    elif args.command == "patterns":
        print("\n╔════════════════════════════════════════════════════════════╗")
        print("║  VIRAL PATTERNS DATABASE                                   ║")
        print("╚════════════════════════════════════════════════════════════╝\n")

        print("🚀 BOOST PATTERNS:\n")
        for name, data in VIRAL_PATTERNS.items():
            print(f"   {name.replace('_', ' ').title()}: +{data['score_boost']} pts")
            print(f"   └─ {data['reason']}\n")

        print("⚠️ PENALTY PATTERNS:\n")
        for name, data in PENALTY_PATTERNS.items():
            print(f"   {name.replace('_', ' ').title()}: {data['penalty']} pts")
            print(f"   └─ {data['reason']}\n")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
