import time
import json
import logging
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class ProviderMetrics:
    def __init__(self):
        self._lock = Lock()
        self._timing_data = defaultdict(list)
        self._success_counts = Counter()
        self._failure_counts = Counter()
        self._error_categories = defaultdict(lambda: defaultdict(int))
        self._last_reset = datetime.now()

    def record_attempt(self, provider_name: str, success: bool, duration: float,
                      error_category: Optional[str] = None):
        """Record a provider generation attempt with timing and outcome."""
        with self._lock:
            self._timing_data[provider_name].append({
                'timestamp': datetime.now(),
                'duration': duration,
                'success': success,
                'error_category': error_category
            })

            # Keep only last 100 attempts per provider to avoid memory bloat
            if len(self._timing_data[provider_name]) > 100:
                self._timing_data[provider_name] = self._timing_data[provider_name][-100:]

            if success:
                self._success_counts[provider_name] += 1
            else:
                self._failure_counts[provider_name] += 1
                if error_category:
                    self._error_categories[provider_name][error_category] += 1

    def get_provider_stats(self, provider_name: str, hours_back: int = 24) -> Dict[str, Any]:
        """Get comprehensive stats for a provider within the time window."""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)

        with self._lock:
            attempts = self._timing_data.get(provider_name, [])
            recent_attempts = [a for a in attempts if a['timestamp'] >= cutoff_time]

            if not recent_attempts:
                return {
                    'total_attempts': 0,
                    'success_rate': 0.0,
                    'avg_duration': 0.0,
                    'error_breakdown': {}
                }

            successful = [a for a in recent_attempts if a['success']]
            failed = [a for a in recent_attempts if not a['success']]

            durations = [a['duration'] for a in recent_attempts]
            error_breakdown = defaultdict(int)

            for attempt in failed:
                if attempt['error_category']:
                    error_breakdown[attempt['error_category']] += 1

            return {
                'total_attempts': len(recent_attempts),
                'successful_attempts': len(successful),
                'failed_attempts': len(failed),
                'success_rate': len(successful) / len(recent_attempts) if recent_attempts else 0.0,
                'avg_duration': sum(durations) / len(durations) if durations else 0.0,
                'min_duration': min(durations) if durations else 0.0,
                'max_duration': max(durations) if durations else 0.0,
                'error_breakdown': dict(error_breakdown)
            }

    def get_all_provider_summary(self) -> Dict[str, Dict]:
        """Get summary stats for all providers."""
        summary = {}
        with self._lock:
            all_providers = set(self._timing_data.keys()) | set(self._success_counts.keys())

            for provider in all_providers:
                summary[provider] = self.get_provider_stats(provider)

        return summary

    def log_summary(self, provider_name: Optional[str] = None):
        """Log current metrics summary."""
        if provider_name:
            stats = self.get_provider_stats(provider_name)
            logger.info(f"Provider {provider_name} metrics: "
                       f"attempts={stats['total_attempts']}, "
                       f"success_rate={stats['success_rate']:.2%}, "
                       f"avg_duration={stats['avg_duration']:.2f}s")

            if stats['error_breakdown']:
                error_summary = ', '.join([f"{k}={v}" for k, v in stats['error_breakdown'].items()])
                logger.info(f"Provider {provider_name} errors: {error_summary}")
        else:
            summary = self.get_all_provider_summary()
            for provider, stats in summary.items():
                if stats['total_attempts'] > 0:
                    logger.info(f"Provider {provider}: "
                               f"{stats['total_attempts']} attempts, "
                               f"{stats['success_rate']:.2%} success, "
                               f"{stats['avg_duration']:.2f}s avg")

    def reset_metrics(self):
        """Reset all collected metrics."""
        with self._lock:
            self._timing_data.clear()
            self._success_counts.clear()
            self._failure_counts.clear()
            self._error_categories.clear()
            self._last_reset = datetime.now()

    def export_json(self) -> str:
        """Export current metrics as JSON."""
        with self._lock:
            export_data = {
                'last_reset': self._last_reset.isoformat(),
                'export_time': datetime.now().isoformat(),
                'providers': self.get_all_provider_summary()
            }
            return json.dumps(export_data, indent=2, default=str)

class TimingContext:
    """Context manager for timing provider operations."""

    def __init__(self, metrics: ProviderMetrics, provider_name: str):
        self.metrics = metrics
        self.provider_name = provider_name
        self.start_time = None
        self.success = False
        self.error_category = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            duration = time.time() - self.start_time
            self.metrics.record_attempt(
                self.provider_name,
                self.success,
                duration,
                self.error_category
            )

    def mark_success(self):
        """Mark the operation as successful."""
        self.success = True

    def mark_failure(self, error_category: str):
        """Mark the operation as failed with error category."""
        self.success = False
        self.error_category = error_category

# Global metrics instance
_global_metrics = ProviderMetrics()

def get_metrics() -> ProviderMetrics:
    """Get the global metrics instance."""
    return _global_metrics

def time_provider_operation(provider_name: str) -> TimingContext:
    """Create a timing context for a provider operation."""
    return TimingContext(_global_metrics, provider_name)
