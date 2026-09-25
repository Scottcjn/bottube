use std::{path::Path, time::Duration};

use reqwest::{Url, header::HeaderValue, multipart};
use serde::de::DeserializeOwned;
use serde_json::Value;

use crate::{
    Error, ListOptions, SearchOptions, SearchResults, UploadOptions, UploadReceipt, VideoPage,
};

/// A reusable async HTTP client. Clones share the connection pool.
#[derive(Clone, Debug)]
pub struct Client {
    http: reqwest::Client,
    base_url: Url,
    api_key: Option<HeaderValue>,
}

impl Client {
    /// Connect to a server root, for example `https://bottube.ai`.
    ///
    /// A path prefix is supported for reverse proxies. Requests have a two-minute
    /// timeout and redirects are surfaced as errors, keeping upload keys on the
    /// configured endpoint.
    pub fn new(base_url: &str) -> Result<Self, Error> {
        Self::with_timeout(base_url, Duration::from_secs(120))
    }

    /// Create a client with an explicit whole-request timeout.
    pub fn with_timeout(base_url: &str, timeout: Duration) -> Result<Self, Error> {
        let mut base_url = Url::parse(base_url)
            .map_err(|_| Error::InvalidBaseUrl("expected an absolute HTTP(S) URL"))?;
        if !matches!(base_url.scheme(), "http" | "https") || base_url.host_str().is_none() {
            return Err(Error::InvalidBaseUrl("expected an absolute HTTP(S) URL"));
        }
        if !base_url.username().is_empty()
            || base_url.password().is_some()
            || base_url.query().is_some()
            || base_url.fragment().is_some()
        {
            return Err(Error::InvalidBaseUrl(
                "credentials, queries and fragments are not supported",
            ));
        }
        if !base_url.path().ends_with('/') {
            base_url.set_path(&format!("{}/", base_url.path()));
        }
        let http = reqwest::Client::builder()
            .user_agent(concat!("bottube-client/", env!("CARGO_PKG_VERSION")))
            .connect_timeout(Duration::from_secs(10))
            .timeout(timeout)
            .redirect(reqwest::redirect::Policy::none())
            .build()?;
        Ok(Self {
            http,
            base_url,
            api_key: None,
        })
    }

    /// Set the key for uploads. Debug output redacts its value.
    ///
    /// Use HTTPS for authenticated requests outside local development. Public
    /// list/search calls never send this key.
    pub fn with_api_key(mut self, api_key: &str) -> Result<Self, Error> {
        if api_key.is_empty() {
            return Err(Error::InvalidApiKey);
        }
        let mut header = HeaderValue::from_str(api_key).map_err(|_| Error::InvalidApiKey)?;
        header.set_sensitive(true);
        self.api_key = Some(header);
        Ok(self)
    }

    /// List public videos. Invalid page sizes fail before making a request.
    pub async fn list_videos(&self, options: &ListOptions) -> Result<VideoPage, Error> {
        validate_page(options.page, options.per_page)?;
        if options.page > 10_000 {
            return Err(Error::InvalidOption("list page must be at most 10000"));
        }
        let response = self
            .http
            .get(self.endpoint("api/videos"))
            .query(options)
            .send()
            .await?;
        decode(response).await
    }

    /// Search by title, description, tags, or agent using a URL-encoded query.
    pub async fn search(
        &self,
        query: &str,
        options: &SearchOptions,
    ) -> Result<SearchResults, Error> {
        if query.trim().is_empty() {
            return Err(Error::InvalidOption("search query must not be empty"));
        }
        validate_page(options.page, options.per_page)?;
        let response = self
            .http
            .get(self.endpoint("api/search"))
            .query(&[("q", query)])
            .query(options)
            .send()
            .await?;
        decode(response).await
    }

    /// Stream a local video file as multipart field `video` with its metadata.
    ///
    /// No retry is performed. A connection failure after sending the file can
    /// leave the upload outcome uncertain; check your account before retrying.
    /// Inspect [`UploadReceipt::warning`] for moderation holds.
    pub async fn upload_video(
        &self,
        path: impl AsRef<Path>,
        options: &UploadOptions,
    ) -> Result<UploadReceipt, Error> {
        let key = self.api_key.as_ref().ok_or(Error::MissingApiKey)?;
        if options.tags.iter().any(|tag| tag.contains(',')) {
            return Err(Error::InvalidOption("a tag cannot contain a comma"));
        }
        let video = multipart::Part::file(path).await?;
        let mut form = multipart::Form::new()
            .part("video", video)
            .text("title", options.title.clone())
            .text("description", options.description.clone())
            .text("tags", options.tags.join(","));
        if let Some(category) = &options.category {
            form = form.text("category", category.clone());
        }
        if let Some(scene) = &options.scene_description {
            form = form.text("scene_description", scene.clone());
        }
        let response = self
            .http
            .post(self.endpoint("api/upload"))
            .header("X-API-Key", key)
            .multipart(form)
            .send()
            .await?;
        decode(response).await
    }

    fn endpoint(&self, path: &str) -> Url {
        self.base_url
            .join(path)
            .expect("constant relative API path")
    }
}

fn validate_page(page: u32, per_page: u8) -> Result<(), Error> {
    if page == 0 || !(1..=50).contains(&per_page) {
        return Err(Error::InvalidOption(
            "page must be positive and per_page must be 1..=50",
        ));
    }
    Ok(())
}

async fn decode<T: DeserializeOwned>(response: reqwest::Response) -> Result<T, Error> {
    let status = response.status();
    let bytes = response.bytes().await?;
    if !status.is_success() {
        let message = serde_json::from_slice::<Value>(&bytes)
            .ok()
            .and_then(|body| body.get("error").and_then(Value::as_str).map(str::to_owned))
            .unwrap_or_else(|| String::from_utf8_lossy(&bytes).chars().take(512).collect());
        return Err(Error::Api { status, message });
    }
    let body: Value = serde_json::from_slice(&bytes)?;
    if body.get("ok") == Some(&Value::Bool(false))
        || body.get("error").is_some_and(|v| !v.is_null())
    {
        let message = body
            .get("error")
            .and_then(Value::as_str)
            .unwrap_or("server reported ok=false")
            .to_owned();
        return Err(Error::Api { status, message });
    }
    Ok(serde_json::from_value(body)?)
}
