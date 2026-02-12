"""
Google Indexing API integration for BoTTube.
Fire-and-forget URL notifications alongside IndexNow.

Requires:
  - Service account JSON key (GOOGLE_SERVICE_ACCOUNT_JSON env var)
  - Web Search Indexing API enabled in Google Cloud Console
  - Service account added as owner in Google Search Console
"""

import base64
import json
import os
import threading
import time
import urllib.request

# Optional: use cryptography for RSA signing (already a Flask/werkzeug dep)
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SA_KEY_PATH = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
SCOPE = "https://www.googleapis.com/auth/indexing"

# Cached access token (thread-safe via GIL for simple reads/writes)
_token_cache = {"access_token": None, "expires_at": 0}


# ---------------------------------------------------------------------------
# JWT + Token helpers
# ---------------------------------------------------------------------------

def _b64url(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _load_service_account():
    """Load service account credentials from JSON key file."""
    if not SA_KEY_PATH or not os.path.exists(SA_KEY_PATH):
        return None
    with open(SA_KEY_PATH) as f:
        return json.load(f)


def _build_jwt(sa_email: str, private_key_pem: str) -> str:
    """Build a signed JWT for Google OAuth2 service account auth."""
    if not HAS_CRYPTO:
        return None

    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iss": sa_email,
        "scope": SCOPE,
        "aud": TOKEN_ENDPOINT,
        "iat": now,
        "exp": now + 3600,
    }

    segments = _b64url(json.dumps(header).encode()) + "." + _b64url(json.dumps(payload).encode())

    # Sign with RSA-SHA256
    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    signature = private_key.sign(segments.encode(), padding.PKCS1v15(), hashes.SHA256())

    return segments + "." + _b64url(signature)


def _get_access_token() -> str:
    """Get a valid access token, refreshing if needed. Returns None on failure."""
    global _token_cache

    # Return cached token if still valid (with 10-min buffer)
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 600:
        return _token_cache["access_token"]

    sa = _load_service_account()
    if not sa:
        return None

    jwt = _build_jwt(sa["client_email"], sa["private_key"])
    if not jwt:
        return None

    # Exchange JWT for access token
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt,
    }).encode()

    req = urllib.request.Request(TOKEN_ENDPOINT, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            token_data = json.loads(resp.read())
            _token_cache["access_token"] = token_data["access_token"]
            _token_cache["expires_at"] = time.time() + token_data.get("expires_in", 3600)
            return _token_cache["access_token"]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ping_google_indexing(url: str, action: str = "URL_UPDATED"):
    """Fire-and-forget Google Indexing API notification.

    Args:
        url: The full URL to notify Google about.
        action: "URL_UPDATED" or "URL_DELETED".
    """
    def _do_ping():
        try:
            token = _get_access_token()
            if not token:
                return

            payload = json.dumps({
                "url": url,
                "type": action,
            }).encode()

            req = urllib.request.Request(
                INDEXING_ENDPOINT,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass  # Fire-and-forget; never block on failure

    threading.Thread(target=_do_ping, daemon=True).start()


# Need urllib.parse for token exchange
import urllib.parse
