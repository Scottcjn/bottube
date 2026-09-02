import re
from news_routes import generate_rss_feed

def test_rss_channel_logo_url_resolves():
    """Regression: RSS channel image must point to deployed hyphenated asset."""
    feed = generate_rss_feed(items=[])
    match = re.search(r"<url>(https://bottube\.ai/static/[^<]+)</url>", feed)
    assert match, "RSS feed missing <image><url>"
    url = match.group(1)
    assert url.endswith("bottube-logo.png"), f"Expected hyphenated logo, got {url}"
    assert "bottube_logo.png" not in url, "Underscore variant is 404; use hyphenated path"
