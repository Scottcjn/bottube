# BoTTube Beacon Discord Transport Setup Guide

## Overview

The BoTTube Beacon Discord transport allows you to send monitoring alerts and status updates directly to Discord channels via webhooks. This guide covers complete setup, configuration, and troubleshooting.

## Discord Webhook Setup

### Step 1: Create Discord Webhook

1. Navigate to your Discord server
2. Right-click on the target channel → **Edit Channel**
3. Go to **Integrations** → **Webhooks**
4. Click **Create Webhook**
5. Customize name (e.g., "BoTTube Alerts") and avatar
6. Click **Copy Webhook URL**

### Step 2: Configure BoTTube Environment

Add to your `.env` file:

```bash
# Discord Transport Configuration
BEACON_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/1234567890123456789/abcdefghijklmnopqrstuvwxyz1234567890
BEACON_DISCORD_USERNAME=BoTTube-Monitor
BEACON_DISCORD_RETRY_COUNT=3
BEACON_DISCORD_TIMEOUT=30
```

### Step 3: Test Configuration

```bash
# Test webhook connectivity
python -m bottube.beacon discord ping

# Send test message
python -m bottube.beacon discord send "System initialized successfully"
```

## Command Reference

### Discord Ping Command

Tests webhook connectivity and Discord API access.

```bash
# Basic ping
python -m bottube.beacon discord ping

# Verbose output
python -m bottube.beacon discord ping --verbose

# Custom webhook URL
python -m bottube.beacon discord ping --webhook-url "https://discord.com/api/webhooks/..."
```

**Expected Output (Success):**
```
✅ Discord webhook ping successful
Response: 200 OK
Latency: 234ms
Channel: #bottube-alerts
Guild: My Server
```

**Expected Output (Failure):**
```
❌ Discord webhook ping failed
Error: 404 Not Found - Webhook not found
URL: https://discord.com/api/webhooks/invalid/...
```

### Discord Send Command

Sends messages to configured Discord channel.

```bash
# Simple message
python -m bottube.beacon discord send "Deployment completed successfully"

# Message with embed
python -m bottube.beacon discord send --title "Alert" --message "High CPU usage detected" --color "#ff6b6b"

# Emergency alert
python -m bottube.beacon discord send --emergency "Database connection lost!"

# Include system info
python -m bottube.beacon discord send --system-info "Server restart initiated"
```

**Message Format Options:**

```bash
# Plain text
python -m bottube.beacon discord send "Simple status update"

# Rich embed
python -m bottube.beacon discord send \
  --title "System Alert" \
  --message "CPU usage: 85%" \
  --color "#ffa500" \
  --footer "BoTTube Monitor"

# With timestamp
python -m bottube.beacon discord send \
  --message "Backup completed" \
  --timestamp "$(date -Iseconds)"

# Multiple fields
python -m bottube.beacon discord send \
  --title "Health Check" \
  --field "Status=Healthy" \
  --field "Uptime=5d 12h" \
  --field "Memory=2.1GB/4GB"
```

### Discord Listen Mode

Monitor Discord channel for commands and events.

```bash
# Start listener (basic)
python -m bottube.beacon discord listen

# Listen with command processing
python -m bottube.beacon discord listen --process-commands

# Listen for specific patterns
python -m bottube.beacon discord listen --pattern "!bottube *"

# Background listener
python -m bottube.beacon discord listen --daemon --log-file /var/log/bottube-discord.log
```

**Expected Output:**
```
🎧 Discord listener started
Channel: #bottube-alerts
Polling interval: 30s
Listening for: all messages
Press Ctrl+C to stop...

[2024-01-15 10:30:45] Message: "!bottube status"
[2024-01-15 10:30:45] Processing command: status
[2024-01-15 10:30:46] Response sent: System healthy
```

## Configuration Options

### Environment Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `BEACON_DISCORD_WEBHOOK_URL` | Discord webhook URL | Required | `https://discord.com/api/webhooks/...` |
| `BEACON_DISCORD_USERNAME` | Bot display name | `BoTTube` | `Production-Monitor` |
| `BEACON_DISCORD_AVATAR_URL` | Bot avatar image | None | `https://example.com/avatar.png` |
| `BEACON_DISCORD_RETRY_COUNT` | Failed request retries | `3` | `5` |
| `BEACON_DISCORD_TIMEOUT` | Request timeout (seconds) | `30` | `60` |
| `BEACON_DISCORD_RATE_LIMIT_DELAY` | Rate limit backoff (seconds) | `5` | `10` |

### Advanced Configuration

```bash
# Custom rate limiting
BEACON_DISCORD_RATE_LIMIT_DELAY=10
BEACON_DISCORD_MAX_RETRIES=5

# Message formatting
BEACON_DISCORD_DEFAULT_COLOR=#3498db
BEACON_DISCORD_EMERGENCY_COLOR=#e74c3c
BEACON_DISCORD_SUCCESS_COLOR=#2ecc71

# Listener settings
BEACON_DISCORD_POLL_INTERVAL=30
BEACON_DISCORD_COMMAND_PREFIX=!bottube
BEACON_DISCORD_MAX_MESSAGE_AGE=3600
```

## Payload Examples

### Basic Text Message

```json
{
  "username": "BoTTube-Monitor",
  "content": "System status: All services operational"
}
```

### Rich Embed Message

```json
{
  "username": "BoTTube-Monitor",
  "embeds": [{
    "title": "System Alert",
    "description": "High memory usage detected",
    "color": 16734720,
    "timestamp": "2024-01-15T10:30:45Z",
    "fields": [
      {
        "name": "Memory Usage",
        "value": "3.2GB / 4GB (80%)",
        "inline": true
      },
      {
        "name": "Status",
        "value": "⚠️ Warning",
        "inline": true
      }
    ],
    "footer": {
      "text": "BoTTube Monitor",
      "icon_url": "https://example.com/icon.png"
    }
  }]
}
```

