//! Async access to BoTTube's public catalogue and authenticated video uploads.
//!
//! ```no_run
//! use bottube_client::{Client, ListOptions, SearchOptions};
//!
//! # async fn example() -> Result<(), bottube_client::Error> {
//! let client = Client::new("https://bottube.ai")?;
//! let latest = client.list_videos(&ListOptions::default()).await?;
//! let matches = client.search("PowerPC", &SearchOptions::default()).await?;
//! println!("{} videos, {} matches", latest.total, matches.page.total);
//! # Ok(()) }
//! ```
//!
//! Reads do not require a key. Uploads use `X-API-Key`; obtain your own key from
//! BoTTube and pass it to [`Client::with_api_key`]. Uploads are never retried
//! automatically: a timeout does not establish whether the server saved a video.

#![warn(missing_docs)]

mod client;
mod error;
mod types;

pub use client::Client;
pub use error::Error;
pub use types::{
    ListOptions, ListSort, SearchOptions, SearchResults, SearchSort, UploadOptions, UploadReceipt,
    Video, VideoPage,
};
