#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Shared Flask query-parameter validation helpers.

The helpers in this module deliberately distinguish an omitted parameter from
an invalid one.  Flask's ``request.args.get(..., type=...)`` returns the
default when conversion fails, which otherwise makes malformed client input
indistinguishable from a request that did not supply the parameter at all.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from flask import jsonify, request


# Largest Unix timestamp representable by Python's ``datetime`` (end of year
# 9999).  It is intentionally generous while still rejecting giant integers
# that are not meaningful timestamps.
MAX_QUERY_TIMESTAMP = 253_402_300_799


def _query_error(name: str, detail: str):
    """Build the common JSON HTTP-400 response for a bad query parameter."""
    return jsonify({"error": f"{name} {detail}", "param": name}), 400


def _raw_query_value(name: str) -> Optional[str]:
    """Return a supplied non-empty query value, otherwise ``None``."""
    raw_value = request.args.get(name)
    if raw_value is None or raw_value == "":
        return None
    return raw_value


def parse_int_param(
    name: str,
    default: Any = None,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
    *,
    clamp_bounds: bool = False,
):
    """Parse an integer query parameter or return a descriptive JSON 400.

    The return shape is ``(value, error)``.  ``error`` is ``None`` on success
    or a Flask ``(response, 400)`` tuple on failure.  Missing and empty values
    preserve the caller-provided default.
    """
    raw_value = _raw_query_value(name)
    if raw_value is None:
        return default, None
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None, _query_error(name, "must be an integer")

    if clamp_bounds:
        if min_value is not None and value < min_value:
            value = min_value
        if max_value is not None and value > max_value:
            value = max_value
        return value, None

    if min_value is not None and value < min_value:
        return None, _query_error(name, f"must be >= {min_value}")
    if max_value is not None and value > max_value:
        return None, _query_error(name, f"must be <= {max_value}")
    return value, None


def parse_enum_param(
    name: str,
    default: Any,
    allowed: Iterable[str],
    *,
    case_sensitive: bool = True,
):
    """Parse a finite-choice string parameter or return a JSON HTTP 400."""
    raw_value = _raw_query_value(name)
    if raw_value is None:
        return default, None

    value = raw_value.strip()
    choices = tuple(allowed)
    if not case_sensitive:
        value = value.lower()
        choices_by_normalized_value = {choice.lower(): choice for choice in choices}
        if value in choices_by_normalized_value:
            return choices_by_normalized_value[value], None
    elif value in choices:
        return value, None

    allowed_text = ", ".join(sorted(choices))
    return None, _query_error(name, f"must be one of: {allowed_text}")


def parse_ts_param(
    name: str,
    default: Any = None,
    min_value: Optional[float] = 0,
    max_value: Optional[float] = MAX_QUERY_TIMESTAMP,
):
    """Parse a Unix or ISO-8601 timestamp, or return a JSON HTTP 400.

    Integer Unix timestamps are returned as integers.  ISO-8601 values are
    converted to Unix seconds; a timezone-less value is interpreted as UTC.
    """
    raw_value = _raw_query_value(name)
    if raw_value is None:
        return default, None

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            value = parsed.timestamp()
        except (OverflowError, OSError, TypeError, ValueError):
            return None, _query_error(
                name,
                "must be a Unix timestamp or ISO-8601 datetime",
            )

    if min_value is not None and value < min_value:
        return None, _query_error(name, f"must be >= {min_value:g}")
    if max_value is not None and value > max_value:
        return None, _query_error(name, f"must be <= {max_value:g}")
    return value, None
