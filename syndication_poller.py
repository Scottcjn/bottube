#!/usr/bin/env python3
"""
BoTTube Syndication Queue Poller (Issue #310)

Daemon service that polls for new video uploads and manages the syndication
queue. Integrates with adapter interface, configuration management, and
scheduling controls.

Features:
    - Polls bottube_server for new uploads at configurable intervals
    - Automatically queues new videos for syndication to configured platforms
    - Processes pending queue items with backoff and retry logic
    - Graceful shutdown on SIGTERM/SIGINT
    - Configuration via YAML/JSON file with environment overrides
    - Cron-based scheduling with quiet hours support
    - Rate limiting per platform and global
    - Adapter-based platform integration

Usage:
    python3 syndication_poller.py

Configuration:
    Create syndication.yaml in project root or BOTTUBE_BASE_DIR:
    
    enabled: true
    poll_interval: 60
    platforms:
      moltbook:
        enabled: true
        priority: 10
        rate_limit: 30
        config:
          base_url: https://moltbook.com
          api_key: ${MOLTBOOK_API_KEY}
      twitter:
        enabled: true
        priority: 5
        rate_limit: 60
        config:
          api_key: ${TWITTER_API_KEY}
    schedule:
      enabled: true
      cron_expression: "*/5 * * * *"
      quiet_hours_start: "22:00"
      quiet_hours_end: "06:00"

Environment Variables:
    BOTTUBE_URL: Base URL for BoTTube API (default: http://localhost:8097)
    BOTTUBE_API_KEY: API key for authentication (required)
    BOTTUBE_DB_PATH: Path to SQLite database (default: ./bottube.db)
    BOTTUBE_SYNDICATION_CONFIG: Path to config file (optional)
    BOTTUBE_SYNDICATION_*: Override config values (see syndication_config.py)

Systemd Service:
    Copy syndication_poller.service to /etc/systemd/system/
    systemctl enable syndication_poller
    systemctl start syndication_poller
"""

