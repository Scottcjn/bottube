# Provider Router Hardening

This document describes reliability and observability updates for `providers/router.py`.

## Scope

- Retry and backoff for transient/throttled failures.
- Structured error categorization.
- Per-provider attempt timing and aggregate metadata.
- Repeated-failure warning signal for operator visibility.

## Error Categories

`classify_error()` maps provider failures to:

- `auth`: unauthorized/forbidden/API key issues.
- `throttled`: rate limit or quota errors.
- `transient`: timeout/network/5xx temporary failures.
- `permanent`: invalid request/unsupported/4xx non-retryable.
- `unknown`: fallback category.

## Retry Strategy

`generate_video(..., max_retries, retry_backoff_s)` behavior:

- Retries only for `transient` and `throttled` categories.
- Backoff is exponential per retry index:
  - `retry_backoff_s * (2 ** retry_index)` (capped to 10s).
- No retries for `auth` or `permanent` errors.

## Runtime Metadata

Returned `GeneratedVideo.metadata` now includes:

- `router_primary`
- `router_provider`
- `router_fallback_used`
- `router_attempts` (attempt-level timeline with status/category/duration)
- `router_provider_time_ms` (accumulated provider timing)
- `router_error_categories` (category counters)

## Alerting / Observability

- Router tracks consecutive failures per provider.
- When a provider reaches 3 consecutive failed runs, a warning is logged:
  - `Provider '<name>' has failed <N> consecutive router runs`

## CLI Compatibility

`tools/grok_video.py` remains compatible and adds optional knobs:

- `--router-max-retries`
- `--router-retry-backoff`

Defaults preserve current behavior while adding better resilience.
