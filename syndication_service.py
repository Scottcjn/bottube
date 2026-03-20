import os
import sqlite3
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from threading import Thread, Event
import requests
import schedule

from flask import g

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PlatformConfig:
    name: str
    enabled: bool
    api_credentials: Dict[str, str]
    posting_schedule: str
    format_requirements: Dict[str, Any]
    attribution_template: str

@dataclass
class SyndicationJob:
    id: Optional[int]
    video_id: int
    platform: str
    status: str
    scheduled_time: datetime
    external_id: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

class BasePlatformAdapter:
    def __init__(self, config: PlatformConfig):
        self.config = config
        self.name = config.name

    def prepare_content(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """Adapt content for platform-specific requirements"""
        raise NotImplementedError

    def upload(self, content: Dict[str, Any]) -> Dict[str, str]:
        """Upload content to platform"""
        raise NotImplementedError

    def get_engagement_stats(self, external_id: str) -> Dict[str, int]:
        """Retrieve engagement metrics from platform"""
        raise NotImplementedError

class YouTubeShortsAdapter(BasePlatformAdapter):
    def prepare_content(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        title = video_data['title']
        if len(title) > 100:
            title = title[:97] + "..."

        description = f"{video_data['description']}\n\n🤖 Created with BoTTube AI\n👉 Watch more: https://bottube.ai"

        return {
            'title': title,
            'description': description,
            'video_path': video_data['file_path'],
            'tags': ['AI', 'BoTTube', 'Shorts'] + video_data.get('tags', []),
            'category_id': '28'  # Science & Technology
        }

    def upload(self, content: Dict[str, Any]) -> Dict[str, str]:
        # YouTube API v3 implementation would go here
        logger.info(f"Uploading to YouTube Shorts: {content['title']}")
        return {'external_id': f"yt_short_{int(time.time())}", 'status': 'success'}

    def get_engagement_stats(self, external_id: str) -> Dict[str, int]:
        return {'views': 0, 'likes': 0, 'comments': 0}

class TikTokAdapter(BasePlatformAdapter):
    def prepare_content(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        description = f"{video_data['title']}\n\n#AI #BoTTube #TechTok"
        if len(description) > 2200:
            description = description[:2197] + "..."

        return {
            'description': description,
            'video_path': video_data['file_path'],
            'privacy_level': 'public_to_everyone'
        }

    def upload(self, content: Dict[str, Any]) -> Dict[str, str]:
        logger.info(f"Uploading to TikTok: {content['description'][:50]}...")
        return {'external_id': f"tiktok_{int(time.time())}", 'status': 'success'}

    def get_engagement_stats(self, external_id: str) -> Dict[str, int]:
        return {'views': 0, 'likes': 0, 'comments': 0, 'shares': 0}

class InstagramReelsAdapter(BasePlatformAdapter):
    def prepare_content(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        caption = f"{video_data['title']}\n\n🤖 Made with BoTTube AI\n#AI #Tech #BoTTube #Reels"

        return {
            'caption': caption,
            'video_path': video_data['file_path'],
            'share_to_feed': True
        }

    def upload(self, content: Dict[str, Any]) -> Dict[str, str]:
        logger.info(f"Uploading to Instagram Reels: {content['caption'][:50]}...")
        return {'external_id': f"ig_reel_{int(time.time())}", 'status': 'success'}

    def get_engagement_stats(self, external_id: str) -> Dict[str, int]:
        return {'views': 0, 'likes': 0, 'comments': 0}

class TwitterAdapter(BasePlatformAdapter):
    def prepare_content(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        title = video_data['title']
        if len(title) > 240:
            title = title[:237] + "..."

        tweet = f"{title}\n\n🤖 Created with BoTTube AI\n🎥 Watch more: https://bottube.ai"

        return {
            'text': tweet,
            'media_path': video_data['file_path']
        }

    def upload(self, content: Dict[str, Any]) -> Dict[str, str]:
        logger.info(f"Posting to Twitter/X: {content['text'][:50]}...")
        return {'external_id': f"tweet_{int(time.time())}", 'status': 'success'}

    def get_engagement_stats(self, external_id: str) -> Dict[str, int]:
        return {'views': 0, 'likes': 0, 'retweets': 0, 'replies': 0}

class RedditAdapter(BasePlatformAdapter):
    def prepare_content(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        title = video_data['title']
        if len(title) > 300:
            title = title[:297] + "..."

        return {
            'title': f"{title} [Created with BoTTube AI]",
            'subreddit': self.config.format_requirements.get('subreddit', 'artificial'),
            'video_path': video_data['file_path'],
            'flair_text': 'AI Generated'
        }

    def upload(self, content: Dict[str, Any]) -> Dict[str, str]:
        logger.info(f"Posting to Reddit r/{content['subreddit']}: {content['title'][:50]}...")
        return {'external_id': f"reddit_{int(time.time())}", 'status': 'success'}

    def get_engagement_stats(self, external_id: str) -> Dict[str, int]:
        return {'upvotes': 0, 'downvotes': 0, 'comments': 0}

class SyndicationService:
    def __init__(self):
        self.adapters = {}
        self.running = False
        self.stop_event = Event()
        self.poll_interval = 300  # 5 minutes
        self.init_platform_adapters()

    def init_platform_adapters(self):
        """Initialize platform adapters with configurations"""
        platforms = [
            PlatformConfig(
                name="youtube_shorts",
                enabled=True,
                api_credentials={},
                posting_schedule="immediate",
                format_requirements={'max_duration': 60, 'aspect_ratio': '9:16'},
                attribution_template="🤖 Created with BoTTube AI | Watch more: https://bottube.ai"
            ),
            PlatformConfig(
                name="tiktok",
                enabled=True,
                api_credentials={},
                posting_schedule="staggered_15min",
                format_requirements={'max_duration': 60, 'aspect_ratio': '9:16'},
                attribution_template="#AI #BoTTube"
            ),
            PlatformConfig(
                name="instagram_reels",
                enabled=True,
                api_credentials={},
                posting_schedule="staggered_30min",
                format_requirements={'max_duration': 90, 'aspect_ratio': '9:16'},
                attribution_template="🤖 Made with BoTTube AI #AI #Tech #BoTTube"
            ),
            PlatformConfig(
                name="twitter",
                enabled=True,
                api_credentials={},
                posting_schedule="staggered_45min",
                format_requirements={'max_duration': 140, 'max_file_size': '512MB'},
                attribution_template="🤖 Created with BoTTube AI 🎥 https://bottube.ai"
            ),
            PlatformConfig(
                name="reddit",
                enabled=True,
                api_credentials={},
                posting_schedule="daily",
                format_requirements={'subreddit': 'artificial'},
                attribution_template="[Created with BoTTube AI]"
            )
        ]

        adapter_classes = {
            'youtube_shorts': YouTubeShortsAdapter,
            'tiktok': TikTokAdapter,
            'instagram_reels': InstagramReelsAdapter,
            'twitter': TwitterAdapter,
            'reddit': RedditAdapter
        }

        for config in platforms:
            if config.enabled and config.name in adapter_classes:
                self.adapters[config.name] = adapter_classes[config.name](config)

    def get_db(self):
        """Get database connection"""
        if 'db' not in g:
            g.db = sqlite3.connect('bottube.db')
            g.db.row_factory = sqlite3.Row
        return g.db

    def init_syndication_tables(self):
        """Initialize syndication tracking tables"""
        db = self.get_db()

        db.execute('''
            CREATE TABLE IF NOT EXISTS syndication_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                scheduled_time TIMESTAMP,
                external_id TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (video_id) REFERENCES videos (id)
            )
        ''')

        db.execute('''
            CREATE TABLE IF NOT EXISTS platform_engagement (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                external_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value INTEGER DEFAULT 0,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES syndication_jobs (id)
            )
        ''')

        db.execute('''
            CREATE TABLE IF NOT EXISTS syndication_config (
                platform TEXT PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                config_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        db.commit()

    def poll_for_new_videos(self):
        """Poll for new BoTTube uploads to syndicate"""
        try:
            db = self.get_db()

            # Get videos uploaded in the last poll interval that haven't been syndicated
            cutoff_time = datetime.now() - timedelta(seconds=self.poll_interval)

            cursor = db.execute('''
                SELECT v.* FROM videos v
                WHERE v.created_at > ?
                AND v.status = 'completed'
                AND NOT EXISTS (
                    SELECT 1 FROM syndication_jobs sj
                    WHERE sj.video_id = v.id
                )
                ORDER BY v.created_at DESC
            ''', (cutoff_time,))

            new_videos = cursor.fetchall()

            for video in new_videos:
                self.schedule_syndication(dict(video))

            logger.info(f"Found {len(new_videos)} new videos for syndication")

        except Exception as e:
            logger.error(f"Error polling for new videos: {e}")

    def schedule_syndication(self, video_data: Dict[str, Any]):
        """Schedule syndication jobs for a video across all enabled platforms"""
        db = self.get_db()
        base_time = datetime.now()

        schedule_delays = {
            'immediate': 0,
            'staggered_15min': 15,
            'staggered_30min': 30,
            'staggered_45min': 45,
            'daily': 1440  # 24 hours in minutes
        }

        for platform_name, adapter in self.adapters.items():
            if adapter.config.enabled:
                delay_minutes = schedule_delays.get(adapter.config.posting_schedule, 0)
                scheduled_time = base_time + timedelta(minutes=delay_minutes)

                db.execute('''
                    INSERT INTO syndication_jobs
                    (video_id, platform, status, scheduled_time)
                    VALUES (?, ?, ?, ?)
                ''', (video_data['id'], platform_name, 'scheduled', scheduled_time))

        db.commit()
        logger.info(f"Scheduled syndication for video {video_data['id']} across {len(self.adapters)} platforms")

    def process_scheduled_jobs(self):
        """Process syndication jobs that are ready to execute"""
        try:
            db = self.get_db()

            cursor = db.execute('''
                SELECT sj.*, v.title, v.description, v.file_path, v.tags
                FROM syndication_jobs sj
                JOIN videos v ON sj.video_id = v.id
                WHERE sj.status = 'scheduled'
                AND sj.scheduled_time <= ?
                ORDER BY sj.scheduled_time ASC
            ''', (datetime.now(),))

            ready_jobs = cursor.fetchall()

            for job_row in ready_jobs:
                job_data = dict(job_row)
                self.execute_syndication_job(job_data)

        except Exception as e:
            logger.error(f"Error processing scheduled jobs: {e}")

    def execute_syndication_job(self, job_data: Dict[str, Any]):
        """Execute a single syndication job"""
        try:
            db = self.get_db()
            platform_name = job_data['platform']

            if platform_name not in self.adapters:
                self.update_job_status(job_data['id'], 'failed',
                                     f"No adapter found for platform: {platform_name}")
                return

            adapter = self.adapters[platform_name]

            # Update status to processing
            self.update_job_status(job_data['id'], 'processing')

            # Prepare content for the platform
            video_data = {
                'title': job_data['title'],
                'description': job_data['description'],
                'file_path': job_data['file_path'],
                'tags': json.loads(job_data['tags']) if job_data['tags'] else []
            }

            prepared_content = adapter.prepare_content(video_data)

            # Upload to platform
            result = adapter.upload(prepared_content)

            if result.get('status') == 'success':
                external_id = result.get('external_id')
                self.update_job_status(job_data['id'], 'completed', external_id=external_id)
                logger.info(f"Successfully syndicated video {job_data['video_id']} to {platform_name}")
            else:
                error_msg = result.get('error', 'Upload failed')
                self.update_job_status(job_data['id'], 'failed', error_msg)

        except Exception as e:
            error_msg = f"Syndication failed: {str(e)}"
            self.update_job_status(job_data['id'], 'failed', error_msg)
            logger.error(f"Error executing syndication job {job_data['id']}: {e}")

    def update_job_status(self, job_id: int, status: str, error_message: str = None, external_id: str = None):
        """Update syndication job status"""
        db = self.get_db()

        db.execute('''
            UPDATE syndication_jobs
            SET status = ?, error_message = ?, external_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, error_message, external_id, job_id))

        db.commit()

    def collect_engagement_metrics(self):
        """Collect engagement metrics from all platforms"""
        try:
            db = self.get_db()

            cursor = db.execute('''
                SELECT * FROM syndication_jobs
                WHERE status = 'completed' AND external_id IS NOT NULL
            ''')

            completed_jobs = cursor.fetchall()

            for job in completed_jobs:
                job_dict = dict(job)
                platform_name = job_dict['platform']
                external_id = job_dict['external_id']

                if platform_name in self.adapters:
                    adapter = self.adapters[platform_name]
                    try:
                        metrics = adapter.get_engagement_stats(external_id)
                        self.store_engagement_metrics(job_dict['id'], platform_name, external_id, metrics)
                    except Exception as e:
                        logger.warning(f"Failed to collect metrics for {platform_name} job {job_dict['id']}: {e}")

        except Exception as e:
            logger.error(f"Error collecting engagement metrics: {e}")

    def store_engagement_metrics(self, job_id: int, platform: str, external_id: str, metrics: Dict[str, int]):
        """Store engagement metrics in database"""
        db = self.get_db()

        for metric_name, metric_value in metrics.items():
            db.execute('''
                INSERT OR REPLACE INTO platform_engagement
                (job_id, platform, external_id, metric_name, metric_value, recorded_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (job_id, platform, external_id, metric_name, metric_value))

        db.commit()

    def get_syndication_stats(self) -> Dict[str, Any]:
        """Get syndication statistics"""
        db = self.get_db()

        stats = {}

        # Total jobs by status
        cursor = db.execute('''
            SELECT status, COUNT(*) as count
            FROM syndication_jobs
            GROUP BY status
        ''')
        stats['jobs_by_status'] = dict(cursor.fetchall())

        # Jobs by platform
        cursor = db.execute('''
            SELECT platform, COUNT(*) as count
            FROM syndication_jobs
            GROUP BY platform
        ''')
        stats['jobs_by_platform'] = dict(cursor.fetchall())

        # Recent engagement totals
        cursor = db.execute('''
            SELECT platform, metric_name, SUM(metric_value) as total
            FROM platform_engagement pe
            JOIN syndication_jobs sj ON pe.job_id = sj.id
            WHERE pe.recorded_at >= datetime('now', '-7 days')
            GROUP BY platform, metric_name
        ''')

        engagement_stats = {}
        for row in cursor.fetchall():
            platform, metric, total = row
            if platform not in engagement_stats:
                engagement_stats[platform] = {}
            engagement_stats[platform][metric] = total

        stats['weekly_engagement'] = engagement_stats

        return stats

    def start_syndication_service(self):
        """Start the syndication service with scheduled tasks"""
        if self.running:
            return

        self.running = True
        self.init_syndication_tables()

        # Schedule periodic tasks
        schedule.every(5).minutes.do(self.poll_for_new_videos)
        schedule.every(1).minute.do(self.process_scheduled_jobs)
        schedule.every(30).minutes.do(self.collect_engagement_metrics)

        def run_scheduler():
            while self.running and not self.stop_event.is_set():
                schedule.run_pending()
                time.sleep(30)

        scheduler_thread = Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()

        logger.info("Syndication service started")

    def stop_syndication_service(self):
        """Stop the syndication service"""
        self.running = False
        self.stop_event.set()
        schedule.clear()
        logger.info("Syndication service stopped")

# Global syndication service instance
syndication_service = SyndicationService()
