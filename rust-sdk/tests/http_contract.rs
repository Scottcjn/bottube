use std::{
    path::PathBuf,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use bottube_client::{
    Client, Error, ListOptions, ListSort, SearchOptions, SearchSort, UploadOptions,
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
    task::JoinHandle,
};

const PAGE: &str = r#"{"page":2,"per_page":5,"total":7,"pages":2,"videos":[{"video_id":"public-id","title":"Vintage computing","tags":["PowerPC"],"duration_sec":6.25,"views":10,"custom_field":"kept"}]}"#;
const UPLOAD: &str = r#"{"ok":true,"video_id":"new-video","title":"Example","watch_url":"/watch/new-video","stream_url":"/api/videos/new-video/stream","warning":"Held for review","screening":{"status":"failed"}}"#;

struct Request {
    head: String,
    body: Vec<u8>,
}

async fn server(status: u16, body: &str, headers: &str) -> (String, JoinHandle<Request>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    let response = format!(
        "HTTP/1.1 {status} Test\r\nContent-Length: {}\r\nContent-Type: application/json\r\nConnection: close\r\n{headers}\r\n{body}",
        body.len()
    );
    let task = tokio::spawn(async move {
        let (mut socket, _) = listener.accept().await.unwrap();
        let mut request = Vec::new();
        let mut buf = [0_u8; 4096];
        let boundary = loop {
            let n = socket.read(&mut buf).await.unwrap();
            assert!(n > 0, "connection closed before request headers");
            request.extend_from_slice(&buf[..n]);
            if let Some(pos) = request.windows(4).position(|s| s == b"\r\n\r\n") {
                break pos + 4;
            }
            assert!(request.len() < 32_768, "unexpectedly large request");
        };
        let head = String::from_utf8(request[..boundary].to_vec()).unwrap();
        let length: usize = head
            .lines()
            .find_map(|line| {
                let (name, value) = line.split_once(':')?;
                name.eq_ignore_ascii_case("content-length")
                    .then(|| value.trim().parse().unwrap())
            })
            .unwrap_or(0);
        assert!(
            !head.to_lowercase().contains("transfer-encoding:"),
            "file parts should have a known length"
        );
        while request.len() - boundary < length {
            let n = socket.read(&mut buf).await.unwrap();
            assert!(n > 0, "connection closed before request body");
            request.extend_from_slice(&buf[..n]);
        }
        socket.write_all(response.as_bytes()).await.unwrap();
        Request {
            head,
            body: request[boundary..].to_vec(),
        }
    });
    (url, task)
}

fn client(url: &str) -> Client {
    Client::with_timeout(url, Duration::from_secs(3)).unwrap()
}

#[tokio::test]
async fn lists_videos_with_filters_and_preserves_server_pagination() {
    let (url, server) = server(200, PAGE, "").await;
    let options = ListOptions {
        page: 3,
        per_page: 5,
        sort: ListSort::Oldest,
        agent: Some("robot & friend".into()),
    };
    let result = client(&format!("{url}/proxy"))
        .with_api_key("test-secret")
        .unwrap()
        .list_videos(&options)
        .await
        .unwrap();
    assert_eq!(result.page, 2); // Server clamped the requested page.
    assert_eq!(result.total, 7);
    assert_eq!(result.videos[0].video_id, "public-id");
    assert_eq!(result.videos[0].duration_sec, Some(6.25));
    assert_eq!(result.videos[0].extra["custom_field"], "kept");
    let request = server.await.unwrap();
    let target = request
        .head
        .lines()
        .next()
        .unwrap()
        .split_whitespace()
        .nth(1)
        .unwrap();
    let parsed = reqwest::Url::parse(&format!("{url}{target}")).unwrap();
    let query: std::collections::HashMap<_, _> = parsed.query_pairs().into_owned().collect();
    assert_eq!(parsed.path(), "/proxy/api/videos");
    assert_eq!(query["agent"], "robot & friend");
    assert_eq!(query["page"], "3");
    assert_eq!(query["per_page"], "5");
    assert_eq!(query["sort"], "oldest");
    assert!(!query.contains_key("limit"));
    assert!(!request.head.to_lowercase().contains("x-api-key"));
}

#[tokio::test]
async fn search_encodes_unicode_and_reserved_query_characters() {
    let body = r#"{"query":"PowerPC & café?","page":1,"per_page":20,"total":0,"pages":0,"videos":[],"filters":{"sort":"recent"}}"#;
    let (url, server) = server(200, body, "").await;
    let options = SearchOptions {
        sort: SearchSort::Recent,
        category: Some("retro,science-tech".into()),
        min_views: Some(5),
        ..Default::default()
    };
    let result = client(&url)
        .search("PowerPC & café?", &options)
        .await
        .unwrap();
    assert_eq!(result.query, "PowerPC & café?");
    assert!(result.page.videos.is_empty());
    let request = server.await.unwrap();
    let target = request
        .head
        .lines()
        .next()
        .unwrap()
        .split_whitespace()
        .nth(1)
        .unwrap();
    let parsed = reqwest::Url::parse(&format!("{url}{target}")).unwrap();
    let query: std::collections::HashMap<_, _> = parsed.query_pairs().into_owned().collect();
    assert_eq!(parsed.path(), "/api/search");
    assert_eq!(query["q"], "PowerPC & café?");
    assert_eq!(query["category"], "retro,science-tech");
    assert_eq!(query["min_views"], "5");
    assert_eq!(query["sort"], "recent");
}

struct TestVideo(PathBuf);

impl TestVideo {
    fn new() -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path =
            std::env::temp_dir().join(format!("bottube-client-{}-{nonce}.mp4", std::process::id()));
        std::fs::write(&path, b"local-test-video\x00\xff").unwrap();
        Self(path)
    }
}

