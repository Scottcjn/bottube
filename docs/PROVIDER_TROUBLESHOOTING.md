# BoTTube Provider Troubleshooting Guide

## Overview

This guide covers common issues, error categories, and debugging strategies for BoTTube's provider system, including Grok, Runway, and other content generation providers.

## Error Categories

### Authentication Errors
**Category**: `auth`
**Description**: Issues with API keys, tokens, or authentication credentials.

**Common Causes**:
- Invalid or expired API keys
- Incorrect environment variable names
- Missing authentication headers
- Token refresh failures

**Resolution Steps**:
1. Verify API key format and validity
2. Check environment variable spelling
3. Test authentication with provider's API directly
4. Regenerate API keys if necessary

### Rate Limiting / Throttling
**Category**: `throttled`
**Description**: Provider enforced rate limits or quota exceeded.

**Common Causes**:
- Too many requests in short time window
- Daily/monthly quota exceeded
- Concurrent request limits reached
- IP-based rate limiting

**Resolution Steps**:
1. Implement exponential backoff
2. Check provider dashboard for quota usage
3. Reduce request frequency
4. Consider upgrading provider plan

### Transient Errors
**Category**: `transient`
**Description**: Temporary failures that may resolve with retry.

**Common Causes**:
- Network connectivity issues
- Provider service temporary outages
- DNS resolution failures
- Connection timeouts

**Resolution Steps**:
1. Retry with exponential backoff
2. Check network connectivity
3. Verify provider service status
4. Try alternative providers if available

### Permanent Errors
**Category**: `permanent`
**Description**: Errors that won't resolve with retries.

**Common Causes**:
- Invalid request parameters
- Unsupported content types
- Provider service deprecated
- Account suspended

**Resolution Steps**:
1. Review request parameters
2. Check provider documentation for changes
3. Validate content type support
4. Contact provider support if needed

## Environment Variable Configuration

### Grok Provider
```bash
# xAI Grok API configuration
GROK_API_KEY=your_grok_api_key_here
GROK_BASE_URL=https://api.x.ai/v1
GROK_MODEL=grok-beta
GROK_MAX_TOKENS=4096
GROK_TIMEOUT=30
GROK_RETRY_ATTEMPTS=3
GROK_RETRY_DELAY=1
```

### Runway Provider
```bash
# Runway ML API configuration
RUNWAY_API_KEY=your_runway_api_key_here
RUNWAY_BASE_URL=https://api.runwayml.com/v1
RUNWAY_MODEL=gen3a_turbo
RUNWAY_TIMEOUT=300
RUNWAY_RETRY_ATTEMPTS=3
RUNWAY_RETRY_DELAY=2
RUNWAY_WEBHOOK_URL=https://your-domain.com/webhook/runway
```

### Provider Router Configuration
```bash
# Router behavior settings
PROVIDER_FALLBACK_ENABLED=true
PROVIDER_RETRY_ATTEMPTS=3
PROVIDER_RETRY_DELAY=1
PROVIDER_TIMEOUT=60
PROVIDER_LOG_LEVEL=INFO
PROVIDER_METRICS_ENABLED=true
```

## Debugging Steps

### 1. Enable Debug Logging
```bash
export PROVIDER_LOG_LEVEL=DEBUG
python -m bottube.providers.router --debug
```

### 2. Test Individual Providers
```bash
# Test Grok provider
python -c "from bottube.providers.grok import GrokProvider; p = GrokProvider(); print(p.test_connection())"

# Test Runway provider
python -c "from bottube.providers.runway import RunwayProvider; p = RunwayProvider(); print(p.test_connection())"
```

### 3. Check Provider Status
```bash
# View provider health status
python -m bottube.providers.router --status

# Check specific provider metrics
python -m bottube.providers.router --metrics --provider grok
```

### 4. Validate Configuration
```bash
# Verify environment variables
python -m bottube.providers.router --validate-config

# Test provider authentication
python -m bottube.providers.router --test-auth
```

## Common Issues and Solutions

### Issue: "Provider authentication failed"
**Error Category**: `auth`
**Solution**:
1. Verify API key is correctly set in environment
2. Check for extra whitespace or newlines in key
3. Ensure key has required permissions
4. Test key directly with provider's API

