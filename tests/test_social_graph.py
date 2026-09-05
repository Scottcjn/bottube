# SPDX-License-Identifier: MIT
import os
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_social_bootstrap.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_social_bootstrap.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    """Redirect the hardcoded production DB path to the test bootstrap path.

    `paypal_packages`/`bottube_server` import-time code opens
    `/root/bottube/bottube.db` unconditionally before the `client` fixture
    gets a chance to monkeypatch `DB_PATH`, so without this shim collecting
    this test module would create or touch the real production database.
    """
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    """Force paypal_packages' schema init onto the test bootstrap DB.

    `bottube_server` calls `paypal_packages.init_store_db()` with no
    arguments at import time, which would otherwise default to the real
    on-disk store; pinning it here keeps the module import side effect
    isolated from production data.
    """
    bootstrap_path = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """Yield a Flask test client wired to a throwaway per-test SQLite file.

    Also clears the module-level rate-limit buckets: social-graph and
    agent-interactions endpoints are rate limited, and a leftover bucket
    from a previous test in the same process would make an otherwise
    correct request fail with 429 instead of the assertion actually being
    tested.
    """
    db_path = tmp_path / "bottube_social_graph_test.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, created_at: float) -> int:
    """Insert a minimal agent row and return its id.

    `created_at` is a caller-controlled float rather than `time.time()` so
    seed helpers below can build a deterministic, orderable timeline of
    interactions instead of racing real wall-clock time.
    """
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, bio, avatar_url, created_at, last_active)
            VALUES (?, ?, ?, '', '', ?, ?)
            """,
            (agent_name, agent_name.title(), f"bottube_sk_{agent_name}", created_at, created_at),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(video_id: str, agent_id: int, created_at: float) -> None:
    """Seed a video row owned by `agent_id` so comments/votes have a target.

    The social-graph and interactions endpoints join through videos to
    attribute a comment or vote to its owner; without a video row those
    joins would silently drop the seeded interaction instead of exercising
    the code path under test.
    """
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos (video_id, agent_id, title, filename, created_at, is_removed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (video_id, agent_id, f"Video {video_id}", f"{video_id}.mp4", created_at),
        )
        db.commit()


def _insert_comment(video_id: str, agent_id: int, content: str, created_at: float) -> None:
    """Record `agent_id` commenting on `video_id`, feeding the commenter tally.

    Both the social graph's pairwise `strength` score and the per-agent
    `commenters`/`comments_given` breakdowns count rows in this table, so
    tests build expected results by counting how many times this helper
    was called rather than inspecting the endpoint's SQL.
    """
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO comments (video_id, agent_id, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (video_id, agent_id, content, created_at),
        )
        db.commit()


def _insert_vote(video_id: str, agent_id: int, vote: int, created_at: float) -> None:
    """Record `agent_id` voting on `video_id`, feeding the liker tally.

    Mirrors `_insert_comment` for the votes table: only upvotes (`vote=1`)
    are used by the seed data below because the endpoints under test count
    likes, not net score, so a downvote would silently change what the
    assertions are actually checking.
    """
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO votes (agent_id, video_id, vote, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (agent_id, video_id, vote, created_at),
        )
        db.commit()


def _insert_subscription(follower_id: int, following_id: int, created_at: float) -> None:
    """Record `follower_id` following `following_id`, feeding follower counts.

    Direction matters here: the interactions endpoint reports followers
    under "incoming" for `following_id` and the subscription itself under
    "outgoing" for `follower_id`, so swapping the two arguments would seed
    a valid row that asserts against the wrong side of the graph.
    """
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO subscriptions (follower_id, following_id, created_at)
            VALUES (?, ?, ?)
            """,
            (follower_id, following_id, created_at),
        )
        db.commit()


def _seed_interaction_data():
    """Build a fixed three-agent interaction graph shared by every test below.

    Alice is deliberately the hub: she has more incoming than outgoing
    interactions from Bob and Carol, so `top_pairs`/`most_connected` have an
    unambiguous top result and the exact-count assertions in the tests
    below don't depend on ordering ties.
    """
    t = 1000.0
    alice_id = _insert_agent("alice", t)
    bob_id = _insert_agent("bob", t + 1)
    carol_id = _insert_agent("carol", t + 2)

    _insert_video("alice_vid_01", alice_id, t + 10)
    _insert_video("bob_vid_001", bob_id, t + 11)
    _insert_video("carol_vid01", carol_id, t + 12)

    # Incoming interactions for alice.
    _insert_comment("alice_vid_01", bob_id, "great cut", t + 20)
    _insert_comment("alice_vid_01", bob_id, "nice pacing", t + 21)
    _insert_comment("alice_vid_01", carol_id, "solid intro", t + 22)
    _insert_vote("alice_vid_01", bob_id, 1, t + 23)
    _insert_vote("alice_vid_01", carol_id, 1, t + 24)
    _insert_subscription(bob_id, alice_id, t + 25)
    _insert_subscription(carol_id, alice_id, t + 26)

    # Outgoing interactions from alice.
    _insert_comment("bob_vid_001", alice_id, "love the style", t + 30)
    _insert_comment("bob_vid_001", alice_id, "clean framing", t + 31)
    _insert_comment("bob_vid_001", alice_id, "nice loops", t + 32)
    _insert_comment("carol_vid01", alice_id, "great color grade", t + 33)
    _insert_vote("bob_vid_001", alice_id, 1, t + 34)
    _insert_vote("carol_vid01", alice_id, 1, t + 35)
    _insert_subscription(alice_id, bob_id, t + 36)
    _insert_subscription(alice_id, carol_id, t + 37)


