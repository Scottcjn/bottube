# SPDX-License-Identifier: MIT
"""Behavioral coverage for the public agent-directory controls."""


def _seed_agents(client):
    import bottube_server

    with client.application.app_context():
        db = bottube_server.get_db()
        agents = [
            ("alpha_creator", "alpha-key", "Alpha Creator", "Needle specialist", 100.0),
            ("beta_creator", "beta-key", "Beta Creator", "Popular channel", 300.0),
            ("gamma_creator", "gamma-key", "Gamma Creator", "Quiet channel", 200.0),
        ]
        db.executemany(
            """INSERT INTO agents
               (agent_name, api_key, display_name, bio, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            agents,
        )
        agent_ids = {
            row["agent_name"]: row["id"]
            for row in db.execute(
                "SELECT id, agent_name FROM agents WHERE agent_name LIKE '%_creator'"
            ).fetchall()
        }
        videos = [
            ("alpha-one", agent_ids["alpha_creator"], "Alpha One", 1, 101.0),
            ("alpha-two", agent_ids["alpha_creator"], "Alpha Two", 1, 102.0),
            ("beta-one", agent_ids["beta_creator"], "Beta One", 1000, 301.0),
        ]
        db.executemany(
            """INSERT INTO videos
               (video_id, agent_id, title, filename, views, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (video_id, agent_id, title, f"{video_id}.mp4", views, created_at)
                for video_id, agent_id, title, views, created_at in videos
            ],
        )
        db.commit()


def _positions(html):
    return {
        name: html.index(f"@{name}")
        for name in ("alpha_creator", "beta_creator", "gamma_creator")
    }


def test_agent_directory_search_filters_name_display_name_and_bio(client):
    _seed_agents(client)

    response = client.get("/agents?q=Needle")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "@alpha_creator" in html
    assert "@beta_creator" not in html
    assert "@gamma_creator" not in html
    assert 'value="Needle"' in html
    assert 'Agents matching "Needle"' in html


def test_agent_directory_sort_tabs_apply_requested_order(client):
    _seed_agents(client)

    videos_html = client.get("/agents?sort=videos").get_data(as_text=True)
    videos_positions = _positions(videos_html)
    assert videos_positions["alpha_creator"] < videos_positions["beta_creator"]
    assert videos_positions["beta_creator"] < videos_positions["gamma_creator"]

    recent_html = client.get("/agents?sort=recent").get_data(as_text=True)
    recent_positions = _positions(recent_html)
    assert recent_positions["beta_creator"] < recent_positions["gamma_creator"]
    assert recent_positions["gamma_creator"] < recent_positions["alpha_creator"]

    name_html = client.get("/agents?sort=name").get_data(as_text=True)
    name_positions = _positions(name_html)
    assert name_positions["alpha_creator"] < name_positions["beta_creator"]
    assert name_positions["beta_creator"] < name_positions["gamma_creator"]


def test_agent_directory_invalid_sort_falls_back_to_video_count(client):
    _seed_agents(client)

    html = client.get("/agents?sort=not-a-sort").get_data(as_text=True)

    positions = _positions(html)
    assert positions["alpha_creator"] < positions["beta_creator"]
    assert positions["beta_creator"] < positions["gamma_creator"]
    assert 'sort=videos" class="active"' in html
