#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Shared Flask query-parameter validation helpers.

Provides a stable public API for parsing and validating common query-parameter
shapes across all BoTTube API endpoints.  Every validator returns HTTP 400 with
a descriptive JSON body naming the bad parameter on malformed input, fixing the
silent coercion bugs described in Scottcjn/bottube#1586.

The helpers deliberately distinguish an omitted parameter from an invalid one.
Flask's ``request.args.get(..., type=...)`` returns the default when conversion
fails, which otherwise makes malformed client input indistinguishable from a
request that did not supply the parameter at all.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Tuple

from flask import jsonify, request

# ── helpers ────────────────────────────────────────────────────────────────

# Largest Unix timestamp representable by Python's ``datetime`` (end of year
# 9999).  It is intentionally generous while still rejecting giant integers
# that are not meaningful timestamps.
MAX_QUERY_TIMESTAMP = 253_402_300_799


def _query_error(name: str, detail: str) -> Tuple:
    """Build the common JSON HTTP-400 response for a bad query parameter."""
    return jsonify({"error": f"{name} {detail}", "param": name}), 400


def _raw_query_value(name: str) -> Optional[str]:
    """Return a supplied non-empty query value, otherwise ``None``."""
    raw_value = request.args.get(name)
    if raw_value is None or raw_value == "":
        return None
    return raw_value


# ── scalar parsers ─────────────────────────────────────────────────────────

def parse_positive_int(
    name: str,
    default: Any = None,
    min_value: Optional[int] = 1,
    max_value: Optional[int] = None,
    *,
    clamp_bounds: bool = False,
) -> Tuple[Optional[int], Optional[Tuple]]:
    """Parse a positive integer query parameter (``value >= 1``).

    Returns ``(value, None)`` on success or ``(None, (response, 400))`` on
    failure.  Missing and empty values preserve the caller-provided default.
    """
    return _parse_int_param(
        name, default,
        min_value=min_value if min_value is not None else 1,
        max_value=max_value,
        clamp_bounds=clamp_bounds,
    )


def parse_non_negative_int(
    name: str,
    default: Any = None,
    min_value: Optional[int] = 0,
    max_value: Optional[int] = None,
    *,
    clamp_bounds: bool = False,
) -> Tuple[Optional[int], Optional[Tuple]]:
    """Parse a non-negative integer (``value >= 0``).

    Returns ``(value, None)`` on success or ``(None, (response, 400))`` on
    failure.
    """
    return _parse_int_param(
        name, default,
        min_value=min_value if min_value is not None else 0,
        max_value=max_value,
        clamp_bounds=clamp_bounds,
    )


def parse_enum(
    name: str,
    default: Any,
    allowed: Iterable[str],
    *,
    case_sensitive: bool = True,
) -> Tuple[Any, Optional[Tuple]]:
    """Parse a finite-choice string parameter.

    Returns ``(value, None)`` on success, or ``(None, (response, 400))`` if
    the supplied value is not in the *allowed* set.
    """
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


def parse_timestamp(
    name: str,
    default: Any = None,
    min_value: Optional[float] = 0,
    max_value: Optional[float] = MAX_QUERY_TIMESTAMP,
) -> Tuple[Optional[float], Optional[Tuple]]:
    """Parse a Unix epoch timestamp.

    Accepts integer or float Unix timestamps.  ISO-8601 values are not
    accepted by this parser — use :func:`parse_timestamp_iso` instead.

    Returns ``(value, None)`` on success or ``(None, (response, 400))`` on
    failure.
    """
    return _parse_ts_param(
        name, default,
        min_value=min_value,
        max_value=max_value,
        accept_iso=False,
    )


def parse_timestamp_iso(
    name: str,
    default: Any = None,
    min_value: Optional[float] = 0,
    max_value: Optional[float] = MAX_QUERY_TIMESTAMP,
) -> Tuple[Optional[float], Optional[Tuple]]:
    """Parse a Unix epoch or ISO-8601 datetime.

    Integer Unix timestamps are returned as integers.  ISO-8601 values are
    converted to Unix seconds; a timezone-less value is interpreted as UTC.

    Returns ``(value, None)`` on success or ``(None, (response, 400))`` on
    failure.
    """
    return _parse_ts_param(
        name, default,
        min_value=min_value,
        max_value=max_value,
        accept_iso=True,
    )


# ── compound parsers ───────────────────────────────────────────────────────

def parse_offset_and_limit(
    name_offset: str = "offset",
    name_limit: str = "limit",
    default_offset: int = 0,
    default_limit: int = 20,
    max_offset: Optional[int] = None,
    max_limit: Optional[int] = 50,
) -> Tuple[Tuple[Optional[int], Optional[int]], Optional[Tuple]]:
    """Parse an ``(offset, limit)`` pair in a single call.

    Returns ``((offset, limit), None)`` on success or
    ``((None, None), (response, 400))`` on failure.
    """
    offset, err = _parse_int_param(
        name_offset, default_offset,
        min_value=0, max_value=max_offset,
    )
    if err:
        return (None, None), err
    limit, err = _parse_int_param(
        name_limit, default_limit,
        min_value=1, max_value=max_limit,
    )
    if err:
        return (None, None), err
    return (offset, limit), None


def parse_standard_pagination(
    name_page: str = "page",
    name_per_page: str = "per_page",
    default_page: int = 1,
    default_per_page: int = 20,
    max_page: Optional[int] = 10000,
    max_per_page: Optional[int] = 50,
) -> Tuple[Tuple[Optional[int], Optional[int]], Optional[Tuple]]:
    """Parse a ``(page, per_page)`` pair in a single call.

    Returns ``((page, per_page), None)`` on success or
    ``((None, None), (response, 400))`` on failure.
    """
    page, err = _parse_int_param(
        name_page, default_page,
        min_value=1, max_value=max_page,
    )
    if err:
        return (None, None), err
    per_page, err = _parse_int_param(
        name_per_page, default_per_page,
        min_value=1, max_value=max_per_page,
    )
    if err:
        return (None, None), err
    return (page, per_page), None


# ── internal shared implementation ─────────────────────────────────────────

def _parse_int_param(
    name: str,
    default: Any = None,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
    *,
    clamp_bounds: bool = False,
) -> Tuple[Optional[int], Optional[Tuple]]:
    """Parse an integer query parameter or return a descriptive JSON 400.

    Internal implementation shared by :func:`parse_positive_int` and
    :func:`parse_non_negative_int`.
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


def _parse_ts_param(
    name: str,
    default: Any = None,
    min_value: Optional[float] = 0,
    max_value: Optional[float] = MAX_QUERY_TIMESTAMP,
    *,
    accept_iso: bool = True,
) -> Tuple[Optional[float], Optional[Tuple]]:
    """Parse a Unix or ISO-8601 timestamp, or return a JSON HTTP 400.

    Internal implementation shared by :func:`parse_timestamp` and
    :func:`parse_timestamp_iso`.
    """
    raw_value = _raw_query_value(name)
    if raw_value is None:
        return default, None

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        if not accept_iso:
            return None, _query_error(name, "must be a Unix timestamp")
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