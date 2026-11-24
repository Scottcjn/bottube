# SPDX-License-Identifier: MIT
"""Regression tests for webhook outbound SSRF protection."""

import socket
import ssl
import threading

import pytest


def _fake_addrinfo(*ips):
    """Build socket.getaddrinfo tuples for the supplied IP literals."""
    results = []
    for ip in ips:
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        sockaddr = (ip, 443, 0, 0) if family == socket.AF_INET6 else (ip, 443)
        results.append((family, socket.SOCK_STREAM, 6, "", sockaddr))
    return results


def _insert_raw_webhook(app, agent_name: str, url: str) -> int:
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        agent = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            (agent_name,),
        ).fetchone()
        cur = db.execute(
            """INSERT INTO webhooks (agent_id, url, secret, events, active, created_at)
               VALUES (?, ?, ?, '*', 1, 1.0)""",
            (agent["id"], url, "whsec_unit_test_value"),
        )
        db.commit()
        return int(cur.lastrowid)


def _agent_id(app, agent_name: str) -> int:
    import bottube_server

    with app.app_context():
        row = bottube_server.get_db().execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            (agent_name,),
        ).fetchone()
        return int(row["id"])


def test_create_webhook_rejects_ssrf_targets(app, client, registered_agent):
    headers = {"X-API-Key": registered_agent["api_key"]}
    bad_urls = (
        "http://example.com/hook",
        "https://localhost/hook",
        "https://LOCALHOST./hook",
        "https://sub.localhost/hook",
        "https://127.0.0.1/hook",
        "https://127.0.0.1:9053/wallet/transactionById",
        "https://0.0.0.0/hook",
        "https://10.0.0.1/hook",
        "https://172.16.0.1/hook",
        "https://192.168.1.1/hook",
        "https://100.64.0.1/hook",
        "https://169.254.169.254/latest/meta-data/",
        "https://224.0.0.1/hook",
        "https://255.255.255.255/hook",
        "https://[::1]/hook",
        "https://[::]/hook",
        "https://[fc00::1]/hook",
        "https://[fe80::1]/hook",
        "https://[fe80::1%25eth0]/hook",
        "https://[::ffff:127.0.0.1]/hook",
        "https://[::ffff:169.254.169.254]/hook",
        "https://[2002:7f00:0001::1]/hook",
        "https://[2001:0000:4136:e378:8000:63bf:3fff:fdd2]/hook",
        "https://2130706433/hook",
        "https://0x7f000001/hook",
        "https://0177.0.0.1/hook",
        "https://127.1/hook",
        "https://ergo:9053/info",
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://printer.local/hook",
        "https://user:pass@example.com/hook",
        "https://example.com@127.0.0.1/hook",
        "https://127.0.0.1\\@example.com/hook",
        "https://127%2e0%2e0%2e1/hook",
        "https://%6c%6f%63%61%6c%68%6f%73%74/hook",
        "https://example.com:0/hook",
        "https://example.com:99999/hook",
        "https://example.com/hook\r\nX-Injected: 1",
        "https://example.com/" + ("a" * 2050),
    )

    for bad_url in bad_urls:
        resp = client.post("/api/webhooks", headers=headers, json={"url": bad_url})
        assert resp.status_code == 400, (bad_url, resp.get_json())
        assert "error" in resp.get_json()

    import bottube_server

    with app.app_context():
        count = (
            bottube_server.get_db()
            .execute("SELECT COUNT(*) FROM webhooks")
            .fetchone()[0]
        )
    assert count == 0


