# Generation provider reliability

This document describes the production-hardening path for the BoTTube generation provider router/worker.

## Retry and fallback behavior

Provider operations are normalized through `generation.reliability.run_with_retries()`:

- `auth` errors (`401`, `403`, invalid API key) fail fast and move to the next provider.
- `permanent` errors fail fast and move to the next provider.
- `transient` errors (timeouts, temporary network failures, `502`/`503`/`504`) retry with bounded exponential backoff.
- `throttled` errors (`429`, quota/rate-limit responses) retry with bounded exponential backoff.

Default retry policy:

```text
attempts=3
base_delay_s=0.5
max_delay_s=4.0
jitter_s=0.2
```

The fallback chain remains deterministic: the worker retries only the current provider for retryable categories; if it still fails, it records the category and advances to the next provider selected by `GenerationRouter`.

## Observability

Each provider attempt records:

- provider name
- success/failure
- error category (`ok`, `auth`, `throttled`, `transient`, `permanent`)
- latency in seconds
- timestamp
- human-readable detail

The in-memory job entry also exposes a `provider_metrics` snapshot with per-provider counters:

```json
{
  "grok": {
    "attempts": 12,
    "successes": 10,
    "failures": 2,
    "avg_latency_s": 1.812,
    "total_latency_s": 21.744,
    "error_categories": {"throttled": 1, "transient": 1}
  }
}
```

The worker logs structured `provider_attempt` lines suitable for ingestion by journald, Docker logs, or a hosted log pipeline.

## Environment examples

Typical provider secrets should be supplied by environment variables or a secrets manager, never committed:

```bash
export GROK_API_KEY="..."
export RUNWAY_API_KEY="..."
export BOTTUBE_BASE_DIR=/srv/bottube
python bottube_server.py
```

If a provider key is absent or invalid, the router/worker should classify it as `auth` and fall back without retry storms.

## Troubleshooting

1. Check the job's `attempts` list for provider-level categories and details.
2. Check `provider_metrics` for repeated `throttled` or `transient` failures.
3. Confirm that API keys are present in the runtime environment.
4. If a provider is permanently failing validation, verify `GenerationRequest` mode, duration, style and capability matching.
5. If all providers fail, confirm the local `ffmpeg_titlecard` fallback is registered and available.

## Testing

Run the targeted reliability tests:

```bash
python -m pytest tests/test_generation_reliability.py -q
```

Run the broader generation/worker test suite when available:

```bash
python -m pytest tests -q
```