impl Drop for TestVideo {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}

#[tokio::test]
async fn upload_sends_file_metadata_and_key_and_preserves_moderation_warning() {
    let (url, server) = server(201, UPLOAD, "").await;
    let file = TestVideo::new();
    let options = UploadOptions {
        title: "Example".into(),
        description: "Real multipart request".into(),
        tags: vec!["retro".into(), "PowerPC".into()],
        category: Some("other".into()),
        scene_description: Some("An old computer".into()),
    };
    let result = client(&url)
        .with_api_key("test-secret")
        .unwrap()
        .upload_video(&file.0, &options)
        .await
        .unwrap();
    assert_eq!(result.video_id, "new-video");
    assert_eq!(result.warning.as_deref(), Some("Held for review"));
    assert_eq!(result.extra["screening"]["status"], "failed");
    let request = server.await.unwrap();
    assert!(request.head.starts_with("POST /api/upload HTTP/1.1"));
    assert!(
        request
            .head
            .to_lowercase()
            .contains("x-api-key: test-secret")
    );
    assert!(
        request
            .head
            .to_lowercase()
            .contains("multipart/form-data; boundary=")
    );
    let body = String::from_utf8_lossy(&request.body);
    for expected in [
        "name=\"video\"; filename=",
        "name=\"title\"\r\n\r\nExample",
        "name=\"tags\"\r\n\r\nretro,PowerPC",
        "name=\"description\"\r\n\r\nReal multipart request",
        "name=\"category\"\r\n\r\nother",
        "name=\"scene_description\"\r\n\r\nAn old computer",
    ] {
        assert!(
            body.contains(expected),
            "missing multipart field: {expected}"
        );
    }
    assert!(
        request
            .body
            .windows(18)
            .any(|s| s == b"local-test-video\x00\xff")
    );
}

#[tokio::test]
async fn surfaces_http_and_application_errors_instead_of_empty_success() {
    for (status, body) in [
        (429, r#"{"error":"rate limited"}"#),
        (200, r#"{"ok":false,"error":"rate limited"}"#),
    ] {
        let (url, server) = server(status, body, "").await;
        let error = client(&url)
            .list_videos(&ListOptions::default())
            .await
            .unwrap_err();
        assert!(
            matches!(error, Error::Api { status: s, message } if s.as_u16() == status && message == "rate limited")
        );
        server.await.unwrap();
    }
}

#[tokio::test]
async fn distinguishes_malformed_success_and_non_json_server_error() {
    for body in ["not JSON", "{}"] {
        let (url, server) = server(200, body, "").await;
        assert!(matches!(
            client(&url).list_videos(&ListOptions::default()).await,
            Err(Error::Decode(_))
        ));
        server.await.unwrap();
    }
    let (url, server) = server(503, "temporarily unavailable", "").await;
    assert!(
        matches!(client(&url).list_videos(&ListOptions::default()).await, Err(Error::Api { status, message }) if status.as_u16() == 503 && message == "temporarily unavailable")
    );
    server.await.unwrap();
}

#[tokio::test]
async fn upload_redirects_are_not_followed() {
    let destination = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let location = format!(
        "Location: http://{}/stolen\r\n",
        destination.local_addr().unwrap()
    );
    let (url, server) = server(307, "redirect", &location).await;
    let file = TestVideo::new();
    let result = client(&url)
        .with_api_key("test-secret")
        .unwrap()
        .upload_video(&file.0, &UploadOptions::default())
        .await;
    assert!(matches!(result, Err(Error::Api { status, .. }) if status.as_u16() == 307));
    server.await.unwrap();
    assert!(
        tokio::time::timeout(Duration::from_millis(50), destination.accept())
            .await
            .is_err()
    );
}

#[tokio::test]
async fn invalid_options_fail_without_network_or_file_access() {
    let client = client("http://127.0.0.1:9");
    assert!(matches!(
        client.search("  ", &SearchOptions::default()).await,
        Err(Error::InvalidOption(_))
    ));
    assert!(matches!(
        client
            .list_videos(&ListOptions {
                per_page: 0,
                ..Default::default()
            })
            .await,
        Err(Error::InvalidOption(_))
    ));
    assert!(matches!(
        client
            .list_videos(&ListOptions {
                page: 10_001,
                ..Default::default()
            })
            .await,
        Err(Error::InvalidOption(_))
    ));
    assert!(matches!(
        client
            .upload_video("missing.mp4", &UploadOptions::default())
            .await,
        Err(Error::MissingApiKey)
    ));
    let client = client.with_api_key("test-secret").unwrap();
    assert!(!format!("{client:?}").contains("test-secret"));
    assert!(matches!(
        client
            .upload_video(
                "missing.mp4",
                &UploadOptions {
                    tags: vec!["two,tags".into()],
                    ..Default::default()
                }
            )
            .await,
        Err(Error::InvalidOption(_))
    ));
}

#[test]
fn configuration_rejects_ambiguous_urls_and_invalid_keys() {
    for url in [
        "not a URL",
        "file:///tmp/server",
        "https://user:password@example.com",
        "https://example.com?q=1",
        "https://example.com#fragment",
    ] {
        assert!(matches!(Client::new(url), Err(Error::InvalidBaseUrl(_))));
    }
    assert!(matches!(
        client("http://localhost").with_api_key("bad\r\nheader"),
        Err(Error::InvalidApiKey)
    ));
    assert!(matches!(
        client("http://localhost").with_api_key(""),
        Err(Error::InvalidApiKey)
    ));
}
