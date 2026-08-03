# SPDX-License-Identifier: MIT
"""
Recommendation Engine for BoTTube Feed (Issue #46)

Provides real feed recommendations with:
- Freshness scoring (recency bonus)
- Engagement scoring (views, likes, comments weighted)
- Diversity scoring (agent/category diversity)
- Optional category affinity (based on user's watch history)

Deterministic fallback mode=latest ensures consistent results.
"""

import math
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Weights for scoring components
FRESHNESS_WEIGHT = 1.0
ENGAGEMENT_WEIGHT = 2.0
DIVERSITY_WEIGHT = 1.5
CATEGORY_AFFINITY_WEIGHT = 1.0

# Freshness decay: videos lose freshness score over time
FRESHNESS_HALF_LIFE_HOURS = 24.0  # freshness halves every 24 hours

# Engagement normalization
ENGAGEMENT_VIEW_WEIGHT = 1.0
ENGAGEMENT_LIKE_WEIGHT = 3.0
ENGAGEMENT_COMMENT_WEIGHT = 4.0

# Diversity penalty for over-representation
DIVERSITY_AGENT_PENALTY_THRESHOLD = 3  # penalty after 3 videos from same agent
DIVERSITY_AGENT_PENALTY_FACTOR = 0.7  # multiply score by this for each excess video

# Category affinity
CATEGORY_AFFINITY_MIN_VIDEOS = 3  # minimum videos watched to build affinity
CATEGORY_AFFINITY_DECAY_DAYS = 7  # older views count less


# ---------------------------------------------------------------------------
# Scoring Functions
# ---------------------------------------------------------------------------

def score_freshness(created_at: float, now: Optional[float] = None) -> float:
    """
    Compute freshness score based on video age.
    
    Uses exponential decay with configurable half-life.
    Fresh videos (recently uploaded) get higher scores.
    
    Args:
        created_at: Unix timestamp of video creation
        now: Current time (defaults to time.time())
    
    Returns:
        Freshness score in range (0, 1]
    """
    if now is None:
        now = time.time()
    
    age_hours = (now - created_at) / 3600.0
    if age_hours < 0:
        age_hours = 0  # Future-dated videos get max freshness
    
    # Exponential decay: score = 2^(-age/half_life)
    decay_exponent = -age_hours / FRESHNESS_HALF_LIFE_HOURS
    return math.pow(2, decay_exponent)


def score_engagement(
    views: int,
    likes: int,
    comments: int = 0,
    recent_views: int = 0,
    recent_comments: int = 0
) -> float:
    """
    Compute engagement score based on video interactions.
    
    Combines lifetime and recent engagement metrics.
    Recent engagement is weighted higher to capture trending content.
    
    Args:
        views: Total view count
        likes: Total like count
        comments: Total comment count
        recent_views: Views in last 24h (optional)
        recent_comments: Comments in last 24h (optional)
    
    Returns:
        Engagement score (unbounded, typically 0-100)
    """
    # Base engagement from lifetime stats
    base_score = (
        views * ENGAGEMENT_VIEW_WEIGHT +
        likes * ENGAGEMENT_LIKE_WEIGHT +
        comments * ENGAGEMENT_COMMENT_WEIGHT
    )
    
    # Bonus for recent activity (trending indicator)
    recent_bonus = (
        recent_views * ENGAGEMENT_VIEW_WEIGHT * 2 +  # 2x weight for recent views
        recent_comments * ENGAGEMENT_COMMENT_WEIGHT * 2
    )
    
    return base_score + recent_bonus


def compute_diversity_penalty(
    selected_videos: List[Dict[str, Any]],
    candidate_agent_id: int,
    candidate_category: str
) -> float:
    """
    Compute diversity penalty based on already-selected videos.
    
    Penalizes over-representation of agents and categories.
    Encourages diverse feed content.
    
    Args:
        selected_videos: List of already selected video dicts
        candidate_agent_id: Agent ID of candidate video
        candidate_category: Category of candidate video
    
    Returns:
        Diversity multiplier in range (0, 1] (1 = no penalty)
    """
    agent_count = sum(
        1 for v in selected_videos 
        if v.get("agent_id") == candidate_agent_id
    )
    
    category_count = sum(
        1 for v in selected_videos 
        if v.get("category") == candidate_category
    )
    
    # Agent diversity penalty
    agent_penalty = 1.0
    if agent_count >= DIVERSITY_AGENT_PENALTY_THRESHOLD:
        excess = agent_count - DIVERSITY_AGENT_PENALTY_THRESHOLD + 1
        agent_penalty = math.pow(DIVERSITY_AGENT_PENALTY_FACTOR, excess)
    
    # Category diversity penalty (softer)
    category_penalty = 1.0
    if category_count >= DIVERSITY_AGENT_PENALTY_THRESHOLD + 1:
        excess = category_count - (DIVERSITY_AGENT_PENALTY_THRESHOLD + 1) + 1
        category_penalty = math.pow(DIVERSITY_AGENT_PENALTY_FACTOR * 1.2, excess)
    
    return agent_penalty * category_penalty


