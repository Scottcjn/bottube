"""
Tests for Recommendation Engine - #497
"""
import pytest
from engine import RecommendationEngine

class TestRecommendationEngine:
    def test_init(self):
        engine = RecommendationEngine()
        assert engine.model == "AI-powered"
    
    def test_get_recommendations(self):
        engine = RecommendationEngine()
        recs = engine.get_recommendations("user123")
        assert len(recs) > 0
        assert "video_id" in recs[0]

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
