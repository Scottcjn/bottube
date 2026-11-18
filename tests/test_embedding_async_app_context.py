# SPDX-License-Identifier: MIT
"""Regression: the post-upload embedding thread must not need a Flask app context.

``_ue_record_for_video_async`` runs ``_ue_record_for_video`` on a bare
thread. It used to call ``get_db()`` there, which raised
"Working outside of application context", so new uploads never got a
semantic embedding row.
"""

import sqlite3
import threading
import time

import numpy as np


def test_async_embedding_thread_writes_record(app, monkeypatch):
    import bottube_server

    db_path = app.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO agents (agent_name, api_key, created_at) VALUES (?, ?, ?)",
        ("embed_bot", "bottube_sk_embed_test", time.time()),
    )
    agent_id = conn.execute("SELECT id FROM agents WHERE agent_name='embed_bot'").fetchone()[0]
    conn.execute(
        """INSERT INTO videos (video_id, agent_id, title, description, filename, tags, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("vidEmbed001", agent_id, "Sunset timelapse", "Clouds over hills",
         "vidEmbed001.mp4", '["sunset"]', time.time()),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        bottube_server, "_ue_embed_text",
        lambda text, attempts=4: np.ones(8, dtype="float32"),
    )

    thread_errors = []
    monkeypatch.setattr(threading, "excepthook", lambda args: thread_errors.append(args.exc_value))

    # Called exactly as the upload handler does: no app/request context.
    bottube_server._ue_record_for_video_async("vidEmbed001")
    for t in threading.enumerate():
        if t.name == "embed-vidEmbed001":
            t.join(timeout=10)

    assert thread_errors == []
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT model, dim FROM video_embeddings WHERE video_id = ?", ("vidEmbed001",)
    ).fetchone()
    conn.close()
    assert row == (bottube_server.EMBEDDING_MODEL, 8)
