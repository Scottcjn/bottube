"""
BoTTube Provider Adapters
Standardized interfaces for AI providers with error handling and instrumentation.
"""
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union
from enum import Enum
from dataclasses import dataclass
import requests
from threading import Lock
import json


class ErrorCategory(Enum):
    """Categorize provider errors for proper handling."""
    AUTH = "auth"          # API key issues, permissions
    THROTTLED = "throttled"  # Rate limiting
    TRANSIENT = "transient"  # Network, timeouts, temporary server issues
    PERMANENT = "permanent"  # Invalid requests, content violations


@dataclass
class ProviderMetrics:
    """Track provider performance metrics."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration: float = 0.0
    avg_duration: float = 0.0

    def record_success(self, duration: float):
        self.total_requests += 1
        self.successful_requests += 1
        self.total_duration += duration
        self.avg_duration = self.total_duration / self.total_requests

    def record_failure(self, duration: float):
        self.total_requests += 1
        self.failed_requests += 1
        self.total_duration += duration
        self.avg_duration = self.total_duration / self.total_requests


class ProviderError(Exception):
    """Base exception for provider errors."""
    def __init__(self, message: str, category: ErrorCategory, retryable: bool = False):
        super().__init__(message)
        self.category = category
        self.retryable = retryable


class BaseProviderAdapter(ABC):
    """Base class for all provider adapters."""

    def __init__(self, api_key: str, base_url: str = None):
        self.api_key = api_key
        self.base_url = base_url
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
        self.metrics = ProviderMetrics()
        self._session_lock = Lock()
        self._session = None

    @property
    def session(self) -> requests.Session:
        """Thread-safe session creation with connection pooling."""
        if self._session is None:
            with self._session_lock:
                if self._session is None:
                    self._session = requests.Session()
                    # Connection pooling configuration
                    adapter = requests.adapters.HTTPAdapter(
                        pool_connections=10,
                        pool_maxsize=20,
                        max_retries=0  # We handle retries at adapter level
                    )
                    self._session.mount('http://', adapter)
                    self._session.mount('https://', adapter)
        return self._session

    @abstractmethod
    def generate_content(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate content using the provider."""
        pass

    @abstractmethod
    def classify_error(self, error: Exception) -> ErrorCategory:
        """Classify error into appropriate category."""
        pass

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with timing instrumentation."""
        start_time = time.time()
        try:
            response = self.session.request(method, url, **kwargs)
            duration = time.time() - start_time

            if response.status_code >= 400:
                self.metrics.record_failure(duration)
                self._handle_http_error(response)
            else:
                self.metrics.record_success(duration)

            self.logger.debug(f"Request to {url} took {duration:.3f}s")
            return response

        except Exception as e:
            duration = time.time() - start_time
            self.metrics.record_failure(duration)
            self.logger.error(f"Request failed after {duration:.3f}s: {str(e)}")
            raise

    def _handle_http_error(self, response: requests.Response):
        """Handle HTTP error responses."""
        error_data = {}
        try:
            error_data = response.json()
        except (ValueError, json.JSONDecodeError):
            error_data = {"error": response.text}

        if response.status_code == 401:
            raise ProviderError(
                f"Authentication failed: {error_data.get('error', 'Invalid API key')}",
                ErrorCategory.AUTH
            )
        elif response.status_code == 429:
            raise ProviderError(
                f"Rate limit exceeded: {error_data.get('error', 'Too many requests')}",
                ErrorCategory.THROTTLED,
                retryable=True
            )
        elif response.status_code >= 500:
            raise ProviderError(
                f"Server error: {error_data.get('error', 'Internal server error')}",
                ErrorCategory.TRANSIENT,
                retryable=True
            )
        elif response.status_code == 400:
            raise ProviderError(
                f"Bad request: {error_data.get('error', 'Invalid request')}",
                ErrorCategory.PERMANENT
            )
        else:
            raise ProviderError(
                f"HTTP {response.status_code}: {error_data.get('error', 'Unknown error')}",
                ErrorCategory.TRANSIENT,
                retryable=True
            )


class GrokAdapter(BaseProviderAdapter):
    """Adapter for Grok AI provider."""

    def __init__(self, api_key: str):
        super().__init__(api_key, "https://api.x.ai/v1")
        self.model = "grok-beta"

    def generate_content(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate text content using Grok."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "model": self.model,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 1024),
            "stream": False
        }

        self.logger.info(f"Generating content with Grok (model: {self.model})")

        try:
            response = self._make_request(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )

            result = response.json()

            if "choices" not in result or not result["choices"]:
                raise ProviderError(
                    "No content generated by Grok",
                    ErrorCategory.PERMANENT
                )

            content = result["choices"][0]["message"]["content"]

            return {
                "content": content,
                "provider": "grok",
                "model": self.model,
                "usage": result.get("usage", {}),
                "finish_reason": result["choices"][0].get("finish_reason")
            }

        except ProviderError:
            raise
        except requests.exceptions.Timeout:
            raise ProviderError(
                "Request to Grok timed out",
                ErrorCategory.TRANSIENT,
                retryable=True
            )
        except requests.exceptions.ConnectionError as e:
            raise ProviderError(
                f"Connection error to Grok: {str(e)}",
                ErrorCategory.TRANSIENT,
                retryable=True
            )
        except Exception as e:
            category = self.classify_error(e)
            raise ProviderError(f"Grok generation failed: {str(e)}", category)

    def classify_error(self, error: Exception) -> ErrorCategory:
        """Classify Grok-specific errors."""
        error_str = str(error).lower()

        if "api key" in error_str or "unauthorized" in error_str:
            return ErrorCategory.AUTH
        elif "rate limit" in error_str or "quota" in error_str:
            return ErrorCategory.THROTTLED
        elif "timeout" in error_str or "connection" in error_str:
            return ErrorCategory.TRANSIENT
        elif "content policy" in error_str or "violation" in error_str:
            return ErrorCategory.PERMANENT
        else:
            return ErrorCategory.TRANSIENT


class RunwayAdapter(BaseProviderAdapter):
    """Adapter for Runway ML provider."""

    def __init__(self, api_key: str):
        super().__init__(api_key, "https://api.runwayml.com/v1")
        self.default_model = "gen3a_turbo"

    def generate_content(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate video content using Runway."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        model = kwargs.get("model", self.default_model)
        duration = kwargs.get("duration", 5)  # seconds
        resolution = kwargs.get("resolution", "1280x768")

        payload = {
            "model": model,
            "prompt": prompt,
            "duration": duration,
            "resolution": resolution,
            "seed": kwargs.get("seed"),
            "watermark": kwargs.get("watermark", False)
        }

        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}

        self.logger.info(f"Generating video with Runway (model: {model}, duration: {duration}s)")

        try:
            # Submit generation request
            response = self._make_request(
                "POST",
                f"{self.base_url}/image_to_video",
                headers=headers,
                json=payload,
                timeout=60
            )

            result = response.json()
            task_id = result.get("id")

            if not task_id:
                raise ProviderError(
                    "No task ID returned from Runway",
                    ErrorCategory.PERMANENT
                )

            # Poll for completion
            video_url = self._poll_generation_status(task_id, headers)

            return {
                "content": video_url,
                "provider": "runway",
                "model": model,
                "task_id": task_id,
                "duration": duration,
                "resolution": resolution,
                "type": "video"
            }

        except ProviderError:
            raise
        except requests.exceptions.Timeout:
            raise ProviderError(
                "Request to Runway timed out",
                ErrorCategory.TRANSIENT,
                retryable=True
            )
        except requests.exceptions.ConnectionError as e:
            raise ProviderError(
                f"Connection error to Runway: {str(e)}",
                ErrorCategory.TRANSIENT,
                retryable=True
            )
        except Exception as e:
            category = self.classify_error(e)
            raise ProviderError(f"Runway generation failed: {str(e)}", category)

    def _poll_generation_status(self, task_id: str, headers: Dict[str, str]) -> str:
        """Poll generation status until completion."""
        max_polls = 30
        poll_interval = 10  # seconds

        for attempt in range(max_polls):
            try:
                response = self._make_request(
                    "GET",
                    f"{self.base_url}/tasks/{task_id}",
                    headers=headers,
                    timeout=30
                )

                result = response.json()
                status = result.get("status")

                if status == "SUCCEEDED":
                    artifacts = result.get("output", [])
                    if artifacts and len(artifacts) > 0:
                        return artifacts[0].get("url")
                    else:
                        raise ProviderError(
                            "No video URL in completed task",
                            ErrorCategory.PERMANENT
                        )
                elif status == "FAILED":
                    error_msg = result.get("failure_reason", "Unknown failure")
                    raise ProviderError(
                        f"Runway generation failed: {error_msg}",
                        ErrorCategory.PERMANENT
                    )
                elif status in ["PENDING", "RUNNING"]:
                    self.logger.debug(f"Task {task_id} status: {status}, polling again in {poll_interval}s")
                    time.sleep(poll_interval)
                    continue
                else:
                    raise ProviderError(
                        f"Unknown task status: {status}",
                        ErrorCategory.PERMANENT
                    )

            except ProviderError:
                raise
            except Exception as e:
                self.logger.warning(f"Polling attempt {attempt + 1} failed: {str(e)}")
                if attempt == max_polls - 1:
                    raise ProviderError(
                        f"Failed to poll task status: {str(e)}",
                        ErrorCategory.TRANSIENT,
                        retryable=True
                    )
                time.sleep(poll_interval)

        raise ProviderError(
            f"Task {task_id} did not complete within {max_polls * poll_interval} seconds",
            ErrorCategory.TRANSIENT,
            retryable=True
        )

    def classify_error(self, error: Exception) -> ErrorCategory:
        """Classify Runway-specific errors."""
        error_str = str(error).lower()

        if "api key" in error_str or "unauthorized" in error_str:
            return ErrorCategory.AUTH
        elif "rate limit" in error_str or "quota" in error_str:
            return ErrorCategory.THROTTLED
        elif "timeout" in error_str or "connection" in error_str:
            return ErrorCategory.TRANSIENT
        elif "content" in error_str or "inappropriate" in error_str:
            return ErrorCategory.PERMANENT
        else:
            return ErrorCategory.TRANSIENT


def create_adapter(provider_name: str, api_key: str) -> BaseProviderAdapter:
    """Factory function to create provider adapters."""
    adapters = {
        "grok": GrokAdapter,
        "runway": RunwayAdapter
    }

    if provider_name not in adapters:
        raise ValueError(f"Unknown provider: {provider_name}")

    return adapters[provider_name](api_key)
