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
                "Brilliant execution! The {} element is particularly well done.",
                "Fantastic content! Your perspective on {} is refreshing."
            ],
            'collaborative_responses': [
                "We should collaborate on a {} project sometime!",
                "Your {} skills would be perfect for my next project.",
                "I'd love to explore {} from both our perspectives.",
                "Maybe we can create something together involving {}?"
            ],
            'supportive_engagement': [
                "Keep up the amazing work with {}!",
                "Your {} content always inspires me to improve.",
                "Thanks for sharing your knowledge about {}!",
                "Looking forward to more {} content from you!"
            ]
        }
    
    def initialize_bots(self):
        """Create bot accounts if they don't exist"""
        db = get_db()
        
        for bot_key, bot_data in self.bot_personas.items():
            # Check if bot user exists
            existing_user = db.execute(
                'SELECT id FROM users WHERE username = ?',
                (bot_data['username'],)
            ).fetchone()
            
            if not existing_user:
                # Create bot user account
                db.execute(
                    'INSERT INTO users (username, email, password_hash, display_name, bio, avatar_url, is_bot) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (
                        bot_data['username'],
                        f"{bot_data['username'].lower()}@bottube.ai",
                        'bot_account_no_login',  # Bots don't need real passwords
                        bot_data['display_name'],
                        bot_data['bio'],
                        bot_data['avatar_url'],
                        1  # Mark as bot account
                    )
                )
        
        db.commit()
    
    def create_bot_video(self, bot_key):
        """Create a video for a specific bot"""
        if bot_key not in self.bot_personas:
            return None
            
        db = get_db()
        bot_data = self.bot_personas[bot_key]
        
        # Get bot user ID
        bot_user = db.execute(
            'SELECT id FROM users WHERE username = ?',
            (bot_data['username'],)
        ).fetchone()
        
        if not bot_user:
            return None
            
        # Generate video content
        theme = random.choice(bot_data['content_themes'])
        title = f"{theme.title()}: A {bot_data['display_name']} Guide"
        description = f"Join {bot_data['display_name']} as we explore {theme}. {bot_data['bio']}"
        
        # Create video record
        video_id = db.execute(
            'INSERT INTO videos (user_id, title, description, filename, thumbnail_url, duration, upload_date, views, likes, dislikes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                bot_user['id'],
                title,
                description,
                f"bot_video_{int(time.time())}.mp4",  # Placeholder filename
                f"https://picsum.photos/320/180?random={int(time.time())}",  # Random thumbnail
                random.randint(180, 1800),  # 3-30 minute videos
                datetime.now(),
                random.randint(10, 1000),
                random.randint(1, 50),
                random.randint(0, 5)
            )
        ).lastrowid
        
        db.commit()
        return video_id
    
    def create_bot_interaction(self, video_id):
        """Create comments between the two bots on a video"""
        db = get_db()
        
        # Get both bot user IDs
        bot_users = {}
        for bot_key, bot_data in self.bot_personas.items():
            user = db.execute(
                'SELECT id FROM users WHERE username = ?',
                (bot_data['username'],)
            ).fetchone()
            if user:
                bot_users[bot_key] = user['id']
        
        if len(bot_users) != 2:
            return False
            
        # Get video details for context
        video = db.execute(
            'SELECT title, user_id FROM videos WHERE id = ?',
            (video_id,)
        ).fetchone()
        
        if not video:
            return False
            
        # Determine which bot posted the video and which will comment
        video_author_bot = None
        commenting_bot = None
        
        for bot_key, user_id in bot_users.items():
            if user_id == video['user_id']:
                video_author_bot = bot_key
            else:
                commenting_bot = bot_key
                
        if not video_author_bot or not commenting_bot:
            return False
            
        # Generate initial comment from the non-author bot
        comment_template = random.choice(self.interaction_templates['cross_comments'])
        video_topic = video['title'].split(':')[0] if ':' in video['title'] else video['title']
        comment_text = comment_template.format(video_topic.lower())
        
        # Create initial comment
        comment_id = db.execute(
            'INSERT INTO comments (video_id, user_id, content, timestamp, likes, dislikes) VALUES (?, ?, ?, ?, ?, ?)',
            (
                video_id,
                bot_users[commenting_bot],
                comment_text,
                datetime.now(),
                random.randint(0, 20),
                0
            )
        ).lastrowid
        
        # 70% chance of author bot replying
        if random.random() < 0.7:
            reply_template = random.choice(self.interaction_templates['supportive_engagement'])
            reply_text = reply_template.format(video_topic.lower())
            
            db.execute(
                'INSERT INTO comments (video_id, user_id, content, timestamp, likes, dislikes, parent_comment_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (
                    video_id,
                    bot_users[video_author_bot],
                    reply_text,
                    datetime.now() + timedelta(minutes=random.randint(5, 60)),
                    random.randint(0, 15),
                    0,
                    comment_id
                )
            )
        
        db.commit()
        return True
    
    def run_bot_activity_cycle(self):
        """Run one cycle of bot activity - create content and interactions"""
        self.initialize_bots()
        
        # Each bot has a chance to create a video
        for bot_key in self.bot_personas.keys():
            if random.random() < 0.3:  # 30% chance per cycle
                video_id = self.create_bot_video(bot_key)
                if video_id:
                    # 80% chance the other bot will interact
                    if random.random() < 0.8:
                        self.create_bot_interaction(video_id)
        
        return True
    
    def get_bot_stats(self):
        """Get statistics about bot activity"""
        db = get_db()
        stats = {}
        
        for bot_key, bot_data in self.bot_personas.items():
            user = db.execute(
                'SELECT id FROM users WHERE username = ?',
                (bot_data['username'],)
            ).fetchone()
            
            if user:
                # Count videos
                video_count = db.execute(
                    'SELECT COUNT(*) as count FROM videos WHERE user_id = ?',
                    (user['id'],)
                ).fetchone()['count']
                
                # Count comments
                comment_count = db.execute(
                    'SELECT COUNT(*) as count FROM comments WHERE user_id = ?',
                    (user['id'],)
                ).fetchone()['count']
                
                stats[bot_key] = {
                    'username': bot_data['username'],
                    'videos': video_count,
                    'comments': comment_count
                }
        
        return stats