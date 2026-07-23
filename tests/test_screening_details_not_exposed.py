"""Verify screening_details and removed_reason are stripped from API responses."""
import pytest


def test_video_to_dict_strips_screening_details():
    """video_to_dict must not include screening_details in the output."""
    from bottube_server import video_to_dict

    class FakeRow:
        def keys(self):
            return ['id', 'video_id', 'title', 'screening_details',
                     'removed_reason', 'tags', 'thumbnail', 'category']
        def __getitem__(self, key):
            data = {
                'id': 42,
                'video_id': 'test-vid-001',
                'title': 'Test Video',
                'screening_details': '{"score": 0.8, "internal_model": "guard-v2"}',
                'removed_reason': 'tos_violation_pending',
                'tags': '[]',
                'thumbnail': '',
                'category': 'other',
            }
            return data[key]

    result = video_to_dict(FakeRow())
    assert 'screening_details' not in result, \
        "screening_details leaked into API response"
    assert 'removed_reason' not in result, \
        "removed_reason leaked into API response"
    assert 'id' not in result, "internal id should also be stripped"


def test_video_to_dict_preserves_expected_fields():
    """video_to_dict should keep the fields consumers actually need."""
    from bottube_server import video_to_dict

    class FakeRow:
        def keys(self):
            return ['id', 'video_id', 'title', 'screening_details',
                     'removed_reason', 'tags', 'thumbnail', 'category']
        def __getitem__(self, key):
            data = {
                'id': 1,
                'video_id': 'abc123',
                'title': 'My Video',
                'screening_details': '{"score": 1.0}',
                'removed_reason': '',
                'tags': '["gaming"]',
                'thumbnail': 'thumb.jpg',
                'category': 'gaming',
            }
            return data[key]

    result = video_to_dict(FakeRow())
    assert result['video_id'] == 'abc123'
    assert result['title'] == 'My Video'
    assert result['tags'] == ['gaming']
    assert result['url'] == '/api/videos/abc123/stream'
