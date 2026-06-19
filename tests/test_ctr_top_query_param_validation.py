# SPDX-License-Identifier: MIT


class FakeCTRTracker:
    def __init__(self):
        self.calls = []

    def get_top_by_ctr(self, *, limit, min_impressions):
        self.calls.append((limit, min_impressions))
        return [{"video_id": "vid_high", "ctr": 0.5}]


def test_ctr_top_rejects_invalid_query_values(client, monkeypatch):
    import bottube_server

    tracker = FakeCTRTracker()
    monkeypatch.setattr(bottube_server, "_get_ctr_tracker", lambda: tracker)

    cases = {
        "limit=abc": "limit must be an integer",
        "limit=0": "limit must be >= 1",
        "limit=51": "limit must be <= 50",
        "min_impressions=abc": "min_impressions must be an integer",
        "min_impressions=-1": "min_impressions must be >= 0",
    }

    for query, expected_error in cases.items():
        resp = client.get(f"/api/ctr/top?{query}")

        assert resp.status_code == 400
        assert resp.get_json() == {"error": expected_error}

    assert tracker.calls == []


def test_ctr_top_accepts_default_and_boundary_values(client, monkeypatch):
    import bottube_server

    tracker = FakeCTRTracker()
    monkeypatch.setattr(bottube_server, "_get_ctr_tracker", lambda: tracker)

    default_resp = client.get("/api/ctr/top")
    lower_resp = client.get("/api/ctr/top?limit=1&min_impressions=0")
    upper_resp = client.get("/api/ctr/top?limit=50&min_impressions=25")

    assert default_resp.status_code == 200
    assert lower_resp.status_code == 200
    assert upper_resp.status_code == 200
    assert default_resp.get_json()["ok"] is True
    assert lower_resp.get_json()["ok"] is True
    assert upper_resp.get_json()["ok"] is True
    assert tracker.calls == [(20, 10), (1, 0), (50, 25)]
