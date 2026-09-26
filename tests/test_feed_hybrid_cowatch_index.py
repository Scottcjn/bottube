from __future__ import annotations

import ast
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "bottube_server.py"


def _server_schema() -> str:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "SCHEMA" for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("SCHEMA assignment not found")


def _cowatch_plan(db: sqlite3.Connection) -> list[str]:
    anchors = ["a1", "a2", "a3"]
    placeholders = ",".join("?" for _ in anchors)
    query = f"""SELECT v2.video_id AS vid,
                       COUNT(DISTINCT v1.ip_address) AS cnt
                  FROM views v1
                  JOIN views v2
                    ON v1.ip_address = v2.ip_address
                   AND v1.video_id != v2.video_id
                 WHERE v1.video_id IN ({placeholders})
                   AND v1.ip_address IS NOT NULL
                   AND v1.ip_address != ''
                 GROUP BY v2.video_id
                 ORDER BY cnt DESC
                 LIMIT 400"""
    return [
        str(row[3])
        for row in db.execute("EXPLAIN QUERY PLAN " + query, anchors).fetchall()
    ]


def test_views_schema_has_cowatch_lookup_index():
    db = sqlite3.connect(":memory:")
    try:
        db.executescript(_server_schema())
        columns = [
            row[2]
            for row in db.execute("PRAGMA index_info('idx_views_ip_video')").fetchall()
        ]
    finally:
        db.close()

    assert columns == ["ip_address", "video_id"]


def test_cowatch_plan_searches_v2_by_ip_instead_of_scanning_views():
    db = sqlite3.connect(":memory:")
    try:
        db.executescript(_server_schema())
        plan = _cowatch_plan(db)
    finally:
        db.close()

    assert any(
        "SEARCH v2 USING COVERING INDEX idx_views_ip_video (ip_address=?)" in step
        for step in plan
    ), plan
    assert not any("SCAN v2" in step for step in plan), plan