def compute_category_affinity(
    user_watch_history: List[Dict[str, Any]],
    category: str,
    now: Optional[float] = None
) -> float:
    """
    Compute user's affinity for a category based on watch history.
    
    Analyzes user's past video watches to determine category preferences.
    Older watches decay in importance.
    
    Args:
        user_watch_history: List of watched video dicts with category, created_at
        category: Category to compute affinity for
        now: Current time for decay calculation
    
    Returns:
        Affinity score in range [0, 1] (0 = no affinity, 1 = strong affinity)
    """
    if now is None:
        now = time.time()
    
    if len(user_watch_history) < CATEGORY_AFFINITY_MIN_VIDEOS:
        return 0.5  # Neutral affinity for new users
    
    # Count category occurrences with time decay
    category_score = 0.0
    total_weight = 0.0
    
    decay_seconds = CATEGORY_AFFINITY_DECAY_DAYS * 24 * 3600
    
    for video in user_watch_history:
        video_category = video.get("category", "other")
        watched_at = video.get("watched_at", video.get("created_at", now))
        
        # Time decay weight
        age = now - watched_at
        if age < 0:
            age = 0
        time_weight = math.exp(-age / decay_seconds)
        
        total_weight += time_weight
        if video_category == category:
            category_score += time_weight
    
    if total_weight == 0:
        return 0.5
    
    return category_score / total_weight


# ---------------------------------------------------------------------------
# Main Recommendation Engine
# ---------------------------------------------------------------------------

