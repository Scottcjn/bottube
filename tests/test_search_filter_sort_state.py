# SPDX-License-Identifier: MIT
"""Regression coverage for the public search filter/sort controls."""

import html as html_lib
import re
import time
from urllib.parse import parse_qs, urlsplit


def _insert_video(client, registered_agent, video_id, title, category, *, views, likes, created_at):
    import bottube_server

    with client.application.app_context():
        db = bottube_server.get_db()
        agent = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            (registered_agent["agent_name"],),
        ).fetchone()
        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, description, filename, category,
                views, likes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                video_id,
                agent["id"],
                title,
                "Needle search fixture",
                f"{video_id}.mp4",
                category,
                views,
                likes,
                created_at,
            ),
        )
        db.commit()


def test_search_category_control_filters_and_likes_sort_orders(client, registered_agent):
    now = time.time()
    _insert_video(
        client, registered_agent, "music-low", "Needle Music Low", "music",
        views=500, likes=2, created_at=now,
    )
    _insert_video(
        client, registered_agent, "music-high", "Needle Music High", "music",
        views=1, likes=40, created_at=now - 100,
    )
    _insert_video(
        client, registered_agent, "tech-high", "Needle Tech High", "science-tech",
        views=900, likes=900, created_at=now + 100,
    )

    response = client.get("/search?q=Needle&category=music&sort=likes")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Needle Tech High" not in html
    assert html.index("Needle Music High") < html.index("Needle Music Low")
    assert 'id="cat-music"' in html
    assert 'value="likes"\n                           checked' in html


def test_search_pagination_preserves_category_and_sort(client, registered_agent):
    now = time.time()
    for index in range(25):
        _insert_video(
            client,
            registered_agent,
            f"paged-{index}",
            f"Needle Paged {index:02d}",
            "music",
            views=index,
            likes=index,
            created_at=now + index,
        )

    response = client.get("/search?q=Needle&category=music&sort=recent&page=1")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Page 1 of 2" in html
    next_link = re.search(r'href="([^"]*[?&amp;]page=2)"', html)
    assert next_link is not None
    query = parse_qs(urlsplit(html_lib.unescape(next_link.group(1))).query)
    assert query == {
        "q": ["Needle"],
        "sort": ["recent"],
        "category": ["music"],
        "page": ["2"],
    }


def test_search_accepts_legacy_cat_parameter(client, registered_agent):
    now = time.time()
    _insert_video(
        client, registered_agent, "legacy-music", "Needle Legacy Music", "music",
        views=1, likes=1, created_at=now,
    )
    _insert_video(
        client, registered_agent, "legacy-tech", "Needle Legacy Tech", "science-tech",
        views=2, likes=2, created_at=now,
    )

    response = client.get("/search?q=Needle&cat=music")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Needle Legacy Music" in html
    assert "Needle Legacy Tech" not in html
