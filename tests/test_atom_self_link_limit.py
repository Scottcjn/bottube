import re
from feed_blueprint import atom_feed

class FakeRequest:
    def __init__(self, args):
        self.args = args

def test_atom_self_link_preserves_limit(monkeypatch):
    """Regression: Atom self link must include limit when non-default."""
    from flask import Flask
    app = Flask(__name__)
    
    with app.test_request_context('/feed/atom?limit=5'):
        # Mock _fetch_videos to avoid DB/API calls
        import feed_blueprint as fb
        monkeypatch.setattr(fb, '_fetch_videos', lambda **kw: [])
        
        resp = atom_feed()
        body = resp.get_data(as_text=True)
        
        match = re.search(r'<link href="([^"]+)" rel="self"', body)
        assert match, "Atom feed missing rel=self link"
        url = match.group(1)
        assert "limit=5" in url, f"Self link should preserve limit=5, got {url}"

def test_atom_self_link_omits_default_limit(monkeypatch):
    """Default limit (20) should not appear in self link."""
    from flask import Flask
    app = Flask(__name__)
    
    with app.test_request_context('/feed/atom'):
        import feed_blueprint as fb
        monkeypatch.setattr(fb, '_fetch_videos', lambda **kw: [])
        
        resp = atom_feed()
        body = resp.get_data(as_text=True)
        
        match = re.search(r'<link href="([^"]+)" rel="self"', body)
        assert match
        url = match.group(1)
        assert "limit=" not in url, f"Default limit should be omitted, got {url}"
