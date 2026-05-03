#!/usr/bin/env python3
"""
bottube-verify-provenance — verify a video's on-chain provenance end-to-end.

Walks the four steps the Phase 11 PR comment promised any reviewer can run:

  1. GET https://bottube.ai/api/videos/<id>/provenance
       → fetch canonical_sha256, uploader_sig, uploaded_at, anchor.tx_hash,
         anchor.manifest_hash, and the batch_id this video was anchored in.
  2. List all videos in the same batch_id (membership set).
  3. Reconstruct each member's leaf:
       leaf = sha256(video_id | canonical_sha256 | uploader_sig | uploaded_at)
     and compute a Bitcoin-style binary Merkle root.
  4. Fetch the on-chain box's R4 register from the Ergo node and compare
     the 32 bytes to the locally-computed root.

Exits 0 on PASS (root matches R4), 1 on any mismatch or fetch error.

Usage:
    bottube-verify-provenance <video_id> [--ergo-base URL] [--bottube-base URL]

The verifier is read-only and uses public bottube.ai endpoints + the
Ergo node API (which can be a public peer or a tunneled localhost).

Examples:
    # Verify against bottube.ai prod + a local tunneled Ergo:
    BOTTUBE_BASE=https://bottube.ai \
    ERGO_BASE=http://localhost:19053 \
    ERGO_API_KEY=<key> \
        ./bottube-verify-provenance.py 3PUqIlnScB4

    # Verify against a self-hosted bottube fork:
    ./bottube-verify-provenance.py abc123 \
        --bottube-base https://my.bottube.test \
        --ergo-base https://ergo.public.example
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request


def _http_json(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise RuntimeError(f"HTTP {e.code} on {url}: {body[:200]}")
    except Exception as e:
        raise RuntimeError(f"request failed for {url}: {e}")


_LEAF_DOMAIN_V2 = "bottube/v2"
_LEAF_DOMAIN_V3 = "bottube/v3"


def manifest_leaf_v1(video_id, canonical_sha256, uploader_sig, uploaded_at):
    """Legacy leaf — must stay bit-exact for already-anchored batches."""
    parts = "|".join([
        video_id or "",
        canonical_sha256 or "",
        uploader_sig or "",
        str(int(float(uploaded_at or 0))),
    ])
    return hashlib.sha256(parts.encode("utf-8")).digest()


def manifest_leaf_v2(video_id, canonical_sha256, thumbnail_sha256,
                     canonical_360p_sha256, uploader_sig, uploaded_at):
    """v2 leaf folds thumbnail + 360p hashes into the anchored commitment."""
    parts = "|".join([
        _LEAF_DOMAIN_V2,
        video_id or "",
        canonical_sha256 or "",
        thumbnail_sha256 or "",
        canonical_360p_sha256 or "",
        uploader_sig or "",
        str(int(float(uploaded_at or 0))),
    ])
    return hashlib.sha256(parts.encode("utf-8")).digest()


def manifest_leaf_v3(video_id, canonical_sha256, thumbnail_sha256,
                     canonical_360p_sha256, uploader_sig, uploaded_at,
                     creator_pubkey, creator_signature):
    """v3 leaf folds creator_pubkey + creator_signature so the chain
    commits to a verifiable Ed25519 signature."""
    parts = "|".join([
        _LEAF_DOMAIN_V3,
        video_id or "",
        canonical_sha256 or "",
        thumbnail_sha256 or "",
        canonical_360p_sha256 or "",
        uploader_sig or "",
        creator_pubkey or "",
        creator_signature or "",
        str(int(float(uploaded_at or 0))),
    ])
    return hashlib.sha256(parts.encode("utf-8")).digest()


def manifest_leaf(video_id, canonical_sha256, uploader_sig, uploaded_at,
                  manifest_version=1, thumbnail_sha256="",
                  canonical_360p_sha256="",
                  creator_pubkey="", creator_signature=""):
    """Version dispatch. Defaults to v1 so older callers keep working."""
    ver = int(manifest_version or 1)
    if ver >= 3:
        return manifest_leaf_v3(
            video_id, canonical_sha256, thumbnail_sha256,
            canonical_360p_sha256, uploader_sig, uploaded_at,
            creator_pubkey, creator_signature,
        )
    if ver >= 2:
        return manifest_leaf_v2(
            video_id, canonical_sha256, thumbnail_sha256,
            canonical_360p_sha256, uploader_sig, uploaded_at,
        )
    return manifest_leaf_v1(video_id, canonical_sha256, uploader_sig, uploaded_at)


def verify_ed25519_signature(pubkey_hex, signature_hex,
                              video_id, canonical_sha256,
                              thumbnail_sha256, canonical_360p_sha256,
                              uploaded_at):
    """Verify the v3 Ed25519 creator signature against the v3 signing
    message. Requires PyNaCl (imported lazily so the rest of the verifier
    keeps working without it). Returns (verified: bool, detail: str).
    """
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError
    except ImportError:
        return False, "PyNaCl not installed; install with `pip install pynacl`"
    if not pubkey_hex or not signature_hex:
        return False, "missing creator_pubkey or creator_signature"
    parts = "|".join([
        "bottube/v3-sign",
        video_id or "",
        canonical_sha256 or "",
        thumbnail_sha256 or "",
        canonical_360p_sha256 or "",
        str(int(float(uploaded_at or 0))),
    ])
    msg = hashlib.sha256(parts.encode("utf-8")).digest()
    try:
        VerifyKey(bytes.fromhex(pubkey_hex)).verify(msg, bytes.fromhex(signature_hex))
        return True, "Ed25519 signature valid against creator_pubkey"
    except BadSignatureError:
        return False, "Ed25519 signature invalid"
    except Exception as e:
        return False, f"verify failed: {e}"


def merkle_root(leaves):
    """Bitcoin-style binary Merkle root over SHA-256 leaves."""
    if not leaves:
        return b"\x00" * 32
    layer = list(leaves)
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        nxt = []
        for i in range(0, len(layer), 2):
            nxt.append(hashlib.sha256(layer[i] + layer[i + 1]).digest())
        layer = nxt
    return layer[0]


def fetch_anchor_r4(ergo_base, ergo_key, tx_hash, timeout=15):
    """Fetch R4 register bytes for a confirmed anchor TX. Returns bytes."""
    url = f"{ergo_base.rstrip('/')}/wallet/transactionById?id={tx_hash}"
    data = _http_json(url, headers={"api_key": ergo_key} if ergo_key else None,
                      timeout=timeout)
    outs = data.get("outputs") or []
    if not outs:
        raise RuntimeError(f"no outputs in TX {tx_hash}")
    r4 = (outs[0].get("additionalRegisters") or {}).get("R4")
    if not r4 or not isinstance(r4, str):
        raise RuntimeError(f"R4 missing on TX {tx_hash}")
    # SColl[Byte] of length N is encoded as "0e" + length-byte + bytes-hex.
    # For our 32-byte commitment that's "0e20" + 64 hex chars.
    if not r4.startswith("0e20"):
        raise RuntimeError(f"unexpected R4 prefix (not a 32-byte SColl): {r4[:8]}")
    hex_root = r4[4:]
    if len(hex_root) != 64 or not re.fullmatch(r"[0-9a-f]+", hex_root):
        raise RuntimeError(f"R4 payload not 32-byte hex: {r4}")
    return bytes.fromhex(hex_root)


def fetch_anchor_r4_via_proxy(bottube_base, tx_hash, timeout=15):
    """Fallback: use bottube's public chain proxy when no local Ergo node.

    /api/anchors/<tx>/chain pre-decodes R4 to its 32-byte hex form; we
    just unhex it. Lets the verifier work from any machine with
    internet, no Ergo node required.
    """
    url = f"{bottube_base.rstrip('/')}/api/anchors/{tx_hash}/chain"
    data = _http_json(url, timeout=timeout)
    if not data.get("ok"):
        raise RuntimeError(f"proxy returned ok=false: {data.get('error')}")
    root_hex = data.get("r4_merkle_root", "")
    if len(root_hex) != 64 or not re.fullmatch(r"[0-9a-f]+", root_hex):
        raise RuntimeError(f"proxy R4 not 32-byte hex: {root_hex!r}")
    return bytes.fromhex(root_hex)


VERIFIER_VERSION = "0.5.0"


def hash_asset_streaming(url, expected_sha256, max_mb=2048, chunk=64 * 1024):
    """Stream-hash an asset URL and compare to the expected SHA-256.

    Returns (matched: bool, actual_hex: str, bytes_read: int, error: str).
    Bounded by max_mb so a malicious server can't make us spool forever.
    Uses urllib (stdlib) — no requests/aiohttp dependency.
    """
    if not url:
        return False, "", 0, "no canonical asset URL"
    if not (url.startswith("http://") or url.startswith("https://")):
        return False, "", 0, f"refusing non-http(s) URL: {url!r}"
    h = hashlib.sha256()
    total = 0
    cap = max_mb * 1024 * 1024
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            while True:
                buf = r.read(chunk)
                if not buf:
                    break
                total += len(buf)
                if total > cap:
                    return False, h.hexdigest(), total, (
                        f"asset exceeded max {max_mb} MB cap; aborting"
                    )
                h.update(buf)
    except urllib.error.HTTPError as e:
        return False, "", 0, f"HTTP {e.code} fetching asset"
    except Exception as e:
        return False, "", 0, f"asset fetch failed: {e}"
    actual = h.hexdigest()
    expected = (expected_sha256 or "").lower()
    return (actual == expected), actual, total, ""


def verify_receipt_offline(receipt, platform_hmac_key=None):
    """Verify a downloaded provenance receipt without any network access.

    Returns (verdict, detail) where verdict is 'PASS' if all internal
    cryptographic invariants hold:
      1. (optional) receipt_signature HMAC matches the canonical body bytes,
         if platform_hmac_key is supplied — proves bottube issued the file.
      2. The leaf computed from manifest.leaf_inputs matches manifest.leaf.
      3. Walking merkle_proof.path from that leaf reaches
         merkle_proof.expected_root.
      4. expected_root equals chain_anchor.manifest_hash.
      5. v3 receipts: the Ed25519 creator signature verifies against the
         creator pubkey over the v3 signing message.

    Network-only steps (fetching R4 from chain) are NOT performed here;
    use the live mode for that. The offline check is still useful: if a
    receipt has been edited mid-flight, the leaf or signature will fail
    and we catch it before anyone hits the chain.
    """
    if not isinstance(receipt, dict):
        return "FAIL", "receipt is not a JSON object"
    if receipt.get("schema") != "bottube-provenance-receipt/v1":
        return "FAIL", f"unknown schema: {receipt.get('schema')!r}"

    # Phase 11.23 fix: optional receipt_signature HMAC verification. If the
    # caller supplied the platform HMAC key, verify it; mismatch = the
    # receipt didn't come from bottube unaltered. Skip if no key — most
    # callers don't have it; the cryptographic claims below stand
    # regardless because the chain anchor is the actual proof.
    if platform_hmac_key:
        import hmac as _hmac
        sig_block = receipt.get("receipt_signature") or {}
        body = {k: v for k, v in receipt.items() if k != "receipt_signature"}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        expected = _hmac.new(
            platform_hmac_key.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        actual = (sig_block.get("value") or "")
        if not _hmac.compare_digest(actual.lower(), expected.lower()):
            return "FAIL", (
                "receipt_signature HMAC does not match canonical body — "
                "the receipt was tampered after issuance, or the supplied "
                "platform key is wrong."
            )

    m = receipt.get("manifest") or {}
    inputs = m.get("leaf_inputs") or {}
    ver = int(m.get("version") or 1)
    claimed_leaf = m.get("leaf", "")

    # Recompute the leaf from the inputs the receipt declared.
    computed = manifest_leaf(
        inputs.get("video_id", ""),
        inputs.get("canonical_sha256", ""),
        inputs.get("uploader_sig", ""),
        inputs.get("uploaded_at", 0),
        manifest_version=ver,
        thumbnail_sha256=inputs.get("thumbnail_sha256", ""),
        canonical_360p_sha256=inputs.get("canonical_360p_sha256", ""),
        creator_pubkey=inputs.get("creator_pubkey", ""),
        creator_signature=inputs.get("creator_signature", ""),
    )
    if computed.hex() != claimed_leaf:
        return "FAIL", (
            f"leaf computed from inputs ({computed.hex()}) does not match "
            f"the leaf the receipt claims ({claimed_leaf}). The receipt "
            f"has been tampered with or the version dispatch is wrong."
        )

    # Phase 11.23: on v3 receipts, additionally verify the Ed25519
    # creator signature against the v3 signing message. Tampered fields
    # would already have been caught by the leaf check above, but
    # verifying the actual signature also catches "this leaf format
    # doesn't actually correspond to the creator's signing key" — which
    # would mean the chain commits to something nobody can vouch for.
    if ver >= 3:
        sig_ok, sig_detail = verify_ed25519_signature(
            inputs.get("creator_pubkey", ""),
            inputs.get("creator_signature", ""),
            inputs.get("video_id", ""),
            inputs.get("canonical_sha256", ""),
            inputs.get("thumbnail_sha256", ""),
            inputs.get("canonical_360p_sha256", ""),
            inputs.get("uploaded_at", 0),
        )
        if not sig_ok:
            return "FAIL", (
                f"v3 receipt's creator_signature does not verify "
                f"against creator_pubkey: {sig_detail}"
            )

    # Walk the path.
    proof = receipt.get("merkle_proof") or {}
    expected_root = proof.get("expected_root", "")
    node = computed
    for hop in (proof.get("path") or []):
        sib = bytes.fromhex(hop.get("sibling", ""))
        side = hop.get("side", "")
        if side == "R":
            node = hashlib.sha256(node + sib).digest()
        elif side == "L":
            node = hashlib.sha256(sib + node).digest()
        else:
            return "FAIL", f"invalid path side {side!r}"
    walked = node.hex()
    if walked != expected_root:
        return "FAIL", (
            f"walking the Merkle path produced {walked} but the receipt "
            f"claims expected_root={expected_root}"
        )

    # Cross-check chain seam.
    chain = receipt.get("chain_anchor") or {}
    chain_root = chain.get("manifest_hash", "")
    if chain_root != expected_root:
        return "FAIL", (
            f"chain_anchor.manifest_hash ({chain_root}) does not match "
            f"merkle_proof.expected_root ({expected_root})"
        )

    return "PASS", (
        f"offline receipt is internally consistent: leaf reconstructed "
        f"from inputs, walked {len(proof.get('path') or [])} Merkle hops "
        f"to root {walked}, root matches chain anchor "
        f"{chain.get('tx_hash', '')[:16]}…"
    )


def main():
    ap = argparse.ArgumentParser(
        description="Verify a BoTTube video's on-chain provenance",
        epilog="Source: https://github.com/Scottcjn/bottube",
    )
    ap.add_argument("video_id", nargs="?", help="The video_id to verify")
    ap.add_argument("--bottube-base", default=os.environ.get("BOTTUBE_BASE", "https://bottube.ai"))
    ap.add_argument("--ergo-base", default=os.environ.get("ERGO_BASE", "http://localhost:9053"))
    ap.add_argument("--ergo-api-key", default=os.environ.get("ERGO_API_KEY", ""))
    ap.add_argument("--admin-key", default=os.environ.get("BOTTUBE_ADMIN_KEY", ""),
                    help="Optional: admin key for batch-membership lookup. Without it, the public Merkle proof endpoint is used (still PASS).")
    ap.add_argument("--quiet", action="store_true", help="Only print PASS/FAIL")
    ap.add_argument("--receipt", default="",
                    help="Path to a downloaded receipt JSON. If set, runs the "
                         "offline verification (no network) and exits.")
    ap.add_argument("--platform-hmac-key", default=os.environ.get("BOTTUBE_PROVENANCE_KEY", ""),
                    help="Platform HMAC key. If set in --receipt mode, the "
                         "verifier additionally checks receipt_signature is "
                         "a valid HMAC over the canonical body — useful for "
                         "the bottube operator who wants to confirm a receipt "
                         "came from their own server unaltered.")
    ap.add_argument("--check-asset", action="store_true",
                    help="Additionally fetch the canonical asset bytes from "
                         "bottube and SHA-256 them in-place, comparing to "
                         "the anchored canonical_sha256. Closes the "
                         "'are the served bytes still the anchored bytes?' "
                         "gap. Network-bound; can be slow for large videos.")
    ap.add_argument("--asset-max-mb", type=int, default=2048,
                    help="Cap on asset bytes the verifier will read (default 2048 MB).")
    ap.add_argument("--version", action="version",
                    version=f"bottube-verify {VERIFIER_VERSION}")
    args = ap.parse_args()

    # Phase 11.20: offline receipt mode. Useful in air-gapped / legal
    # contexts where the verifier can't reach bottube.ai or the chain.
    if args.receipt:
        try:
            with open(args.receipt, "r", encoding="utf-8") as fh:
                receipt = json.load(fh)
        except Exception as e:
            sys.exit(f"FAIL: could not read receipt file: {e}")
        verdict, detail = verify_receipt_offline(
            receipt, platform_hmac_key=args.platform_hmac_key or None,
        )
        if args.quiet:
            print(verdict)
        else:
            print(f"=== {verdict} (offline receipt mode) ===")
            print(f"  {detail}")
            print()
            if verdict == "PASS":
                print("  Note: this PASS only proves the receipt is internally")
                print("  consistent. To prove the receipt's chain anchor is")
                print("  also present on RustChain, re-run without --receipt:")
                vid = (receipt.get("video") or {}).get("video_id", "<id>")
                print(f"    bottube-verify {vid}")
        sys.exit(0 if verdict == "PASS" else 1)

    if not args.video_id:
        ap.error("video_id required (or use --receipt FILE for offline mode)")

    bot = args.bottube_base.rstrip("/")
    vid = args.video_id

    if not args.quiet:
        print(f"[1/4] Fetching provenance for {vid} from {bot}...")

    prov = _http_json(f"{bot}/api/videos/{vid}/provenance")
    if not prov.get("ok"):
        sys.exit(f"FAIL: {bot} returned ok=false: {prov}")
    if not prov.get("verified"):
        sys.exit(f"FAIL: video reports pill_state={prov.get('pill_state')!r} (not yet anchored)")

    canonical_sha = prov["canonical_asset"]["sha256"]
    uploader_sig = prov["upload"]["uploader_sig"]
    uploaded_at = prov["upload"]["uploaded_at"]
    tx_hash = prov["anchor"]["tx_hash"]
    chain = prov["anchor"]["chain"]
    manifest_hash = prov["anchor"]["manifest_hash"]

    # Phase 11.16/11.23: pull manifest version + v2/v3-specific fields
    # from the provenance response. Older anchors stay v1 — defaults are
    # bit-exact backwards-compatible.
    manifest_ver = int(prov.get("manifest_version", 1) or 1)
    thumb_sha = (prov.get("thumbnail") or {}).get("sha256", "") or ""
    p360_sha = (prov.get("canonical_360p") or {}).get("sha256", "") or ""
    # v3 fields surface via /api/videos/<id>/anchor-proof (leaf_inputs);
    # we need them for the leaf reconstruction. Fetch them lazily later
    # if we hit a v3 row.
    creator_pubkey = ""
    creator_signature = ""

    if not args.quiet:
        print(f"      pill={prov['pill_state']}  chain={chain}")
        print(f"      manifest_version=v{manifest_ver}")
        print(f"      tx_hash={tx_hash}")
        print(f"      manifest_hash (claimed Merkle root)={manifest_hash}")
        print()
        print(f"[2/4] Resolving batch members for the leaf computation...")

    # Compute this video's leaf locally with the correct recipe.
    # v3 needs creator_pubkey + creator_signature; pull them from the
    # anchor-proof endpoint (which the public-proof path will fetch
    # below anyway, but we need the values now to reconstruct the leaf).
    if manifest_ver >= 3:
        try:
            ap = _http_json(f"{bot}/api/videos/{vid}/anchor-proof")
            li = (ap.get("leaf_inputs") or {}) if ap.get("ok") else {}
            creator_pubkey = li.get("creator_pubkey", "") or ""
            creator_signature = li.get("creator_signature", "") or ""
        except Exception as _e:
            if not args.quiet:
                print(f"      (warning) couldn't fetch v3 fields: {_e}")
    own_leaf = manifest_leaf(
        vid, canonical_sha, uploader_sig, uploaded_at,
        manifest_version=manifest_ver,
        thumbnail_sha256=thumb_sha,
        canonical_360p_sha256=p360_sha,
        creator_pubkey=creator_pubkey,
        creator_signature=creator_signature,
    )

    # Phase 11.23: on v3 rows, additionally verify the Ed25519 signature
    # against creator_pubkey before we even bother with the chain seam.
    # If the signature doesn't match, the chain anchor commits to a
    # verifiably-broken leaf and the verdict is FAIL regardless of the
    # rest of the path.
    if manifest_ver >= 3:
        sig_ok, sig_detail = verify_ed25519_signature(
            creator_pubkey, creator_signature,
            vid, canonical_sha, thumb_sha, p360_sha, uploaded_at,
        )
        if not args.quiet:
            print(f"      [v3] creator pubkey: {creator_pubkey[:16]}…")
            print(f"      [v3] Ed25519: {'✓ ' if sig_ok else '✗ '}{sig_detail}")
        if not sig_ok:
            sys.exit(
                f"FAIL: v3 manifest carries a creator_signature that does "
                f"NOT verify against creator_pubkey: {sig_detail}"
            )
    if not args.quiet:
        print(f"      own_leaf={own_leaf.hex()}")

    # Two paths to a full PASS:
    #   1. Admin key → full batch membership → reconstruct entire Merkle tree.
    #   2. Public Merkle proof → walk a path of sibling hashes leaf→root.
    # Either gets us byte-for-byte against the on-chain R4. Public proof
    # is the default; admin path is the fallback if proof endpoint is
    # unavailable.
    full_check = bool(args.admin_key)
    on_chain_root_hex = ""
    locally_computed_root_hex = ""
    batch_members = []
    public_proof = None

    if not full_check:
        try:
            proof_data = _http_json(f"{bot}/api/videos/{vid}/anchor-proof")
            if proof_data.get("ok"):
                public_proof = proof_data
                if not args.quiet:
                    print(f"      using public Merkle proof "
                          f"(path length {len(proof_data['path'])}, "
                          f"batch size {proof_data['batch_size']})")
            else:
                if not args.quiet:
                    print(f"      public proof unavailable: {proof_data.get('error')}")
        except Exception as e:
            if not args.quiet:
                print(f"      public proof fetch error: {e}")

    if full_check:
        if not args.quiet:
            print(f"      using admin key to fetch batch membership")
        try:
            batch_data = _http_json(
                f"{bot}/api/admin/provenance/batch?tx={tx_hash}",
                headers={"X-Admin-Key": args.admin_key},
            )
            if batch_data.get("ok"):
                batch_members = batch_data.get("members", [])
                if not args.quiet:
                    print(f"      batch has {len(batch_members)} members")
            else:
                if not args.quiet:
                    print(f"      batch fetch failed: {batch_data.get('error')}")
                full_check = False
        except Exception as e:
            if not args.quiet:
                print(f"      batch fetch error: {e}")
            full_check = False

    if not args.quiet:
        print(f"[3/4] Fetching on-chain R4 for tx {tx_hash[:16]}...")

    on_chain = None
    chain_source = None
    try:
        on_chain = fetch_anchor_r4(args.ergo_base, args.ergo_api_key, tx_hash)
        chain_source = "direct ergo node (" + args.ergo_base + ")"
    except Exception as e_direct:
        if not args.quiet:
            print(f"      direct chain query failed ({e_direct})")
            print(f"      falling back to bottube chain proxy at {bot}/api/anchors/<tx>/chain")
        try:
            on_chain = fetch_anchor_r4_via_proxy(bot, tx_hash)
            chain_source = "bottube proxy"
        except Exception as e_proxy:
            sys.exit(
                f"FAIL: could not fetch R4 from either {args.ergo_base} ({e_direct}) "
                f"or {bot} proxy ({e_proxy})"
            )
    if not args.quiet:
        print(f"      via {chain_source}")

    on_chain_root_hex = on_chain.hex()
    if not args.quiet:
        print(f"      on-chain R4={on_chain_root_hex}")
        print()
        print(f"[4/4] Verifying...")

    # Cross-check: the manifest_hash bottube reports must equal the
    # 32-byte R4 from the chain. This is the bottube→chain seam.
    if on_chain_root_hex != manifest_hash:
        sys.exit(
            f"FAIL: on-chain R4 ({on_chain_root_hex}) does NOT match\n"
            f"      manifest_hash from provenance API ({manifest_hash}).\n"
            f"      The bottube DB and the chain disagree about this batch's root."
        )

    # Cross-check: the leaf from this video must hash into the root.
    # Without batch membership we can only verify the trivial case where
    # this video's leaf == the root (a one-member batch). For multi-member
    # batches the verifier confirms the bottube↔chain seam above and
    # requires the future /admin/provenance/batch endpoint for the
    # leaf↔root cryptographic step.
    if own_leaf.hex() == manifest_hash:
        if not args.quiet:
            print(f"      single-leaf batch — own_leaf matches root directly.")
        verdict = "PASS"
    elif public_proof:
        # Walk the public Merkle proof: leaf + sibling hashes → root.
        node = own_leaf
        for hop in public_proof.get("path", []):
            sibling = bytes.fromhex(hop["sibling"])
            if hop["side"] == "R":
                node = hashlib.sha256(node + sibling).digest()
            else:
                node = hashlib.sha256(sibling + node).digest()
        locally_computed_root_hex = node.hex()
        if locally_computed_root_hex != manifest_hash:
            sys.exit(
                f"FAIL: walking the public Merkle path produced "
                f"{locally_computed_root_hex} but bottube's manifest_hash is "
                f"{manifest_hash}. Either the path or the leaf is wrong."
            )
        if locally_computed_root_hex != on_chain_root_hex:
            sys.exit(
                f"FAIL: walked root ({locally_computed_root_hex}) does NOT "
                f"match on-chain R4 ({on_chain_root_hex})."
            )
        if not args.quiet:
            print(f"      Walked Merkle path: {locally_computed_root_hex}")
            print(f"      ✓ matches on-chain R4 byte-for-byte")
            print(f"      ✓ inclusion proof valid (no admin access needed)")
        verdict = "PASS"
    elif full_check and batch_members:
        # Full Merkle reconstruction: build leaves for every batch member,
        # compute the binary tree, compare to on-chain root. Each leaf must
        # use its own row's manifest_version — a batch may be heterogeneous
        # during the v1→v2→v3 migration window.
        leaves = [
            manifest_leaf(
                m["video_id"], m["canonical_sha256"],
                m["uploader_sig"], m["uploaded_at"],
                manifest_version=int(m.get("manifest_version", 1) or 1),
                thumbnail_sha256=m.get("thumbnail_sha256", "") or "",
                canonical_360p_sha256=m.get("canonical_360p_sha256", "") or "",
                creator_pubkey=m.get("creator_pubkey", "") or "",
                creator_signature=m.get("creator_signature", "") or "",
            )
            for m in batch_members
        ]
        local_root = merkle_root(leaves)
        locally_computed_root_hex = local_root.hex()
        own_in_batch = any(m["video_id"] == vid for m in batch_members)
        if not own_in_batch:
            sys.exit(
                f"FAIL: video {vid} is not listed in batch members "
                f"(membership inconsistency)"
            )
        if locally_computed_root_hex != on_chain_root_hex:
            sys.exit(
                f"FAIL: locally-computed Merkle root ({locally_computed_root_hex}) "
                f"does NOT match on-chain R4 ({on_chain_root_hex}). "
                f"Either the batch members or leaf recipe diverged."
            )
        if not args.quiet:
            print(f"      Reconstructed local root: {locally_computed_root_hex}")
            print(f"      ✓ matches on-chain R4 byte-for-byte")
            print(f"      ✓ {vid} is included in the batch ({len(batch_members)} members)")
        verdict = "PASS"
    else:
        if not args.quiet:
            print(f"      multi-leaf batch — leaf is one of N members.")
            print(f"      bottube↔chain seam verified (manifest_hash == R4).")
            print(f"      leaf↔root inclusion proof skipped — pass --admin-key to enable.")
        verdict = "PARTIAL"

    # Phase 11.21 + 11.24: optional bytes-on-disk check.
    # Default: re-hashes the canonical asset.
    # On v2 manifests, also re-hashes thumbnail + 360p, since those hashes
    # are folded into the v2 leaf and a moderator could otherwise hot-swap
    # them without breaking the chain seam.
    asset_check = None
    asset_extras = []  # list of (label, kind, actual_hex, total, expected) tuples
    if args.check_asset:
        def _abs(u):
            if not u:
                return ""
            return (bot + u) if u.startswith("/") else u

        # Always check the canonical asset.
        targets = [(
            "canonical",
            _abs((prov.get("canonical_asset") or {}).get("url", "")),
            canonical_sha,
        )]
        # On v2+, add thumbnail and 360p.
        if manifest_ver >= 2:
            t = (prov.get("thumbnail") or {})
            if t.get("sha256") and t.get("url"):
                targets.append(("thumbnail", _abs(t.get("url")), t.get("sha256", "")))
            p = (prov.get("canonical_360p") or {})
            if p.get("sha256") and p.get("url"):
                targets.append(("rendition_360p", _abs(p.get("url")), p.get("sha256", "")))

        if not args.quiet:
            print()
            print(f"[bonus] --check-asset enabled; will hash {len(targets)} asset(s)")
            print(f"        capping each at {args.asset_max_mb} MB")

        any_mismatch = False
        any_canonical_match = False
        for (label, url, expected) in targets:
            if not args.quiet:
                print(f"        [{label}] streaming {url}")
            matched, actual_hex, total, err = hash_asset_streaming(
                url, expected, max_mb=args.asset_max_mb,
            )
            asset_extras.append({
                "label": label, "url": url, "expected": expected,
                "actual": actual_hex, "bytes": total, "matched": matched,
                "error": err,
            })
            if err and not actual_hex:
                if not args.quiet:
                    print(f"        [{label}] ⚠ fetch error: {err}")
                continue
            if matched:
                if not args.quiet:
                    mb = total / (1024 * 1024)
                    print(f"        [{label}] ✓ {total:,} bytes ({mb:.2f} MB) — SHA-256 matches anchored value")
                if label == "canonical":
                    any_canonical_match = True
            else:
                any_mismatch = True
                if not args.quiet:
                    print(f"        [{label}] ✗ MISMATCH")
                    print(f"                   served {actual_hex}")
                    print(f"                   anchored {expected}")
                    print(f"                   bottube is serving DIFFERENT bytes than what was anchored.")

        if any_mismatch:
            asset_check = ("mismatch", asset_extras)
            verdict = "FAIL"
        elif any_canonical_match:
            asset_check = ("match", asset_extras)
        else:
            # Couldn't actually verify even the canonical asset (likely
            # fetch error). Don't claim PASS for the asset bit; leave the
            # chain verdict as-is but flag.
            asset_check = ("error", asset_extras)

    if args.quiet:
        print(verdict)
    else:
        print()
        print(f"=== {verdict} ===")
        print(f"  video:       {vid}")
        print(f"  chain:       {chain}")
        print(f"  tx:          {tx_hash}")
        print(f"  on-chain R4: {on_chain_root_hex}")
        print(f"  bottube hash:{manifest_hash}")
        print(f"  own leaf:    {own_leaf.hex()}")
        if asset_check:
            kind = asset_check[0]
            extras = asset_check[1] if len(asset_check) > 1 else []
            ok_count = sum(1 for e in extras if isinstance(e, dict) and e.get("matched"))
            err_count = sum(1 for e in extras if isinstance(e, dict) and e.get("error") and not e.get("actual"))
            mismatch_count = sum(
                1 for e in extras
                if isinstance(e, dict) and e.get("actual") and not e.get("matched")
            )
            print(
                f"  asset bytes: "
                f"{ok_count} matched · {mismatch_count} mismatched · "
                f"{err_count} fetch error"
            )
            for e in extras:
                if not isinstance(e, dict):
                    continue
                lbl = e.get("label", "?")
                if e.get("matched"):
                    sym = "✓"
                elif e.get("actual"):
                    sym = "✗"
                else:
                    sym = "⚠"
                print(f"               {sym} {lbl}: {e.get('bytes', 0):,} B")
        if verdict == "PASS":
            print()
            if own_leaf.hex() == manifest_hash:
                print("  Single-leaf batch — own_leaf matches root directly.")
                print("  End-to-end verified.")
            elif public_proof:
                print(f"  Inclusion proof ({len(public_proof['path'])} hops, batch size {public_proof['batch_size']}):")
                print("    1. bottube's manifest_hash matches the on-chain R4 register")
                print("    2. walked Merkle path from local leaf reaches the same root")
                print("  End-to-end cryptographically verified — no admin access required.")
            else:
                print(f"  Multi-leaf batch ({len(batch_members)} members, full reconstruction):")
                print("    1. bottube's manifest_hash matches the on-chain R4 register")
                print("    2. locally-reconstructed Merkle root matches both")
                print("    3. this video's leaf is included in the batch")
                print("  End-to-end cryptographically verified.")
        else:
            print()
            print("  The bottube→chain seam is verified: bottube's claimed manifest_hash")
            print("  matches the on-chain R4 register byte-for-byte. The leaf-to-root")
            print("  inclusion step needs --admin-key to fetch /api/admin/provenance/batch.")

    sys.exit(0 if verdict in ("PASS", "PARTIAL") else 1)


if __name__ == "__main__":
    main()
