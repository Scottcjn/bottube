import time
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TransportConfig:
    """Configuration for transport operations."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    backoff_multiplier: float = 2.0
    timeout: int = 30


class TransportError(Exception):
    """Base exception for transport operations."""
    def __init__(self, message: str, status_code: Optional[int] = None, retry_after: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class RateLimitError(TransportError):
    """Raised when rate limited by the transport service."""
    pass


class TransportBase(ABC):
    """Base class for beacon transport implementations."""

    def __init__(self, config: Optional[TransportConfig] = None):
        self.config = config or TransportConfig()
        self.logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")

    @abstractmethod
    def send_message(self, payload: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        """Send a message through the transport.

        Returns:
            Dict containing response data and metadata
        """
        pass

    @abstractmethod
    def ping(self) -> Dict[str, Any]:
        """Test connectivity to the transport service.

        Returns:
            Dict with ping results and timing info
        """
        pass

    def send_with_retry(self, payload: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        """Send message with retry logic for transient failures."""
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                return self.send_message(payload, dry_run=dry_run)
            except RateLimitError as e:
                last_exception = e
                if attempt == self.config.max_retries:
                    break

                # Use retry_after if provided, otherwise exponential backoff
                delay = e.retry_after if e.retry_after else self._calculate_backoff_delay(attempt)
                self.logger.warning(f"Rate limited, retrying in {delay}s (attempt {attempt + 1}/{self.config.max_retries + 1})")
                time.sleep(delay)

            except TransportError as e:
                last_exception = e
                if not self._is_retryable_error(e) or attempt == self.config.max_retries:
                    break

                delay = self._calculate_backoff_delay(attempt)
                self.logger.warning(f"Transport error (status: {e.status_code}), retrying in {delay}s: {e}")
                time.sleep(delay)

            except Exception as e:
                # Non-transport errors should not be retried
                raise TransportError(f"Unexpected error during transport operation: {e}") from e

        raise last_exception or TransportError("Maximum retries exceeded")

    def ping_with_retry(self) -> Dict[str, Any]:
        """Ping with retry logic for connectivity issues."""
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                return self.ping()
            except TransportError as e:
                last_exception = e
                if not self._is_retryable_error(e) or attempt == self.config.max_retries:
                    break

                delay = self._calculate_backoff_delay(attempt)
                self.logger.warning(f"Ping failed (status: {e.status_code}), retrying in {delay}s: {e}")
                time.sleep(delay)

            except Exception as e:
                raise TransportError(f"Unexpected error during ping: {e}") from e

        raise last_exception or TransportError("Ping failed after maximum retries")

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter."""
        delay = min(
            self.config.base_delay * (self.config.backoff_multiplier ** attempt),
            self.config.max_delay
        )
        # Add small jitter to avoid thundering herd
        import random
        jitter = delay * 0.1 * random.random()
        return delay + jitter

    def _is_retryable_error(self, error: TransportError) -> bool:
        """Determine if an error should trigger a retry."""
        if isinstance(error, RateLimitError):
            return True

        # Retry on 5xx server errors and some 4xx client errors
        if error.status_code:
            if 500 <= error.status_code < 600:
                return True
            if error.status_code in [408, 429, 502, 503, 504]:
                return True

        return False

    def validate_payload(self, payload: Dict[str, Any]) -> None:
        """Validate payload structure before sending."""
        if not isinstance(payload, dict):
            raise TransportError("Payload must be a dictionary")

        required_fields = self.get_required_payload_fields()
        missing_fields = [field for field in required_fields if field not in payload]
        if missing_fields:
            raise TransportError(f"Missing required payload fields: {missing_fields}")

    def get_required_payload_fields(self) -> list:
        """Return list of required payload fields for this transport."""
        return []

    def format_error_response(self, error: Exception) -> Dict[str, Any]:
        """Format error for consistent response structure."""
        return {
            'success': False,
            'error': str(error),
            'error_type': error.__class__.__name__,
            'timestamp': time.time()
        }


class ListenerTransportBase(TransportBase):
    """Base class for transports that support listening for events."""

    @abstractmethod
    def start_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Start listening for transport events."""
        pass

    @abstractmethod
    def stop_listener(self) -> None:
        """Stop the event listener."""
        pass

    @abstractmethod
    def poll_events(self, timeout: Optional[int] = None) -> list:
        """Poll for new events without persistent listening."""
        pass
