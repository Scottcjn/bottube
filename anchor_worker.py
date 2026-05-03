#!/usr/bin/env python3
"""
BoTTube provenance anchor worker.

Pulls pending video manifests from BoTTube, anchors a Merkle root on
RustChain (via the Ergo wallet at /opt/rustchain), and POSTs the result
back so each video's `anchor_tx_hash` is populated and the public
Verified Provenance pill flips green.

Operates in three modes:

  --mode dry      Fetch a batch, compute the Merkle root, do NOT
                  post back. Read-only smoke test.
  --mode stub     Fetch + compute + post back with a deterministic
                  tx_hash derived from the merkle root. Useful for
                  validating the round-trip before wiring real Ergo
                  credentials.
  --mode real     Compute the Merkle root, anchor it on Ergo via the
                  /wallet/transaction/sign + /transactions endpoints,
                  then post back the real tx_hash + block height.

Run via systemd timer or cron. Idempotent: a duplicate callback on
the same batch_id is a no-op.

Environment / config:
  BOTTUBE_BASE      Default https://bottube.ai
  BOTTUBE_ADMIN_KEY Admin key for /api/admin/* endpoints (required).
  ERGO_API_KEY      Ergo node API key (required for --mode real).
  ERGO_BASE         Default http://localhost:9053
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error


def _hex(b):
    return b.hex() if isinstance(b, (bytes, bytearray)) else str(b)


def _http(method, url, headers=None, body=None, timeout=30):
    """Tiny urllib wrapper. Returns (status, parsed_json_or_text)."""
    h = dict(headers or {})
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw.decode("utf-8"))
            except Exception:
                return r.status, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, raw
        except Exception:
            return e.code, str(e)


def merkle_root(leaves):
    """Compute a binary Merkle root over SHA-256 leaves.

    Leaves are bytes. Odd levels duplicate the last node (Bitcoin-style).
    Empty leaves return all-zero. Result is 32 bytes.
    """
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


_LEAF_DOMAIN_V2 = "bottube/v2"
_LEAF_DOMAIN_V3 = "bottube/v3"


def manifest_leaf_v1(m):
    """Legacy leaf: sha256(video_id|canonical_sha256|uploader_sig|uploaded_at)."""
    parts = "|".join([
        m.get("video_id", "") or "",
        m.get("canonical_sha256", "") or "",
        m.get("uploader_sig", "") or "",
        str(int(float(m.get("uploaded_at", 0) or 0))),
    ])
    return hashlib.sha256(parts.encode("utf-8")).digest()


def manifest_leaf_v2(m):
    """v2 leaf: folds thumbnail_sha256 + canonical_360p_sha256 into the leaf
    under a domain separator so v1 and v2 leaves can never collide.
    """
    parts = "|".join([
        _LEAF_DOMAIN_V2,
        m.get("video_id", "") or "",
        m.get("canonical_sha256", "") or "",
        m.get("thumbnail_sha256", "") or "",
        m.get("canonical_360p_sha256", "") or "",
        m.get("uploader_sig", "") or "",
        str(int(float(m.get("uploaded_at", 0) or 0))),
    ])
    return hashlib.sha256(parts.encode("utf-8")).digest()


def manifest_leaf_v3(m):
    """v3 leaf: folds creator_pubkey + creator_signature so the chain
    commits to a verifiable Ed25519 signature, not just a platform HMAC.
    """
    parts = "|".join([
        _LEAF_DOMAIN_V3,
        m.get("video_id", "") or "",
        m.get("canonical_sha256", "") or "",
        m.get("thumbnail_sha256", "") or "",
        m.get("canonical_360p_sha256", "") or "",
        m.get("uploader_sig", "") or "",
        m.get("creator_pubkey", "") or "",
        m.get("creator_signature", "") or "",
        str(int(float(m.get("uploaded_at", 0) or 0))),
    ])
    return hashlib.sha256(parts.encode("utf-8")).digest()


def manifest_leaf(m):
    """Dispatch by manifest_version. Legacy callers without the field
    get v1 — preserves bit-exact behavior for already-anchored batches.
    """
    ver = int(m.get("manifest_version", 1) or 1)
    if ver >= 3:
        return manifest_leaf_v3(m)
    if ver >= 2:
        return manifest_leaf_v2(m)
    return manifest_leaf_v1(m)


def _ergo_get(base, path, key, timeout=20):
    s, body = _http("GET", base + path, headers={"api_key": key}, timeout=timeout)
    if s != 200:
        raise RuntimeError(f"GET {path} -> {s}: {str(body)[:200]}")
    return body


def _ergo_post(base, path, key, payload, timeout=30):
    s, body = _http("POST", base + path, headers={"api_key": key}, body=payload, timeout=timeout)
    if s != 200:
        raise RuntimeError(f"POST {path} -> {s}: {str(body)[:200]}")
    return body


def anchor_real(merkle_root_hex, member_count, ergo_base, ergo_key,
                wallet_password=None, anchor_value=1_000_000, max_tx_wait=180):
    """Anchor merkle_root_hex in an Ergo box's R4 register on the private chain.

    Reuses the proven pattern from /root/rustchain/ergo_miner_anchor.py
    (UTXO selection, R4 = 0e20<32-byte hex>, sign + broadcast, TX
    confirmation poll). Differs only in the source of the commitment —
    here it's the BoTTube Merkle root, not the miner-attestation digest.

    Returns (tx_id, block_height). block_height=0 if not yet mined when
    we finish polling; caller re-checks later.
    """
    if not re.fullmatch(r"[0-9a-f]{64}", merkle_root_hex):
        raise RuntimeError("merkle_root_hex must be 64 hex chars (32 bytes)")

    # 1) Unlock wallet (idempotent — re-unlocking a locked wallet is OK).
    if wallet_password:
        try:
            _ergo_post(ergo_base, "/wallet/unlock", ergo_key,
                       {"pass": wallet_password}, timeout=15)
        except Exception:
            # Already unlocked is fine; surface only on later step.
            pass

    # 2) Pick a UTXO with enough balance (>= 2x anchor value).
    # Important: the wallet's unspent-boxes list may include boxes that have
    # been spent in mempool TXs but not yet mined — picking the first one
    # deterministically causes "Double spending attempt" loops. Randomize
    # the selection so consecutive batches don't collide on the same box.
    import random as _random
    boxes = _ergo_get(ergo_base, "/wallet/boxes/unspent?minConfirmations=1", ergo_key)
    candidates = []
    for b in (boxes or []):
        box = b.get("box", {}) if isinstance(b, dict) else {}
        if int(box.get("value", 0) or 0) >= 2 * anchor_value:
            candidates.append(box)
    if not candidates:
        raise RuntimeError("no UTXO with sufficient balance (>= 0.002 ERG)")
    # Sort by creationHeight DESC so newer boxes are tried first (more
    # likely to actually be unspent), then random-shuffle within ties.
    candidates.sort(key=lambda b: -int(b.get("creationHeight", 0)))
    # Take a random one of the top 32 most-recent boxes — keeps us out of
    # mempool conflicts without going off the deep end of the list.
    pool = candidates[:32] if len(candidates) > 32 else candidates
    input_box = _random.choice(pool)

    # 3) Get the raw bytes for the input box + current chain height.
    box_bytes = _ergo_get(
        ergo_base, "/utxo/byIdBinary/" + input_box["boxId"], ergo_key,
    ).get("bytes")
    if not box_bytes:
        raise RuntimeError("could not fetch box raw bytes")
    info = _ergo_get(ergo_base, "/info", ergo_key)
    height = int(info.get("fullHeight") or 0)

    input_val = int(input_box["value"])
    change_val = input_val - anchor_value  # zero-fee chain config

    # 4) Build the unsigned TX: anchor box (with R4=merkle_root, R5=count)
    #    + change box back to the same wallet (same ergoTree).
    #
    # Ergo SInt is ZigZag-VarInt, not fixed-width big-endian. Earlier
    # commits stored R5 with `format(n, "08x")` which serialized as a
    # 4-byte VarInt that the Ergo deserializer interpreted as 0 (the
    # leading "0" zero-byte stops the VarInt scan). Fixed below.
    def _zigzag_varint_hex(n):
        # ZigZag encode signed int: (n << 1) ^ (n >> 63) (assume 64-bit
        # but truncate the result to fit Int = 32-bit; member_count is
        # always positive and small).
        z = (n << 1) ^ (n >> 31) if n < 0 else (n << 1)
        # Encode as VarInt (little-endian 7-bit groups).
        out = []
        while True:
            b = z & 0x7F
            z >>= 7
            if z:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
        return "".join(format(b, "02x") for b in out)

    unsigned_tx = {
        "inputs": [{"boxId": input_box["boxId"], "extension": {}}],
        "dataInputs": [],
        "outputs": [
            {
                "value": anchor_value,
                "ergoTree": input_box["ergoTree"],
                "creationHeight": height,
                "assets": [],
                "additionalRegisters": {
                    # SColl[Byte] of 32 bytes: 0e + 20 (length 32) + hex
                    "R4": "0e20" + merkle_root_hex,
                    # SInt: type tag 04 + ZigZag VarInt
                    "R5": "04" + _zigzag_varint_hex(int(member_count)),
                },
            },
            {
                "value": change_val,
                "ergoTree": input_box["ergoTree"],
                "creationHeight": height,
                "assets": [],
                "additionalRegisters": {},
            },
        ],
    }

    # 5) Sign.
    signed = _ergo_post(
        ergo_base, "/wallet/transaction/sign", ergo_key,
        {"tx": unsigned_tx, "inputsRaw": [box_bytes], "dataInputsRaw": []},
        timeout=60,
    )

    # 6) Broadcast.
    tx_id = _ergo_post(ergo_base, "/transactions", ergo_key, signed, timeout=30)
    if isinstance(tx_id, dict):
        tx_id = tx_id.get("id") or tx_id.get("transactionId") or ""
    if not isinstance(tx_id, str) or len(tx_id) < 32:
        raise RuntimeError(f"unexpected broadcast response: {tx_id!r}")

    # 7) Poll for confirmation. block_height stays 0 if it never mines.
    block_height = 0
    deadline = time.time() + max_tx_wait
    while time.time() < deadline:
        time.sleep(10)
        try:
            tx_info = _ergo_get(
                ergo_base, f"/wallet/transactionById?id={tx_id}", ergo_key, timeout=10,
            )
            num_confs = int((tx_info or {}).get("numConfirmations", 0) or 0)
            if num_confs >= 1:
                # height-of-tx isn't returned directly; use current chain height
                # minus confirmations as an approximation.
                cur = _ergo_get(ergo_base, "/info", ergo_key, timeout=10)
                block_height = max(0, int(cur.get("fullHeight") or 0) - num_confs + 1)
                break
        except Exception:
            continue

    return tx_id, block_height


def main():
    ap = argparse.ArgumentParser(description="BoTTube provenance anchor worker")
    ap.add_argument("--mode", choices=("dry", "stub", "real"), default="dry",
                    help="dry = compute only; stub = stub tx_hash callback; real = anchor on Ergo")
    ap.add_argument("--limit", type=int, default=100,
                    help="max manifests per batch")
    ap.add_argument("--bottube-base", default=os.environ.get("BOTTUBE_BASE", "https://bottube.ai"))
    ap.add_argument("--admin-key", default=os.environ.get("BOTTUBE_ADMIN_KEY", ""))
    ap.add_argument("--insecure", action="store_true", help="(curl-style; not used by urllib)")
    args = ap.parse_args()

    if not args.admin_key:
        sys.exit("BOTTUBE_ADMIN_KEY env not set")

    base = args.bottube_base.rstrip("/")

    # 1. Claim a batch
    print(f"[anchor-worker] claiming batch (limit={args.limit}) from {base}")
    status, body = _http(
        "POST",
        f"{base}/api/admin/provenance/pending",
        headers={"X-Admin-Key": args.admin_key},
        body={"limit": args.limit},
    )
    if status != 200 or not isinstance(body, dict) or not body.get("ok"):
        sys.exit(f"pending claim failed: status={status} body={body}")

    batch_id = body.get("batch_id", "")
    manifests = body.get("manifests", [])
    if not batch_id or not manifests:
        print("[anchor-worker] no manifests pending — exiting")
        return

    # Version histogram so the worker log makes the v1→v2 rollout visible
    # to whoever's tailing journalctl. Phase 11.16: a batch may be mixed
    # during the migration window.
    versions = {}
    for m in manifests:
        v = int(m.get("manifest_version", 1) or 1)
        versions[v] = versions.get(v, 0) + 1
    ver_summary = ", ".join(f"v{k}={v}" for k, v in sorted(versions.items()))
    print(f"[anchor-worker] batch_id={batch_id}  count={len(manifests)}  ({ver_summary})")

    # 2. Compute Merkle root — each leaf uses its own row's manifest_version
    leaves = [manifest_leaf(m) for m in manifests]
    root = merkle_root(leaves)
    root_hex = root.hex()
    print(f"[anchor-worker] merkle_root={root_hex}")

    if args.mode == "dry":
        print("[anchor-worker] dry-run — releasing claim by reporting error=dry-run")
        _http(
            "POST",
            f"{base}/api/admin/provenance/anchor-result",
            headers={"X-Admin-Key": args.admin_key},
            body={
                "batch_id": batch_id,
                "error": "dry-run; claim released, no anchor performed",
            },
        )
        return

    # 3. Anchor (or stub)
    if args.mode == "stub":
        # Deterministic pseudo-TX so the same root produces the same tx_hash —
        # makes idempotency testing trivial.
        tx_hash = hashlib.sha256(("stub:" + root_hex).encode()).hexdigest()
        block_height = 0
        chain = "stub"
    else:
        ergo_key = os.environ.get("ERGO_API_KEY", "")
        ergo_base = os.environ.get("ERGO_BASE",
                                   os.environ.get("ERGO_NODE", "http://localhost:9053"))
        wallet_password = os.environ.get("ERGO_WALLET_PASSWORD", "rustchain123")
        if not ergo_key:
            sys.exit("ERGO_API_KEY env not set for --mode real")
        try:
            tx_hash, block_height = anchor_real(
                root_hex, len(manifests), ergo_base, ergo_key,
                wallet_password=wallet_password,
            )
            chain = "rustchain"
        except Exception as e:
            print(f"[anchor-worker] real anchor failed: {e}")
            _http(
                "POST",
                f"{base}/api/admin/provenance/anchor-result",
                headers={"X-Admin-Key": args.admin_key},
                body={"batch_id": batch_id, "error": str(e)[:500]},
            )
            sys.exit(1)

    # 4. Callback
    print(f"[anchor-worker] anchored on {chain}: tx_hash={tx_hash} block={block_height}")
    status, cb = _http(
        "POST",
        f"{base}/api/admin/provenance/anchor-result",
        headers={"X-Admin-Key": args.admin_key},
        body={
            "batch_id": batch_id,
            "chain": chain,
            "tx_hash": tx_hash,
            "block_height": block_height,
            "merkle_root": root_hex,
            "video_ids": [m["video_id"] for m in manifests],
        },
    )
    if status != 200 or not isinstance(cb, dict) or not cb.get("ok"):
        sys.exit(f"callback failed: status={status} body={cb}")
    print(f"[anchor-worker] done: rows_anchored={cb.get('rows_anchored', 0)}")


if __name__ == "__main__":
    main()
