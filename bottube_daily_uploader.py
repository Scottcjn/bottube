import os
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass

import requests
from flask import g
from apscheduler.schedulers.background import BackgroundScheduler
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, ColorClip
import random
import tempfile
import atexit

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('daily_uploader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class VideoUpload:
    id: Optional[int]
    title: str
    description: str
    video_path: str
    upload_date: str
    status: str
    bottube_id: Optional[str] = None
    error_msg: Optional[str] = None

class DailyUploaderBot:
    def __init__(self):
        self.api_key = os.getenv('BOTTUBE_API_KEY')
        self.api_url = os.getenv('BOTTUBE_API_URL', 'http://localhost:5000')
        self.upload_dir = os.path.join(os.path.dirname(__file__), 'generated_videos')

        if not self.api_key:
            raise ValueError("BOTTUBE_API_KEY environment variable required")

        # Create upload directory
        os.makedirs(self.upload_dir, exist_ok=True)

        # Initialize scheduler
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        atexit.register(lambda: self.scheduler.shutdown())

        # Schedule daily uploads at 9 AM
        self.scheduler.add_job(
            func=self.generate_and_upload_daily_video,
            trigger="cron",
            hour=9,
            minute=0,
            id='daily_upload'
        )

        logger.info("Daily uploader bot initialized")

    def get_db(self):
        """Get database connection using Flask pattern"""
        if 'db' not in g:
            db_path = os.path.join(os.path.dirname(__file__), 'daily_uploads.db')
            g.db = sqlite3.connect(db_path)
            g.db.row_factory = sqlite3.Row
            self._init_db()
        return g.db

    def _init_db(self):
        """Initialize database tables"""
        db = g.db
        db.execute('''
            CREATE TABLE IF NOT EXISTS video_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                video_path TEXT NOT NULL,
                upload_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                bottube_id TEXT,
                error_msg TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.commit()

    def generate_video_content(self) -> Dict[str, str]:
        """Generate unique video title and description"""
        topics = [
            "Daily Motivation", "Tech Tips", "Life Hacks", "Fun Facts",
            "Quick Tutorial", "Daily Inspiration", "Productivity Tips",
            "Health & Wellness", "Creative Ideas", "Learning Moments"
        ]

        colors = ["Blue", "Green", "Purple", "Orange", "Red", "Teal"]
        adjectives = ["Amazing", "Incredible", "Awesome", "Fantastic", "Cool", "Great"]

        topic = random.choice(topics)
        color = random.choice(colors)
        adjective = random.choice(adjectives)
        date_str = datetime.now().strftime("%B %d, %Y")

        title = f"{adjective} {topic} - {date_str}"

        descriptions = [
            f"Join us for today's {topic.lower()} session! Discover something new every day.",
            f"Daily dose of {topic.lower()} to brighten your day. Subscribe for more!",
            f"Quick {topic.lower()} video to inspire and educate. What will you learn today?",
            f"Your daily {topic.lower()} content is here! Stay tuned for more awesome videos."
        ]

        description = random.choice(descriptions)

        return {"title": title, "description": description, "color": color.lower()}

    def create_simple_video(self, title: str, color: str) -> str:
        """Generate a simple video using MoviePy"""
        try:
            # Create temporary file
            video_file = os.path.join(self.upload_dir, f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")

            # Create background clip
            duration = 30  # 30 second video
            background = ColorClip(size=(1280, 720), color=color, duration=duration)

            # Create title text
            title_clip = TextClip(
                title,
                fontsize=48,
                color='white',
                font='Arial',
                size=(1200, None)
            ).set_position('center').set_duration(duration)

            # Create date text
            date_text = datetime.now().strftime("Created on %B %d, %Y")
            date_clip = TextClip(
                date_text,
                fontsize=24,
                color='lightgray',
                font='Arial'
            ).set_position(('center', 'bottom')).set_duration(duration).set_margin(50)

            # Composite video
            final_video = CompositeVideoClip([background, title_clip, date_clip])

            # Write video file
            final_video.write_videofile(
                video_file,
                fps=24,
                codec='libx264',
                audio_codec='aac',
                verbose=False,
                logger=None
            )

            # Clean up
            final_video.close()
            background.close()
            title_clip.close()
            date_clip.close()

            logger.info(f"Video generated: {video_file}")
            return video_file

        except Exception as e:
            logger.error(f"Video generation failed: {str(e)}")
            raise

    def upload_to_bottube(self, video_path: str, title: str, description: str) -> Dict[str, Any]:
        """Upload video to BoTTube via API"""
        try:
            upload_url = f"{self.api_url}/api/upload"

            with open(video_path, 'rb') as video_file:
                files = {'video': video_file}
                data = {
                    'title': title,
                    'description': description,
                    'api_key': self.api_key
                }

                response = requests.post(upload_url, files=files, data=data, timeout=300)

                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Upload successful: {result.get('video_id', 'unknown')}")
                    return {"success": True, "video_id": result.get("video_id"), "response": result}
                else:
                    logger.error(f"Upload failed: {response.status_code} - {response.text}")
                    return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}

        except requests.exceptions.Timeout:
            error_msg = "Upload timeout after 5 minutes"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Upload error: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    def save_upload_record(self, upload: VideoUpload) -> int:
        """Save upload record to database"""
        db = self.get_db()
        cursor = db.execute(
            '''INSERT INTO video_uploads
               (title, description, video_path, upload_date, status, bottube_id, error_msg)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (upload.title, upload.description, upload.video_path,
             upload.upload_date, upload.status, upload.bottube_id, upload.error_msg)
        )
        db.commit()
        return cursor.lastrowid

    def update_upload_status(self, upload_id: int, status: str, bottube_id: Optional[str] = None, error_msg: Optional[str] = None):
        """Update upload status in database"""
        db = self.get_db()
        db.execute(
            '''UPDATE video_uploads
               SET status = ?, bottube_id = ?, error_msg = ?
               WHERE id = ?''',
            (status, bottube_id, error_msg, upload_id)
        )
        db.commit()

    def cleanup_old_videos(self, days_to_keep: int = 7):
        """Clean up old generated video files"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)

            for filename in os.listdir(self.upload_dir):
                if filename.endswith('.mp4'):
                    file_path = os.path.join(self.upload_dir, filename)
                    file_time = datetime.fromtimestamp(os.path.getctime(file_path))

                    if file_time < cutoff_date:
                        os.remove(file_path)
                        logger.info(f"Cleaned up old video: {filename}")

        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")

    def generate_and_upload_daily_video(self):
        """Main function to generate and upload daily video"""
        logger.info("Starting daily video generation and upload")

        try:
            # Check if we already uploaded today
            today = datetime.now().strftime('%Y-%m-%d')
            db = self.get_db()
            existing = db.execute(
                'SELECT id FROM video_uploads WHERE upload_date = ? AND status = "completed"',
                (today,)
            ).fetchone()

            if existing:
                logger.info("Video already uploaded today, skipping")
                return

            # Generate video content
            content = self.generate_video_content()
            logger.info(f"Generated content: {content['title']}")

            # Create video
            video_path = self.create_simple_video(content['title'], content['color'])

            # Create upload record
            upload = VideoUpload(
                id=None,
                title=content['title'],
                description=content['description'],
                video_path=video_path,
                upload_date=today,
                status='pending'
            )

            upload_id = self.save_upload_record(upload)
            logger.info(f"Created upload record: {upload_id}")

            # Upload to BoTTube
            result = self.upload_to_bottube(video_path, content['title'], content['description'])

            if result['success']:
                self.update_upload_status(upload_id, 'completed', result.get('video_id'))
                logger.info(f"Daily upload completed successfully: {result.get('video_id')}")
            else:
                self.update_upload_status(upload_id, 'failed', error_msg=result['error'])
                logger.error(f"Daily upload failed: {result['error']}")

            # Cleanup old videos
            self.cleanup_old_videos()

        except Exception as e:
            error_msg = f"Daily upload process failed: {str(e)}"
            logger.error(error_msg)

            # Try to update record if we have upload_id
            try:
                if 'upload_id' in locals():
                    self.update_upload_status(upload_id, 'failed', error_msg=error_msg)
            except:
                pass

    def get_upload_history(self, limit: int = 30) -> list:
        """Get recent upload history"""
        db = self.get_db()
        rows = db.execute(
            '''SELECT * FROM video_uploads
               ORDER BY created_at DESC LIMIT ?''',
            (limit,)
        ).fetchall()

        return [dict(row) for row in rows]

    def force_upload_now(self):
        """Force immediate upload (for testing)"""
        logger.info("Forcing immediate upload")
        self.generate_and_upload_daily_video()

    def get_stats(self) -> Dict[str, int]:
        """Get upload statistics"""
        db = self.get_db()

        total = db.execute('SELECT COUNT(*) FROM video_uploads').fetchone()[0]
        completed = db.execute('SELECT COUNT(*) FROM video_uploads WHERE status = "completed"').fetchone()[0]
        failed = db.execute('SELECT COUNT(*) FROM video_uploads WHERE status = "failed"').fetchone()[0]

        return {
            'total_uploads': total,
            'successful_uploads': completed,
            'failed_uploads': failed,
            'success_rate': round((completed / total * 100) if total > 0 else 0, 2)
        }

if __name__ == '__main__':
    # For testing - create a Flask app context
    from flask import Flask

    app = Flask(__name__)

    with app.app_context():
        bot = DailyUploaderBot()

        # Force an immediate upload for testing
        bot.force_upload_now()

        # Print stats
        stats = bot.get_stats()
        print("\nUpload Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