def test_create_webhook_accepts_public_ipv6_and_rejects_private_or_mixed_dns(
    app, client, registered_agent, monkeypatch
):
    import bottube_server

    headers = {"X-API-Key": registered_agent["api_key"]}

    # Single loopback answer
    monkeypatch.setattr(
        bottube_server.socket,
        "getaddrinfo",
        lambda host, port, *a, **kw: _fake_addrinfo("127.0.0.1"),
    )
    resp_loopback = client.post(
        "/api/webhooks",
        headers=headers,
        json={"url": "https://rebind.example.com/hook"},
    )
    assert resp_loopback.status_code == 400

    # Mixed public + metadata answers must also be rejected
    monkeypatch.setattr(
        bottube_server.socket,
        "getaddrinfo",
        lambda host, port, *a, **kw: _fake_addrinfo("93.184.216.34", "169.254.169.254"),
    )
    resp_mixed = client.post(
        "/api/webhooks",
        headers=headers,
        json={"url": "https://mixed.example.com/hook"},
    )
    assert resp_mixed.status_code == 400

    # Teredo DNS answer must be rejected
    monkeypatch.setattr(
        bottube_server.socket,
        "getaddrinfo",
        lambda host, port, *a, **kw: _fake_addrinfo(
            "2001:0000:4136:e378:8000:63bf:3fff:fdd2"
        ),
    )
    resp_teredo = client.post(
        "/api/webhooks",
        headers=headers,
        json={"url": "https://teredo.example.com/hook"},
    )
    assert resp_teredo.status_code == 400

    # Globally routable IPv6 literal is accepted without DNS lookup
    resp_ipv6 = client.post(
        "/api/webhooks",
        headers=headers,
        json={"url": "https://[2606:2800:220:1:248:1893:25c8:1946]/hook"},
    )
    assert resp_ipv6.status_code == 201


def test_pinned_https_connection_dials_pinned_ip_with_sni(app, monkeypatch):
    import bottube_server

    dialed = []
    wrapped = []

    class _FakeSocket:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class _FakeContext:
        def __init__(self, fail=False):
            self.fail = fail
            self.verify_mode = ssl.CERT_REQUIRED
            self.check_hostname = True

        def wrap_socket(self, sock, *, server_hostname=None):
            wrapped.append((sock, server_hostname))
            if self.fail:
                raise OSError("tls handshake failed")
            return sock

    sock_ok = _FakeSocket()
    monkeypatch.setattr(
        bottube_server.socket,
        "create_connection",
        lambda addr, timeout=None, source_address=None: dialed.append(addr) or sock_ok,
    )
    conn = bottube_server._PinnedHTTPSConnection(
        "hooks.example.com",
        8443,
        pinned_ip="93.184.216.34",
        timeout=5.0,
        context=_FakeContext(fail=False),
    )
    conn.connect()
    assert dialed == [("93.184.216.34", 8443)]
    assert wrapped[-1][1] == "hooks.example.com"
    assert conn.sock is sock_ok

    sock_fail = _FakeSocket()
    monkeypatch.setattr(
        bottube_server.socket,
        "create_connection",
        lambda addr, timeout=None, source_address=None: sock_fail,
    )
    conn_fail = bottube_server._PinnedHTTPSConnection(
        "hooks.example.com",
        443,
        pinned_ip="93.184.216.34",
        timeout=5.0,
        context=_FakeContext(fail=True),
    )
    with pytest.raises(OSError, match="tls handshake failed"):
        conn_fail.connect()
    assert sock_fail.closed is True


