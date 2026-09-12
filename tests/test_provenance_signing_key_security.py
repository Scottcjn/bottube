import hashlib
import hmac
import os
import pytest
import bottube_server


@pytest.fixture(autouse=True)
def clean_provenance_env(monkeypatch):
    """Ensure a clean environment for each test and reset module ephemeral state."""
    monkeypatch.delenv("BOTTUBE_PROVENANCE_KEY", raising=False)
    monkeypatch.delenv("BOTTUBE_SECRET_KEY", raising=False)
    bottube_server._PROVENANCE_EPHEMERAL_KEY = None
    yield
    monkeypatch.delenv("BOTTUBE_PROVENANCE_KEY", raising=False)
    monkeypatch.delenv("BOTTUBE_SECRET_KEY", raising=False)
    bottube_server._PROVENANCE_EPHEMERAL_KEY = None


def test_provenance_signing_key_not_static_bootstrap():
    """Test 1: Default key must never be the predictable public bootstrap string."""
    key = bottube_server._provenance_signing_key()
    assert key != "bottube-provenance-bootstrap", (
        "Vulnerability regression: _provenance_signing_key() must not use "
        "hardcoded static string 'bottube-provenance-bootstrap'"
    )


def test_provenance_signing_key_ephemeral_entropy_and_stability():
    """Test 2: Key must be cryptographically random and stable within process."""
    key1 = bottube_server._provenance_signing_key()
    key2 = bottube_server._provenance_signing_key()
    assert key1 == key2, "Ephemeral key must remain stable across calls within process"
    assert len(key1) >= 64, "Ephemeral key must have at least 256 bits of hex entropy"
    int(key1, 16)  # Must be valid hex


def test_provenance_uploader_sig_prevents_static_forgery():
    """Test 3: Attacker using public bootstrap key cannot forge uploader signatures."""
    video_id = "test_vid_123"
    sha256_hash = hashlib.sha256(b"fake_video_content").hexdigest()
    agent_id = "agent_omega"
    uploaded_at = 1710000000

    # Attacker tries to forge signature using the known public static bootstrap key
    forged_msg = f"{video_id}|{sha256_hash}|{agent_id}|{int(uploaded_at)}".encode("utf-8")
    forged_sig = hmac.new(
        b"bottube-provenance-bootstrap",
        forged_msg,
        hashlib.sha256
    ).hexdigest()

    # Server generates legitimate platform signature
    legit_sig = bottube_server._provenance_uploader_sig(
        video_id, sha256_hash, agent_id, uploaded_at
    )

    assert legit_sig != forged_sig, (
        "Security finding: Public bootstrap key was able to forge platform signature!"
    )


def test_provenance_signing_key_respects_provenance_key_env(monkeypatch):
    """Test 4: Explicit BOTTUBE_PROVENANCE_KEY must take top precedence."""
    monkeypatch.setenv("BOTTUBE_PROVENANCE_KEY", "explicit-provenance-secret-12345")
    monkeypatch.setenv("BOTTUBE_SECRET_KEY", "fallback-secret-key")
    key = bottube_server._provenance_signing_key()
    assert key == "explicit-provenance-secret-12345"


def test_provenance_signing_key_respects_secret_key_fallback(monkeypatch):
    """Test 5: BOTTUBE_SECRET_KEY is used as fallback when provenance key is unset."""
    monkeypatch.delenv("BOTTUBE_PROVENANCE_KEY", raising=False)
    monkeypatch.setenv("BOTTUBE_SECRET_KEY", "app-session-secret-99999")
    key = bottube_server._provenance_signing_key()
    assert key == "app-session-secret-99999"


def test_agent_ed25519_seal_cannot_be_unsealed_with_bootstrap_secret():
    """Test 6: Sealed Ed25519 seeds cannot be recovered using public bootstrap string."""
    raw_seed = os.urandom(32)
    sealed_hex = bottube_server._agent_ed25519_seal(raw_seed)
    assert sealed_hex != "", "Sealed seed should not be empty"

    # Attacker tries to unseal using known static bootstrap key
    fake_master = hashlib.sha256(b"bottube-provenance-bootstrap").digest()
    sealed_bytes = bytes.fromhex(sealed_hex)
    attacker_unsealed = bytes(b ^ fake_master[i % len(fake_master)] for i, b in enumerate(sealed_bytes))

    assert attacker_unsealed != raw_seed, (
        "Security finding: Attacker recovered Ed25519 seed using public bootstrap string!"
    )

    # Server with proper key unseals perfectly
    server_unsealed = bottube_server._agent_ed25519_unseal(sealed_hex)
    assert server_unsealed == raw_seed, "Server must unseal valid seed correctly"
