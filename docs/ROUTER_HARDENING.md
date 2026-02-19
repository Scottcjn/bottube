# Provider Router Hardening Guide

 hardened provider router with retry, backoff, and observability.

## Features

### 1. Retry with Exponential Backoff

Automatic retry for transient failures:
- **Max retries**: 3 attempts
- **Base delay**: 1 second
- **Max delay**: 10 seconds
- **Backoff**: Exponential (1s, 2s, 4s...)

```python
# Transient errors (network, timeout) will retry
# Permanent errors (invalid input) will not retry
```

### 2. Structured Error Categories

| Category | Description | Retry? |
|----------|-------------|--------|
| `auth` | API key, permission errors | No |
| `throttled` | Rate limiting, quota exceeded | Yes |
| `transient` | Network issues, timeouts | Yes |
| `permanent` | Invalid input, bad params | No |
| `unknown` | Uncategorized | No |

### 3. Metrics & Observability

Each generation attempt logs:
- Provider name
- Duration (ms)
- Success/failure status
- Error category (if failed)
- Retry count

Example log output:
```json
{
  "provider": "grok",
  "duration_ms": 2450.5,
  "success": true,
  "retry_count": 0
}
```

### 4. Fallback Behavior

When primary provider fails:
1. Retry primary up to 3 times (for transient errors)
2. Switch to fallback provider
3. Retry fallback up to 3 times
4. Fail with detailed error report

## Usage

### Basic Usage (unchanged)

```python
from providers.router_hardened import generate_video

# Auto-select provider
result = generate_video("A cat playing piano")

# Explicit provider
result = generate_video("A cat playing piano", prefer="runway")

# No fallback
result = generate_video("A cat playing piano", fallback=False)
```

### With Metrics Logging

```python
import logging

# Enable logging
logging.basicConfig(level=logging.INFO)

result = generate_video("A cat playing piano", log_metrics=True)
# Logs: Generation timing, provider used, fallback status
```

### Error Handling

```python
from providers.router_hardened import ProviderError, ErrorCategory

try:
    result = generate_video("test")
except RuntimeError as e:
    # All providers failed
    print(f"Generation failed: {e}")
except ProviderError as e:
    # Specific provider error
    print(f"Provider {e.provider} failed: {e.category.value}")
```

## Environment Variables

```bash
# Grok API
export GROK_API_KEY="your-key"

# Runway API
export RUNWAY_API_KEY="your-key"

# Optional: Enable debug logging
export CLAWRTC_LOG_LEVEL=DEBUG
```

## Troubleshooting

### "All provider attempts failed"

Check error categories in the message:
- `[auth]`: Check API keys
- `[throttled]`: Wait and retry (rate limited)
- `[transient]`: Network issue, auto-retried
- `[permanent]`: Invalid prompt/parameters

### Slow generation

Check metrics for timing:
```python
# Duration > 10s may indicate issues
# Check retry_count in logs
```

### Fallback always used

Primary provider may be unstable:
```python
# Force specific provider
result = generate_video("prompt", prefer="runway", fallback=False)
```

## Testing

Run tests:
```bash
pytest tests/test_router_hardened.py -v
```

Test coverage:
- Error categorization (5 cases)
- Retry logic (4 cases)
- Provider selection (4 cases)
- Integration tests (2 cases)

## Migration from Old Router

The hardened router is **drop-in replacement**:

```python
# Old
from providers.router import generate_video

# New
from providers.router_hardened import generate_video

# Same API, enhanced behavior
```

## Performance

- **Overhead**: ~1-2ms per call (metrics)
- **Retry delay**: 1-10s (only on failure)
- **Memory**: Minimal (stateless)

## CLI Compatibility

`tools/grok_video.py` remains compatible:
```bash
python tools/grok_video.py "prompt" --duration 8
```

The hardened router is used internally with all enhancements.
