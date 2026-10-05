"""Run the BoTTube MCP server: python -m bottube_mcp [--host 127.0.0.1] [--port 8098]."""

from __future__ import annotations

import argparse
import os

import uvicorn

from .app import create_app


def main() -> None:
    ap = argparse.ArgumentParser(prog="bottube_mcp", description=__doc__)
    ap.add_argument("--host", default=os.environ.get("BOTTUBE_MCP_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("BOTTUBE_MCP_PORT", "8098")))
    ap.add_argument("--log-level", default=os.environ.get("BOTTUBE_MCP_LOG_LEVEL", "info"))
    args = ap.parse_args()
    uvicorn.run(
        create_app(),
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        proxy_headers=False,      # app.py reads X-Real-IP / X-Forwarded-For itself, from loopback only
        server_header=False,
        timeout_keep_alive=15,
        limit_concurrency=200,
    )


if __name__ == "__main__":
    main()
