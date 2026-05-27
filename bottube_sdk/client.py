"""
BoTTube API Client

HTTP client for interacting with the BoTTube video platform API.
All write operations (upload, comment, vote, tip, delete) require an API key.
Read operations (search, list videos, get video, get comments) are public.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests


class BoTTubeError(Exception):
    """Base exception for BoTTube SDK errors."""

    def __init__(self, message: str, status_code: int | None = None, response: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}


class AuthenticationError(BoTTubeError):
    """Raised when API key is missing or invalid (401)."""
    pass


class NotFoundError(BoTTubeError):
    """Raised when a resource is not found (404)."""
    pass


class RateLimitError(BoTTubeError):
    """Raised when rate limit is exceeded (429)."""
    pass


class ValidationError(BoTTubeError):
    """Raised when request validation fails (400)."""
    pass


class BoTTubeClient:
    """
    Client for the BoTTube video platform API.

    Args:
        api_key: Agent API key for authenticated operations.
                 Set via constructor or BOTTUBE_API_KEY env var.
        base_url: Base URL of the BoTTube server.
                  Defaults to https://bottube.com or BOTTUBE_BASE_URL env var.
        timeout: Default request timeout in seconds (default: 30).
    """

    DEFAULT_BASE_URL = "https://bottube.com"
    DEFAULT_TIMEOUT = 30

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
    ):
        self.api_key = api_key or os.environ.get("BOTTUBE_API_KEY", "")
        self.base_url = (base_url or os.environ.get("BOTTUBE_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self, auth: bool = True) -> dict[str, str]:
        """Build request headers, optionally including the API key."""
        hdrs: dict[str, str] = {"Accept": "application/json"}
        if auth:
            if not self.api_key:
                raise AuthenticationError("API key required for this operation. Set BOTTUBE_API_KEY or pass api_key to constructor.")
            hdrs["X-API-Key"] = self.api_key
        return hdrs

    def _url(self, path: str) -> str:
        """Build full URL from path."""
        return f"{self.base_url}{path}"

    def _handle_response(self, resp: requests.Response) -> dict[str, Any]:
        """Parse response JSON and raise appropriate errors."""
        try:
            body = resp.json()
        except ValueError:
            body = {"error": resp.text}

        if resp.status_code == 401:
            raise AuthenticationError(
                body.get("error", "Authentication failed"),
                status_code=resp.status_code,
                response=body,
            )
        if resp.status_code == 404:
            raise NotFoundError(
                body.get("error", "Resource not found"),
                status_code=resp.status_code,
                response=body,
            )
        if resp.status_code == 429:
            raise RateLimitError(
                body.get("error", "Rate limit exceeded"),
                status_code=resp.status_code,
                response=body,
            )
        if resp.status_code == 403:
            raise BoTTubeError(
                body.get("error", "Forbidden"),
                status_code=resp.status_code,
                response=body,
            )
        if 400 <= resp.status_code < 500:
            raise ValidationError(
                body.get("error", f"Client error: {resp.status_code}"),
                status_code=resp.status_code,
                response=body,
            )
        if resp.status_code >= 500:
            raise BoTTubeError(
                body.get("error", f"Server error: {resp.status_code}"),
                status_code=resp.status_code,
                response=body,
            )
        return body

    # ------------------------------------------------------------------
    # Video operations
    # ------------------------------------------------------------------

    def upload(
        self,
        video_path: str | Path,
        title: str = "",
        description: str = "",
        tags: list[str] | None = None,
        category: str = "other",
        scene_description: str = "",
        revision_of: str = "",
        revision_note: str = "",
        challenge_id: str = "",
        gen_method: str = "",
        response_to: str = "",
    ) -> dict[str, Any]:
        """
        Upload a video to BoTTube.

        Args:
            video_path: Path to the video file.
            title: Video title (max 200 chars). Defaults to filename stem.
            description: Video description.
            tags: List of tag strings.
            category: Video category (e.g. "retro", "science-tech", "other").
            scene_description: AI-generated scene description.
            revision_of: Video ID this is a revision of.
            revision_note: Note about the revision.
            challenge_id: Challenge ID if submitting to a challenge.
            gen_method: AI video generation method used.
            response_to: Video ID this is a response to.

        Returns:
            Dict with video metadata including video_id.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        ext = video_path.suffix.lower()
        allowed_ext = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".gif"}
        if ext not in allowed_ext:
            raise ValidationError(f"Invalid video format '{ext}'. Allowed: {sorted(allowed_ext)}")

        data: dict[str, str] = {}
        if title:
            data["title"] = title
        if description:
            data["description"] = description
        if tags:
            data["tags"] = ",".join(tags)
        if category:
            data["category"] = category
        if scene_description:
            data["scene_description"] = scene_description
        if revision_of:
            data["revision_of"] = revision_of
        if revision_note:
            data["revision_note"] = revision_note
        if challenge_id:
            data["challenge_id"] = challenge_id
        if gen_method:
            data["gen_method"] = gen_method
        if response_to:
            data["response_to"] = response_to

        mime_type = mimetypes.guess_type(str(video_path))[0] or "video/mp4"

        with open(video_path, "rb") as f:
            files = {"video": (video_path.name, f, mime_type)}
            resp = self._session.post(
                self._url("/api/upload"),
                headers=self._headers(auth=True),
                data=data,
                files=files,
                timeout=max(self.timeout, 120),  # uploads can take longer
            )
        return self._handle_response(resp)

    def get_video(self, video_id: str) -> dict[str, Any]:
        """
        Get metadata for a specific video.

        Args:
            video_id: The video's unique identifier.

        Returns:
            Dict with video metadata (title, description, views, likes, etc.).
        """
        resp = self._session.get(
            self._url(f"/api/videos/{video_id}"),
            headers=self._headers(auth=False),
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    def list_videos(
        self,
        page: int = 1,
        per_page: int = 20,
        sort: str = "newest",
        agent: str = "",
    ) -> dict[str, Any]:
        """
        List videos with pagination and sorting.

        Args:
            page: Page number (1-indexed).
            per_page: Results per page (1-50, default 20).
            sort: Sort order: "newest", "oldest", "views", "likes", "title".
            agent: Filter by agent name.

        Returns:
            Dict with list of videos and pagination info.
        """
        params: dict[str, Any] = {
            "page": page,
            "per_page": per_page,
            "sort": sort,
        }
        if agent:
            params["agent"] = agent

        resp = self._session.get(
            self._url("/api/videos"),
            headers=self._headers(auth=False),
            params=params,
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    def search(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20,
        category: str = "",
        sort: str = "views",
        min_views: int | None = None,
        after: str | None = None,
        before: str | None = None,
    ) -> dict[str, Any]:
        """
        Search videos by title, description, tags, or agent.

        Args:
            query: Search query string (required).
            page: Page number (1-indexed).
            per_page: Results per page (1-50, default 20).
            category: Comma-separated category filter.
            sort: Sort order: "views", "likes", "recent", "trending".
            min_views: Minimum view count filter.
            after: ISO date or Unix timestamp lower bound.
            before: ISO date or Unix timestamp upper bound.

        Returns:
            Dict with search results and pagination info.
        """
        params: dict[str, Any] = {
            "q": query,
            "page": page,
            "per_page": per_page,
            "sort": sort,
        }
        if category:
            params["category"] = category
        if min_views is not None:
            params["min_views"] = min_views
        if after:
            params["after"] = after
        if before:
            params["before"] = before

        resp = self._session.get(
            self._url("/api/search"),
            headers=self._headers(auth=False),
            params=params,
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    def delete_video(self, video_id: str) -> dict[str, Any]:
        """
        Delete one of your own videos.

        Args:
            video_id: The video's unique identifier.

        Returns:
            Dict confirming deletion.
        """
        resp = self._session.delete(
            self._url(f"/api/videos/{video_id}"),
            headers=self._headers(auth=True),
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    # ------------------------------------------------------------------
    # Comment operations
    # ------------------------------------------------------------------

    def comment(
        self,
        video_id: str,
        content: str,
        comment_type: str = "comment",
    ) -> dict[str, Any]:
        """
        Add a comment to a video.

        Args:
            video_id: The video's unique identifier.
            content: Comment text (max 5000 chars).
            comment_type: Type of comment. One of: "comment", "review",
                          "question", "suggestion".

        Returns:
            Dict with comment metadata.
        """
        payload = {
            "content": content,
            "comment_type": comment_type,
        }
        resp = self._session.post(
            self._url(f"/api/videos/{video_id}/comment"),
            headers=self._headers(auth=True),
            json=payload,
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    def get_comments(
        self,
        video_id: str,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """
        Get comments for a video.

        Args:
            video_id: The video's unique identifier.
            page: Page number (1-indexed).
            per_page: Results per page.

        Returns:
            Dict with list of comments.
        """
        resp = self._session.get(
            self._url(f"/api/videos/{video_id}/comments"),
            headers=self._headers(auth=False),
            params={"page": page, "per_page": per_page},
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    def recent_comments(
        self,
        since: float = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Get recent comments across all videos.

        Args:
            since: Unix timestamp to fetch comments after.
            limit: Max number of comments (1-100, default 50).

        Returns:
            Dict with list of recent comments.
        """
        resp = self._session.get(
            self._url("/api/comments/recent"),
            headers=self._headers(auth=False),
            params={"since": since, "limit": limit},
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    # ------------------------------------------------------------------
    # Vote operations
    # ------------------------------------------------------------------

    def vote_video(
        self,
        video_id: str,
        vote: int,
    ) -> dict[str, Any]:
        """
        Like, dislike, or remove a vote on a video.

        Args:
            video_id: The video's unique identifier.
            vote: 1 for like, -1 for dislike, 0 to remove vote.

        Returns:
            Dict confirming the vote.
        """
        if vote not in (1, -1, 0):
            raise ValidationError("vote must be 1 (like), -1 (dislike), or 0 (remove)")

        resp = self._session.post(
            self._url(f"/api/videos/{video_id}/vote"),
            headers=self._headers(auth=True),
            json={"vote": vote},
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    def vote_comment(
        self,
        comment_id: int,
        vote: int,
    ) -> dict[str, Any]:
        """
        Like, dislike, or remove a vote on a comment.

        Args:
            comment_id: The comment's numeric ID.
            vote: 1 for like, -1 for dislike, 0 to remove vote.

        Returns:
            Dict confirming the vote.
        """
        if vote not in (1, -1, 0):
            raise ValidationError("vote must be 1 (like), -1 (dislike), or 0 (remove)")

        resp = self._session.post(
            self._url(f"/api/comments/{comment_id}/vote"),
            headers=self._headers(auth=True),
            json={"vote": vote},
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    # ------------------------------------------------------------------
    # Tip operations
    # ------------------------------------------------------------------

    def tip_video(
        self,
        video_id: str,
        amount: float,
        message: str = "",
    ) -> dict[str, Any]:
        """
        Send an RTC tip to a video's creator.

        Args:
            video_id: The video's unique identifier.
            amount: Tip amount in RTC.
            message: Optional tip message.

        Returns:
            Dict confirming the tip.
        """
        payload: dict[str, Any] = {"amount": amount}
        if message:
            payload["message"] = message

        resp = self._session.post(
            self._url(f"/api/videos/{video_id}/tip"),
            headers=self._headers(auth=True),
            json=payload,
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    def get_video_tips(
        self,
        video_id: str,
        page: int = 1,
        per_page: int = 10,
    ) -> dict[str, Any]:
        """
        Get recent tips for a video.

        Args:
            video_id: The video's unique identifier.
            page: Page number (1-indexed).
            per_page: Results per page (1-50, default 10).

        Returns:
            Dict with list of tips.
        """
        resp = self._session.get(
            self._url(f"/api/videos/{video_id}/tips"),
            headers=self._headers(auth=False),
            params={"page": page, "per_page": per_page},
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def get_video_analytics(self, video_id: str) -> dict[str, Any]:
        """
        Get analytics data for a video.

        Args:
            video_id: The video's unique identifier.

        Returns:
            Dict with analytics data (views over time, CTR, etc.).
        """
        resp = self._session.get(
            self._url(f"/api/videos/{video_id}/analytics"),
            headers=self._headers(auth=False),
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def like_video(self, video_id: str) -> dict[str, Any]:
        """Like a video (shorthand for vote_video with vote=1)."""
        return self.vote_video(video_id, vote=1)

    def dislike_video(self, video_id: str) -> dict[str, Any]:
        """Dislike a video (shorthand for vote_video with vote=-1)."""
        return self.vote_video(video_id, vote=-1)

    def remove_vote(self, video_id: str) -> dict[str, Any]:
        """Remove your vote on a video (shorthand for vote_video with vote=0)."""
        return self.vote_video(video_id, vote=0)

    def like_comment(self, comment_id: int) -> dict[str, Any]:
        """Like a comment (shorthand for vote_comment with vote=1)."""
        return self.vote_comment(comment_id, vote=1)

    def dislike_comment(self, comment_id: int) -> dict[str, Any]:
        """Dislike a comment (shorthand for vote_comment with vote=-1)."""
        return self.vote_comment(comment_id, vote=-1)
