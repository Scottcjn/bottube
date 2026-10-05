"""Fixtures: run the real ASGI app under uvicorn on a free loopback port, in a thread."""

from __future__ import annotations

import socket
import threading
import time

import pytest

pytest.importorskip("mcp", reason="bottube_mcp needs its pinned requirements (bottube_mcp/requirements.txt)")

import uvicorn  # noqa: E402

from bottube_mcp.app import Settings, create_app  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class RunningServer:
    def __init__(self, settings: Settings):
        self.port = _free_port()
        self.url = "http://127.0.0.1:%d" % self.port
        cfg = uvicorn.Config(create_app(settings), host="127.0.0.1", port=self.port,
                             log_level="warning", lifespan="on")
        self.server = uvicorn.Server(cfg)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> "RunningServer":
        self.thread.start()
        deadline = time.time() + 15
        while not self.server.started:
            if time.time() > deadline:
                raise RuntimeError("uvicorn did not start")
            time.sleep(0.05)
        return self

    def __exit__(self, *exc) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def run_server():
    servers = []

    def _start(settings: Settings) -> RunningServer:
        srv = RunningServer(settings).__enter__()
        servers.append(srv)
        return srv

    yield _start
    for srv in servers:
        srv.__exit__(None, None, None)
