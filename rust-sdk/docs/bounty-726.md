# Bounty #726 review evidence

Prepared for [the Rust client crate bounty](https://github.com/Scottcjn/rustchain-bounties/issues/726).
The [`/claim` marker](https://github.com/Scottcjn/rustchain-bounties/issues/726#issuecomment-5777691125)
was [accepted by the claim bot](https://github.com/Scottcjn/rustchain-bounties/issues/726#issuecomment-5777693691)
on September 22, 2026.

## Deliverable

[`bottube-client` 0.1.0](https://crates.io/crates/bottube-client/0.1.0) is an
MIT-licensed async client with typed video listings, search filters, pagination,
and streaming multipart uploads. It includes README examples, public rustdocs,
API errors, upload-key handling, and moderation warnings.

- Published source: [`af4b870a0fba90c86627bd6f737220bfb088dbf5`](https://github.com/arthurianresolve/bottube-client/tree/af4b870a0fba90c86627bd6f737220bfb088dbf5).
- Release tag: [`v0.1.0`](https://github.com/arthurianresolve/bottube-client/tree/v0.1.0).
- Package SHA-256: `7de54b8367f4071225f94ec6ff51fa323bb40f9d1748e7b1bde899315748863d`.
- [Published API docs](https://docs.rs/bottube-client/0.1.0/bottube_client/) and
  [successful docs.rs build](https://docs.rs/crate/bottube-client/0.1.0/builds/4534442).
- [Linux and Windows CI for the published source](https://github.com/arthurianresolve/bottube-client/actions/runs/35541453051).

The `rust-sdk/src` implementation in this pull request is the published source.
The review additions provide documentation, CI, and a registry consumer; they do
not change the published crate, release tag, or library implementation.

## Reproduce

From `rust-sdk/`, compile and optionally run the exact published release:

```text
cargo check --locked --manifest-path verification/published-client/Cargo.toml
cargo run --locked --manifest-path verification/published-client/Cargo.toml
```

The standalone manifest depends on crates.io version `=0.1.0`, with a checked-in
lockfile. It has no local path override. The run performs only public list and
search requests and requires no credentials. It reports changing server counts,
not a fixed expected count. HTTP failures produce a nonzero exit.

Source validation is documented in the [README](../README.md#develop-and-verify).
The published commit passed eight local HTTP contract tests, one doctest,
formatting, Clippy and rustdoc with warnings denied, and package verification.
The contract tests inspect multipart bytes, API-key handling, error responses,
moderation holds, and rejection of upload redirects. Public list/search checks
also succeeded on September 21, 2026. No authenticated public upload was made;
upload behavior is covered by local fixtures.

## Requested assessment

The prepared claim requests the 10 RTC published-crate tier plus the 5 RTC
documentation and 5 RTC passing-CI bonuses, up to 20 RTC subject to acceptance.
The first-bounty payment rule is still pending maintainer acceptance. Claimant:
`@arthurianresolve`.
Payout wallet: `RTC417dc819a4a1c3f2237e488bd77f78ba861377f2`.

Codex assisted with implementation, review, documentation, and verification.
