use reqwest::StatusCode;

/// A configuration, transport, server, or response-contract failure.
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum Error {
    /// The server URL must be HTTP(S), without credentials, a query, or a fragment.
    #[error("invalid base URL: {0}")]
    InvalidBaseUrl(&'static str),
    /// A supplied option is invalid before a request can be sent.
    #[error("invalid option: {0}")]
    InvalidOption(&'static str),
    /// Authenticated uploads need an API key.
    #[error("an API key is required for uploads")]
    MissingApiKey,
    /// The key cannot be represented as an HTTP header.
    #[error("invalid API key header")]
    InvalidApiKey,
    /// The HTTP request failed, including connection and timeout errors.
    #[error("HTTP transport failed: {0}")]
    Transport(#[from] reqwest::Error),
    /// The local video file could not be opened.
    #[error("could not read upload file: {0}")]
    Io(#[from] std::io::Error),
    /// A non-2xx response or an application-level failure returned by the API.
    #[error("BoTTube returned {status}: {message}")]
    Api {
        /// HTTP status, including 2xx when the JSON reports an application error.
        status: StatusCode,
        /// Server error message, or a bounded excerpt for non-JSON errors.
        message: String,
    },
    /// The response was not valid JSON or lacked required contract fields.
    #[error("invalid BoTTube JSON response: {0}")]
    Decode(#[from] serde_json::Error),
}
