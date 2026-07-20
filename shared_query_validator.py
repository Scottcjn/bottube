# SPDX-License-Identifier: MIT
"""Shared query parameter validator for BoTTube API endpoints.

Centralizes validation logic used across /api/feed, /api/trending, /api/videos,
and /api/videos/<id>/related to reject malformed parameters with HTTP 400
instead of silently coercing invalid input.

Usage:
    from shared_query_validator import parse_int_param, parse_enum_param

    limit, err = parse_int_param("limit", default=20, min_value=1, max_value=50)
    if err:
        return err  # (jsonify response, 400)
"""
from flask import jsonify, request


def parse_int_param(name, default=1, min_value=None, max_value=None):
    """Parse an integer query parameter with bounds checking.

    Args:
        name: Parameter name in the query string.
        default: Default value when parameter is missing or empty.
        min_value: Minimum allowed value (inclusive). None = no minimum.
        max_value: Maximum allowed value (inclusive). None = no maximum.

    Returns:
        Tuple of (value, error). If error is not None, it's a Flask response tuple
        (jsonify({"error": "..."}), 400).
    """
    raw_value = request.args.get(name)
    if raw_value is None or raw_value == "":
        return default, None

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None, (
            jsonify({"error": f"{name} must be an integer"}),
            400,
        )

    if min_value is not None and value < min_value:
        return None, (
            jsonify({"error": f"{name} must be >= {min_value}"}),
            400,
        )

    if max_value is not None and value > max_value:
        return None, (
            jsonify({"error": f"{name} must be <= {max_value}"}),
            400,
        )

    return value, None


def parse_enum_param(name, allowed_values, default=None):
    """Parse an enum-style query parameter.

    Args:
        name: Parameter name in the query string.
        allowed_values: Set/list of valid string values.
        default: Default value when parameter is missing or empty.

    Returns:
        Tuple of (value, error). If error is not None, it's a Flask response tuple.
    """
    raw_value = request.args.get(name)
    if raw_value is None or raw_value == "":
        return default, None

    value = raw_value.strip().lower()
    if value not in allowed_values:
        allowed_text = ", ".join(sorted(allowed_values))
        return None, (
            jsonify({"error": f"{name} must be one of: {allowed_text}"}),
            400,
        )

    return value, None


def parse_ts_param(name, default=0, min_value=None):
    """Parse a timestamp query parameter.

    Args:
        name: Parameter name in the query string.
        default: Default value when parameter is missing or empty.
        min_value: Minimum allowed value (inclusive). None = no minimum.

    Returns:
        Tuple of (value, error). Value is a float timestamp.
    """
    import math

    raw_value = request.args.get(name)
    if raw_value is None or raw_value == "":
        return default, None

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None, (
            jsonify({"error": f"{name} must be a number"}),
            400,
        )

    if not math.isfinite(value):
        return None, (
            jsonify({"error": f"{name} must be a finite number"}),
            400,
        )

    if min_value is not None and value < min_value:
        return None, (
            jsonify({"error": f"{name} must be >= {min_value}"}),
            400,
        )

    return value, None
