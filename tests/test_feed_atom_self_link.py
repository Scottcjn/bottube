from flask import Flask

import feed_blueprint


def _client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(feed_blueprint.feed_bp)
    monkeypatch.setattr(feed_blueprint, "_fetch_videos", lambda **kwargs: [])
    return app.test_client()


def test_atom_self_link_preserves_explicit_limit(monkeypatch):
    response = _client(monkeypatch).get("/feed/atom?limit=5")

    assert response.status_code == 200
    assert (
        '<link href="https://bottube.ai/feed/atom?limit=5" rel="self" />'
        in response.get_data(as_text=True)
    )


def test_atom_self_link_url_encodes_combined_filters(monkeypatch):
    response = _client(monkeypatch).get(
        "/feed/atom",
        query_string={
            "agent": "alice bob",
            "category": "music & ai",
            "limit": "7",
        },
    )

    assert response.status_code == 200
    assert (
        'href="https://bottube.ai/feed/atom?agent=alice+bob&amp;'
        'category=music+%26+ai&amp;limit=7" rel="self"'
        in response.get_data(as_text=True)
    )


def test_atom_self_link_keeps_default_url_when_limit_is_omitted(monkeypatch):
    response = _client(monkeypatch).get("/feed/atom")

    assert response.status_code == 200
    assert (
        '<link href="https://bottube.ai/feed/atom" rel="self" />'
        in response.get_data(as_text=True)
    )
