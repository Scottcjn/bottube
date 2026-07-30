# SPDX-License-Identifier: MIT
"""
Shared query-parameter validator helpers for BoTTube API endpoints.

All validators return (parsed_value, None) on success or (None, (response, 400))
on failure, so callers can write::

    page, err = parse_positive_int("page", 1, max_value=100)
    if err:
        return err

This eliminates the per-endpoint hand-rolled parsing that caused four
regression issues (#1456, #1436, #1435, #1468).
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple, Union

from flask import jsonify, request

# Re-export common types for convenience.  A validator returns either:
#   (value, None)                                          — success
#   (None, (jsonify({"error": msg}), status_code))         — failure
ValidatorResult = Tuple[Optional[object], Optional[Tuple]]


# ---------------------------------------------------------------------------
# Integer helpers
# ---------------------------------------------------------------------------

def parse_positive_int(
    name: str,
    default: int,
    *,
    min_value: int = 1,
    max_value: Optional[int] = None,
) -> ValidatorResult:
    """Parse a positive integer query parameter.

    Returns ``default`` when the param is absent or empty.
    Rejects non-integer strings, floats, out-of-range values with HTTP 400.
    """
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default, None

    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _err(name, f"'{name}' must be an integer")

    if value != int(float(raw)):
        # Catches things like "1.5", "NaN", "Infinity"
        return _err(name, f"'{name}' must be an integer")

    if value < min_value:
        return _err(name, f"'{name}' must be >= {min_value}")
    if max_value is not None and value > max_value:
        return _err(name, f"'{name}' must be <= {max_value}")

    return value, None


def parse_non_negative_int(
    name: str,
    default: Optional[int],
    *,
    max_value: Optional[int] = None,
) -> ValidatorResult:
    """Parse a non-negative integer (>= 0) query parameter.

    Returns ``default`` when absent.  Useful for ``min_views`` style params
    where 0 is a meaningful value meaning "no minimum".
    """
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default, None

    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _err(name, f"'{name}' must be an integer")

    if value != int(float(raw)):
        return _err(name, f"'{name}' must be an integer")

    if value < 0:
        return _err(name, f"'{name}' must be >= 0")
    if max_value is not None and value > max_value:
        return _err(name, f"'{name}' must be <= {max_value}")

    return value, None


# ---------------------------------------------------------------------------
# Enum / string helpers
# ---------------------------------------------------------------------------

def parse_enum(
    name: str,
    default: str,
    valid_values: set,
    *,
    case_sensitive: bool = False,
) -> ValidatorResult:
    """Parse an enum-like query parameter.

    Rejects values not in ``valid_values`` with HTTP 400.
    When ``case_sensitive=False`` (default), matching is case-insensitive
    and the canonical (first-matching) valid value is returned so the
    rest of the handler sees a consistent case.
    """
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default, None

    if case_sensitive:
        if raw not in valid_values:
            return _err(
                name,
                f"'{name}' must be one of: {', '.join(sorted(valid_values))}",
            )
        return raw, None

    # Case-insensitive: find the canonical form
    raw_lower = raw.lower()
    for v in valid_values:
        if v.lower() == raw_lower:
            return v, None

    return _err(
        name,
        f"'{name}' must be one of: {', '.join(sorted(valid_values))}",
    )


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def parse_timestamp(
    name: str,
    default: Optional[float] = None,
) -> ValidatorResult:
    """Parse a Unix-epoch timestamp query parameter.

    Accepts numeric strings (int or float).  Rejects non-numeric strings,
    NaN, Infinity.  Returns ``default`` when absent.
    """
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default, None

    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _err(name, f"'{name}' must be a numeric timestamp")

    if not math.isfinite(value):
        return _err(name, f"'{name}' must be a finite number")

    return value, None


def parse_timestamp_iso(
    name: str,
    default: Optional[str] = None,
) -> ValidatorResult:
    """Parse an ISO-8601 timestamp query parameter.

    Accepts formats like ``2024-01-15T12:00:00Z`` or ``2024-01-15``.
    Returns ``default`` when absent.  On success returns the ISO-8601
    string in a normalized form.
    """
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default, None

    try:
        # Try full ISO-8601 first
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.isoformat(), None
    except (ValueError, TypeError):
        pass

    return _err(name, f"'{name}' must be a valid ISO-8601 date/timestamp")


# ---------------------------------------------------------------------------
# Combined / compound helpers
# ---------------------------------------------------------------------------

def parse_offset_and_limit(
    offset_default: int = 0,
    limit_default: int = 20,
    max_limit: int = 100,
) -> Tuple[ValidatorResult, ValidatorResult]:
    """Convenience: parse both ``offset`` and ``limit`` in one call."""
    offset, err = parse_non_negative_int("offset", offset_default)
    if err:
        return (offset, err), (None, None)
    limit, err = parse_positive_int("limit", limit_default, max_value=max_limit)
    return (offset, None), (limit, err)


def parse_standard_pagination(
    page_default: int = 1,
    per_page_default: int = 20,
    max_per_page: int = 50,
) -> Tuple[ValidatorResult, ValidatorResult]:
    """Convenience: parse both ``page`` and ``per_page`` in one call."""
    page, err = parse_positive_int("page", page_default, max_value=10000)
    if err:
        return (page, err), (None, None)
    per_page, err = parse_positive_int(
        "per_page", per_page_default, max_value=max_per_page
    )
    return (page, None), (per_page, err)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _err(name: str, message: str) -> ValidatorResult:
    return None, (jsonify({"error": message}), 400)
