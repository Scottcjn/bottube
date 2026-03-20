class ProviderError(Exception):
    """Base class for all provider-related errors."""

    def __init__(self, message, provider_name=None, retry_after=None):
        super().__init__(message)
        self.provider_name = provider_name
        self.retry_after = retry_after
        self.user_message = message

    def should_retry(self):
        """Whether this error type supports retry logic."""
        return False

    def get_retry_delay(self):
        """Get recommended retry delay in seconds."""
        return self.retry_after or 0


class AuthenticationError(ProviderError):
    """Authentication failed - API key invalid or expired."""

    def __init__(self, message, provider_name=None):
        super().__init__(message, provider_name)
        self.user_message = f"Authentication failed for {provider_name or 'provider'}: {message}"

    def should_retry(self):
        return False


class ThrottledError(ProviderError):
    """Rate limiting or quota exceeded."""

    def __init__(self, message, provider_name=None, retry_after=None):
        super().__init__(message, provider_name, retry_after)
        delay_msg = f" (retry in {retry_after}s)" if retry_after else ""
        self.user_message = f"Rate limited by {provider_name or 'provider'}: {message}{delay_msg}"

    def should_retry(self):
        return True

    def get_retry_delay(self):
        return self.retry_after or 60


class TransientError(ProviderError):
    """Temporary failure that may succeed on retry."""

    def __init__(self, message, provider_name=None, retry_after=None):
        super().__init__(message, provider_name, retry_after)
        self.user_message = f"Temporary error from {provider_name or 'provider'}: {message}"

    def should_retry(self):
        return True

    def get_retry_delay(self):
        return self.retry_after or 5


class PermanentError(ProviderError):
    """Permanent failure that should not be retried."""

    def __init__(self, message, provider_name=None):
        super().__init__(message, provider_name)
        self.user_message = f"Permanent error from {provider_name or 'provider'}: {message}"

    def should_retry(self):
        return False


def classify_http_error(status_code, response_text="", provider_name=None):
    """Classify HTTP errors into appropriate error types."""
    if status_code == 401:
        return AuthenticationError("Invalid API key or unauthorized", provider_name)
    elif status_code == 403:
        return AuthenticationError("Access forbidden", provider_name)
    elif status_code == 429:
        return ThrottledError("Rate limit exceeded", provider_name)
    elif status_code >= 500:
        return TransientError(f"Server error ({status_code})", provider_name)
    elif status_code >= 400:
        return PermanentError(f"Client error ({status_code}): {response_text[:100]}", provider_name)
    else:
        return TransientError(f"HTTP error ({status_code})", provider_name)


def classify_network_error(error, provider_name=None):
    """Classify network-related errors."""
    error_str = str(error).lower()

    if any(term in error_str for term in ['timeout', 'timed out']):
        return TransientError("Request timeout", provider_name, retry_after=10)
    elif any(term in error_str for term in ['connection', 'network', 'dns']):
        return TransientError("Network connectivity issue", provider_name, retry_after=15)
    else:
        return TransientError(f"Network error: {error}", provider_name)