### Issue: "Request rate limited"
**Error Category**: `throttled`
**Solution**:
1. Implement request queuing
2. Add delays between requests
3. Check provider rate limit documentation
4. Consider upgrading API plan

### Issue: "Connection timeout"
**Error Category**: `transient`
**Solution**:
1. Increase timeout values
2. Check network connectivity
3. Verify provider service status
4. Enable retry with backoff

### Issue: "Invalid model specified"
**Error Category**: `permanent`
**Solution**:
1. Check provider documentation for available models
2. Update model name in configuration
3. Verify model supports required features
4. Test with default model first

### Issue: "Provider quota exceeded"
**Error Category**: `throttled`
**Solution**:
1. Check provider dashboard for usage
2. Wait for quota reset
3. Implement request batching
4. Consider multiple API keys

## Production Configuration Recommendations

### High Availability Setup
```bash
# Enable multiple providers with fallback
PROVIDER_FALLBACK_ENABLED=true
PROVIDER_FALLBACK_ORDER=grok,runway,openai

# Circuit breaker configuration
PROVIDER_CIRCUIT_BREAKER_ENABLED=true
PROVIDER_CIRCUIT_BREAKER_THRESHOLD=5
PROVIDER_CIRCUIT_BREAKER_TIMEOUT=300
```

### Monitoring and Observability
```bash
# Enable detailed metrics
PROVIDER_METRICS_ENABLED=true
PROVIDER_METRICS_INTERVAL=60

# Structured logging
PROVIDER_LOG_FORMAT=json
PROVIDER_LOG_LEVEL=INFO

# Health check configuration
PROVIDER_HEALTH_CHECK_ENABLED=true
PROVIDER_HEALTH_CHECK_INTERVAL=300
```

### Performance Optimization
```bash
# Connection pooling
PROVIDER_CONNECTION_POOL_SIZE=10
PROVIDER_CONNECTION_TIMEOUT=30

# Request batching
PROVIDER_BATCH_SIZE=5
PROVIDER_BATCH_TIMEOUT=10

# Caching
PROVIDER_CACHE_ENABLED=true
PROVIDER_CACHE_TTL=3600
```

## Retry Strategy Configuration

### Exponential Backoff
```python
# Default retry configuration
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 1  # seconds
RETRY_MAX_DELAY = 60  # seconds
RETRY_MULTIPLIER = 2
RETRY_JITTER = True
```

### Provider-Specific Retries
```bash
# Grok retry settings
GROK_RETRY_ATTEMPTS=3
GROK_RETRY_DELAY=1
GROK_RETRY_MULTIPLIER=2

# Runway retry settings (longer for video generation)
RUNWAY_RETRY_ATTEMPTS=5
RUNWAY_RETRY_DELAY=5
RUNWAY_RETRY_MULTIPLIER=1.5
```

## Log Analysis

### Error Pattern Recognition
Look for these patterns in logs:
- `provider_error_auth`: Authentication failures
- `provider_error_throttled`: Rate limiting issues
- `provider_error_transient`: Temporary failures
- `provider_error_permanent`: Non-retryable errors

### Performance Monitoring
Key metrics to track:
- `provider_request_duration`: Request timing
- `provider_success_rate`: Success percentage
- `provider_retry_count`: Retry attempts
- `provider_fallback_count`: Fallback usage

### Troubleshooting Commands
```bash
# View recent errors
tail -f logs/provider.log | grep ERROR

# Filter by provider
tail -f logs/provider.log | grep "provider=grok"

# Monitor retry attempts
tail -f logs/provider.log | grep "retry_attempt"
```

## Support Resources

### Provider Documentation
- [xAI Grok API Docs](https://docs.x.ai/)
- [Runway ML API Docs](https://docs.runwayml.com/)
- [OpenAI API Docs](https://platform.openai.com/docs/)

### Community Resources
- GitHub Issues: Report bugs and feature requests
- Discord: Real-time community support
- Documentation: Comprehensive guides and examples

### Emergency Procedures
1. **Provider Outage**: Enable fallback providers immediately
2. **API Key Compromise**: Rotate keys and update configuration
3. **Rate Limit Exceeded**: Implement temporary queuing
4. **Service Degradation**: Scale down request frequency