def test_social_graph_has_expected_keys_and_limit(client):
    """`/api/social/graph` should shape its response, not just return 200.

    Checks response shape with subset assertions (`<=`) rather than
    equality so the endpoint stays free to add new fields later without
    breaking this test; only `limit`'s effect on `top_pairs` length is
    pinned exactly, since that's the behavior actually under test.
    """
    _seed_interaction_data()

    resp = client.get("/api/social/graph?limit=1")
    assert resp.status_code == 200
    body = resp.get_json()

    assert {"network", "top_pairs", "most_connected"} <= set(body.keys())
    assert {"total_agents", "total_subscriptions", "active_commenters", "active_likers"} <= set(
        body["network"].keys()
    )
    assert body["network"]["total_agents"] == 3
    assert len(body["top_pairs"]) == 1
    assert len(body["most_connected"]) >= 1

    top_pair = body["top_pairs"][0]
    assert {"from", "from_display", "to", "to_display", "comments", "likes", "strength"} <= set(
        top_pair.keys()
    )


@pytest.mark.parametrize("query, expected_error", [
    ("limit=abc", "limit must be an integer"),
    ("limit=0", "limit must be >= 1"),
    ("limit=51", "limit must be <= 50"),
])
def test_social_graph_rejects_invalid_limit(client, query, expected_error):
    """Non-integer and out-of-range `limit` values must 400 with a specific message.

    No seed data is needed: validation is expected to run before the query
    touches the (empty) database, so a bug that validates after querying
    would still pass a test that seeded data first.
    """
    resp = client.get(f"/api/social/graph?{query}")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": expected_error}


def test_agent_interactions_shape_not_found_and_limit(client):
    """Cover both the 404 branch and the full success shape in one test.

    Checking the unknown-agent 404 message right before the happy path
    guards against a common regression where a broadened query stops
    filtering by agent and starts returning results for anyone.
    """
    _seed_interaction_data()

    not_found = client.get("/api/agents/no_such_agent/interactions")
    assert not_found.status_code == 404
    assert not_found.get_json()["error"] == "Agent not found"

    resp = client.get("/api/agents/alice/interactions?limit=1")
    assert resp.status_code == 200
    body = resp.get_json()

    assert {"agent", "incoming", "outgoing"} <= set(body.keys())
    assert {"commenters", "likers", "followers"} <= set(body["incoming"].keys())

    # limit=1 should apply to each section.
    assert len(body["incoming"]["commenters"]) == 1
    assert len(body["incoming"]["likers"]) == 1
    assert len(body["incoming"]["followers"]) == 1
    assert len(body["outgoing"]) == 1

    commenter = body["incoming"]["commenters"][0]
    assert {"agent_name", "display_name", "avatar_url", "comment_count", "last_at"} <= set(
        commenter.keys()
    )

    liker = body["incoming"]["likers"][0]
    assert {"agent_name", "display_name", "avatar_url", "like_count", "last_at"} <= set(
        liker.keys()
    )

    follower = body["incoming"]["followers"][0]
    assert {"agent_name", "display_name", "avatar_url", "subscribed_at"} <= set(
        follower.keys()
    )

    outgoing = body["outgoing"][0]
    assert {"agent_name", "display_name", "avatar_url", "comments_given", "likes_given", "total"} <= set(
        outgoing.keys()
    )


@pytest.mark.parametrize("query, expected_error", [
    ("limit=abc", "limit must be an integer"),
    ("limit=0", "limit must be >= 1"),
    ("limit=51", "limit must be <= 50"),
])
def test_agent_interactions_rejects_invalid_limit(client, query, expected_error):
    """Same invalid-`limit` matrix as the graph endpoint, but on a real agent.

    Data is seeded first (unlike the sibling graph test) so a validation
    bug that only triggers once there's something to paginate can't hide
    behind an otherwise-empty result set.
    """
    _seed_interaction_data()

    resp = client.get(f"/api/agents/alice/interactions?{query}")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": expected_error}


def test_agent_profile_does_not_run_discarded_interaction_aggregates(client, monkeypatch):
    """The profile response must not execute social aggregates it never returns."""
    _seed_interaction_data()
    statements = []
    original_get_db = bottube_server.get_db

    def traced_get_db():
        db = original_get_db()
        db.set_trace_callback(statements.append)
        return db

    monkeypatch.setattr(bottube_server, "get_db", traced_get_db)

    response = client.get("/api/agents/alice")

    assert response.status_code == 200
    assert response.get_json()["agent"]["agent_name"] == "alice"
    normalized = [" ".join(statement.lower().split()) for statement in statements]
    assert not any(
        "group by a2.id order by cnt desc limit 8" in statement
        or "order by comments_given + likes_given desc limit 8" in statement
        for statement in normalized
    )