class RecommendationEngine:
    """
    Feed recommendation engine combining freshness, engagement, diversity, and affinity.
    """
    
    def __init__(
        self,
        freshness_weight: float = FRESHNESS_WEIGHT,
        engagement_weight: float = ENGAGEMENT_WEIGHT,
        diversity_weight: float = DIVERSITY_WEIGHT,
        category_affinity_weight: float = CATEGORY_AFFINITY_WEIGHT
    ):
        self.freshness_weight = freshness_weight
        self.engagement_weight = engagement_weight
        self.diversity_weight = diversity_weight
        self.category_affinity_weight = category_affinity_weight
    
    def score_video(
        self,
        video: Dict[str, Any],
        selected_videos: List[Dict[str, Any]],
        user_category_affinity: Optional[Dict[str, float]] = None,
        now: Optional[float] = None
    ) -> float:
        """
        Compute composite score for a video candidate.
        
        Args:
            video: Video dict with agent_id, category, created_at, views, likes, etc.
            selected_videos: Already selected videos for diversity calculation
            user_category_affinity: Pre-computed category affinities (optional)
            now: Current timestamp
        
        Returns:
            Composite recommendation score
        """
        if now is None:
            now = time.time()
        
        # Freshness score
        freshness = score_freshness(video.get("created_at", now), now)
        
        # Engagement score
        engagement = score_engagement(
            views=video.get("views", 0),
            likes=video.get("likes", 0),
            comments=video.get("comment_count", 0),
            recent_views=video.get("recent_views", 0),
            recent_comments=video.get("recent_comments", 0)
        )
        
        # Normalize engagement (log scale to prevent domination)
        engagement_normalized = math.log1p(engagement)
        
        # Diversity penalty
        diversity_multiplier = compute_diversity_penalty(
            selected_videos,
            video.get("agent_id", 0),
            video.get("category", "other")
        )
        
        # Category affinity bonus
        category = video.get("category", "other")
        affinity = 0.5  # Default neutral
        if user_category_affinity and category in user_category_affinity:
            affinity = user_category_affinity[category]
        
        # Composite score
        score = (
            self.freshness_weight * freshness +
            self.engagement_weight * engagement_normalized +
            self.category_affinity_weight * affinity
        )
        
        # Apply diversity as multiplier (penalty)
        score *= diversity_multiplier
        
        return score
    
    def compute_category_affinities(
        self,
        watch_history: List[Dict[str, Any]],
        categories: List[str],
        now: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Pre-compute affinities for all categories.
        
        Args:
            watch_history: User's watch history
            categories: List of categories to compute affinities for
            now: Current timestamp
        
        Returns:
            Dict mapping category -> affinity score
        """
        affinities = {}
        for category in categories:
            affinities[category] = compute_category_affinity(
                watch_history, category, now
            )
        return affinities
    
    def recommend(
        self,
        candidates: List[Dict[str, Any]],
        limit: int = 20,
        user_watch_history: Optional[List[Dict[str, Any]]] = None,
        now: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate ranked recommendations from candidate videos.
        
        Greedy selection: picks highest-scoring video, updates diversity,
        repeats until limit reached.
        
        Args:
            candidates: List of candidate video dicts
            limit: Maximum number of recommendations
            user_watch_history: User's watch history for affinity (optional)
            now: Current timestamp
        
        Returns:
            List of recommended videos with 'recommend_score' added
        """
        if now is None:
            now = time.time()
        
        # Pre-compute category affinities
        all_categories = set(v.get("category", "other") for v in candidates)
        user_category_affinity = None
        if user_watch_history:
            user_category_affinity = self.compute_category_affinities(
                user_watch_history, list(all_categories), now
            )
        
        selected = []
        remaining = list(candidates)  # Copy to avoid mutation
        
        for _ in range(limit):
            if not remaining:
                break
            
            # Score all remaining candidates
            scored = []
            for video in remaining:
                score = self.score_video(
                    video,
                    selected,
                    user_category_affinity,
                    now
                )
                scored.append((score, video))
            
            # Pick highest score (deterministic tie-breaking by created_at, then video_id)
            scored.sort(key=lambda x: (-x[0], -x[1].get("created_at", 0), x[1].get("video_id", "")))
            
            best_score, best_video = scored[0]
            
            # Add score to video and move to selected
            best_video["recommend_score"] = round(best_score, 4)
            selected.append(best_video)
            remaining.remove(best_video)
        
        return selected


# ---------------------------------------------------------------------------
# Fallback: Latest Mode (Deterministic)
# ---------------------------------------------------------------------------

def fallback_latest(
    videos: List[Dict[str, Any]],
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Deterministic fallback: sort by created_at DESC, then video_id.
    
    Used when mode=latest or recommendation engine is disabled.
    Guarantees consistent, reproducible results.
    
    Args:
        videos: List of video dicts
        limit: Maximum number to return
    
    Returns:
        Sorted list of videos
    """
    sorted_videos = sorted(
        videos,
        key=lambda v: (-v.get("created_at", 0), v.get("video_id", ""))
    )
    return sorted_videos[:limit]


# ---------------------------------------------------------------------------
# Feed Endpoint Integration
# ---------------------------------------------------------------------------

def get_feed_recommendations(
    db,
    agent_id: Optional[int] = None,
    limit: int = 20,
    mode: str = "latest",
    category: Optional[str] = None,
    exclude_agent: Optional[int] = None
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Get feed recommendations from database.
    
    Args:
        db: Database connection
        agent_id: User's agent ID (for affinity, subscriptions)
        limit: Number of videos to return
        mode: "latest" (deterministic) or "recommended" (ML scoring)
        category: Filter by category (optional)
        exclude_agent: Exclude videos from this agent (optional)
    
    Returns:
        Tuple of (video list, mode used)
    """
    now = time.time()
    
    # Build base query
    base_query = """
        SELECT v.*, a.agent_name, a.display_name, a.avatar_url, a.is_human,
               COALESCE(rv.recent_views, 0) AS recent_views,
               COALESCE(rc.recent_comments, 0) AS recent_comments
        FROM videos v
        JOIN agents a ON v.agent_id = a.id
        LEFT JOIN (
            SELECT video_id, COUNT(*) AS recent_views
            FROM views 
            WHERE created_at > ?
            GROUP BY video_id
        ) rv ON rv.video_id = v.video_id
        LEFT JOIN (
            SELECT video_id, COUNT(*) AS recent_comments
            FROM comments 
            WHERE created_at > ?
            GROUP BY video_id
        ) rc ON rc.video_id = v.video_id
        WHERE v.is_removed = 0 AND COALESCE(a.is_banned, 0) = 0
    """
    
    params: List[Any] = [now - 86400, now - 86400]  # 24h ago for recent counts
    
    # Optional filters
    if category:
        base_query += " AND v.category = ?"
        params.append(category)
    
    if exclude_agent:
        base_query += " AND v.agent_id != ?"
        params.append(exclude_agent)
    
    # Subscription feed for authenticated users
    if agent_id and mode == "subscriptions":
        base_query += " AND v.agent_id IN (SELECT following_id FROM subscriptions WHERE follower_id = ?)"
        params.append(agent_id)
    
    base_query += " ORDER BY v.created_at DESC"
    
    # Fetch candidates (oversample for diversity selection)
    candidate_limit = limit * 5
    base_query += " LIMIT ?"
    params.append(candidate_limit)
    
    rows = db.execute(base_query, params).fetchall()
    
    # Convert to dicts
    candidates = []
    for row in rows:
        video = dict(row)
        candidates.append(video)
    
    # Mode selection
    if mode == "recommended" and agent_id:
        # Get user's watch history for affinity
        watch_history = db.execute(
            """SELECT v.category, v.created_at AS watched_at
               FROM views w
               JOIN videos v ON w.video_id = v.video_id
               WHERE w.agent_id = ?
               ORDER BY w.created_at DESC
               LIMIT 50""",
            (agent_id,)
        ).fetchall()
        
        engine = RecommendationEngine()
        recommended = engine.recommend(
            candidates,
            limit=limit,
            user_watch_history=[dict(h) for h in watch_history],
            now=now
        )
        return recommended, "recommended"
    
    # Default: latest mode (deterministic fallback)
    latest = fallback_latest(candidates, limit)
    return latest, "latest"
