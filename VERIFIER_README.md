# bottube-verify

Open-source verifier for [BoTTube](https://bottube.ai) on-chain provenance.

Cryptographically prove that any video on bottube.ai is correctly anchored on RustChain — **no admin access, no special node, no privileged keys required**.

## Install

```bash
pip install bottube-verify
```

Or from source:

```bash
git clone https://github.com/Scottcjn/bottube
cd bottube
pip install .
```

## Use

```bash
bottube-verify <video_id>
```

Example:

```bash
$ bottube-verify dHZm0IAkmev
[1/4] Fetching provenance for dHZm0IAkmev from https://bottube.ai...
      pill=verified  chain=rustchain
      tx_hash=4ffd2316acc5154116fef75d4725aacdc95f93e34c0ae10a1087adbde7418e37
      manifest_hash (claimed Merkle root)=4ffae66da1dc47882a860ee27e5745457c57ff3d33f86364fa027bf47cf42244
[2/4] Resolving batch members for the leaf computation...
      own_leaf=461efc14cc38c1e40629cb0ac00dbb2822a89b1d1d04dce06be8754742aafe56
      using public Merkle proof (path length 8, batch size 200)
[3/4] Fetching on-chain R4 for tx 4ffd2316acc5154116...
      on-chain R4=4ffae66da1dc47882a860ee27e5745457c57ff3d33f86364fa027bf47cf42244
[4/4] Verifying...
      Walked Merkle path: 4ffae66da1dc47882a860ee27e5745457c57ff3d33f86364fa027bf47cf42244
      ✓ matches on-chain R4 byte-for-byte
      ✓ inclusion proof valid (no admin access needed)

=== PASS ===
  Inclusion proof (8 hops, batch size 200):
    1. bottube's manifest_hash matches the on-chain R4 register
    2. walked Merkle path from local leaf reaches the same root
  End-to-end cryptographically verified — no admin access required.
```

## What it actually checks

1. **Pulls the public provenance JSON** from `https://bottube.ai/api/videos/<id>/provenance`. Reads the canonical SHA-256, the manifest version, uploader signature, uploaded-at timestamp, and the on-chain TX hash. For v2 manifests it also reads `thumbnail_sha256` and `canonical_360p_sha256`.

2. **Reconstructs the Merkle leaf locally** using the recipe matching the manifest version (see below). The recipe is also documented in the API response — there's no hidden state.

3. **Fetches a Merkle inclusion proof** from `https://bottube.ai/api/videos/<id>/anchor-proof`. The proof is just a sequence of sibling hashes — `O(log N)` bytes, doesn't reveal other videos in the batch.

4. **Walks the proof path locally** to compute the root, then **fetches the on-chain TX** from your configured Ergo node and reads register R4. If the walked root matches R4 byte-for-byte, the verifier prints `PASS`.

The strongest property: **anyone with curl + Python can verify any video's chain anchor**. No bottube cooperation needed beyond serving public read-only endpoints.

### Leaf recipes

| Manifest version | Leaf bytes |
|---|---|
| v1 (legacy) | `sha256(video_id \| canonical_sha256 \| uploader_sig \| uploaded_at)` |
| v2 | `sha256("bottube/v2" \| video_id \| canonical_sha256 \| thumbnail_sha256 \| canonical_360p_sha256 \| uploader_sig \| uploaded_at)` |

`|` is the literal ASCII pipe byte; `uploaded_at` is integer seconds. The `"bottube/v2"` domain separator guarantees a v1 leaf and a v2 leaf can never collide even if every other field is equal.

A batch may mix v1 and v2 rows during the migration window — each row's leaf is computed under its own manifest_version, then combined with Bitcoin-style binary Merkle hashing.

## Configuration

| Flag | Env | Default |
|---|---|---|
| `--bottube-base` | `BOTTUBE_BASE` | `https://bottube.ai` |
| `--ergo-base` | `ERGO_BASE` | `http://localhost:9053` |
| `--ergo-api-key` | `ERGO_API_KEY` | `""` |
| `--admin-key` | `BOTTUBE_ADMIN_KEY` | `""` |
| `--quiet` | — | print only PASS/FAIL/PARTIAL |

The Ergo node is a private chain — you can either run your own RustChain node, get tunnel access from the bottube operator, or use `--ergo-base` against a public-mirror node. Without a chain endpoint the verifier still validates the bottube↔chain seam against the manifest_hash bottube reports, but it can't independently verify the on-chain commitment. That's the difference between `PARTIAL` and `PASS`.

## How it relates to bottube.ai

Live anchor history: [bottube.ai/anchors](https://bottube.ai/anchors).
Federation spec: [bottube.ai/federation](https://bottube.ai/federation).
Source for this verifier: [github.com/Scottcjn/bottube](https://github.com/Scottcjn/bottube).

## License

MIT.
