"""Regression coverage for duplicate upload reward delivery."""

import sqlite3

from banano_blueprint import REWARDS, award_ban_upload, init_ban_tables


def test_upload_reward_is_idempotent_for_one_agent_and_video():
    db = sqlite3.connect(":memory:")
    init_ban_tables(db)

    first = award_ban_upload(db, 17, "video-public-id")
    duplicate = award_ban_upload(db, 17, "video-public-id")

    rows = db.execute(
        "SELECT amount_ban FROM ban_transactions "
        "WHERE agent_id=? AND video_id=? AND reason='video_upload'",
        (17, "video-public-id"),
    ).fetchall()
    assert rows == [(REWARDS["upload"],)]
    assert first == REWARDS["upload"]
    assert duplicate == 0.0


def test_upload_reward_remains_distinct_per_video():
    db = sqlite3.connect(":memory:")
    init_ban_tables(db)

    award_ban_upload(db, 17, "video-a")
    award_ban_upload(db, 17, "video-b")

    total = db.execute(
        "SELECT SUM(amount_ban) FROM ban_transactions "
        "WHERE agent_id=? AND reason='video_upload'",
        (17,),
    ).fetchone()[0]
    assert total == 2 * REWARDS["upload"]
