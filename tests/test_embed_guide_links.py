import os
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_embed_guide.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_embed_guide.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import bottube_server  # noqa: E402

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_embed_guide.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def test_iframe_embed_examples_use_iframe_safe_embed_route(client):
    response = client.get("/embed-guide")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'src="https://bottube.ai/embed/VIDEO_ID"' in html
    assert 'iframe.src = "https://bottube.ai/embed/" + videoId' in html
    assert 'iframe src="https://bottube.ai/watch/' not in html
