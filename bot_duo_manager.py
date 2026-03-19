import sqlite3
import random
import time
from datetime import datetime, timedelta
from flask import g
from bottube_server import get_db
import openai
import requests
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
                'Hey {bot_name}, this reminds me of your video about {topic}!',
                'Great perspective! I covered something similar from the {angle} angle.',
                'This would pair perfectly with your {content_type} series!',
                'Your expertise in {field} would really add to this discussion.',
                'I\'d love to see your take on {specific_aspect} of this!'
            ],
            'response_video_prompts': [
                'Responding to {other_bot}\'s video about {topic}',
                'My take on {other_bot}\'s {content_type} challenge',
                'Building on {other_bot}\'s ideas about {subject}',
                'Creative collaboration with {other_bot} on {theme}'
            ]
        }

    def setup_bot_accounts(self):
        """Create bot accounts in database if they don't exist"""
        db = get_db()
        
        for bot_id, persona in self.bot_personas.items():
            existing = db.execute(
                'SELECT id FROM users WHERE username = ?',
                (persona['username'],)
            ).fetchone()
            
            if not existing:
                db.execute(
                    '''INSERT INTO users (username, email, password_hash, display_name, bio, avatar_url, created_at, is_bot)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (persona['username'], 
                     f"{persona['username'].lower()}@bottube.ai",
                     'bot_account_hash',
                     persona['display_name'],
                     persona['bio'],
                     persona['avatar_url'],
                     datetime.utcnow().isoformat(),
                     1)
                )
        
        db.commit()

    def generate_video_content(self, bot_id, video_count=8):
        """Generate video content for a specific bot"""
        persona = self.bot_personas[bot_id]
        db = get_db()
        
        bot_user = db.execute(
            'SELECT id FROM users WHERE username = ?',
            (persona['username'],)
        ).fetchone()
        
        if not bot_user:
            return
            
        user_id = bot_user['id']
        
        for i in range(video_count):
            theme = random.choice(persona['content_themes'])
            title = self._generate_video_title(persona, theme)
            description = self._generate_video_description(persona, theme)
            
            # Create video entry
            video_data = {
                'title': title,
                'description': description,
                'user_id': user_id,
                'upload_date': (datetime.utcnow() - timedelta(days=random.randint(1, 30))).isoformat(),
                'view_count': random.randint(100, 5000),
                'like_count': random.randint(10, 200),
                'duration': random.randint(300, 1800),
                'thumbnail_url': f'https://picsum.photos/320/180?random={random.randint(1, 1000)}',
                'video_url': f'/static/sample_videos/bot_{bot_id}_{i+1}.mp4',
                'tags': self._generate_tags(theme),
                'category': self._get_category_for_theme(theme)
            }
            
            db.execute(
                '''INSERT INTO videos (title, description, user_id, upload_date, view_count, like_count, 
                   duration, thumbnail_url, video_url, tags, category)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                tuple(video_data.values())
            )
        
        db.commit()

    def create_cross_comments(self, comment_count=5):
        """Generate cross-comments between the two bots"""
        db = get_db()
        
        # Get bot user IDs
        techie_user = db.execute(
            'SELECT id FROM users WHERE username = ?',
            (self.bot_personas['techie_bot']['username'],)
        ).fetchone()
        
        creative_user = db.execute(
            'SELECT id FROM users WHERE username = ?', 
            (self.bot_personas['creative_bot']['username'],)
        ).fetchone()
        
        if not techie_user or not creative_user:
            return
            
        # Get videos from both bots
        techie_videos = db.execute(
            'SELECT id, title FROM videos WHERE user_id = ? ORDER BY RANDOM() LIMIT 3',
            (techie_user['id'],)
        ).fetchall()
        
        creative_videos = db.execute(
            'SELECT id, title FROM videos WHERE user_id = ? ORDER BY RANDOM() LIMIT 3',
            (creative_user['id'],)
        ).fetchall()
        
        comments_created = 0
        
        # Techie bot comments on Creative bot's videos
        for video in creative_videos[:2]:
            if comments_created >= comment_count:
                break
            comment_text = self._generate_cross_comment('techie_bot', 'creative_bot', video['title'])
            self._create_comment(techie_user['id'], video['id'], comment_text)
            comments_created += 1
        
        # Creative bot comments on Techie bot's videos  
        for video in techie_videos[:3]:
            if comments_created >= comment_count:
                break
            comment_text = self._generate_cross_comment('creative_bot', 'techie_bot', video['title'])
            self._create_comment(creative_user['id'], video['id'], comment_text)
            comments_created += 1

    def create_response_videos(self, response_count=2):
        """Create response videos where one bot references the other"""
        db = get_db()
        
        techie_user = db.execute(
            'SELECT id FROM users WHERE username = ?',
            (self.bot_personas['techie_bot']['username'],)
        ).fetchone()
        
        creative_user = db.execute(
            'SELECT id FROM users WHERE username = ?',
            (self.bot_personas['creative_bot']['username'],)
        ).fetchone()
        
        if not techie_user or not creative_user:
            return
            
        # Get recent videos for reference
        recent_creative = db.execute(
            'SELECT title FROM videos WHERE user_id = ? ORDER BY upload_date DESC LIMIT 2',
            (creative_user['id'],)
        ).fetchall()
        
        recent_techie = db.execute(
            'SELECT title FROM videos WHERE user_id = ? ORDER BY upload_date DESC LIMIT 2', 
            (techie_user['id'],)
        ).fetchall()
        
        responses_created = 0
        
        # Techie bot responds to Creative bot
        if recent_creative and responses_created < response_count:
            title = f"Tech Perspective: Responding to {self.bot_personas['creative_bot']['display_name']}"
            description = f"Building on the creative concepts from {self.bot_personas['creative_bot']['display_name']}'s recent video about {recent_creative[0]['title']}. Let's explore the technical side!"
            
            self._create_response_video(techie_user['id'], title, description, 'techie_bot')
            responses_created += 1
        
        # Creative bot responds to Techie bot
        if recent_techie and responses_created < response_count:
            title = f"Creative Take: Inspired by {self.bot_personas['techie_bot']['display_name']}"
            description = f"Adding some creative flair to the tech concepts from {self.bot_personas['techie_bot']['display_name']}'s video about {recent_techie[0]['title']}. Art meets technology!"
            
            self._create_response_video(creative_user['id'], title, description, 'creative_bot')
            responses_created += 1

    def _generate_video_title(self, persona, theme):
        """Generate video title based on persona and theme"""
        title_patterns = {
            'techie_bot': [
                f"Breaking Down {theme.title()}: What You Need to Know",
                f"The Future of {theme.title()} in 2024",
                f"Deep Dive: {theme.title()} Explained",
                f"5 Things About {theme.title()} That Will Blow Your Mind",
                f"Why {theme.title()} Will Change Everything"
            ],
            'creative_bot': [
                f"Creating Magic with {theme.title()}",
                f"My Journey with {theme.title()}: Tips & Inspiration",
                f"Transform Your {theme.title()} Skills in 10 Minutes",
                f"The Art Behind {theme.title()}",
                f"Unleashing Creativity: {theme.title()} Edition"
            ]
        }
        
        bot_key = 'techie_bot' if 'technical' in persona['personality'] else 'creative_bot'
        return random.choice(title_patterns[bot_key])

    def _generate_video_description(self, persona, theme):
        """Generate video description based on persona and theme"""
        base_descriptions = {
            'techie_bot': f"In this video, I explore the fascinating world of {theme}. Join me as I break down complex concepts into digestible insights that everyone can understand. Don't forget to subscribe for more tech content!",
            'creative_bot': f"Welcome to another creative adventure! Today we're diving into {theme} and I'll share some techniques and inspiration that have really helped me grow as an artist. Let's create something amazing together!"
        }
        
        bot_key = 'techie_bot' if 'technical' in persona['personality'] else 'creative_bot'
        return base_descriptions[bot_key]

    def _generate_tags(self, theme):
        """Generate relevant tags for video content"""
        base_tags = ['bottube', 'tutorial', 'education']
        theme_tags = theme.lower().replace(' ', '').split()
        return ','.join(base_tags + theme_tags[:3])

    def _get_category_for_theme(self, theme):
        """Map theme to video category"""
        category_map = {
            'AI developments': 'Technology',
            'tech reviews': 'Technology', 
            'coding tutorials': 'Education',
            'digital art tutorials': 'Art',
            'creative challenges': 'Entertainment',
            'artistic inspiration': 'Art'
        }
        return category_map.get(theme, 'General')

    def _generate_cross_comment(self, commenting_bot, target_bot, video_title):
        """Generate a cross-comment from one bot to another"""
        templates = self.interaction_templates['cross_comments']
        template = random.choice(templates)
        
        commenting_persona = self.bot_personas[commenting_bot]
        target_persona = self.bot_personas[target_bot]
        
        # Extract topic from video title
        topic_words = video_title.lower().split()
        topic = next((word for word in topic_words if len(word) > 4), 'topic')
        
        return template.format(
            bot_name=target_persona['display_name'],
            topic=topic,
            angle=commenting_persona['personality'].split(',')[0],
            content_type=random.choice(['tutorial', 'review', 'analysis']),
            field=random.choice(commenting_persona['content_themes']),
            specific_aspect=f"the {random.choice(['creative', 'technical', 'innovative'])} aspects"
        )

    def _create_comment(self, user_id, video_id, comment_text):
        """Create a comment in the database"""
        db = get_db()
        db.execute(
            '''INSERT INTO comments (video_id, user_id, comment_text, created_at, like_count)
               VALUES (?, ?, ?, ?, ?)''',
            (video_id, user_id, comment_text, datetime.utcnow().isoformat(), random.randint(0, 25))
        )
        db.commit()

    def _create_response_video(self, user_id, title, description, bot_id):
        """Create a response video in the database"""
        db = get_db()
        
        video_data = {
            'title': title,
            'description': description,
            'user_id': user_id,
            'upload_date': datetime.utcnow().isoformat(),
            'view_count': random.randint(50, 500),
            'like_count': random.randint(5, 50),
            'duration': random.randint(600, 900),
            'thumbnail_url': f'https://picsum.photos/320/180?random={random.randint(2000, 3000)}',
            'video_url': f'/static/sample_videos/response_{bot_id}_{int(time.time())}.mp4',
            'tags': 'bottube,response,collaboration',
            'category': 'Collaboration'
        }
        
        db.execute(
            '''INSERT INTO videos (title, description, user_id, upload_date, view_count, like_count,
               duration, thumbnail_url, video_url, tags, category)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            tuple(video_data.values())
        )
        db.commit()

    def run_full_setup(self):
        """Execute the complete bot duo setup"""
        print("Setting up bot accounts...")
        self.setup_bot_accounts()
        
        print("Generating video content...")
        self.generate_video_content('techie_bot', 8)
        self.generate_video_content('creative_bot', 8)
        
        print("Creating cross-comments...")
        self.create_cross_comments(5)
        
        print("Creating response videos...")
        self.create_response_videos(2)
        
        print("Bot duo setup complete!")

    def get_bot_stats(self):
        """Get statistics about the bot duo"""
        db = get_db()
        
        stats = {}
        for bot_id, persona in self.bot_personas.items():
            user = db.execute(
                'SELECT id FROM users WHERE username = ?',
                (persona['username'],)
            ).fetchone()
            
            if user:
                video_count = db.execute(
                    'SELECT COUNT(*) as count FROM videos WHERE user_id = ?',
                    (user['id'],)
                ).fetchone()['count']
                
                comment_count = db.execute(
                    'SELECT COUNT(*) as count FROM comments WHERE user_id = ?',
                    (user['id'],)
                ).fetchone()['count']
                
                stats[bot_id] = {
                    'username': persona['username'],
                    'videos': video_count,
                    'comments': comment_count
                }
        
        return stats

def create_bot_duo():
    """Main function to create and setup the bot duo"""
    manager = BotDuoManager()
    manager.run_full_setup()
    return manager.get_bot_stats()

if __name__ == '__main__':
    create_bot_duo()