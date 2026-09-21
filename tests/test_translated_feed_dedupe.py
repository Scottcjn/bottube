# SPDX-License-Identifier: MIT
"""Regression: GET /api/videos/translated/<language> lists each video once.

``video_translations`` is UNIQUE(video_id, language, translator_id), so a
video translated into the same language by several translators has several
rows. The feed joined straight through that table and returned the video once
per translator. It now returns one row per video, carrying the most recent
translation for the requested language.
"""

import time


def _agent_id(db, name):
    return db.execute(
        "SELECT id FROM agents WHERE agent_name = ?", (name,)
    ).fetchone()["id"]


def _seed(client, registered_agent):
    import bottube_server
    from translation_routes import init_translation_tables

    with client.application.app_context():
        db = bottube_server.get_db()
        init_translation_tables(db)
        owner = _agent_id(db, registered_agent["agent_name"])
        now = time.time()
        db.execute(
            "INSERT INTO agents (agent_name, display_name, api_key, created_at) "
            "VALUES ('translator_two', 'T2', 'k-t2', ?)",
            (now,),
        )
        other = _agent_id(db, "translator_two")

        for vid, title in (("shared", "Shared video"), ("solo", "Solo video")):
            db.execute(
                """INSERT INTO videos
                   (video_id, agent_id, title, description, filename, category,
                    views, likes, created_at)
                   VALUES (?, ?, ?, 'desc', ?, 'other', 0, 0, ?)""",
                (vid, owner, title, f"{vid}.mp4", now),
            )

        rows = [
            # "shared" translated into Spanish by two translators; the second
            # translation is newer and must be the one surfaced.
            ("shared", "Spanish", "Video compartido (viejo)", owner, now - 100),
            ("shared", "Spanish", "Video compartido (nuevo)", other, now - 10),
            # A French translation must not leak into the Spanish feed.
            ("shared", "French", "Vidéo partagée", owner, now - 5),
            ("solo", "Spanish", "Video solo", other, now - 50),
        ]
        db.executemany(
            """INSERT INTO video_translations
               (video_id, language, title, description, translator_id, created_at)
               VALUES (?, ?, ?, 'd', ?, ?)""",
            rows,
        )
        db.commit()


def test_translated_feed_lists_each_video_once(client, registered_agent):
    _seed(client, registered_agent)

    resp = client.get("/api/videos/translated/Spanish")
    assert resp.status_code == 200
    feed = resp.get_json()
    ids = [v["video_id"] for v in feed]

    assert sorted(ids) == ["shared", "solo"]
    assert len(ids) == len(set(ids))
    # Ordered by the surfaced translation's recency: shared (-10s) before solo (-50s).
    assert ids == ["shared", "solo"]

    shared = next(v for v in feed if v["video_id"] == "shared")
    assert shared["translated_title"] == "Video compartido (nuevo)"
