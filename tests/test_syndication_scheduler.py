#!/usr/bin/env python3
"""
Tests for Syndication Scheduler (Issue #310)

Tests cover:
- Cron expression parsing and evaluation
- Rate limiting with token bucket
- Time window restrictions (quiet hours)
- Day-of-week filtering
- Batch processing
- Scheduler integration
"""

import time
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

import sys

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from syndication_scheduler import (
    CronParser,
    RateLimiter,
    SyndicationScheduler,
    BatchProcessor,
    create_scheduler,
    create_batch_processor,
)
from syndication_config import SyndicationConfig, PlatformConfig, ScheduleConfig


class TestCronParser:
    """Tests for cron expression parser."""

    def test_every_minute(self):
        """Test * * * * * expression."""
        cron = CronParser("* * * * *")
        dt = datetime(2026, 3, 10, 12, 30, 0)
        assert cron.matches(dt) is True

    def test_every_5_minutes(self):
        """Test */5 * * * * expression."""
        cron = CronParser("*/5 * * * *")
        assert cron.matches(datetime(2026, 3, 10, 12, 0, 0)) is True
        assert cron.matches(datetime(2026, 3, 10, 12, 5, 0)) is True
        assert cron.matches(datetime(2026, 3, 10, 12, 3, 0)) is False
        assert cron.matches(datetime(2026, 3, 10, 12, 7, 0)) is False

    def test_every_hour(self):
        """Test 0 * * * * expression."""
        cron = CronParser("0 * * * *")
        assert cron.matches(datetime(2026, 3, 10, 12, 0, 0)) is True
        assert cron.matches(datetime(2026, 3, 10, 12, 1, 0)) is False

    def test_specific_hour(self):
        """Test 0 12 * * * expression (noon every day)."""
        cron = CronParser("0 12 * * *")
        assert cron.matches(datetime(2026, 3, 10, 12, 0, 0)) is True
        assert cron.matches(datetime(2026, 3, 10, 13, 0, 0)) is False

    def test_range(self):
        """Test 0 9-17 * * * expression (business hours)."""
        cron = CronParser("0 9-17 * * *")
        assert cron.matches(datetime(2026, 3, 10, 9, 0, 0)) is True
        assert cron.matches(datetime(2026, 3, 10, 12, 0, 0)) is True
        assert cron.matches(datetime(2026, 3, 10, 17, 0, 0)) is True
        assert cron.matches(datetime(2026, 3, 10, 8, 0, 0)) is False
        assert cron.matches(datetime(2026, 3, 10, 18, 0, 0)) is False

    def test_specific_values(self):
        """Test 0 9,12,17 * * * expression."""
        cron = CronParser("0 9,12,17 * * *")
        assert cron.matches(datetime(2026, 3, 10, 9, 0, 0)) is True
        assert cron.matches(datetime(2026, 3, 10, 12, 0, 0)) is True
        assert cron.matches(datetime(2026, 3, 10, 17, 0, 0)) is True
        assert cron.matches(datetime(2026, 3, 10, 10, 0, 0)) is False

    def test_day_of_week(self):
        """Test day of week matching."""
        # Every Sunday at midnight (0 = Sunday in cron)
        cron = CronParser("0 0 * * 0")
        # March 15, 2026 is a Sunday
        assert cron.matches(datetime(2026, 3, 15, 0, 0, 0)) is True
        # March 16, 2026 is a Monday
        assert cron.matches(datetime(2026, 3, 16, 0, 0, 0)) is False

    def test_weekdays_only(self):
        """Test weekdays only (Monday-Friday)."""
        # 1-5 = Monday-Friday in cron
        cron = CronParser("0 0 * * 1-5")
        # March 16, 2026 is a Monday
        assert cron.matches(datetime(2026, 3, 16, 0, 0, 0)) is True
        # March 15, 2026 is a Sunday
        assert cron.matches(datetime(2026, 3, 15, 0, 0, 0)) is False

    def test_invalid_expression_wrong_field_count(self):
        """Test invalid expression with wrong field count."""
        with pytest.raises(ValueError, match="expected 5 fields"):
            CronParser("* * * *")

    def test_invalid_expression_out_of_range(self):
        """Test invalid expression with out-of-range value."""
        with pytest.raises(ValueError, match="out of range"):
            CronParser("60 * * * *")

    def test_invalid_step_value(self):
        """Test invalid step value."""
        with pytest.raises(ValueError, match="Invalid step"):
            CronParser("*/0 * * * *")

    def test_next_run(self):
        """Test calculating next run time."""
        cron = CronParser("0 * * * *")  # Every hour
        dt = datetime(2026, 3, 10, 12, 30, 0)
        next_run = cron.next_run(dt)
        assert next_run == datetime(2026, 3, 10, 13, 0, 0)

    def test_next_run_every_5_minutes(self):
        """Test next run for every 5 minutes."""
        cron = CronParser("*/5 * * * *")
        dt = datetime(2026, 3, 10, 12, 33, 0)
        next_run = cron.next_run(dt)
        assert next_run == datetime(2026, 3, 10, 12, 35, 0)


