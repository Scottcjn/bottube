"""
BoTTube SDK Exceptions

Hierarchy:
    BoTTubeError
    ├── AuthenticationError  (401)
    ├── NotFoundError        (404)
    ├── RateLimitError       (429)
    └── ValidationError      (400)
"""

from bottube_sdk.client import (
    BoTTubeError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)

__all__ = [
    "BoTTubeError",
    "AuthenticationError",
    "NotFoundError",
    "RateLimitError",
    "ValidationError",
]
