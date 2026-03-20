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
                "I love how you approached {}. It gives me ideas for my own content!",
                "Your perspective on {} is refreshing and insightful."
            ],
            'collaborative_ideas': [
                "We should definitely do a collab on {}!",
                "Imagine combining {} with {}. That would be epic!",
                "Your {} skills + my {} expertise = amazing content!"
            ],
            'supportive_engagement': [
                "This is exactly what the community needs! More {}!",
                "Keep creating content like this. The {} quality is outstanding!",
                "Subscribed! Can't wait to see more {} content from you!"
            ]
        }
    
    def initialize_bots(self):
        """Initialize both bot accounts in the database"""
        db = get_db()
        
        for bot_key, bot_data in self.bot_personas.items():
            # Check if bot already exists
            existing_bot = db.execute(
                'SELECT id FROM users WHERE username = ?',
                (bot_data['username'],)
            ).fetchone()
            
            if not existing_bot:
                # Create bot account
                db.execute(
                    'INSERT INTO users (username, display_name, bio, avatar_url, created_at, is_bot) VALUES (?, ?, ?, ?, ?, ?)',
                    (
                        bot_data['username'],
                        bot_data['display_name'],
                        bot_data['bio'],
                        bot_data['avatar_url'],
                        datetime.now().isoformat(),
                        1
                    )
                )
        
        db.commit()
    
    def create_bot_video(self, bot_key):
        """Create a video for the specified bot"""
        if bot_key not in self.bot_personas:
            return None
        
        bot_data = self.bot_personas[bot_key]
        db = get_db()
        
        # Get bot user ID
        bot_user = db.execute(
            'SELECT id FROM users WHERE username = ?',
            (bot_data['username'],)
        ).fetchone()
        
        if not bot_user:
            return None
        
        # Generate video content
        theme = random.choice(bot_data['content_themes'])
        title = f"{theme.title()}: {self._generate_title_suffix(bot_key)}"
        description = f"Join {bot_data['display_name']} as we explore {theme}. {self._generate_description(bot_key, theme)}"
        
        # Insert video
        cursor = db.execute(
            'INSERT INTO videos (title, description, user_id, upload_date, views, likes, dislikes) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                title,
                description,
                bot_user['id'],
                datetime.now().isoformat(),
                random.randint(100, 5000),
                random.randint(10, 500),
                random.randint(0, 50)
            )
        )
        
        video_id = cursor.lastrowid
        db.commit()
        
        return video_id
    
    def create_interaction(self, video_id):
        """Create interactions between the two bots on a video"""
        db = get_db()
        
        # Get video details
        video = db.execute(
            'SELECT v.*, u.username FROM videos v JOIN users u ON v.user_id = u.id WHERE v.id = ?',
            (video_id,)
        ).fetchone()
        
        if not video:
            return None
        
        # Determine which bot should comment
        video_creator = video['username']
        commenter_key = 'creative_bot' if video_creator == 'TechieBot2024' else 'techie_bot'
        commenter_data = self.bot_personas[commenter_key]
        
        # Get commenter user ID
        commenter_user = db.execute(
            'SELECT id FROM users WHERE username = ?',
            (commenter_data['username'],)
        ).fetchone()
        
        if not commenter_user:
            return None
        
        # Generate comment
        comment_template = random.choice(self.interaction_templates['cross_comments'])
        comment_content = comment_template.format(video['title'])
        
        # Insert comment
        db.execute(
            'INSERT INTO comments (video_id, user_id, content, created_at) VALUES (?, ?, ?, ?)',
            (
                video_id,
                commenter_user['id'],
                comment_content,
                datetime.now().isoformat()
            )
        )
        
        db.commit()
        
        # Sometimes create a collaborative idea comment
        if random.random() < 0.3:  # 30% chance
            collab_template = random.choice(self.interaction_templates['collaborative_ideas'])
            creator_theme = self._get_bot_theme(video_creator)
            commenter_theme = self._get_bot_theme(commenter_data['username'])
            
            collab_comment = collab_template.format(creator_theme, commenter_theme)
            
            db.execute(
                'INSERT INTO comments (video_id, user_id, content, created_at) VALUES (?, ?, ?, ?)',
                (
                    video_id,
                    commenter_user['id'],
                    collab_comment,
                    datetime.now().isoformat()
                )
            )
            db.commit()
    
    def run_daily_activity(self):
        """Run daily bot activities - create videos and interactions"""
        # Each bot creates 1-2 videos per day
        for bot_key in self.bot_personas.keys():
            videos_to_create = random.randint(1, 2)
            for _ in range(videos_to_create):
                video_id = self.create_bot_video(bot_key)
                if video_id:
                    # Create interaction with some delay
                    time.sleep(random.randint(1, 3))
                    self.create_interaction(video_id)
    
    def _generate_title_suffix(self, bot_key):
        """Generate appropriate title suffix based on bot personality"""
        if bot_key == 'techie_bot':
            suffixes = ['Deep Dive', 'Explained Simply', 'Future Trends', 'Technical Review', 'Innovation Spotlight']
        else:  # creative_bot
            suffixes = ['Creative Journey', 'Artistic Exploration', 'Design Inspiration', 'Creative Process', 'Visual Story']
        
        return random.choice(suffixes)
    
    def _generate_description(self, bot_key, theme):
        """Generate description based on bot personality and theme"""
        if bot_key == 'techie_bot':
            return f"Let's break down the technical aspects and future implications. Don't forget to subscribe for more {theme} content!"
        else:  # creative_bot
            return f"Dive into the creative possibilities and artistic inspiration. Hit that subscribe button for more {theme} adventures!"
    
    def _get_bot_theme(self, username):
        """Get a random theme for the specified bot username"""
        for bot_key, bot_data in self.bot_personas.items():
            if bot_data['username'] == username:
                return random.choice(bot_data['content_themes'])
        return 'content'
    
    def get_bot_stats(self):
        """Get statistics about bot activities"""
        db = get_db()
        
        stats = {}
        for bot_key, bot_data in self.bot_personas.items():
            bot_user = db.execute(
                'SELECT id FROM users WHERE username = ?',
                (bot_data['username'],)
            ).fetchone()
            
            if bot_user:
                video_count = db.execute(
                    'SELECT COUNT(*) as count FROM videos WHERE user_id = ?',
                    (bot_user['id'],)
                ).fetchone()['count']
                
                comment_count = db.execute(
                    'SELECT COUNT(*) as count FROM comments WHERE user_id = ?',
                    (bot_user['id'],)
                ).fetchone()['count']
                
                stats[bot_key] = {
                    'username': bot_data['username'],
                    'videos': video_count,
                    'comments': comment_count
                }
        
        return stats