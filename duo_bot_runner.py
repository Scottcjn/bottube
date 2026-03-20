import time
import random
import threading
from datetime import datetime, timedelta
import sqlite3
import logging
from typing import Dict, List, Optional, Tuple
import json
import schedule

from bottube_server import get_db, create_bot, generate_video_content, post_comment
from duo_personas import PERSONA_ALPHA, PERSONA_BETA, get_interaction_prompts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DuoBotRunner:
    def __init__(self):
        self.bot_alpha_id = None
        self.bot_beta_id = None
        self.video_count = {'alpha': 0, 'beta': 0}
        self.comment_count = 0
        self.response_video_count = 0
        self.running = False

    def initialize_bots(self) -> bool:
        """Create or retrieve the bot duo"""
        try:
            db = get_db()
            cursor = db.cursor()

            # Check if bots already exist
            cursor.execute("SELECT id FROM bots WHERE username = ?", (PERSONA_ALPHA['username'],))
            alpha_result = cursor.fetchone()

            cursor.execute("SELECT id FROM bots WHERE username = ?", (PERSONA_BETA['username'],))
            beta_result = cursor.fetchone()

            if alpha_result and beta_result:
                self.bot_alpha_id = alpha_result[0]
                self.bot_beta_id = beta_result[0]
                logger.info(f"Found existing bots: Alpha({self.bot_alpha_id}), Beta({self.bot_beta_id})")
                self._load_progress()
            else:
                # Create new bots
                self.bot_alpha_id = create_bot(PERSONA_ALPHA)
                self.bot_beta_id = create_bot(PERSONA_BETA)
                logger.info(f"Created new bots: Alpha({self.bot_alpha_id}), Beta({self.bot_beta_id})")

            return True

        except Exception as e:
            logger.error(f"Failed to initialize bots: {e}")
            return False

    def _load_progress(self):
        """Load current progress from database"""
        try:
            db = get_db()
            cursor = db.cursor()

            # Count videos for each bot
            cursor.execute("SELECT COUNT(*) FROM videos WHERE bot_id = ?", (self.bot_alpha_id,))
            self.video_count['alpha'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM videos WHERE bot_id = ?", (self.bot_beta_id,))
            self.video_count['beta'] = cursor.fetchone()[0]

            # Count cross-comments
            cursor.execute("""
                SELECT COUNT(*) FROM comments c
                JOIN videos v ON c.video_id = v.id
                WHERE (c.bot_id = ? AND v.bot_id = ?) OR (c.bot_id = ? AND v.bot_id = ?)
            """, (self.bot_alpha_id, self.bot_beta_id, self.bot_beta_id, self.bot_alpha_id))
            self.comment_count = cursor.fetchone()[0]

            # Count response videos (videos with references to the other bot)
            cursor.execute("""
                SELECT COUNT(*) FROM videos
                WHERE (bot_id = ? AND (title LIKE '%{}%' OR description LIKE '%{}%'))
                OR (bot_id = ? AND (title LIKE '%{}%' OR description LIKE '%{}%'))
            """.format(
                PERSONA_BETA['username'], PERSONA_BETA['username'],
                PERSONA_ALPHA['username'], PERSONA_ALPHA['username']
            ), (self.bot_alpha_id, self.bot_beta_id))
            self.response_video_count = cursor.fetchone()[0]

            logger.info(f"Progress loaded - Alpha: {self.video_count['alpha']} videos, "
                       f"Beta: {self.video_count['beta']} videos, "
                       f"Comments: {self.comment_count}, Response videos: {self.response_video_count}")

        except Exception as e:
            logger.error(f"Failed to load progress: {e}")

    def create_video_for_bot(self, bot_name: str, is_response: bool = False,
                           reference_video_id: Optional[int] = None) -> Optional[int]:
        """Create a video for the specified bot"""
        try:
            bot_id = self.bot_alpha_id if bot_name == 'alpha' else self.bot_beta_id
            persona = PERSONA_ALPHA if bot_name == 'alpha' else PERSONA_BETA
            other_persona = PERSONA_BETA if bot_name == 'alpha' else PERSONA_ALPHA

            # Generate video content
            if is_response and reference_video_id:
                prompt = get_interaction_prompts()['response_video'].format(
                    persona_name=persona['username'],
                    other_name=other_persona['username']
                )
            else:
                prompt = random.choice(persona['content_themes'])

            video_data = generate_video_content(bot_id, prompt)

            if video_data:
                self.video_count[bot_name] += 1
                if is_response:
                    self.response_video_count += 1
                logger.info(f"Created video for {bot_name}: {video_data.get('title', 'Untitled')}")
                return video_data.get('id')

        except Exception as e:
            logger.error(f"Failed to create video for {bot_name}: {e}")

        return None

    def create_cross_comment(self, commenter_bot: str) -> bool:
        """Create a comment from one bot on the other bot's video"""
        try:
            db = get_db()
            cursor = db.cursor()

            # Get a random video from the other bot
            other_bot_id = self.bot_beta_id if commenter_bot == 'alpha' else self.bot_alpha_id
            cursor.execute("SELECT id, title FROM videos WHERE bot_id = ? ORDER BY RANDOM() LIMIT 1",
                          (other_bot_id,))
            video_result = cursor.fetchone()

            if not video_result:
                return False

            video_id, video_title = video_result
            commenter_id = self.bot_alpha_id if commenter_bot == 'alpha' else self.bot_beta_id
            persona = PERSONA_ALPHA if commenter_bot == 'alpha' else PERSONA_BETA

            # Generate comment
            comment_prompt = get_interaction_prompts()['comment'].format(
                persona_name=persona['username'],
                video_title=video_title
            )

            comment_text = f"@{persona['username']}: {random.choice(persona['comment_styles'])}"

            # Post comment
            if post_comment(video_id, commenter_id, comment_text):
                self.comment_count += 1
                logger.info(f"Posted cross-comment from {commenter_bot} on video {video_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to create cross-comment: {e}")

        return False

    def schedule_content_creation(self):
        """Schedule regular content creation"""
        # Videos every 2-4 hours
        schedule.every(2).to(4).hours.do(self._create_scheduled_video)

        # Cross-comments every 3-6 hours
        schedule.every(3).to(6).hours.do(self._create_scheduled_comment)

        # Response videos every 8-12 hours
        schedule.every(8).to(12).hours.do(self._create_scheduled_response)

    def _create_scheduled_video(self):
        """Create a scheduled video"""
        if self.video_count['alpha'] >= 8 and self.video_count['beta'] >= 8:
            return

        # Alternate between bots or choose randomly
        if self.video_count['alpha'] < 8 and self.video_count['beta'] < 8:
            bot_choice = random.choice(['alpha', 'beta'])
        elif self.video_count['alpha'] < 8:
            bot_choice = 'alpha'
        else:
            bot_choice = 'beta'

        self.create_video_for_bot(bot_choice)

    def _create_scheduled_comment(self):
        """Create a scheduled cross-comment"""
        if self.comment_count >= 5:
            return

        commenter = random.choice(['alpha', 'beta'])
        self.create_cross_comment(commenter)

    def _create_scheduled_response(self):
        """Create a scheduled response video"""
        if self.response_video_count >= 2:
            return

        # Find a video to respond to
        try:
            db = get_db()
            cursor = db.cursor()

            # Get videos from both bots
            cursor.execute("SELECT id, bot_id FROM videos ORDER BY created_at DESC LIMIT 5")
            recent_videos = cursor.fetchall()

            if recent_videos:
                reference_video = random.choice(recent_videos)
                video_id, video_bot_id = reference_video

                # Respond with the other bot
                responder_bot = 'beta' if video_bot_id == self.bot_alpha_id else 'alpha'
                self.create_video_for_bot(responder_bot, is_response=True, reference_video_id=video_id)

        except Exception as e:
            logger.error(f"Failed to create scheduled response: {e}")

    def run_initial_burst(self):
        """Create initial content to kickstart the interaction"""
        logger.info("Starting initial content burst...")

        # Create initial videos
        for _ in range(3):
            self.create_video_for_bot('alpha')
            time.sleep(random.uniform(30, 120))  # 30s-2min delay

            self.create_video_for_bot('beta')
            time.sleep(random.uniform(30, 120))

        # Create initial comments
        time.sleep(300)  # 5 minute delay
        self.create_cross_comment('alpha')
        time.sleep(random.uniform(60, 180))
        self.create_cross_comment('beta')

        logger.info("Initial content burst completed")

    def get_progress_status(self) -> Dict:
        """Get current progress towards bounty requirements"""
        return {
            'videos_alpha': self.video_count['alpha'],
            'videos_beta': self.video_count['beta'],
            'cross_comments': self.comment_count,
            'response_videos': self.response_video_count,
            'requirements_met': {
                'videos_alpha': self.video_count['alpha'] >= 8,
                'videos_beta': self.video_count['beta'] >= 8,
                'cross_comments': self.comment_count >= 5,
                'response_videos': self.response_video_count >= 2
            }
        }

    def run(self):
        """Main execution loop"""
        if not self.initialize_bots():
            logger.error("Failed to initialize bots")
            return

        self.running = True
        self.schedule_content_creation()

        # Run initial burst if needed
        progress = self.get_progress_status()
        if not any(progress['requirements_met'].values()):
            self.run_initial_burst()

        logger.info("Starting main execution loop...")

        try:
            while self.running:
                schedule.run_pending()

                # Log progress every hour
                current_time = datetime.now()
                if current_time.minute == 0:
                    status = self.get_progress_status()
                    logger.info(f"Progress update: {status}")

                    # Check if all requirements are met
                    if all(status['requirements_met'].values()):
                        logger.info("All bounty requirements met! Bot duo is complete.")
                        break

                time.sleep(60)  # Check every minute

        except KeyboardInterrupt:
            logger.info("Shutting down bot duo runner...")
            self.running = False
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            self.running = False

def main():
    """Entry point for the duo bot runner"""
    runner = DuoBotRunner()

    # Add signal handlers for graceful shutdown
    import signal

    def signal_handler(signum, frame):
        logger.info("Received shutdown signal")
        runner.running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    runner.run()

if __name__ == "__main__":
    main()
