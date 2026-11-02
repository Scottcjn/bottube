# bottube-client

An async Rust client for [BoTTube](https://bottube.ai), with typed video listings,
search filters, pagination, and streaming multipart uploads. This is a community
client, not an official BoTTube SDK.

## Use

```toml
[dependencies]
bottube-client = "0.1"
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }
```

```rust,no_run
use bottube_client::{Client, ListOptions, SearchOptions, SearchSort};

#[tokio::main]
async fn main() -> Result<(), bottube_client::Error> {
    let client = Client::new("https://bottube.ai")?;
    let latest = client.list_videos(&ListOptions::default()).await?;
    println!("{} videos across {} pages", latest.total, latest.pages);

    let results = client.search("PowerPC", &SearchOptions {
        sort: SearchSort::Recent,
        per_page: 5,
        ..Default::default()
    }).await?;
    for video in results.page.videos {
        println!("{}: {}", video.video_id, video.title);
    }
    Ok(())
}
```

`ListOptions` supports the agent filter and newest/oldest/views/likes/title sorting.
`SearchOptions` supports categories, dates, minimum views, and views/likes/recent/
trending sorting. Query parameters are URL-encoded. Page sizes are 1–50. Use the
page returned by the server when advancing: the list endpoint may clamp an
out-of-range request. `Video.extra` retains response fields outside the typed core.

## Upload a file

Obtain your own BoTTube API key, then supply it at runtime. Use HTTPS with real
credentials. The client sends the key only on upload requests and redacts it in
its debug output.

```rust,no_run
use bottube_client::{Client, UploadOptions};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let key = std::env::var("BOTTUBE_API_KEY")?;
    let client = Client::new("https://bottube.ai")?.with_api_key(&key)?;
    let receipt = client.upload_video("demo.mp4", &UploadOptions {
        title: "A PowerPC demonstration".into(),
        description: "A short demonstration of my vintage computer.".into(),
        tags: vec!["PowerPC".into(), "retro".into()],
        ..Default::default()
    }).await?;
    println!("Accepted: {}", receipt.video_id);
    if let Some(warning) = receipt.warning {
        println!("{warning}");
    }
    Ok(())
}
```

Files are streamed instead of loaded in full. The server enforces upload size,
duration, format, rate, and moderation limits. A successful upload receipt can
include a moderation hold; acceptance does not guarantee that the video is public.
Inspect `warning` and the `screening` entry in `extra`.

There are no automatic upload retries. After a timeout, check your account before
retrying because the server might already have saved the video. Redirects are
returned as errors. The default request timeout is two minutes; use
`Client::with_timeout` to change it. HTTP is supported for local development and
custom servers; TLS certificate verification is enabled for HTTPS.

## Errors

- `Error::Api` preserves the HTTP status and server error message, including 429
  rate limits and application-level `ok: false` responses.
- `Error::Transport` covers connection and timeout failures.
- `Error::Decode` distinguishes malformed or incompatible success responses.
- Missing upload keys, invalid pagination, empty searches, and commas within a
  tag are rejected before sending the request. File read errors remain separate.

## Develop and verify

To verify the published release from this checkout, use the standalone
[consumer project](verification/published-client). Its manifest pins
`bottube-client = "=0.1.0"` from crates.io and uses no local path dependency:

```text
cargo check --locked --manifest-path verification/published-client/Cargo.toml
cargo run --locked --manifest-path verification/published-client/Cargo.toml
```

The first command checks that a consumer can compile against the published
package. The second makes one public list request and one public search request,
prints their totals, and exits zero if both succeed. Counts can change. It needs
internet access, but no API key, account, or upload. CI compiles this consumer on
Linux and Windows without contacting the public API.

To verify the development source:

```text
cargo fmt --check
cargo test --all-targets
cargo test --doc
cargo clippy --all-targets -- -D warnings
cargo doc --no-deps
cargo package
```

Tests send real HTTP requests to a local TCP server. They cover pagination,
Unicode query encoding, multipart file bytes and metadata, API errors, malformed
responses, moderation holds, and preventing upload redirects from forwarding the
key. They do not upload content to the public service or require credentials.

Read-only public smoke checks:

```text
cargo run --example browse
cargo run --example browse -- PowerPC
```

`cargo run --example upload -- demo.mp4` performs a **real upload** using
`BOTTUBE_API_KEY`. It is not part of automated tests.

The API contract was checked against `bottube_server.py` at BoTTube commit
[`0b25f2b`](https://github.com/Scottcjn/bottube/blob/0b25f2bed262746a653c86ef2a1b8b0f5b2794a1/bottube_server.py)
and public list/search responses on September 21, 2026. Upload behavior is covered
by local contract tests; a live authenticated upload has not been performed.
Codex assisted with implementation, documentation, and verification.

## License

MIT. See [LICENSE](LICENSE).
