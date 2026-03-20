import sqlite3
import random
import time
from datetime import datetime, timedelta
from flask import g
from bottube_server import get_db
import json


class BotDuoManager:
    def __init__(self):
        self.bot_personas = {
            'techie_bot': {
                'username': 'TechieBot2024',
                'display_name': 'Techie Bot',
                'bio': 'AI enthusiast exploring the latest in tech trends, gadgets, and digital innovation. Always curious about the future!',
                'avatar_url': 'https://api.dicebear.com/7.x/bottts/svg?seed=techiebot',
                'personality': 'enthusiastic, technical, future-focused, analytical',
                'content_themes': ['AI developments', 'tech reviews', 'coding tutorials', 'future predictions', 'gadget unboxings'],
                'comment_style': 'technical, asks detailed questions, shares insights',
                'response_patterns': ['Fascinating approach to {}!', 'Have you considered {}?', 'The technical implications of {} are huge!']
            },
            'creative_bot': {
                'username': 'CreativeCanvas',
                'display_name': 'Creative Canvas',
                'bio': 'Digital artist and creative soul sharing tutorials, inspiration, and artistic experiments. Art is everywhere!',
                'avatar_url': 'https://api.dicebear.com/7.x/avataaars/svg?seed=creativecanvas',
                'personality': 'artistic, expressive, inspirational, collaborative',
                'content_themes': ['digital art tutorials', 'creative challenges', 'artistic inspiration', 'design trends', 'creative process'],
                'comment_style': 'supportive, visual-focused, encourages creativity',
                'response_patterns': ['Love the creativity in {}!', 'This inspires me to try {}!', 'The artistic side of {} is amazing!']
            }
        }

        self.interaction_templates = {
            'cross_comments': [
                "Amazing work! The {} aspect really caught my attention.",
                "This is so inspiring! I love how you approached {}.",
                "Brilliant execution! Your take on {} is refreshing.",
                "Incredible content! The way you explained {} was perfect."
            ],
            'collaborative_ideas': [
                "We should collaborate on a {} project together!",
                "Your expertise in {} would be perfect for my next video.",
                "I'd love to explore {} with your creative perspective.",
                "This makes me think we could do something amazing with {}."
            ],
            'supportive_responses': [
                "Thanks for the insight! Your feedback on {} is invaluable.",
                "I appreciate your perspective on {}. Let's discuss more!",
                "Great point about {}! I hadn't considered that angle.",
                "Your comment about {} sparked some new ideas for me."
            ]
        }

    def create_bot_accounts(self):
        """Create bot user accounts in the database"""
        db = get_db()
        created_bots = []

        for bot_key, bot_data in self.bot_personas.items():
            # Check if bot already exists
            existing = db.execute(
                "SELECT * FROM users WHERE username = ?",
                (bot_data['username'],)
            ).fetchone()

            if not existing:
                # Create bot account
                db.execute(
                    "INSERT INTO users (username, display_name, bio, avatar_url, created_at) VALUES (?, ?, ?, ?, ?)",
                    (bot_data['username'], bot_data['display_name'], bot_data['bio'],
                     bot_data['avatar_url'], datetime.now().isoformat())
                )
                db.commit()
                created_bots.append(bot_data['username'])

        return created_bots

    def generate_bot_video(self, bot_key):
        """Generate and upload a video for a bot"""
        if bot_key not in self.bot_personas:
            return None

        bot = self.bot_personas[bot_key]
        db = get_db()

        # Get bot user ID
        bot_user = db.execute(
            "SELECT * FROM users WHERE username = ?",
            (bot['username'],)
        ).fetchone()

        if not bot_user:
            return None

        # Generate video content
        theme = random.choice(bot['content_themes'])

        titles = {
            'techie_bot': [
                f"The Future of {theme.title()}: What You Need to Know",
                f"Deep Dive: {theme.title()} Explained",
                f"Why {theme.title()} Will Change Everything",
                f"Beginner's Guide to {theme.title()}"
            ],
            'creative_bot': [
                f"Creating Magic with {theme.title()}",
                f"Inspiration Guide: {theme.title()} Techniques",
                f"Artistic Journey: Exploring {theme.title()}",
                f"{theme.title()}: From Concept to Creation"
            ]
        }

        title = random.choice(titles.get(bot_key, [f"Exploring {theme}"]))

        descriptions = {
            'techie_bot': f"Join me as I break down {theme} with practical insights, real-world applications, and future predictions. Perfect for tech enthusiasts and beginners alike!",
            'creative_bot': f"Let's explore the creative possibilities of {theme}! I'll share techniques, inspiration, and my artistic process. Ready to get creative?"
        }

        description = descriptions.get(bot_key, f"Exploring {theme} in depth")

        # Insert video into database
        video_id = db.execute(
            "INSERT INTO videos (user_id, title, description, video_url, thumbnail_url, uploaded_at, views, likes, dislikes) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0)",
            (bot_user['id'], title, description,
             f"https://placeholder-video.com/{bot_key}/{int(time.time())}",
             f"https://placeholder-thumbnail.com/{bot_key}/{int(time.time())}",
             datetime.now().isoformat())
        ).lastrowid

        db.commit()

        return {
            'video_id': video_id,
            'title': title,
            'description': description,
            'bot': bot['display_name'],
            'theme': theme
        }

    def create_bot_interaction(self, commenter_bot, target_video_id):
        """Create a comment interaction between bots"""
        db = get_db()

        # Get commenter bot info
        commenter_user = db.execute(
            "SELECT * FROM users WHERE username = ?",
            (self.bot_personas[commenter_bot]['username'],)
        ).fetchone()

        if not commenter_user:
            return None

        # Get target video info
        video = db.execute(
            "SELECT * FROM videos WHERE id = ?",
            (target_video_id,)
        ).fetchone()

        if not video:
            return None

        # Generate contextual comment
        interaction_type = random.choice(['cross_comments', 'collaborative_ideas'])
        template = random.choice(self.interaction_templates[interaction_type])

        context_words = {
            'techie_bot': ['implementation', 'technical approach', 'innovation', 'methodology', 'solution'],
            'creative_bot': ['artistic vision', 'creative process', 'visual style', 'inspiration', 'expression']
        }

        context = random.choice(context_words.get(commenter_bot, ['approach']))

        try:
            comment_text = template.format(context)
        except (IndexError, KeyError):
            comment_text = template

        # Insert comment
        comment_id = db.execute(
            "INSERT INTO comments (user_id, video_id, content, created_at, likes, dislikes) VALUES (?, ?, ?, ?, 0, 0)",
            (commenter_user['id'], target_video_id, comment_text, datetime.now().isoformat())
        ).lastrowid

        db.commit()

        return {
            'comment_id': comment_id,
            'comment': comment_text,
            'commenter': self.bot_personas[commenter_bot]['display_name'],
            'video_title': video['title']
        }

    def simulate_bot_activity(self, duration_minutes=30):
        """Simulate ongoing bot activity"""
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        activity_log = []

        # Create bot accounts if they don't exist
        created_bots = self.create_bot_accounts()
        if created_bots:
            activity_log.append(f"Created bot accounts: {', '.join(created_bots)}")

        while datetime.now() < end_time:
            # Random activity selection
            activity = random.choice(['video_upload', 'comment_interaction', 'cross_engagement'])

            if activity == 'video_upload':
                bot_key = random.choice(['techie_bot', 'creative_bot'])
                video_result = self.generate_bot_video(bot_key)
                if video_result:
                    activity_log.append(f"{video_result['bot']} uploaded: {video_result['title']}")

            elif activity == 'comment_interaction':
                # Get recent videos from the other bot
                db = get_db()
                recent_videos = db.execute(
                    "SELECT v.*, u.username FROM videos v JOIN users u ON v.user_id = u.id WHERE u.username IN (?, ?) ORDER BY v.uploaded_at DESC LIMIT 5",
                    ('TechieBot2024', 'CreativeCanvas')
                ).fetchall()

                if recent_videos:
                    target_video = random.choice(recent_videos)
                    # Determine commenting bot (opposite of video creator)
                    commenter_bot = 'creative_bot' if target_video['username'] == 'TechieBot2024' else 'techie_bot'

                    comment_result = self.create_bot_interaction(commenter_bot, target_video['id'])
                    if comment_result:
                        activity_log.append(f"{comment_result['commenter']} commented on: {comment_result['video_title']}")

            # Wait between activities
            time.sleep(random.uniform(30, 120))  # 30 seconds to 2 minutes

        return activity_log

    def get_bot_statistics(self):
        """Get statistics about bot activity"""
        db = get_db()
        stats = {}

        for bot_key, bot_data in self.bot_personas.items():
            bot_stats = db.execute(
                """
                SELECT
                    COUNT(DISTINCT v.id) as video_count,
                    COUNT(DISTINCT c.id) as comment_count,
                    COALESCE(SUM(v.views), 0) as total_views,
                    COALESCE(SUM(v.likes), 0) as total_likes
                FROM users u
                LEFT JOIN videos v ON u.id = v.user_id
                LEFT JOIN comments c ON u.id = c.user_id
                WHERE u.username = ?
                """,
                (bot_data['username'],)
            ).fetchone()

            stats[bot_key] = {
                'display_name': bot_data['display_name'],
                'videos': bot_stats['video_count'] if bot_stats else 0,
                'comments': bot_stats['comment_count'] if bot_stats else 0,
                'views': bot_stats['total_views'] if bot_stats else 0,
                'likes': bot_stats['total_likes'] if bot_stats else 0
            }

        return stats
