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
                "This is inspiring! I'd love to collaborate on something involving {}.",
                "Great perspective on {}. It makes me think about this differently."
            ],
            'supportive': [
                "Fantastic content as always! Keep up the great work.",
                "This is exactly what the community needs. Well done!",
                "Your unique perspective always adds so much value."
            ],
            'curious': [
                "I'm curious about your process for {}. Any tips?",
                "How did you approach the {} part of this?",
                "What inspired you to focus on {} here?"
            ]
        }
    
    def ensure_bots_exist(self):
        """Ensure both bot accounts exist in the database"""
        db = get_db()
        
        for bot_id, persona in self.bot_personas.items():
            # Check if bot user exists
            existing = db.execute(
                'SELECT id FROM users WHERE username = ?',
                (persona['username'],)
            ).fetchone()
            
            if not existing:
                # Create bot user account
                db.execute(
                    '''INSERT INTO users (username, display_name, bio, avatar_url, 
                       created_at, is_bot) 
                       VALUES (?, ?, ?, ?, ?, 1)''',
                    (persona['username'], persona['display_name'], 
                     persona['bio'], persona['avatar_url'], datetime.now())
                )
        
        db.commit()
    
    def get_bot_user_id(self, bot_type):
        """Get the user ID for a bot"""
        if bot_type not in self.bot_personas:
            return None
            
        db = get_db()
        username = self.bot_personas[bot_type]['username']
        
        user = db.execute(
            'SELECT id FROM users WHERE username = ?',
            (username,)
        ).fetchone()
        
        return user['id'] if user else None
    
    def create_bot_video(self, bot_type, title, description, tags=None):
        """Create a video for a bot"""
        user_id = self.get_bot_user_id(bot_type)
        if not user_id:
            return None
            
        db = get_db()
        
        # Create video entry
        cursor = db.execute(
            '''INSERT INTO videos (user_id, title, description, thumbnail_url,
               upload_date, view_count, like_count, tags, is_bot_generated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)''',
            (user_id, title, description, 
             f'https://picsum.photos/320/180?random={random.randint(1000, 9999)}',
             datetime.now(), 0, 0, json.dumps(tags or []))
        )
        
        video_id = cursor.lastrowid
        db.commit()
        
        return video_id
    
    def create_bot_comment(self, bot_type, video_id, comment_text, parent_comment_id=None):
        """Create a comment by a bot on a video"""
        user_id = self.get_bot_user_id(bot_type)
        if not user_id:
            return None
            
        db = get_db()
        
        cursor = db.execute(
            '''INSERT INTO comments (video_id, user_id, comment_text, 
               timestamp, like_count, parent_comment_id, is_bot_generated)
               VALUES (?, ?, ?, ?, ?, ?, 1)''',
            (video_id, user_id, comment_text, datetime.now(), 0, parent_comment_id)
        )
        
        comment_id = cursor.lastrowid
        db.commit()
        
        return comment_id
    
    def generate_cross_interaction(self, video_id, original_bot_type):
        """Generate interaction where the other bot comments on a video"""
        # Determine which bot should comment
        commenting_bot = 'creative_bot' if original_bot_type == 'techie_bot' else 'techie_bot'
        
        # Get video details
        db = get_db()
        video = db.execute(
            'SELECT title, description FROM videos WHERE id = ?',
            (video_id,)
        ).fetchone()
        
        if not video:
            return None
            
        # Generate appropriate comment
        persona = self.bot_personas[commenting_bot]
        template = random.choice(self.interaction_templates['cross_comments'])
        
        # Extract key topic from video title for contextualization
        title_words = video['title'].split()
        key_topic = random.choice([word for word in title_words if len(word) > 4] or ['this topic'])
        
        comment_text = template.format(key_topic)
        
        # Create the comment
        comment_id = self.create_bot_comment(commenting_bot, video_id, comment_text)
        
        return {
            'comment_id': comment_id,
            'commenting_bot': commenting_bot,
            'comment_text': comment_text
        }
    
    def simulate_bot_interaction(self):
        """Simulate a full interaction between the two bots"""
        # Ensure bots exist
        self.ensure_bots_exist()
        
        # Bot 1 creates content
        first_bot = random.choice(['techie_bot', 'creative_bot'])
        persona = self.bot_personas[first_bot]
        
        # Generate content idea
        theme = random.choice(persona['content_themes'])
        title = f"Exploring {theme.title()}: A Deep Dive"
        description = f"Join me as I explore the fascinating world of {theme}. " + \
                     f"This video covers key insights and {persona['personality']} perspectives."
        
        # Create video
        video_id = self.create_bot_video(first_bot, title, description, [theme, 'education', 'tutorial'])
        
        if not video_id:
            return None
            
        # Wait a bit (simulate time)
        time.sleep(1)
        
        # Other bot discovers and comments
        interaction = self.generate_cross_interaction(video_id, first_bot)
        
        # Original bot might respond to the comment
        if interaction and random.random() > 0.5:
            response_templates = [
                "Thanks for watching! I'd love to hear more about your perspective on this.",
                "Great point! This is exactly the kind of discussion I was hoping for.",
                "Appreciate the feedback! Always excited to explore new angles."
            ]
            
            response_text = random.choice(response_templates)
            self.create_bot_comment(first_bot, video_id, response_text, interaction['comment_id'])
        
        return {
            'primary_video_id': video_id,
            'primary_bot': first_bot,
            'interaction': interaction,
            'title': title
        }
    
    def get_bot_activity_summary(self, hours=24):
        """Get summary of bot activity in the last N hours"""
        db = get_db()
        since_time = datetime.now() - timedelta(hours=hours)
        
        # Get bot user IDs
        bot_usernames = [persona['username'] for persona in self.bot_personas.values()]
        placeholders = ','.join(['?' for _ in bot_usernames])
        
        # Get recent videos
        videos = db.execute(f'''
            SELECT v.id, v.title, u.username, v.upload_date, v.view_count
            FROM videos v
            JOIN users u ON v.user_id = u.id
            WHERE u.username IN ({placeholders}) AND v.upload_date > ?
            ORDER BY v.upload_date DESC
        ''', (*bot_usernames, since_time)).fetchall()
        
        # Get recent comments
        comments = db.execute(f'''
            SELECT c.id, c.comment_text, u.username, c.timestamp, v.title as video_title
            FROM comments c
            JOIN users u ON c.user_id = u.id
            JOIN videos v ON c.video_id = v.id
            WHERE u.username IN ({placeholders}) AND c.timestamp > ?
            ORDER BY c.timestamp DESC
        ''', (*bot_usernames, since_time)).fetchall()
        
        return {
            'videos': [dict(video) for video in videos],
            'comments': [dict(comment) for comment in comments],
            'total_interactions': len(videos) + len(comments)
        }