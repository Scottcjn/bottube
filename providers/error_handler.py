import logging
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class ErrorCategory(Enum):
    AUTH = "auth"
    THROTTLED = "throttled"
    TRANSIENT = "transient"
    PERMANENT = "permanent"

class ProviderError(Exception):
    """Base exception for provider errors with classification"""

    def __init__(self, message: str, category: ErrorCategory, provider: str = None, retry_after: Optional[int] = None):
        super().__init__(message)
        self.category = category
        self.provider = provider
        self.retry_after = retry_after

class AuthError(ProviderError):
    def __init__(self, message: str, provider: str = None):
        super().__init__(message, ErrorCategory.AUTH, provider)

class ThrottledError(ProviderError):
    def __init__(self, message: str, provider: str = None, retry_after: Optional[int] = None):
        super().__init__(message, ErrorCategory.THROTTLED, provider, retry_after)

class TransientError(ProviderError):
    def __init__(self, message: str, provider: str = None):
        super().__init__(message, ErrorCategory.TRANSIENT, provider)

class PermanentError(ProviderError):
    def __init__(self, message: str, provider: str = None):
        super().__init__(message, ErrorCategory.PERMANENT, provider)

def classify_error(error: Exception, provider: str = None) -> ProviderError:
    """Classify an exception into a structured error category"""

    if isinstance(error, ProviderError):
        return error

    error_msg = str(error).lower()

    # Auth errors
    auth_keywords = ['unauthorized', 'invalid api key', 'authentication failed', 'forbidden', '401', '403']
    if any(keyword in error_msg for keyword in auth_keywords):
        return AuthError(str(error), provider)

    # Rate limiting
    throttle_keywords = ['rate limit', 'too many requests', '429', 'quota exceeded', 'throttled']
    if any(keyword in error_msg for keyword in throttle_keywords):
        retry_after = _extract_retry_after(error_msg)
        return ThrottledError(str(error), provider, retry_after)

    # Transient errors
    transient_keywords = ['timeout', 'connection', 'network', 'temporary', '502', '503', '504']
    if any(keyword in error_msg for keyword in transient_keywords):
        return TransientError(str(error), provider)

    # Default to permanent for unclassified errors
    return PermanentError(str(error), provider)

def _extract_retry_after(error_msg: str) -> Optional[int]:
    """Extract retry-after value from error message"""
    import re

    patterns = [
        r'retry after (\d+) seconds?',
        r'try again in (\d+) seconds?',
        r'wait (\d+) seconds?'
    ]

    for pattern in patterns:
        match = re.search(pattern, error_msg)
        if match:
            return int(match.group(1))

    return None

def get_retry_delay(error: ProviderError, attempt: int) -> Optional[int]:
    """Calculate retry delay based on error type and attempt number"""

    if error.category == ErrorCategory.PERMANENT:
        return None

    if error.category == ErrorCategory.AUTH:
        return None

    if error.category == ErrorCategory.THROTTLED:
        if error.retry_after:
            return error.retry_after
        return min(60 * (2 ** attempt), 300)  # Exponential backoff, max 5 min

    if error.category == ErrorCategory.TRANSIENT:
        return min(5 * (2 ** attempt), 60)  # Faster recovery for transient issues

    return None

def should_retry(error: ProviderError, attempt: int, max_attempts: int = 3) -> bool:
    """Determine if an error should trigger a retry"""

    if attempt >= max_attempts:
        return False

    if error.category in [ErrorCategory.AUTH, ErrorCategory.PERMANENT]:
        return False

    return True

def format_error_message(error: ProviderError) -> str:
    """Format error for CLI output"""

    category_labels = {
        ErrorCategory.AUTH: "Authentication Error",
        ErrorCategory.THROTTLED: "Rate Limited",
        ErrorCategory.TRANSIENT: "Temporary Error",
        ErrorCategory.PERMANENT: "Permanent Error"
    }

    label = category_labels.get(error.category, "Error")
    provider_info = f" ({error.provider})" if error.provider else ""

    if error.category == ErrorCategory.THROTTLED and error.retry_after:
        return f"{label}{provider_info}: {error} (retry after {error.retry_after}s)"

    return f"{label}{provider_info}: {error}"
