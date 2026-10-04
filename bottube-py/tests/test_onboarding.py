# SPDX-License-Identifier: MIT
"""register() / accept_terms() / upload(category=...) behaviour."""

import json
import pickle

import pytest

import bottube
from bottube import BoTTubeClient, BoTTubeError, RegisterResult


REGISTER_RESPONSE = {
    "ok": True,
    "agent_name": "my-bot",
    "api_key": "bottube_sk_abc123",
    "claim_url": "https://bottube.ai/claim/my-bot/tok",
    "terms": {
        "version": "1.1",
        "terms_url": "https://bottube.ai/terms",
        "acceptance_required": True,
        "accept_endpoint": "/api/agents/me/accept-terms",
    },
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    """Records requests; answers from a {(method, path): response} map."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def request(self, method, url, **kwargs):
        path = url.split("://", 1)[1].split("/", 1)[1]
        path = "/" + path
        self.calls.append((method, path, kwargs))
        route = self.routes.get((method, path))
        if route is None:
            return FakeResponse(404, text="<html>404</html>")
        return route(kwargs) if callable(route) else route


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    def _make(routes, **kwargs):
        client = BoTTubeClient(base_url="https://bottube.test", **kwargs)
        client._session = FakeSession(routes)
        return client

    return _make


def _accept_echo(kwargs):
    body = kwargs.get("json") or {}
    return FakeResponse(200, {"ok": True, "tos_version_accepted": body.get("version", "1.1")})


# -- RegisterResult -------------------------------------------------------

def test_register_result_is_the_api_key_string():
    result = RegisterResult(REGISTER_RESPONSE)
    assert isinstance(result, str)
    assert result == "bottube_sk_abc123"
    assert result.api_key == "bottube_sk_abc123"
    assert type(result.api_key) is str
    assert result.startswith("bottube_sk_")
    assert result[0] == "b" and result[:10] == "bottube_sk"
    assert f"{result}" == "bottube_sk_abc123"
    assert json.dumps({"k": result}) == '{"k": "bottube_sk_abc123"}'
    assert {"X-API-Key": result}["X-API-Key"] == "bottube_sk_abc123"


def test_register_result_exposes_full_response():
    result = RegisterResult(REGISTER_RESPONSE)
    assert result.claim_url == REGISTER_RESPONSE["claim_url"]
    assert result.terms["version"] == "1.1"
    assert result.terms_version == "1.1"
    assert result.agent_name == "my-bot"
    # python-sdk style dict access keeps working too
    assert result["api_key"] == "bottube_sk_abc123"
    assert result["claim_url"] == REGISTER_RESPONSE["claim_url"]
    assert result.get("missing", "d") == "d"
    assert "claim_url" in result
    with pytest.raises(KeyError):
        result["nope"]


def test_register_result_survives_pickle():
    result = RegisterResult(REGISTER_RESPONSE)
    clone = pickle.loads(pickle.dumps(result))
    assert clone == result and clone.claim_url == result.claim_url


def test_register_result_without_terms():
    result = RegisterResult({"api_key": "k"})
    assert result.terms == {} and result.terms_version is None
    assert result.claim_url == ""


# -- register() -----------------------------------------------------------

def test_register_minimal_signature_returns_key_and_response(make_client, tmp_path):
    client = make_client({("POST", "/api/register"): FakeResponse(201, REGISTER_RESPONSE)})
    key = client.register("my-bot")  # the homepage example
    assert key == "bottube_sk_abc123"
    assert key.claim_url.startswith("https://bottube.ai/claim/")
    assert client.api_key == "bottube_sk_abc123"
    assert client.terms_version == "1.1"
    method, path, kwargs = client._session.calls[0]
    assert kwargs["json"]["display_name"] == "my-bot"
    saved = json.loads((tmp_path / ".bottube" / "credentials.json").read_text())
    assert saved["api_key"] == "bottube_sk_abc123"
    assert type(saved["api_key"]) is str


def test_register_without_saving(make_client, tmp_path):
    client = make_client({("POST", "/api/register"): FakeResponse(201, REGISTER_RESPONSE)})
    client.register("my-bot", save_credentials=False)
    assert not (tmp_path / ".bottube" / "credentials.json").exists()


# -- accept_terms() -------------------------------------------------------

def test_accept_terms_uses_version_from_register(make_client):
    client = make_client({
        ("POST", "/api/register"): FakeResponse(201, REGISTER_RESPONSE),
        ("POST", "/api/agents/me/accept-terms"): _accept_echo,
    })
    client.register("my-bot", save_credentials=False)
    result = client.accept_terms()
    assert result["tos_version_accepted"] == "1.1"
    method, path, kwargs = client._session.calls[-1]
    assert kwargs["json"] == {"version": "1.1"}
    assert kwargs["headers"]["X-API-Key"] == "bottube_sk_abc123"
    assert not any(p == "/api/tos" for _, p, _ in client._session.calls)


def test_accept_terms_explicit_version_wins(make_client):
    client = make_client({("POST", "/api/agents/me/accept-terms"): _accept_echo},
                         api_key="k")
    client.terms_version = "1.1"
    client.accept_terms(version="2.0")
    assert client._session.calls[-1][2]["json"] == {"version": "2.0"}
    assert client.terms_version == "2.0"


def test_accept_terms_fetches_current_version(make_client):
    client = make_client({
        ("GET", "/api/tos"): FakeResponse(200, {"ok": True, "version": "1.1"}),
        ("POST", "/api/agents/me/accept-terms"): _accept_echo,
    }, api_key="k")
    client.accept_terms()
    assert client._session.calls[0][:2] == ("GET", "/api/tos")
    assert client._session.calls[-1][2]["json"] == {"version": "1.1"}


def test_accept_terms_without_tos_endpoint_sends_no_version(make_client):
    # /api/tos missing (404 HTML): send {} and let the server use its current version.
    client = make_client({("POST", "/api/agents/me/accept-terms"): _accept_echo},
                         api_key="k")
    result = client.accept_terms()
    assert client._session.calls[-1][2]["json"] == {}
    assert result["tos_version_accepted"] == "1.1"


def test_accept_terms_version_mismatch_raises(make_client):
    mismatch = FakeResponse(400, {"ok": False, "error": "version_mismatch",
                                  "expected": "1.1", "received": "1.0"})
    client = make_client({("POST", "/api/agents/me/accept-terms"): mismatch},
                         api_key="k")
    with pytest.raises(BoTTubeError) as exc:
        client.accept_terms(version="1.0")
    assert exc.value.status_code == 400
    assert exc.value.response["expected"] == "1.1"


def test_accept_terms_requires_api_key(make_client):
    client = make_client({})
    with pytest.raises(BoTTubeError):
        client.accept_terms()
    assert client._session.calls == []


# -- upload(category=...) -------------------------------------------------

def _upload_route(kwargs):
    return FakeResponse(201, {"ok": True, "video_id": "v1", "form": kwargs["data"]})


def test_upload_sends_category(make_client, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 16)
    client = make_client({("POST", "/api/upload"): _upload_route}, api_key="k")
    result = client.upload(str(video), title="Song", category="music")
    assert result["form"]["category"] == "music"
    assert result["form"]["title"] == "Song"
    files = client._session.calls[-1][2]["files"]
    assert "video" in files and files["video"].closed


def test_upload_without_category_omits_field(make_client, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 16)
    client = make_client({("POST", "/api/upload"): _upload_route}, api_key="k")
    result = client.upload(str(video), title="Clip")
    assert "category" not in result["form"]


def test_version_marks_unreleased_changes():
    assert bottube.__version__ == "1.7.0.dev0"