class TestRateLimiter:
    """Tests for token bucket rate limiter."""

    def test_acquire_within_limit(self):
        """Test acquiring tokens within rate limit."""
        limiter = RateLimiter(rate=10, window=60)
        assert limiter.acquire() is True

    def test_acquire_exceeds_limit(self):
        """Test acquiring tokens exceeds rate limit."""
        limiter = RateLimiter(rate=2, window=60)
        assert limiter.acquire() is True
        assert limiter.acquire() is True
        assert limiter.acquire() is False

    def test_acquire_refills_over_time(self):
        """Test token refill over time."""
        limiter = RateLimiter(rate=10, window=1)  # 10 tokens per second
        # Exhaust tokens
        for _ in range(10):
            limiter.acquire()
        assert limiter.acquire() is False

        # Wait for refill
        time.sleep(0.2)  # Should refill ~2 tokens
        assert limiter.acquire() is True

    def test_per_key_rate_limiting(self):
        """Test per-key rate limiting."""
        limiter = RateLimiter(rate=2, window=60)
        # Exhaust "platform1" limit
        assert limiter.acquire("platform1") is True
        assert limiter.acquire("platform1") is True
        assert limiter.acquire("platform1") is False

        # "platform2" should still have tokens
        assert limiter.acquire("platform2") is True

    def test_wait_for_token_success(self):
        """Test waiting for token succeeds."""
        limiter = RateLimiter(rate=10, window=1)
        # Exhaust tokens
        for _ in range(10):
            limiter.acquire()

        # Should wait and then succeed
        assert limiter.wait_for_token(timeout=1.0) is True

    def test_wait_for_token_timeout(self):
        """Test waiting for token times out."""
        limiter = RateLimiter(rate=1, window=60)
        # Exhaust tokens
        limiter.acquire()

        # Should timeout
        assert limiter.wait_for_token(timeout=0.1) is False

    def test_get_wait_time(self):
        """Test getting wait time for tokens."""
        limiter = RateLimiter(rate=10, window=1)
        # Exhaust tokens
        for _ in range(10):
            limiter.acquire()

        wait_time = limiter.get_wait_time()
        assert wait_time > 0


