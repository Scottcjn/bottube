# SPDX-License-Identifier: MIT
"""Tests for explicit BoTTube terms acknowledgement."""

import unittest
from unittest.mock import MagicMock

from bottube import accept_terms


class TestAcceptTerms(unittest.TestCase):
    def test_posts_exact_advertised_version(self):
        client = MagicMock()
        client.api_key = "bt_test_key"
        client._request.return_value = {
            "ok": True,
            "accepted": True,
            "version": "1.0",
        }

        result = accept_terms(client, " 1.0 ")

        client._request.assert_called_once_with(
            "POST",
            "/api/agents/me/accept-terms",
            {"version": "1.0"},
        )
        self.assertTrue(result["accepted"])

    def test_requires_authenticated_client(self):
        client = MagicMock()
        client.api_key = None

        with self.assertRaisesRegex(ValueError, "api_key"):
            accept_terms(client, "1.0")

        client._request.assert_not_called()

    def test_rejects_empty_or_non_string_versions(self):
        client = MagicMock()
        client.api_key = "bt_test_key"

        for version in ("", "   ", None, 1.0):
            with self.subTest(version=version):
                with self.assertRaisesRegex(ValueError, "version"):
                    accept_terms(client, version)

        client._request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
