# BoTTube API Rate Limiter - Bounty #366

**Task**: Implement API Rate Limiting System  
**Value**: 75 RTC  
**Status**: 🚀 In Progress  

---

## 🎯 Problem Statement

BoTTube API needs rate limiting to:
- Prevent abuse and DDoS attacks
- Ensure fair usage across all users
- Protect backend services from overload
- Enable tiered access (free vs premium)

---

## 📋 Rate Limit Tiers

### Free Tier
```
- API Requests: 100 requests/hour
- Video Uploads: 10 videos/day
- Analytics API: 50 requests/hour
- WebSocket Connections: 1 concurrent
```

### Premium Tier (100+ RTC/month)
```
- API Requests: 1000 requests/hour
- Video Uploads: 100 videos/day
- Analytics API: 500 requests/hour
- WebSocket Connections: 5 concurrent
```

### Enterprise Tier (1000+ RTC/month)
```
- API Requests: 10,000 requests/hour
- Video Uploads: Unlimited
- Analytics API: 5,000 requests/hour
- WebSocket Connections: 20 concurrent
- Priority support
- Custom rate limits available
```

---

## 🛠️ Technical Implementation

### Rate Limiting Algorithm: Token Bucket
```javascript
class RateLimiter {
    constructor(maxTokens, refillRate) {
        this.maxTokens = maxTokens;
        this.tokens = maxTokens;
        this.refillRate = refillRate; // tokens per second
        this.lastRefill = Date.now();
    }

    consume(tokens = 1) {
        this.refill();
        if (this.tokens >= tokens) {
            this.tokens -= tokens;
            return { allowed: true, remaining: this.tokens };
        }
        return { 
            allowed: false, 
            retryAfter: Math.ceil((tokens - this.tokens) / this.refillRate)
        };
    }

    refill() {
        const now = Date.now();
        const elapsed = (now - this.lastRefill) / 1000;
        this.tokens = Math.min(
            this.maxTokens,
            this.tokens + (elapsed * this.refillRate)
        );
        this.lastRefill = now;
    }
}
```

### Middleware Implementation (Express.js)
```javascript
const rateLimitMiddleware = async (req, res, next) => {
    const userId = req.user.id;
    const tier = await getUserTier(userId);
    const limits = getTierLimits(tier);
    
    const limiter = getLimiter(userId, limits);
    const result = limiter.consume();
    
    // Set rate limit headers
    res.set('X-RateLimit-Limit', limits.maxTokens);
    res.set('X-RateLimit-Remaining', result.remaining);
    
    if (!result.allowed) {
        res.set('Retry-After', result.retryAfter);
        return res.status(429).json({
            error: 'Rate limit exceeded',
            retryAfter: result.retryAfter,
            tier: tier,
            upgrade: `/api/pricing`
        });
    }
    
    next();
};
```

### Redis-Based Distributed Rate Limiting
```javascript
const Redis = require('ioredis');
const redis = new Redis();

async function checkRateLimit(userId, endpoint, limit) {
    const key = `ratelimit:${userId}:${endpoint}`;
    const current = await redis.incr(key);
    
    if (current === 1) {
        await redis.expire(key, 3600); // 1 hour window
    }
    
    const remaining = Math.max(0, limit - current);
    
    return {
        allowed: current <= limit,
        remaining: remaining,
        resetAt: Date.now() + 3600000
    };
}
```

---

## 📊 API Response Headers

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1710847200
Retry-After: 3600  (only on 429 responses)
```

### 429 Response Example
```json
{
    "error": "Rate limit exceeded",
    "message": "You have exceeded your API rate limit",
    "retryAfter": 3600,
    "currentTier": "free",
    "limits": {
        "requestsPerHour": 100,
        "uploadsPerDay": 10
    },
    "upgrade": {
        "url": "/api/pricing",
        "premium": {
            "requestsPerHour": 1000,
            "price": "100 RTC/month"
        }
    }
}
```

---

## 📐 Dashboard UI

### Usage Monitor
```
┌──────────────────────────────────────────────────────┐
│  📊 API Usage Dashboard                              │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Current Tier: FREE                                  │
│  ─────────────────────────────────────────────────   │
│                                                      │
│  API Requests (Last Hour)                            │
│  ┌────────────────────────────────────────────┐     │
│  │ ████████████████░░░░░░░░░░░░░░░░░░░░  84%  │     │
│  │ 84 / 100 requests used                      │     │
│  │ Resets in: 23 minutes                       │     │
│  └────────────────────────────────────────────┘     │
│                                                      │
│  Video Uploads (Today)                               │
│  ┌────────────────────────────────────────────┐     │
│  │ ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░  80%  │     │
│  │ 8 / 10 uploads used                         │     │
│  │ Resets in: 14 hours                         │     │
│  └────────────────────────────────────────────┘     │
│                                                      │
│  ⚡ Upgrade to Premium                                │
│  ┌────────────────────────────────────────────┐     │
│  │ • 1000 requests/hour (10x more)            │     │
│  │ • 100 uploads/day (10x more)               │     │
│  │ • Priority support                         │     │
│  │                                            │     │
│  │ Price: 100 RTC/month                       │     │
│  │ [Upgrade Now]                              │     │
│  └────────────────────────────────────────────┘     │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

## ✅ Deliverables

- [ ] Token bucket rate limiter implementation
- [ ] Redis-based distributed rate limiting
- [ ] Express.js middleware
- [ ] Rate limit headers on all API responses
- [ ] 429 response handling
- [ ] Usage dashboard UI
- [ ] Tier management system
- [ ] Documentation for API users

---

## 🎯 Success Metrics

- Rate limiting enforced within 10ms
- Zero false positives (legitimate requests never blocked)
- Accurate usage tracking across distributed servers
- Clear user communication when limits hit

---

**Estimated Time**: 2-3 hours  
**Difficulty**: Medium  
**Skills Required**: Node.js, Redis, Express.js, React