def test_test_webhook_blocks_dns_rebinding_and_preexisting_internal_hooks(
    app, client, registered_agent, monkeypatch
):
    import bottube_server

    headers = {"X-API-Key": registered_agent["api_key"]}
    connected_targets = []

    def fail_if_connected(*args, **kwargs):
        connected_targets.append((args, kwargs))
        raise AssertionError("SSRF target must never open a socket connection")

    monkeypatch.setattr(bottube_server.socket, "create_connection", fail_if_connected)

    # 1. Register while DNS points to a public IP
    monkeypatch.setattr(
        bottube_server.socket,
        "getaddrinfo",
        lambda host, port, *a, **kw: _fake_addrinfo("93.184.216.34"),
    )
    create_resp = client.post(
        "/api/webhooks",
        headers=headers,
        json={"url": "https://rebind.example.com/hook"},
    )
    assert create_resp.status_code == 201

    hooks = client.get("/api/webhooks", headers=headers).get_json()["webhooks"]
    rebind_hook_id = hooks[0]["id"]

    # 2. Rebind DNS to localhost before /test
    monkeypatch.setattr(
        bottube_server.socket,
        "getaddrinfo",
        lambda host, port, *a, **kw: _fake_addrinfo("127.0.0.1"),
    )
    rebind_resp = client.post(
        f"/api/webhooks/{rebind_hook_id}/test",
        headers=headers,
    )
    assert rebind_resp.status_code == 400
    assert rebind_resp.get_json()["ok"] is False
    assert connected_targets == []

    # 3. Pre-existing malicious row already stored in DB must also be blocked
    legacy_id = _insert_raw_webhook(
        app,
        registered_agent["agent_name"],
        "http://127.0.0.1:9053/wallet/transactionById",
    )
    legacy_resp = client.post(
        f"/api/webhooks/{legacy_id}/test",
        headers=headers,
    )
    assert legacy_resp.status_code == 400
    assert legacy_resp.get_json()["ok"] is False
    assert connected_targets == []


def test_test_webhook_pins_validated_ip_and_blocks_redirects_and_5xx(
    app, client, registered_agent, monkeypatch
):
    import bottube_server

    headers = {"X-API-Key": registered_agent["api_key"]}
    monkeypatch.setattr(
        bottube_server.socket,
        "getaddrinfo",
        lambda host, port, *a, **kw: _fake_addrinfo("93.184.216.34"),
    )
    create_resp = client.post(
        "/api/webhooks",
        headers=headers,
        json={"url": "https://hooks.example.com/events?source=bot"},
    )
    assert create_resp.status_code == 201
    hook_id = (
        client.get("/api/webhooks", headers=headers)
        .get_json()["webhooks"][0]["id"]
    )

    recorded = []

    class _FakeResp:
        def __init__(self, status):
            self.status = status

        def read(self, amt=None):
            return b"ok"

    class _FakePinnedConn:
        next_status = 204

        def __init__(self, host, port=None, *, pinned_ip, timeout=10, context=None):
            recorded.append({"host": host, "port": port, "pinned_ip": pinned_ip})
            self.closed = False

        def request(self, method, target, body=None, headers=None):
            recorded[-1].update(
                {"method": method, "target": target, "headers": headers}
            )

        def getresponse(self):
            return _FakeResp(self.next_status)

        def close(self):
            self.closed = True

    monkeypatch.setattr(bottube_server, "_PinnedHTTPSConnection", _FakePinnedConn)

    # Normal 2xx response uses pinned IP and original Host/SNI
    ok_resp = client.post(f"/api/webhooks/{hook_id}/test", headers=headers)
    assert ok_resp.status_code == 200
    assert ok_resp.get_json() == {"ok": True, "status": 204}
    assert recorded[-1]["host"] == "hooks.example.com"
    assert recorded[-1]["port"] == 443
    assert recorded[-1]["pinned_ip"] == "93.184.216.34"
    assert recorded[-1]["target"] == "/events?source=bot"

    # 302 redirect to http://127.0.0.1 must never be followed
    _FakePinnedConn.next_status = 302
    calls_before = len(recorded)
    redir_resp = client.post(f"/api/webhooks/{hook_id}/test", headers=headers)
    assert redir_resp.status_code == 502
    assert redir_resp.get_json() == {
        "ok": False,
        "error": "Webhook redirects are not allowed",
    }
    assert len(recorded) == calls_before + 1

    # 500 from remote endpoint returns 502 with status summary
    _FakePinnedConn.next_status = 500
    err_resp = client.post(f"/api/webhooks/{hook_id}/test", headers=headers)
    assert err_resp.status_code == 502
    assert err_resp.get_json() == {
        "ok": False,
        "error": "Webhook endpoint returned HTTP 500",
    }


