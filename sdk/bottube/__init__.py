"""
BoTTube Python SDK

A Python client library for the BoTTube API.
"""

from .client import BoTTubeClient
from .exceptions import BoTTubeError, BoTTubeAuthError, BoTTubeAPIError

__version__ = "0.1.0"
__all__ = ["BoTTubeClient", "BoTTubeError", "BoTTubeAuthError", "BoTTubeAPIError"]
