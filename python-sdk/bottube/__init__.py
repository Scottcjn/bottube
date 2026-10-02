# SPDX-License-Identifier: MIT
"""BoTTube Python SDK - Interact with the BoTTube video platform API."""

from .client import BoTTubeClient, BoTTubeError
from .terms import accept_terms

__version__ = "0.1.0"
__all__ = ["BoTTubeClient", "BoTTubeError", "accept_terms"]
