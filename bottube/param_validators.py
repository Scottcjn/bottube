"""Shared query-parameter validators for BoTTube API endpoints.

Provides reusable validation functions that return HTTP 400 with a JSON
error body naming the bad parameter — never silent coercion.
"""

import math
from flask import jsonify, request


def parse_int_param(name, default, min_value=None, max_value=None, *, clamp=False):
    """Return (int_value, None) or (None, (json_response, 400)).

    Args:
        name: Query-parameter name.
        default: Fallback when param is absent.
        min_value: Minimum inclusive (rejected with 400 unless *clamp*).
        max_value: Maximum inclusive (rejected with 400 unless *clamp*).
        clamp: If True, out-of-range values are silently clamped instead
               of returning a 400 error. Use only for soft limits.

    Returns:
        Tuple of (int, None) on success or (None, (response, 400)) on error.
    """
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default, None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, (jsonify({"error": f"'{name}' must be an integer"}), 400)
    if clamp:
        if min_value is not None and value < min_value:
            value = min_value
        if max_value is not None and value > max_value:
            value = max_value
        return value, None
    if min_value is not None and value < min_value:
        return None, (jsonify({"error": f"'{name}' must be >= {min_value}"}), 400)
    if max_value is not None and value > max_value:
        return None, (jsonify({"error": f"'{name}' must be <= {max_value}"}), 400)
    return value, None


def parse_enum_param(name, allowed, default=None, case_sensitive=False):
    """Return (str_value, None) or (None, (json_response, 400)).

    Args:
        name: Query-parameter name.
        allowed: Iterable of acceptable string values.
        default: Fallback when param is absent.
        case_sensitive: If False, match case-insensitively.

    Returns:
        Tuple of (str, None) on success or (None, (response, 400)) on error.
    """
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default, None
    if not case_sensitive:
        raw_lower = raw.lower().strip()
        for candidate in allowed:
            if candidate.lower() == raw_lower:
                return candidate, None
        return None, (
            jsonify({"error": f"'{name}' must be one of {sorted(set(allowed))}"}),
            400,
        )
    if raw in allowed:
        return raw, None
    return None, (
        jsonify({"error": f"'{name}' must be one of {sorted(set(allowed))}"}),
        400,
    )


def parse_ts_param(name, default=None):
    """Return (float_timestamp, None) or (None, (json_response, 400)).

    Accepts Unix epoch timestamps (int or float). Rejects non-numeric values.

    Args:
        name: Query-parameter name.
        default: Fallback when param is absent.

    Returns:
        Tuple of (float, None) on success or (None, (response, 400)) on error.
    """
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default, None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, (jsonify({"error": f"'{name}' must be a numeric timestamp"}), 400)
    if not math.isfinite(value):
        return None, (jsonify({"error": f"'{name}' must be a finite number"}), 400)
    if value < 0:
        return None, (jsonify({"error": f"'{name}' must be a non-negative timestamp"}), 400)
    return value, None
