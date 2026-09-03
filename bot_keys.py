#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Out-of-repo loader for BoTTube bot API keys.

The bot keys used to be hard-coded in this repo. They were rotated on
2026-09-03 and now live in a mode-0600 env file that is never committed:

    BOT_KEY_SOPHIA_ELYA=bottube_sk_...
    BOT_KEY_LAUGHTRACK_LARRY=bottube_sk_...

Variable name = ``BOT_KEY_`` + agent name upper-cased with every
non-alphanumeric character replaced by ``_`` (``sophia-elya`` ->
``BOT_KEY_SOPHIA_ELYA``).

File resolution order:
  1. ``$BOTTUBE_BOT_KEYS_FILE`` if set
  2. ``/root/bottube/.bot_keys.env``             (bottube.ai host)
  3. ``~/.elyan-secrets/bottube-bot-keys.env``   (Victus / dev boxes)

A variable already present in the process environment (e.g. injected by a
systemd ``Environment=`` line) wins over the file.

Usage::

    from bot_keys import bot_key
    headers = {"X-API-Key": bot_key("sophia-elya")}

``bot_key()`` raises ``BotKeyMissing`` (a ``KeyError``) naming the variable
and the file when a key is absent. See ``bottube-bot-keys.env.example`` for
the full variable list and ``bot_keys.sh`` for the shell equivalent.
Running this module directly lists the variable NAMES found (never values).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Optional

ENV_VAR = "BOTTUBE_BOT_KEYS_FILE"
DEFAULT_PATHS = (
    "/root/bottube/.bot_keys.env",
    "~/.elyan-secrets/bottube-bot-keys.env",
)
PREFIX = "BOT_KEY_"

_MISSING = object()
_cache: Optional[Dict[str, str]] = None
_cache_path: Optional[Path] = None


class BotKeyMissing(KeyError):
    """Raised when an agent's key is not configured. str() is the plain message."""

    def __str__(self) -> str:  # KeyError repr()s its arg by default
        return self.args[0] if self.args else ""


def var_name(agent_name: str) -> str:
    """'sophia-elya' -> 'BOT_KEY_SOPHIA_ELYA'."""
    return PREFIX + re.sub(r"[^A-Za-z0-9]", "_", agent_name).upper()


def keys_file() -> Path:
    """Path of the key file that will be (or would be) read."""
    explicit = os.environ.get(ENV_VAR)
    if explicit:
        return Path(explicit).expanduser()
    for candidate in DEFAULT_PATHS:
        path = Path(candidate).expanduser()
        if path.is_file():
            return path
    return Path(DEFAULT_PATHS[0])


def _parse(path: Path) -> Dict[str, str]:
    keys: Dict[str, str] = {}
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            if "=" not in line:
                raise ValueError(f"{path}:{lineno}: expected NAME=value")
            name, _, value = line.partition("=")
            name, value = name.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            keys[name] = value
    return keys


def load(refresh: bool = False) -> Dict[str, str]:
    """Return {VAR: key} from the key file (cached until the path changes)."""
    global _cache, _cache_path
    path = keys_file()
    if refresh or _cache is None or path != _cache_path:
        if not path.is_file():
            raise FileNotFoundError(
                f"BoTTube bot key file not found: {path} "
                f"(set {ENV_VAR} or create it; see bottube-bot-keys.env.example)"
            )
        _cache, _cache_path = _parse(path), path
    return _cache


def bot_key(agent_name: str, default=_MISSING) -> str:
    """Return the BoTTube API key for ``agent_name``.

    Raises BotKeyMissing (KeyError) unless ``default`` is given.
    """
    var = var_name(agent_name)
    value = os.environ.get(var, "").strip()
    path = keys_file()
    if not value:
        try:
            value = load().get(var, "").strip()
        except FileNotFoundError:
            if default is not _MISSING:
                return default
            raise
    if value:
        return value
    if default is not _MISSING:
        return default
    raise BotKeyMissing(
        f"{var} is not set in {path} (BoTTube API key for agent '{agent_name}'). "
        f"Add a line '{var}=bottube_sk_...' to that file, or point {ENV_VAR} at "
        f"the file that has it."
    )


if __name__ == "__main__":
    import sys

    try:
        names = sorted(load())
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    print(f"# {keys_file()}")
    for name in names:
        print(name)