import json
import logging
import os
import random
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# Add project root to path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from syndication_queue import QueueState, SyndicationQueue, get_queue
from syndication_config import (
    SyndicationConfig,
    SyndicationConfigManager,
    PlatformConfig,
    load_config,
    get_config,
)
from syndication_scheduler import (
    SyndicationScheduler,
    BatchProcessor,
    create_scheduler,
    create_batch_processor,
)
from syndication_adapter import (
    SyndicationAdapter,
    SyndicationPayload,
    get_adapter,
    list_adapters,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BOTTUBE_URL = os.environ.get("BOTTUBE_URL", "http://localhost:8097")
BOTTUBE_API_KEY = os.environ.get("BOTTUBE_API_KEY", "")
BOTTUBE_DB_PATH = os.environ.get(
    "BOTTUBE_DB_PATH",
    os.environ.get("BOTTUBE_BASE_DIR", str(ROOT)) + "/bottube.db",
)
CONFIG_FILE = os.environ.get("BOTTUBE_SYNDICATION_CONFIG", "")
LOG_LEVEL = os.environ.get("BOTTUBE_SYNDICATION_LOG_LEVEL", "INFO")

# Backoff configuration
INITIAL_BACKOFF_SEC = 5
MAX_BACKOFF_SEC = 300  # 5 minutes
BACKOFF_MULTIPLIER = 2.0
JITTER_FACTOR = 0.1

# Processing timeout
ITEM_PROCESSING_TIMEOUT_SEC = 600  # 10 minutes max per item


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bottube-syndication-poller")


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class VideoInfo:
    """Information about a video from the API."""
    video_id: str
    title: str
    agent_id: int
    agent_name: str
    created_at: float


# ---------------------------------------------------------------------------
# Syndication Poller
# ---------------------------------------------------------------------------

class SyndicationPoller:
    """
    Polls for new uploads and manages the syndication queue.

    Integrates with:
        - SyndicationConfigManager: Configuration management
        - SyndicationScheduler: Cron scheduling and rate limiting
        - SyndicationAdapter: Platform-specific syndication
        - SyndicationQueue: Queue state management

    Runs as a daemon, polling at regular intervals and processing
    pending queue items.
    """

    def __init__(
        self,
        bottube_url: str = BOTTUBE_URL,
        api_key: str = BOTTUBE_API_KEY,
        db_path: str = BOTTUBE_DB_PATH,
        config_file: Optional[str] = None,
    ):
        self.bottube_url = bottube_url.rstrip("/")
        self.api_key = api_key
        self.db_path = db_path
        
        # Load configuration
        config_path = config_file or CONFIG_FILE
        self.config_manager = SyndicationConfigManager()
        if config_path:
            self.config = self.config_manager.load(config_path)
        else:
            self.config = self.config_manager.load()
        
        # Initialize scheduler and batch processor
        self.scheduler = create_scheduler(self.config)
        self.batch_processor = create_batch_processor(self.config)
        
        # Initialize queue
        self.queue = SyndicationQueue(db_path)
        
        # Initialize adapters for enabled platforms
        self.adapters: Dict[str, SyndicationAdapter] = {}
        self._init_adapters()
        
        self.running = False
        self.known_video_ids: set[str] = set()
        self.last_poll_time: float = 0.0
        self.backoff_until: float = 0.0
        self.consecutive_failures: int = 0
        
        # Track items being processed to avoid double-processing
        self.processing_items: set[int] = set()
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        signal.signal(signal.SIGINT, self._shutdown_handler)
        
        log.info("Initialized poller with platforms: %s",
                ", ".join(self.config.get_enabled_platforms()))

    def _init_adapters(self):
        """Initialize adapters for enabled platforms."""
        for platform_name in self.config.get_enabled_platforms():
            platform_config = self.config.get_platform(platform_name)
            if platform_config:
                try:
                    adapter_config = platform_config.config.copy()
                    # Inject common settings
                    adapter_config.setdefault("timeout", platform_config.timeout)
                    
                    adapter = get_adapter(platform_name, adapter_config)
                    if adapter.validate_config():
                        self.adapters[platform_name] = adapter
                        log.info("Initialized adapter for %s", platform_name)
                    else:
                        log.warning("Adapter config validation failed for %s",
                                  platform_name)
                except Exception as e:
                    log.error("Failed to initialize adapter for %s: %s",
                            platform_name, e)

    def _shutdown_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        log.info("Shutdown signal received (%s), stopping...", signum)
        self.running = False

    def _api_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        timeout: int = 30,
    ) -> Optional[requests.Response]:
        """Make an authenticated API request."""
        url = f"{self.bottube_url}{endpoint}"
        headers = {"X-API-Key": self.api_key}
        
        try:
            if method == "GET":
                return requests.get(url, headers=headers, params=params, timeout=timeout)
            elif method == "POST":
                return requests.post(
                    url, headers=headers, json=data, timeout=timeout
                )
        except requests.RequestException as e:
            log.warning("API request failed: %s", e)
        
        return None

    def fetch_new_videos(self, since: Optional[float] = None) -> List[VideoInfo]:
        """
        Fetch videos from the API, optionally filtered by creation time.
        
        Returns list of new videos not yet in known_video_ids.
        """
        params = {"per_page": 50}
        if since:
            params["since"] = str(since)
        
        response = self._api_request("/api/feed", params=params)
        if not response or response.status_code != 200:
            log.warning("Failed to fetch videos: %s", 
                       response.status_code if response else "no response")
            return []
        
        videos_data = response.json().get("videos", [])
        new_videos = []
        
        for v in videos_data:
            video_id = v.get("video_id")
            if video_id and video_id not in self.known_video_ids:
                self.known_video_ids.add(video_id)
                new_videos.append(VideoInfo(
                    video_id=video_id,
                    title=v.get("title", "Untitled"),
                    agent_id=v.get("agent_id", 0),
                    agent_name=v.get("agent_name", "unknown"),
                    created_at=v.get("created_at", time.time()),
                ))
        
        log.info("Fetched %d videos, %d new", len(videos_data), len(new_videos))
        return new_videos

    def queue_new_videos(self, videos: List[VideoInfo]) -> int:
        """
        Queue new videos for syndication to all configured platforms.

        Returns the number of items queued.
        """
        queued_count = 0

        for video in videos:
            for platform_name in self.config.get_enabled_platforms():
                platform_config = self.config.get_platform(platform_name)
                if not platform_config or not platform_config.enabled:
                    continue
                    
                # Calculate priority based on platform config
                priority = self._calculate_priority(platform_name, video, platform_config)

                metadata = {
                    "queued_by": "syndication_poller",
                    "video_created_at": video.created_at,
                    "platform_priority": platform_config.priority,
                }

                self.queue.enqueue(
                    video_id=video.video_id,
                    video_title=video.title,
                    agent_id=video.agent_id,
                    agent_name=video.agent_name,
                    target_platform=platform_name,
                    priority=priority,
                    metadata=metadata,
                )
                queued_count += 1
                log.info("Queued '%s' for %s (priority=%d)",
                        video.title, platform_name, priority)

        return queued_count

    def _calculate_priority(
        self,
        platform: str,
        video: VideoInfo,
        platform_config: PlatformConfig,
    ) -> int:
        """
        Calculate syndication priority for a video/platform combination.

        Higher priority = processed first.
        """
        # Start with configured platform priority
        base_priority = platform_config.priority

        # Boost priority for recent uploads (last hour)
        age_hours = (time.time() - video.created_at) / 3600
        if age_hours < 1:
            base_priority += 20
        elif age_hours < 6:
            base_priority += 10

        return base_priority

    def process_pending_items(self) -> int:
        """
        Process pending items in the queue.

        Returns the number of items processed.
        """
        processed_count = 0

        for platform_name in self.config.get_enabled_platforms():
            # Check scheduler - should we run now?
            if not self.scheduler.should_run():
                next_run = self.scheduler.get_next_run_time()
                log.debug("Scheduler says not to run, next run: %s", next_run)
                continue

            # Check rate limit
            if not self.scheduler.acquire_rate_limit(platform_name):
                wait_time = self.scheduler.get_rate_limit_wait_time(platform_name)
                log.debug("Rate limited for %s, wait %.1fs", platform_name, wait_time)
                continue

            # Check batch processing
            if not self.batch_processor.should_process():
                self.batch_processor.wait_if_needed()

            item = self.queue.dequeue(target_platform=platform_name)
            if not item:
                continue

            if item.id in self.processing_items:
                log.debug("Item %d already being processed, skipping", item.id)
                continue

            # Check for stale processing items (timeout)
            if item.state == QueueState.PROCESSING:
                if time.time() - item.updated_at > ITEM_PROCESSING_TIMEOUT_SEC:
                    log.warning("Item %d stuck in processing, resetting", item.id)
                    self.queue.update_state(
                        item.id, QueueState.PENDING,
                        error_message="Processing timeout, retrying"
                    )
                continue

            self.processing_items.add(item.id)

            try:
                success = self._process_item(item)
                if success:
                    self.batch_processor.record_processed()
                    processed_count += 1
            except Exception as e:
                log.error("Error processing item %d: %s", item.id, e)
                self.queue.mark_failed(item.id, str(e))
            finally:
                self.processing_items.discard(item.id)

        return processed_count

    def _process_item(self, item) -> bool:
        """
        Process a single syndication item using adapter.

        Returns True if successful, False otherwise.
        """
        log.info("Processing syndication item %d: '%s' -> %s",
                item.id, item.video_title, item.target_platform)

        # Mark as processing
        if not self.queue.mark_processing(item.id):
            log.error("Failed to mark item %d as processing", item.id)
            return False

        # Get adapter for platform
        adapter = self.adapters.get(item.target_platform)
        if not adapter:
            log.warning("No adapter for platform: %s", item.target_platform)
            # Fall back to legacy handlers for backwards compatibility
            return self._process_item_legacy(item)

        # Build payload for adapter
        payload = self._build_payload(item)

        try:
            result = adapter.syndicate(payload)
            if result.success:
                self.queue.mark_completed(item.id, metadata=result.to_dict())
                log.info("Syndication successful for item %d via %s",
                        item.id, item.target_platform)
                return True
            else:
                self.queue.mark_failed(item.id, result.error_message or "Unknown error")
                log.warning("Syndication failed for item %d: %s",
                          item.id, result.error_message)
                return False
        except Exception as e:
            self.queue.mark_failed(item.id, str(e))
            log.error("Syndication exception for item %d: %s", item.id, e)
            return False

    def _build_payload(self, item) -> SyndicationPayload:
        """Build syndication payload from queue item."""
        # Fetch video details from API
        video_data = self._get_video_details(item.video_id) or {}
        
        return SyndicationPayload(
            video_id=item.video_id,
            video_title=item.video_title,
            video_description=video_data.get("description", ""),
            video_url=f"{self.bottube_url}/videos/{item.video_id}",
            thumbnail_url=video_data.get("thumbnail_url"),
            agent_id=item.agent_id,
            agent_name=item.agent_name,
            tags=video_data.get("tags", []),
            metadata=item.metadata,
        )

    def _get_video_details(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Fetch video details from API."""
        response = self._api_request(f"/api/videos/{video_id}")
        if response and response.status_code == 200:
            return response.json()
        return None

    def _process_item_legacy(self, item) -> bool:
        """
        Legacy item processing for platforms without adapters.
        Falls back to built-in handlers.
        """
        platform_handlers = {
            "moltbook": self._syndicate_to_moltbook,
            "twitter": self._syndicate_to_twitter,
            "rss_feed": self._syndicate_to_rss_feed,
        }

        handler = platform_handlers.get(item.target_platform)
        if not handler:
            log.warning("No handler for platform: %s", item.target_platform)
            self.queue.mark_completed(item.id, metadata={"skipped": True})
            return True

        try:
            result = handler(item)
            if result.get("success"):
                self.queue.mark_completed(item.id, metadata=result)
                log.info("Syndication successful for item %d", item.id)
                return True
            else:
                error_msg = result.get("error", "Unknown error")
                self.queue.mark_failed(item.id, error_msg)
                log.warning("Syndication failed for item %d: %s", item.id, error_msg)
                return False
        except Exception as e:
            self.queue.mark_failed(item.id, str(e))
            log.error("Syndication exception for item %d: %s", item.id, e)
            return False

    def _syndicate_to_moltbook(self, item) -> dict:
        """
        Syndicate a video to Moltbook.
        
        Posts to Moltbook's API with video metadata.
        """
        # Placeholder implementation - integrate with actual Moltbook API
        log.info("Syndicating '%s' to Moltbook", item.video_title)
        
        # Simulate API call (replace with actual integration)
        # response = requests.post(
        #     "https://moltbook.com/api/videos",
        #     headers={"Authorization": f"Bearer {MOLTBOOK_TOKEN}"},
        #     json={
        #         "title": item.video_title,
        #         "source": "bottube",
        #         "video_id": item.video_id,
        #     },
        #     timeout=30,
        # )
        
        # For now, simulate success
        time.sleep(0.1)  # Simulate network delay
        
        return {
            "success": True,
            "platform": "moltbook",
            "external_id": f"moltbook_{item.video_id}",
        }

    def _syndicate_to_twitter(self, item) -> dict:
        """
        Syndicate a video to Twitter/X.
        
        Creates a tweet with video link.
        """
        log.info("Syndicating '%s' to Twitter", item.video_title)
        
        # Placeholder - integrate with Twitter API v2
        # This would use tweepy or direct API calls
        
        time.sleep(0.1)
        
        return {
            "success": True,
            "platform": "twitter",
            "tweet_id": f"tweet_{item.video_id}",
        }

    def _syndicate_to_rss_feed(self, item) -> dict:
        """
        Syndicate to RSS feed.
        
        Updates the RSS feed with new video entry.
        """
        log.info("Adding '%s' to RSS feed", item.video_title)
        
        # RSS feed updates are typically file-based or cached
        # This is a placeholder for the actual implementation
        
        time.sleep(0.1)
        
        return {
            "success": True,
            "platform": "rss_feed",
            "feed_entry_id": f"rss_{item.video_id}",
        }

    def apply_backoff(self):
        """Apply exponential backoff after failures."""
        backoff_time = min(
            INITIAL_BACKOFF_SEC * (BACKOFF_MULTIPLIER ** self.consecutive_failures),
            MAX_BACKOFF_SEC,
        )
        jitter = backoff_time * JITTER_FACTOR * random.random()
        self.backoff_until = time.time() + backoff_time + jitter
        log.info("Applying backoff: %.1f seconds (failures=%d)",
                backoff_time + jitter, self.consecutive_failures)

    def run(self):
        """
        Main poller loop.

        Continuously polls for new videos and processes the queue.
        """
        if not self.api_key:
            log.error("BOTTUBE_API_KEY not set, exiting")
            return

        self.running = True
        log.info("Starting syndication poller")
        log.info("  BoTTube URL: %s", self.bottube_url)
        log.info("  Database: %s", self.db_path)
        log.info("  Poll interval: %ds", self.config.poll_interval)
        log.info("  Enabled platforms: %s",
                ", ".join(self.config.get_enabled_platforms()))
        log.info("  Schedule: %s", self.config.schedule.cron_expression)
        if self.config.schedule.quiet_hours_start:
            log.info("  Quiet hours: %s - %s",
                    self.config.schedule.quiet_hours_start,
                    self.config.schedule.quiet_hours_end)

        # Load existing videos to avoid re-queueing on restart
        self._load_known_videos()

        last_config_reload = time.time()
        config_reload_interval = 300  # Reload config every 5 minutes

        while self.running:
            try:
                # Reload configuration periodically
                if time.time() - last_config_reload > config_reload_interval:
                    self.config = self.config_manager.reload()
                    last_config_reload = time.time()
                    log.debug("Reloaded configuration")

                # Check backoff
                if time.time() < self.backoff_until:
                    remaining = self.backoff_until - time.time()
                    time.sleep(min(remaining, 10))
                    continue

                # Poll for new videos
                new_videos = self.fetch_new_videos(
                    since=self.last_poll_time if self.last_poll_time > 0 else None
                )

                if new_videos:
                    queued = self.queue_new_videos(new_videos)
                    log.info("Queued %d new syndication items", queued)
                    self.consecutive_failures = 0
                else:
                    self.consecutive_failures = max(0, self.consecutive_failures - 1)

                self.last_poll_time = time.time()

                # Process pending queue items
                processed = self.process_pending_items()
                if processed > 0:
                    log.info("Processed %d queue items", processed)

                # Cleanup old completed items periodically
                if random.random() < 0.01:  # ~1% chance each cycle
                    deleted = self.queue.cleanup_old(days=30)
                    if deleted > 0:
                        log.info("Cleaned up %d old queue items", deleted)

                # Sleep until next poll
                sleep_time = self.config.poll_interval
                if self.running:
                    time.sleep(sleep_time)

            except KeyboardInterrupt:
                log.info("Interrupted by user")
                break
            except Exception as e:
                log.error("Poller error: %s", e)
                self.consecutive_failures += 1
                self.apply_backoff()

        log.info("Syndication poller stopped")

    def _load_known_videos(self):
        """Load existing video IDs to avoid duplicate queueing on restart."""
        try:
            response = self._api_request("/api/feed", params={"per_page": 100})
            if response and response.status_code == 200:
                videos = response.json().get("videos", [])
                for v in videos:
                    if "video_id" in v:
                        self.known_video_ids.add(v["video_id"])
                log.info("Loaded %d known video IDs", len(self.known_video_ids))
        except Exception as e:
            log.warning("Could not load known videos: %s", e)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    """Main entry point for the syndication poller daemon."""
    poller = SyndicationPoller()
    poller.run()


if __name__ == "__main__":
    main()
