from __future__ import annotations


def test_stars_redirects_to_current_star_drive_bounty(client) -> None:
    response = client.get("/stars", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == (
        "https://github.com/Scottcjn/rustchain-bounties/issues/1677"
    )
