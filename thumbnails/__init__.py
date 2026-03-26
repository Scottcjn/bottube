# SPDX-License-Identifier: MIT
"""
BoTTube Thumbnail & CTR Tracking System

Modules:
- best_frame: Automatic best-frame selection from video uploads
- ctr_tracker: Click-through rate and watch time tracking
- ab_test: Thumbnail A/B testing with auto-winner selection
- ranking_signal: Feed ranking integration using CTR + watch time signals
"""

from .best_frame import select_best_frame
from .ctr_tracker import CTRTracker
from .ab_test import ABTestManager
from .ranking_signal import compute_feed_score, integrate_with_feed

__all__ = [
    "select_best_frame",
    "CTRTracker",
    "ABTestManager",
    "compute_feed_score",
    "integrate_with_feed",
]