def test_test_webhook_hides_internal_exception_details(
    app, client, registered_agent, monkeypatch
):
    import bottube_server

    headers = {"X-API-Key": registered_agent["api_key"]}
    monkeypatch.setattr(
        bottube_server.socket,
        "getaddrinfo",
        lambda host, port, *a, **kw: _fake_addrinfo("93.184.216.34"),
    )
    assert client.post(
        "/api/webhooks",
        headers=headers,
        json={"url": "https://hooks.example.com/fail"},
    ).status_code == 201
    hook_id = (
        client.get("/api/webhooks", headers=headers)
        .get_json()["webhooks"][0]["id"]
    )

    class _BoomConn:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            raise ConnectionRefusedError(
                "[Errno 111] secret-internal-host:9053 refused"
            )

        def close(self):
            pass

    monkeypatch.setattr(bottube_server, "_PinnedHTTPSConnection", _BoomConn)
    resp = client.post(f"/api/webhooks/{hook_id}/test", headers=headers)
    assert resp.status_code == 502
    body = resp.get_json()
    assert body == {"ok": False, "error": "Webhook delivery failed"}
    assert "secret-internal-host" not in str(body)
    assert "9053" not in str(body)


def test_fire_webhooks_blocks_private_and_redirects_and_delivers_public(
    app, registered_agent, monkeypatch
):
    import bottube_server

    private_id = _insert_raw_webhook(
        app,
        registered_agent["agent_name"],
        "https://169.254.169.254/latest/meta-data/",
    )
    redir_id = _insert_raw_webhook(
        app,
        registered_agent["agent_name"],
        "https://redir.example.com/hook",
    )
    public_id = _insert_raw_webhook(
        app,
        registered_agent["agent_name"],
        "https://ok.example.com/hook",
    )

    monkeypatch.setattr(
        bottube_server.socket,
        "getaddrinfo",
        lambda host, port, *a, **kw: _fake_addrinfo("93.184.216.34"),
    )

    attempts_by_host = []

    class _FakeResp:
        def __init__(self, status):
            self.status = status

        def read(self, amt=None):
            return b""

    class _FakeConn:
        def __init__(self, host, port=None, *, pinned_ip, timeout=10, context=None):
            self.host = host
            attempts_by_host.append((host, pinned_ip))

        def request(self, method, target, body=None, headers=None):
            pass

        def getresponse(self):
            if self.host == "redir.example.com":
                return _FakeResp(307)
            return _FakeResp(200)

        def close(self):
            pass

    monkeypatch.setattr(bottube_server, "_PinnedHTTPSConnection", _FakeConn)

    started_threads = []
    orig_thread = threading.Thread

    def _tracking_thread(*args, **kwargs):
        t = orig_thread(*args, **kwargs)
        started_threads.append(t)
        return t

    monkeypatch.setattr(bottube_server.threading, "Thread", _tracking_thread)
    bottube_server.fire_webhooks(
        _agent_id(app, registered_agent["agent_name"]),
        "video.uploaded",
        {"video_id": "abc123"},
    )

    for thread in started_threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    with app.app_context():
        db = bottube_server.get_db()
        priv_row = db.execute(
            "SELECT fail_count, last_triggered FROM webhooks WHERE id = ?",
            (private_id,),
        ).fetchone()
        redir_row = db.execute(
            "SELECT fail_count, last_triggered FROM webhooks WHERE id = ?",
            (redir_id,),
        ).fetchone()
        ok_row = db.execute(
            "SELECT fail_count, last_triggered FROM webhooks WHERE id = ?",
            (public_id,),
        ).fetchone()

    assert priv_row["fail_count"] == 1
    assert priv_row["last_triggered"] == 0
    assert redir_row["fail_count"] == 1
    assert redir_row["last_triggered"] == 0
    assert ok_row["fail_count"] == 0
    assert ok_row["last_triggered"] > 0
    # Private IP never connected; redirect attempted once (not followed/retried)
    assert attempts_by_host == [
        ("redir.example.com", "93.184.216.34"),
        ("ok.example.com", "93.184.216.34"),
    ]
