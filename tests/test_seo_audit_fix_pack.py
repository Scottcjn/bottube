from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_static_cdn_scripts_are_version_pinned_with_sri():
    analytics = read("bottube_templates/analytics.html")
    atlas = read("bottube_templates/beacon_atlas.html")
    chat = read("templates/chat.html")

    assert "https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js" in analytics
    assert "integrity=\"sha384-jb8JQMbMoBUzgWatfe6COACi2ljcDdZQ2OxczGA3bGNeWe+6DChMTBJemed7ZnvJ\"" in analytics
    assert "crossorigin=\"anonymous\"" in analytics

    assert "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js" in atlas
    assert "integrity=\"sha384-CjloA8y00+1SDAUkjs099PVfnY2KmDC2BZnws9kh8D/lX1s46w6EPhpXdqMfjK6i\"" in atlas
    assert "crossorigin=\"anonymous\"" in atlas

    assert "https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.4/socket.io.min.js" in chat
    assert "integrity=\"sha384-Gr6Lu2Ajx28mzwyVR8CFkULdCU7kMlZ9UthllibdOSo6qAiN+yXNHqtgdTvFXMT4\"" in chat
    assert "crossorigin=\"anonymous\"" in chat


def test_csp_allows_scripts_used_by_templates():
    base_template = read("bottube_templates/base.html")
    server_source = read("bottube_server.py")

    for source in [
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
        "https://imasdk.googleapis.com",
    ]:
        assert source in base_template
        assert source in server_source


def test_listing_images_have_lazy_decode_and_dimensions():
    search = read("bottube_templates/search.html")
    trending = read("bottube_templates/trending.html")
    agents = read("bottube_templates/agents.html")
    news_hub = read("bottube_templates/news_hub.html")

    assert 'loading="lazy" decoding="async" width="720" height="720"' in search
    assert 'loading="lazy" decoding="async" width="40" height="40"' in search
    assert trending.count('loading="lazy" decoding="async" width="720" height="720"') >= 2
    assert 'loading="lazy" decoding="async" width="40" height="40"' in trending
    assert 'loading="lazy" decoding="async" width="56" height="56"' in agents
    assert news_hub.count('loading="lazy" decoding="async" width="720" height="720"') >= 2
    assert news_hub.count('loading="lazy" decoding="async" width="1200" height="630"') >= 2


def test_legacy_base_footer_badges_do_not_shift_layout_or_log_fallbacks():
    legacy_base = read("base.html")

    assert "console.log(" not in legacy_base
    assert "console.error(" not in legacy_base
    assert 'alt="BoTTube featured on Dofollow.Tools" loading="lazy" decoding="async" width="120" height="24"' in legacy_base
    assert 'alt="BoTTube featured on Startup Fame" loading="lazy" decoding="async" width="120" height="24"' in legacy_base
    assert 'href="https://www.moltbook.com" target="_blank" rel="noopener"' in legacy_base
    assert 'href="https://github.com/Scottcjn/bottube" target="_blank" rel="noopener"' in legacy_base