class TestSyndicationScheduler:
    """Tests for SyndicationScheduler."""

    def _create_test_config(self) -> SyndicationConfig:
        """Create test configuration."""
        return SyndicationConfig(
            enabled=True,
            poll_interval=60,
            platforms={
                "moltbook": PlatformConfig(enabled=True, rate_limit=30),
                "twitter": PlatformConfig(enabled=True, rate_limit=60),
            },
            schedule=ScheduleConfig(
                enabled=True,
                cron_expression="* * * * *",
            ),
        )

    def test_should_run_enabled(self):
        """Test should_run with scheduler enabled."""
        config = self._create_test_config()
        scheduler = SyndicationScheduler(config)
        assert scheduler.should_run() is True

    def test_should_run_disabled(self):
        """Test should_run with scheduler disabled."""
        config = self._create_test_config()
        config.enabled = False
        scheduler = SyndicationScheduler(config)
        assert scheduler.should_run() is False

    def test_should_run_schedule_disabled(self):
        """Test should_run with schedule disabled."""
        config = self._create_test_config()
        config.schedule.enabled = False
        scheduler = SyndicationScheduler(config)
        # Schedule disabled = always run (if cron matches)
        assert scheduler.should_run() is True

    def test_should_run_cron_mismatch(self):
        """Test should_run when cron doesn't match."""
        config = self._create_test_config()
        config.schedule.cron_expression = "0 0 * * *"  # Only midnight
        scheduler = SyndicationScheduler(config)
        # Test at noon
        noon = datetime(2026, 3, 10, 12, 30, 0)
        assert scheduler.should_run(noon) is False

    def test_quiet_hours_within(self):
        """Test quiet hours when within range."""
        config = self._create_test_config()
        config.schedule.quiet_hours_start = "22:00"
        config.schedule.quiet_hours_end = "06:00"
        scheduler = SyndicationScheduler(config)

        # 23:00 is within quiet hours
        assert scheduler._is_quiet_hours(datetime(2026, 3, 10, 23, 0, 0)) is True
        # 02:00 is within quiet hours
        assert scheduler._is_quiet_hours(datetime(2026, 3, 10, 2, 0, 0)) is True

    def test_quiet_hours_outside(self):
        """Test quiet hours when outside range."""
        config = self._create_test_config()
        config.schedule.quiet_hours_start = "22:00"
        config.schedule.quiet_hours_end = "06:00"
        scheduler = SyndicationScheduler(config)

        # 12:00 is outside quiet hours
        assert scheduler._is_quiet_hours(datetime(2026, 3, 10, 12, 0, 0)) is False
        # 08:00 is outside quiet hours
        assert scheduler._is_quiet_hours(datetime(2026, 3, 10, 8, 0, 0)) is False

    def test_quiet_hours_no_config(self):
        """Test quiet hours when not configured."""
        config = self._create_test_config()
        scheduler = SyndicationScheduler(config)
        assert scheduler._is_quiet_hours(datetime(2026, 3, 10, 12, 0, 0)) is False

    def test_valid_day_of_week(self):
        """Test day of week filtering."""
        config = self._create_test_config()
        config.schedule.days_of_week = [1, 2, 3, 4, 5]  # Mon-Fri
        scheduler = SyndicationScheduler(config)

        # March 16, 2026 is Monday (cron day 2)
        assert scheduler._is_valid_day(datetime(2026, 3, 16, 0, 0, 0)) is True
        # March 15, 2026 is Sunday (cron day 1)
        assert scheduler._is_valid_day(datetime(2026, 3, 15, 0, 0, 0)) is False

    def test_acquire_rate_limit(self):
        """Test rate limit acquisition."""
        config = self._create_test_config()
        scheduler = SyndicationScheduler(config)

        # Should acquire within limit
        assert scheduler.acquire_rate_limit("moltbook") is True

    def test_get_next_run_time(self):
        """Test getting next run time."""
        config = self._create_test_config()
        config.schedule.cron_expression = "0 * * * *"
        scheduler = SyndicationScheduler(config)

        after = datetime(2026, 3, 10, 12, 30, 0)
        next_run = scheduler.get_next_run_time(after)
        assert next_run == datetime(2026, 3, 10, 13, 0, 0)

    def test_get_rate_limit_wait_time(self):
        """Test getting rate limit wait time."""
        config = self._create_test_config()
        config.platforms["moltbook"].rate_limit = 1
        scheduler = SyndicationScheduler(config)

        # Exhaust limit
        scheduler.acquire_rate_limit("moltbook")

        wait_time = scheduler.get_rate_limit_wait_time("moltbook")
        assert wait_time >= 0


class TestBatchProcessor:
    """Tests for BatchProcessor."""

    def test_should_process_within_batch(self):
        """Test should_process within batch size."""
        processor = BatchProcessor(batch_size=10, batch_delay=5)
        assert processor.should_process() is True

    def test_should_process_exceeds_batch(self):
        """Test should_process after batch limit."""
        processor = BatchProcessor(batch_size=2, batch_delay=5)
        processor._processed_count = 2
        processor._batch_start_time = time.time() - 1  # 1 second ago
        assert processor.should_process() is False

    def test_wait_if_needed(self):
        """Test wait_if_needed delays appropriately."""
        processor = BatchProcessor(batch_size=2, batch_delay=0.5)
        processor._processed_count = 2
        processor._batch_start_time = time.time()

        start = time.time()
        processor.wait_if_needed()
        elapsed = time.time() - start

        assert elapsed >= 0.4  # Allow some tolerance
        assert processor._processed_count == 0

    def test_record_processed(self):
        """Test recording processed items."""
        processor = BatchProcessor(batch_size=10, batch_delay=5)
        assert processor._processed_count == 0

        processor.record_processed()
        assert processor._processed_count == 1

    def test_reset(self):
        """Test resetting batch state."""
        processor = BatchProcessor(batch_size=10, batch_delay=5)
        processor.record_processed()
        processor.record_processed()
        assert processor._processed_count == 2

        processor.reset()
        assert processor._processed_count == 0
        assert processor._batch_start_time is None


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_scheduler(self):
        """Test create_scheduler function."""
        config = SyndicationConfig()
        scheduler = create_scheduler(config)
        assert isinstance(scheduler, SyndicationScheduler)

    def test_create_batch_processor(self):
        """Test create_batch_processor function."""
        config = SyndicationConfig(
            schedule=ScheduleConfig(batch_size=20, batch_delay=10)
        )
        processor = create_batch_processor(config)
        assert isinstance(processor, BatchProcessor)
        assert processor.batch_size == 20
        assert processor.batch_delay == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
