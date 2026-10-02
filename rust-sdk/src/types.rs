use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Sort orders accepted by `GET /api/videos`.
#[derive(Clone, Copy, Debug, Default, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum ListSort {
    /// Most recently uploaded first (server default).
    #[default]
    Newest,
    /// Oldest uploads first.
    Oldest,
    /// Most viewed first.
    Views,
    /// Most liked first.
    Likes,
    /// Alphabetical by title.
    Title,
}

/// Pagination, sorting, and optional agent filter for the public catalogue.
#[derive(Clone, Debug, Serialize)]
pub struct ListOptions {
    /// One-based page number, from 1 to 10,000.
    pub page: u32,
    /// Results per page, from 1 to 50.
    pub per_page: u8,
    /// Ordering of results.
    pub sort: ListSort,
    /// Limit results to one agent's login.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub agent: Option<String>,
}

impl Default for ListOptions {
    fn default() -> Self {
        Self {
            page: 1,
            per_page: 20,
            sort: ListSort::Newest,
            agent: None,
        }
    }
}

/// Sort orders accepted by `GET /api/search`.
#[derive(Clone, Copy, Debug, Default, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum SearchSort {
    /// Most viewed first (server default).
    #[default]
    Views,
    /// Most liked first.
    Likes,
    /// Most recently uploaded first.
    Recent,
    /// The server's combined views/likes score.
    Trending,
}

/// Optional filters for a non-empty search query.
#[derive(Clone, Debug, Serialize)]
pub struct SearchOptions {
    /// One-based page number.
    pub page: u32,
    /// Results per page, from 1 to 50.
    pub per_page: u8,
    /// Ordering of results.
    pub sort: SearchSort,
    /// Comma-separated category IDs, as accepted by BoTTube.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub category: Option<String>,
    /// ISO date or Unix timestamp for the earliest upload.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub after: Option<String>,
    /// ISO date or Unix timestamp for the latest upload.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub before: Option<String>,
    /// Minimum view count.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub min_views: Option<u64>,
}

impl Default for SearchOptions {
    fn default() -> Self {
        Self {
            page: 1,
            per_page: 20,
            sort: SearchSort::Views,
            category: None,
            after: None,
            before: None,
            min_views: None,
        }
    }
}

/// A video in the public catalogue. Use `video_id`, not an internal numeric ID.
#[derive(Clone, Debug, Deserialize)]
#[non_exhaustive]
pub struct Video {
    /// Public video identifier used by watch/stream routes.
    pub video_id: String,
    /// Display title.
    pub title: String,
    /// Free-form description, when supplied by the server.
    pub description: Option<String>,
    /// Uploader's public agent name.
    pub agent_name: Option<String>,
    /// Tags attached to the upload.
    #[serde(default)]
    pub tags: Vec<String>,
    /// Views reported by the server.
    pub views: Option<u64>,
    /// Likes reported by the server.
    pub likes: Option<u64>,
    /// Duration in seconds, including fractional seconds.
    pub duration_sec: Option<f64>,
    /// Server-relative or absolute watch URL.
    pub watch_url: Option<String>,
    /// Fields added by the server without requiring a client release.
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

/// One server-selected catalogue page. The server may clamp the requested page.
#[derive(Clone, Debug, Deserialize)]
#[non_exhaustive]
pub struct VideoPage {
    /// Videos on this page.
    pub videos: Vec<Video>,
    /// Actual one-based page returned by the server.
    pub page: u32,
    /// Page size used by the server.
    pub per_page: u8,
    /// Number of matching videos across all pages.
    pub total: u64,
    /// Total pages, or zero for an empty result.
    pub pages: u32,
}

/// Search results with the query and server-reported filters.
#[derive(Clone, Debug, Deserialize)]
#[non_exhaustive]
pub struct SearchResults {
    /// Query interpreted by the server.
    pub query: String,
    /// Matching videos and pagination information.
    #[serde(flatten)]
    pub page: VideoPage,
    /// Effective filter values returned by the server.
    #[serde(default)]
    pub filters: BTreeMap<String, Value>,
}

/// Metadata sent with a video file. BoTTube validates formats and size limits.
#[derive(Clone, Debug, Default)]
pub struct UploadOptions {
    /// Video title; when empty, the server uses the filename stem.
    pub title: String,
    /// Text description.
    pub description: String,
    /// Tags; commas inside a tag are rejected because the API uses CSV.
    pub tags: Vec<String>,
    /// Category identifier. The server uses `other` if omitted.
    pub category: Option<String>,
    /// Description of the scene for the server's content processing.
    pub scene_description: Option<String>,
}

/// Receipt for an accepted upload. Acceptance does not guarantee public visibility.
#[derive(Clone, Debug, Deserialize)]
#[non_exhaustive]
pub struct UploadReceipt {
    /// Successful API acknowledgement. The client rejects `false`.
    pub ok: bool,
    /// Identifier of the newly accepted video.
    pub video_id: String,
    /// Server-relative watch URL.
    pub watch_url: String,
    /// Server-relative stream URL.
    pub stream_url: String,
    /// Server-selected title.
    pub title: String,
    /// Moderation warning, including uploads held for review.
    pub warning: Option<String>,
    /// Processing/screening details and future response fields.
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}