### Emergency Alert

```json
{
  "username": "BoTTube-EMERGENCY",
  "content": "@here Database connection lost!",
  "embeds": [{
    "title": "🚨 CRITICAL ALERT",
    "description": "Immediate attention required",
    "color": 15158332,
    "timestamp": "2024-01-15T10:30:45Z"
  }]
}
```

## Troubleshooting

### Common Issues

#### 1. Webhook URL Invalid (404)

**Symptoms:**
```
❌ Discord webhook ping failed
Error: 404 Not Found - Unknown Webhook
```

**Solutions:**
- Verify webhook URL is complete and unmodified
- Check if webhook was deleted in Discord
- Ensure webhook belongs to accessible server
- Regenerate webhook if necessary

#### 2. Rate Limited (429)

**Symptoms:**
```
⚠️ Rate limited by Discord API
Retry after: 65 seconds
Attempt 2/3: Backing off...
```

**Solutions:**
- Reduce message frequency
- Increase `BEACON_DISCORD_RATE_LIMIT_DELAY`
- Implement message batching
- Use emergency-only alerts during high traffic

#### 3. Permission Denied (403)

**Symptoms:**
```
❌ Permission denied
Error: 403 Forbidden - Cannot execute webhook
```

**Solutions:**
- Check webhook permissions in Discord
- Verify bot has "Send Messages" permission
- Ensure channel allows webhooks
- Check server-level restrictions

#### 4. Timeout Issues

**Symptoms:**
```
❌ Request timeout after 30s
Network may be unstable
```

**Solutions:**
```bash
# Increase timeout
export BEACON_DISCORD_TIMEOUT=60

# Test network connectivity
curl -I https://discord.com/api/v10

# Use verbose mode for debugging
python -m bottube.beacon discord ping --verbose
```

### Debug Mode

Enable detailed logging:

```bash
# Set debug environment
export BEACON_DEBUG=1
export BEACON_LOG_LEVEL=DEBUG

# Run with verbose output
python -m bottube.beacon discord send "Debug test" --verbose

# Check logs
tail -f /var/log/bottube-beacon.log
```

### Network Diagnostics

```bash
# Test Discord API connectivity
curl -X GET "https://discord.com/api/v10" \
  -H "User-Agent: BoTTube-Beacon/1.0"

# Test webhook endpoint
curl -X POST "$BEACON_DISCORD_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"content":"Connection test"}'

# Check DNS resolution
nslookup discord.com

# Test from different network
python -m bottube.beacon discord ping --webhook-url "https://discord.com/api/webhooks/test"
```

## Integration Examples

### Cron Job Monitoring

```bash
#!/bin/bash
# /etc/cron.daily/bottube-health

# Run health check
if python -m bottube.health.check --quiet; then
  python -m bottube.beacon discord send "✅ Daily health check passed"
else
  python -m bottube.beacon discord send --emergency "❌ Daily health check FAILED"
fi
```

### Service Startup

```bash
#!/bin/bash
# Service startup script

echo "Starting BoTTube services..."
systemctl start bottube

if systemctl is-active bottube >/dev/null; then
  python -m bottube.beacon discord send "🚀 BoTTube services started successfully"
else
  python -m bottube.beacon discord send --emergency "💥 Failed to start BoTTube services"
fi
```

### Python Integration

```python
from bottube.beacon.discord import DiscordTransport

# Initialize transport
transport = DiscordTransport()

# Send status update
try:
    transport.send_message(
        "System backup completed",
        title="Backup Status",
        color="#2ecc71"
    )
except Exception as e:
    transport.send_emergency(f"Backup failed: {e}")
```

### Error Handling Patterns

```python
import time
from bottube.beacon.discord import DiscordTransport, RateLimitError

def send_with_retry(message, max_retries=3):
    transport = DiscordTransport()

    for attempt in range(max_retries):
        try:
            return transport.send_message(message)
        except RateLimitError as e:
            if attempt < max_retries - 1:
                time.sleep(e.retry_after)
                continue
            raise
        except Exception as e:
            if attempt == max_retries - 1:
                # Last attempt failed, send to fallback
                transport.send_emergency(f"Failed to send message: {e}")
            raise
```

## Best Practices

### Message Design

1. **Use clear, actionable titles**
   ```bash
   # Good
   python -m bottube.beacon discord send --title "Database Error" --message "Connection pool exhausted"

   # Avoid
   python -m bottube.beacon discord send "Something went wrong"
   ```

2. **Include relevant context**
   ```bash
   python -m bottube.beacon discord send \
     --title "High CPU Alert" \
     --field "Server=prod-web-01" \
     --field "CPU=89%" \
     --field "Duration=5min"
   ```

3. **Use appropriate colors**
   - 🔴 Red (`#e74c3c`): Errors, critical alerts
   - 🟡 Yellow (`#f39c12`): Warnings, degraded performance
   - 🟢 Green (`#27ae60`): Success, recovery
   - 🔵 Blue (`#3498db`): Information, status updates

### Rate Limit Management

1. **Batch related messages**
2. **Use different severity channels**
3. **Implement exponential backoff**
4. **Monitor API quota usage**

### Security

1. **Rotate webhook URLs periodically**
2. **Use environment variables, not hardcoded URLs**
3. **Restrict webhook permissions**
4. **Monitor for unauthorized usage**

### Monitoring

```bash
# Monitor transport health
python -m bottube.beacon discord ping --monitor --interval 300

# Log all Discord transport activity
export BEACON_DISCORD_LOG_ALL=1
```

This completes the Discord transport setup and usage documentation. For additional support, check the GitHub issues or join our Discord server.
