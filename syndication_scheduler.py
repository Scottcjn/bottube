#!/usr/bin/env python3
"""
Scheduling Controls for BoTTube Syndication

Advanced scheduling features for syndication operations:
- Cron expression parsing and evaluation
- Rate limiting with token bucket algorithm
- Time window restrictions (quiet hours)
- Day-of-week filtering
- Batch processing with delays

This module integrates with syndication_queue.py and syndication_adapter.py
to control when and how syndication operations are executed.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Set

from syndication_config import ScheduleConfig, SyndicationConfig

log = logging.getLogger("bottube-syndication-scheduler")


@dataclass
class RateLimitState:
    """State for rate limiting."""
    tokens: float = 0.0
    last_update: float = field(default_factory=time.time)


class CronParser:
    """
    Simple cron expression parser and evaluator.

    Supports standard 5-field cron format:
        minute hour day_of_month month day_of_week

    Special values:
        * - any value
        */n - every n units
        n-m - range from n to m
        n,m - specific values

    Examples:
        "* * * * *" - every minute
        "*/5 * * * *" - every 5 minutes
        "0 * * * *" - every hour
        "0 0 * * *" - every day at midnight
        "0 0 * * 0" - every Sunday at midnight
    """

    def __init__(self, expression: str):
        """
        Parse cron expression.

        Args:
            expression: Cron expression string

        Raises:
            ValueError: If expression is invalid
        """
        self.expression = expression
        self.fields = self._parse(expression)

    def _parse(self, expression: str) -> List[Set[int]]:
        """Parse cron expression into field sets."""
        parts = expression.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {expression} (expected 5 fields)")

        # Field ranges: minute, hour, day, month, weekday
        ranges = [
            (0, 59),   # minute
            (0, 23),   # hour
            (1, 31),   # day of month
            (1, 12),   # month
            (0, 6),    # day of week (0 = Sunday)
        ]

        fields = []
        for part, (min_val, max_val) in zip(parts, ranges):
            values = self._parse_field(part, min_val, max_val)
            fields.append(values)

        return fields

    def _parse_field(self, field: str, min_val: int, max_val: int) -> Set[int]:
        """Parse a single cron field."""
        values = set()

        for part in field.split(","):
            if part == "*":
                values.update(range(min_val, max_val + 1))
            elif part.startswith("*/"):
                step = int(part[2:])
                if step < 1:
                    raise ValueError(f"Invalid step value: {step}")
                values.update(range(min_val, max_val + 1, step))
            elif "-" in part:
                start, end = map(int, part.split("-"))
                if start > end or start < min_val or end > max_val:
                    raise ValueError(f"Invalid range: {part}")
                values.update(range(start, end + 1))
            else:
                val = int(part)
                if val < min_val or val > max_val:
                    raise ValueError(f"Value {val} out of range [{min_val}, {max_val}]")
                values.add(val)

        return values

    def matches(self, dt: Optional[datetime] = None) -> bool:
        """
        Check if datetime matches cron expression.

        Args:
            dt: datetime to check (default: now)

        Returns:
            True if datetime matches the cron expression
        """
        if dt is None:
            dt = datetime.now()

        # Check each field
        if dt.minute not in self.fields[0]:
            return False
        if dt.hour not in self.fields[1]:
            return False
        if dt.day not in self.fields[2]:
            return False
        if dt.month not in self.fields[3]:
            return False
        
        # Convert Python weekday (0=Monday) to cron (0=Sunday)
        cron_weekday = (dt.weekday() + 1) % 7
        if cron_weekday not in self.fields[4]:
            return False

        return True

    def next_run(self, after: Optional[datetime] = None) -> datetime:
        """
        Calculate next run time after given datetime.

        Args:
            after: Starting datetime (default: now)

        Returns:
            Next datetime that matches the cron expression
        """
        if after is None:
            after = datetime.now()

        # Start from next minute
        dt = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

        # Search for next match (max 4 years to handle edge cases)
        max_iterations = 366 * 24 * 60 * 4  # 4 years of minutes
        for _ in range(max_iterations):
            if self.matches(dt):
                return dt
            dt += timedelta(minutes=1)

        raise ValueError("Could not find next run time within 4 years")


class RateLimiter:
    """
    Token bucket rate limiter.

    Allows bursts up to bucket capacity, then limits to refill rate.
    Thread-safe for concurrent operations.
    """

    def __init__(self, rate: int, window: int = 60):
        """
        Initialize rate limiter.

        Args:
            rate: Maximum requests per window
            window: Time window in seconds (default: 60)
        """
        self.rate = rate
        self.window = window
        self._buckets: Dict[str, RateLimitState] = {}

    def _get_bucket(self, key: str = "default") -> RateLimitState:
        """Get or create bucket for key."""
        if key not in self._buckets:
            self._buckets[key] = RateLimitState(tokens=float(self.rate))
        return self._buckets[key]

    def acquire(self, key: str = "default", tokens: int = 1) -> bool:
        """
        Try to acquire tokens from bucket.

        Args:
            key: Bucket identifier (for per-key rate limiting)
            tokens: Number of tokens to acquire

        Returns:
            True if tokens were acquired, False if rate limited
        """
        bucket = self._get_bucket(key)
        now = time.time()

        # Refill tokens based on elapsed time
        elapsed = now - bucket.last_update
        refill = elapsed * (self.rate / self.window)
        bucket.tokens = min(float(self.rate), bucket.tokens + refill)
        bucket.last_update = now

        # Try to acquire
        if bucket.tokens >= tokens:
            bucket.tokens -= tokens
            return True
        return False

    def wait_for_token(self, key: str = "default", tokens: int = 1,
                       timeout: Optional[float] = None) -> bool:
        """
        Wait until tokens are available.

        Args:
            key: Bucket identifier
            tokens: Number of tokens to acquire
            timeout: Maximum wait time in seconds (None = wait forever)

        Returns:
            True if tokens were acquired, False if timeout
        """
        start = time.time()
        while True:
            if self.acquire(key, tokens):
                return True

            if timeout is not None and (time.time() - start) >= timeout:
                return False

            # Calculate wait time for next token
            bucket = self._get_bucket(key)
            tokens_needed = tokens - bucket.tokens
            wait_time = tokens_needed * (self.window / self.rate)
            time.sleep(min(wait_time, 0.1))  # Cap at 100ms

    def get_wait_time(self, key: str = "default", tokens: int = 1) -> float:
        """Get time to wait until tokens are available."""
        bucket = self._get_bucket(key)
        now = time.time()

        # Refill calculation
        elapsed = now - bucket.last_update
        refill = elapsed * (self.rate / self.window)
        current_tokens = min(float(self.rate), bucket.tokens + refill)

        if current_tokens >= tokens:
            return 0.0

        tokens_needed = tokens - current_tokens
        return tokens_needed * (self.window / self.rate)


class SyndicationScheduler:
    """
    Main scheduler for syndication operations.

    Integrates cron scheduling, rate limiting, and time windows
    to control when syndication operations execute.

    Usage:
        config = load_config()
        scheduler = SyndicationScheduler(config)

        # Check if syndication should run
        if scheduler.should_run():
            # Check rate limit
            if scheduler.acquire_rate_limit("moltbook"):
                # Execute syndication
                ...
    """

    def __init__(self, config: SyndicationConfig):
        """
        Initialize scheduler with configuration.

        Args:
            config: Syndication configuration
        """
        self.config = config
        self.schedule_config = config.schedule

        # Initialize cron parser
        self._cron = CronParser(self.schedule_config.cron_expression)

        # Initialize rate limiters
        self._global_limiter = RateLimiter(
            config.global_rate_limit,
            window=60,
        )
        self._platform_limiters: Dict[str, RateLimiter] = {}
        for name, platform_config in config.platforms.items():
            self._platform_limiters[name] = RateLimiter(
                platform_config.rate_limit,
                window=platform_config.rate_limit_window,
            )

    def should_run(self, dt: Optional[datetime] = None) -> bool:
        """
        Check if syndication should run at given time.

        Considers:
            - Cron expression
            - Enabled status
            - Quiet hours
            - Days of week

        Args:
            dt: datetime to check (default: now)

        Returns:
            True if syndication is allowed to run
        """
        if not self.config.enabled:
            return False

        if not self.schedule_config.enabled:
            return True  # Schedule disabled = always run

        if dt is None:
            dt = datetime.now()

        # Check cron expression
        if not self._cron.matches(dt):
            return False

        # Check quiet hours
        if self._is_quiet_hours(dt):
            return False

        # Check days of week
        if not self._is_valid_day(dt):
            return False

        return True

    def _is_quiet_hours(self, dt: datetime) -> bool:
        """Check if datetime falls within quiet hours."""
        start = self.schedule_config.quiet_hours_start
        end = self.schedule_config.quiet_hours_end

        if not start or not end:
            return False

        try:
            start_hour, start_min = map(int, start.split(":"))
            end_hour, end_min = map(int, end.split(":"))

            current_minutes = dt.hour * 60 + dt.minute
            start_minutes = start_hour * 60 + start_min
            end_minutes = end_hour * 60 + end_min

            if start_minutes <= end_minutes:
                # Normal range (e.g., 22:00 - 08:00 next day)
                return start_minutes <= current_minutes < end_minutes
            else:
                # Spans midnight (e.g., 22:00 - 06:00)
                return current_minutes >= start_minutes or current_minutes < end_minutes
        except (ValueError, AttributeError):
            return False

    def _is_valid_day(self, dt: datetime) -> bool:
        """Check if day of week is allowed."""
        days = self.schedule_config.days_of_week
        if not days:
            return True

        # Convert Python weekday (0=Monday) to cron (0=Sunday)
        cron_weekday = (dt.weekday() + 1) % 7
        return cron_weekday in days

    def acquire_rate_limit(self, platform: str) -> bool:
        """
        Try to acquire rate limit token for platform.

        Args:
            platform: Platform name

        Returns:
            True if token acquired, False if rate limited
        """
        # Check global rate limit first
        if not self._global_limiter.acquire("global"):
            log.debug("Global rate limit exceeded")
            return False

        # Check platform-specific rate limit
        limiter = self._platform_limiters.get(platform)
        if limiter and not limiter.acquire(platform):
            log.debug("Platform rate limit exceeded: %s", platform)
            # Refund global token
            self._global_limiter._get_bucket("global").tokens += 1
            return False

        return True

    def wait_for_rate_limit(self, platform: str,
                            timeout: Optional[float] = None) -> bool:
        """
        Wait until rate limit allows execution.

        Args:
            platform: Platform name
            timeout: Maximum wait time (None = wait forever)

        Returns:
            True if acquired, False if timeout
        """
        # Wait for global rate limit
        if not self._global_limiter.wait_for_token("global", timeout=timeout):
            return False

        # Wait for platform rate limit
        limiter = self._platform_limiters.get(platform)
        if limiter:
            if not limiter.wait_for_token(platform, timeout=timeout):
                # Refund global token
                self._global_limiter._get_bucket("global").tokens += 1
                return False

        return True

    def get_next_run_time(self, after: Optional[datetime] = None) -> datetime:
        """
        Get next scheduled run time.

        Args:
            after: Starting datetime (default: now)

        Returns:
            Next datetime when syndication should run
        """
        return self._cron.next_run(after)

    def get_rate_limit_wait_time(self, platform: str) -> float:
        """
        Get time to wait until rate limit allows execution.

        Args:
            platform: Platform name

        Returns:
            Wait time in seconds (0 if not rate limited)
        """
        global_wait = self._global_limiter.get_wait_time("global")
        platform_wait = 0.0

        limiter = self._platform_limiters.get(platform)
        if limiter:
            platform_wait = limiter.get_wait_time(platform)

        return max(global_wait, platform_wait)


class BatchProcessor:
    """
    Processes syndication items in batches with delays.

    Prevents overwhelming external APIs by spacing out requests.
    """

    def __init__(self, batch_size: int = 10, batch_delay: float = 5.0):
        """
        Initialize batch processor.

        Args:
            batch_size: Number of items per batch
            batch_delay: Delay between batches in seconds
        """
        self.batch_size = batch_size
        self.batch_delay = batch_delay
        self._processed_count = 0
        self._batch_start_time: Optional[float] = None

    def should_process(self) -> bool:
        """Check if next item should be processed now."""
        if self._processed_count < self.batch_size:
            return True

        # Check if enough time has passed since batch started
        if self._batch_start_time is None:
            return True

        elapsed = time.time() - self._batch_start_time
        return elapsed >= self.batch_delay

    def wait_if_needed(self):
        """Wait if batch limit reached."""
        if self._processed_count >= self.batch_size and self._batch_start_time:
            elapsed = time.time() - self._batch_start_time
            if elapsed < self.batch_delay:
                sleep_time = self.batch_delay - elapsed
                log.debug("Batch limit reached, waiting %.1f seconds", sleep_time)
                time.sleep(sleep_time)

        # Reset for next batch
        self._processed_count = 0
        self._batch_start_time = time.time()

    def record_processed(self):
        """Record that an item was processed."""
        if self._batch_start_time is None:
            self._batch_start_time = time.time()
        self._processed_count += 1

    def reset(self):
        """Reset batch state."""
        self._processed_count = 0
        self._batch_start_time = None


def create_scheduler(config: SyndicationConfig) -> SyndicationScheduler:
    """Factory function to create scheduler from config."""
    return SyndicationScheduler(config)


def create_batch_processor(config: SyndicationConfig) -> BatchProcessor:
    """Factory function to create batch processor from config."""
    schedule = config.schedule
    return BatchProcessor(
        batch_size=schedule.batch_size,
        batch_delay=schedule.batch_delay,
    )
