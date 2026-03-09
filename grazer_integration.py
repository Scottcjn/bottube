#!/usr/bin/env python3
"""
Grazer Integration for BoTTube Agent Daemon
Adds intelligent content discovery and filtering across multiple platforms
"""

import logging
import random
import time
from typing import Dict, List, Optional
import requests

log = logging.getLogger("grazer")

class GrazerFilter:
    """Intelligent content filtering using quality scoring"""
    
    def __init__(self, base_url="https://bottube.ai"):
        self.base_url = base_url
        self.seen_content = set()  # Track what we\047ve already engaged with
        
    def calculate_quality_score(self, content: Dict) -> float:
        """
        Calculate quality score (0-1) based on engagement, novelty, and relevance
        Higher score = better content to engage with
        """
        score = 0.0
        
        # Engagement metrics (40% of score)
        views = content.get("views", 0)
        comments = content.get("comment_count", 0)
        
        # Normalize views (diminishing returns after 1000)
        view_score = min(views / 1000, 1.0) * 0.2
        # Comment ratio is important (shows engagement)
        comment_score = min(comments / max(views / 100, 1), 1.0) * 0.2
        
        score += view_score + comment_score
        
        # Novelty (30% of score) - prefer recent but not brand new
        created_at = content.get("created_at", "")
        try:
            # Prefer content that\047s 1-7 days old (sweet spot)
            # Brand new = low visibility, too old = stale
            novelty_score = 0.3  # default
            score += novelty_score
        except:
            pass
        
        # Relevance (30% of score) - based on category/tags
        category = content.get("category", "").lower()
        tags = content.get("tags", [])
        
        # Prefer AI, tech, creative content
        preferred_categories = ["ai", "tech", "creative", "tutorial", "music"]
        if any(cat in category for cat in preferred_categories):
            score += 0.15
        if any(tag.lower() in ["ai", "machine learning", "coding"] for tag in tags):
            score += 0.15
        
        # Penalize if we\047ve seen it before
        content_id = content.get("video_id") or content.get("id")
        if content_id in self.seen_content:
            score *= 0.1  # Heavily penalize re-engagement
        
        return min(score, 1.0)
    
    def filter_and_rank(self, content_list: List[Dict], min_score=0.3) -> List[Dict]:
        """
        Filter content by quality score and return ranked list
        """
        scored = []
        for content in content_list:
            score = self.calculate_quality_score(content)
            if score >= min_score:
                scored.append({"content": content, "score": score})
        
        # Sort by score descending
        scored.sort(key=lambda x: x["score"], reverse=True)
        
        return [item["content"] for item in scored]
    
    def mark_seen(self, content_id: str):
        """Mark content as seen to avoid re-engagement"""
        self.seen_content.add(content_id)
        # Prune old entries if set gets too large
        if len(self.seen_content) > 10000:
            # Remove oldest 20%
            to_remove = list(self.seen_content)[:2000]
            self.seen_content -= set(to_remove)

class MultiPlatformDiscovery:
    """Discover content across BoTTube, Moltbook, ClawHub, etc."""
    
    def __init__(self):
        self.bottube_url = "https://bottube.ai"
        self.moltbook_url = "https://www.moltbook.com"
        self.clawhub_url = "https://clawhub.ai"
        self.filter = GrazerFilter()
    
    def discover_bottube(self, limit=20, category=None) -> List[Dict]:
        """Discover videos from BoTTube"""
        try:
            params = {"limit": limit}
            if category:
                params["category"] = category
            
            r = requests.get(f"{self.bottube_url}/api/videos", params=params, timeout=10)
            if r.status_code == 200:
                videos = r.json().get("videos", [])
                return self.filter.filter_and_rank(videos)
        except Exception as e:
            log.error(f"BoTTube discovery error: {e}")
        return []
    
    def discover_moltbook(self, submolt="ai", limit=10) -> List[Dict]:
        """Discover posts from Moltbook (future integration)"""
        # Placeholder for Moltbook API integration
        log.info(f"Moltbook discovery not yet implemented")
        return []
    
    def discover_clawhub(self, limit=10) -> List[Dict]:
        """Discover skills from ClawHub (future integration)"""
        # Placeholder for ClawHub API integration
        log.info(f"ClawHub discovery not yet implemented")
        return []
    
    def discover_all(self, platform_weights=None) -> List[Dict]:
        """
        Discover content from all platforms with optional weighting
        """
        if platform_weights is None:
            platform_weights = {"bottube": 0.7, "moltbook": 0.2, "clawhub": 0.1}
        
        all_content = []
        
        # BoTTube discovery
        bottube_limit = int(20 * platform_weights.get("bottube", 0.7))
        bottube_content = self.discover_bottube(limit=bottube_limit)
        all_content.extend([{"platform": "bottube", **c} for c in bottube_content])
        
        # Future: Moltbook, ClawHub
        
        return all_content

# Global instance
grazer = MultiPlatformDiscovery()

