"""Regression test for #2304: /api/feed?bucket=hybrid-v1 stalling ~15s.

`_feed_hybrid_v1` used to reload the (large) embedding matrices from disk
synchronously, on the request thread, whenever the in-memory cache was
older than 600s. Every request unlucky enough to land right after the
cache expired paid the full disk-read cost inline. This asserts the fix
stays in place: stale caches are refreshed on a background thread while
the request is served with the stale-but-fast data, and only a genuinely
empty cache (cold start) is allowed to block.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "bottube_server.py"


def _module_ast() -> ast.Module:
    return ast.parse(SERVER.read_text(encoding="utf-8"))


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found in bottube_server.py")


def _source(tree: ast.Module, node: ast.AST) -> str:
    return ast.get_source_segment(SERVER.read_text(encoding="utf-8"), node) or ""


def test_async_warm_helpers_exist():
    tree = _module_ast()
    # Will raise if missing.
    _find_function(tree, "_ue_cache_warm_async")
    _find_function(tree, "_uv_cache_warm_async")


def test_feed_hybrid_v1_does_not_block_on_stale_cache():
    tree = _module_ast()
    fn = _find_function(tree, "_feed_hybrid_v1")
    src = _source(tree, fn)

    assert "_ue_cache_warm_async" in src, (
        "_feed_hybrid_v1 must refresh the stale text-embedding cache in the "
        "background (async), not block the request on _ue_cache_warm()"
    )
    assert "_uv_cache_warm_async" in src, (
        "_feed_hybrid_v1 must refresh the stale visual-embedding cache in the "
        "background (async), not block the request on _uv_cache_warm()"
    )

    # The blocking warm calls must remain only for the cold-start branch
    # (matrix is None), never as the sole reaction to staleness.
    assert src.count("_ue_cache_warm()") == 1, (
        "expected exactly one blocking _ue_cache_warm() call, reserved for "
        "the cold-start (empty cache) branch"
    )
    assert src.count("_uv_cache_warm()") == 1, (
        "expected exactly one blocking _uv_cache_warm() call, reserved for "
        "the cold-start (empty cache) branch"
    )


def test_async_warm_helpers_guard_against_concurrent_threads():
    tree = _module_ast()
    for name, flag in (
        ("_ue_cache_warm_async", "_EMB_CACHE_WARMING"),
        ("_uv_cache_warm_async", "_UV_CACHE_WARMING"),
    ):
        fn = _find_function(tree, name)
        src = _source(tree, fn)
        assert flag in src, f"{name} must guard re-entry with {flag}"
        assert "threading.Thread" in src, f"{name} must spawn a background thread"
        assert "daemon=True" in src, f"{name} thread must be daemon so it can't block shutdown"
