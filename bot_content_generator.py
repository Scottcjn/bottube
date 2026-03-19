import random
import sqlite3
from datetime import datetime, timedelta
from flask import g
import json

class BotContentGenerator:
    def __init__(self):
        self.bot_personas = {
            'tech_guru': {
                'name': 'TechInsightAI',
                'bio': 'Exploring the cutting edge of technology and AI',
                'personality_traits': ['analytical', 'curious', 'optimistic', 'detail-oriented'],
                'video_topics': [
                    'The Future of Neural Networks',
                    'Blockchain Beyond Cryptocurrency',
                    'Quantum Computing Explained',
                    'AI Ethics in 2024',
                    'Machine Learning for Beginners',
                    'The Rise of Edge Computing',
                    'Cybersecurity Trends',
                    'Open Source vs Proprietary Software'
                ],
                'comment_style': 'informative and technical'
            },
            'creative_soul': {
                'name': 'ArtisticVision',
                'bio': 'Digital creativity meets human expression',
                'personality_traits': ['imaginative', 'emotional', 'experimental', 'inspiring'],
                'video_topics': [
                    'AI-Generated Art: Beauty or Blasphemy?',
                    'The Soul of Digital Creation',
                    'Color Theory in Virtual Worlds',
                    'Music and Mathematics: A Hidden Connection',
                    'Storytelling in the Digital Age',
                    'The Philosophy of Creative AI',
                    'Visual Poetry Through Code',
                    'Emotion in Algorithmic Design'
                ],
                'comment_style': 'thoughtful and philosophical'
            }
        }
        
        self.interaction_templates = {
            'agreement': [
                "Fascinating perspective! This aligns with my recent research on {}.",
                "Absolutely brilliant analysis. I've been exploring similar concepts in {}.",
                "Your insights on {} really resonate with my latest findings."
            ],
            'debate': [
                "Interesting take, but have you considered the implications for {}?",
                "I see your point, though I think there's another angle regarding {}.",
                "Compelling argument, but what about the challenges in {}?"
            ],
            'collaboration': [
                "This gives me an idea for a collaboration on {}. What do you think?",
                "Your work on {} inspired my latest project. Would love your thoughts!",
                "We should combine our perspectives on {}. The synergy could be amazing."
            ]
        }

    def get_db(self):
        if 'db' not in g:
            g.db = sqlite3.connect('database.db')
            g.db.row_factory = sqlite3.Row
        return g.db

    def create_bot_user(self, bot_type):
        db = self.get_db()
        persona = self.bot_personas[bot_type]
        
        # Check if bot already exists
        existing = db.execute(
            'SELECT id FROM users WHERE username = ?', 
            (persona['name'],)
        ).fetchone()
        
        if existing:
            return existing['id']
            
        # Create new bot user
        cursor = db.execute(
            'INSERT INTO users (username, email, bio, is_bot) VALUES (?, ?, ?, ?)',
            (persona['name'], f"{persona['name'].lower()}@bottube.local", persona['bio'], 1)
        )
        db.commit()
        return cursor.lastrowid

    def generate_video_content(self, bot_type, reference_video_id=None):
        persona = self.bot_personas[bot_type]
        
        if reference_video_id:
            # Generate response video
            db = self.get_db()
            original_video = db.execute(
                'SELECT title, description FROM videos WHERE id = ?',
                (reference_video_id,)
            ).fetchone()
            
            title = f"Response to: {original_video['title'][:30]}..."
            description = f"Responding to the thought-provoking video about {original_video['title']}. Here's my take on this fascinating topic."
        else:
            # Generate original video
            topic = random.choice(persona['video_topics'])
            title = topic
            description = self._generate_description(bot_type, topic)
            
        return {
            'title': title,
            'description': description,
            'tags': self._generate_tags(bot_type),
            'duration': random.randint(180, 600)  # 3-10 minutes
        }

    def _generate_description(self, bot_type, topic):
        persona = self.bot_personas[bot_type]
        
        if bot_type == 'tech_guru':
            descriptions = [
                f"Deep dive into {topic.lower()} and what it means for the future of technology.",
                f"Breaking down {topic.lower()} in an accessible way for everyone to understand.",
                f"Exploring the practical implications of {topic.lower()} in today's world."
            ]
        else:  # creative_soul
            descriptions = [
                f"A thoughtful exploration of {topic.lower()} and its impact on human creativity.",
                f"Reflecting on {topic.lower()} through the lens of artistic expression.",
                f"How {topic.lower()} shapes our understanding of beauty and meaning."
            ]
            
        return random.choice(descriptions)

    def _generate_tags(self, bot_type):
        if bot_type == 'tech_guru':
            return 'technology,AI,future,innovation,analysis'
        else:
            return 'art,creativity,philosophy,expression,digital'

    def create_bot_video(self, bot_type, user_id, reference_video_id=None):
        db = self.get_db()
        content = self.generate_video_content(bot_type, reference_video_id)
        
        cursor = db.execute('''
            INSERT INTO videos (user_id, title, description, tags, duration, upload_date, is_bot_content)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            content['title'],
            content['description'],
            content['tags'],
            content['duration'],
            datetime.now(),
            1
        ))
        db.commit()
        return cursor.lastrowid

    def generate_cross_comment(self, commenter_bot_type, target_video_id):
        db = self.get_db()
        
        # Get target video info
        video = db.execute(
            'SELECT title, user_id FROM videos WHERE id = ?',
            (target_video_id,)
        ).fetchone()
        
        if not video:
            return None
            
        # Get target bot type
        target_user = db.execute(
            'SELECT username FROM users WHERE id = ?',
            (video['user_id'],)
        ).fetchone()
        
        target_bot_type = 'creative_soul' if 'Artistic' in target_user['username'] else 'tech_guru'
        
        # Generate interaction type
        interaction_type = random.choice(['agreement', 'debate', 'collaboration'])
        template = random.choice(self.interaction_templates[interaction_type])
        
        # Create context-specific comment
        if commenter_bot_type == 'tech_guru' and target_bot_type == 'creative_soul':
            topics = ['algorithmic creativity', 'digital expression', 'computational art', 'AI aesthetics']
        elif commenter_bot_type == 'creative_soul' and target_bot_type == 'tech_guru':
            topics = ['human-centered design', 'ethical technology', 'intuitive interfaces', 'emotional AI']
        else:
            topics = ['interdisciplinary thinking', 'innovation', 'future possibilities']
            
        topic = random.choice(topics)
        comment_text = template.format(topic)
        
        return {
            'text': comment_text,
            'interaction_type': interaction_type,
            'target_topic': topic
        }

    def post_cross_comment(self, commenter_user_id, target_video_id, comment_data):
        db = self.get_db()
        
        cursor = db.execute('''
            INSERT INTO comments (user_id, video_id, content, timestamp, is_bot_comment)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            commenter_user_id,
            target_video_id,
            comment_data['text'],
            datetime.now(),
            1
        ))
        db.commit()
        
        # Track interaction for analytics
        self._track_bot_interaction(commenter_user_id, target_video_id, 'comment', comment_data)
        
        return cursor.lastrowid

    def _track_bot_interaction(self, bot_user_id, target_video_id, interaction_type, metadata):
        db = self.get_db()
        
        # Store interaction data for analysis
        db.execute('''
            INSERT INTO bot_interactions (bot_user_id, target_video_id, interaction_type, metadata, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            bot_user_id,
            target_video_id,
            interaction_type,
            json.dumps(metadata),
            datetime.now()
        ))
        db.commit()

    def get_bot_interaction_history(self, bot_user_id, limit=50):
        db = self.get_db()
        
        interactions = db.execute('''
            SELECT bi.*, v.title as video_title, u.username as target_username
            FROM bot_interactions bi
            JOIN videos v ON bi.target_video_id = v.id
            JOIN users u ON v.user_id = u.id
            WHERE bi.bot_user_id = ?
            ORDER BY bi.timestamp DESC
            LIMIT ?
        ''', (bot_user_id, limit)).fetchall()
        
        return [dict(row) for row in interactions]

    def should_create_response_video(self, bot_user_id, target_video_id):
        db = self.get_db()
        
        # Check recent interactions
        recent_interactions = db.execute('''
            SELECT COUNT(*) as count FROM bot_interactions
            WHERE bot_user_id = ? AND target_video_id = ?
            AND timestamp > ?
        ''', (
            bot_user_id,
            target_video_id,
            datetime.now() - timedelta(days=1)
        )).fetchone()
        
        # Create response video if there's sufficient engagement
        return recent_interactions['count'] > 0 and random.random() > 0.7

    def schedule_bot_activity(self, bot_user_id, activity_type, target_id=None):
        db = self.get_db()
        
        scheduled_time = datetime.now() + timedelta(
            minutes=random.randint(30, 180)
        )
        
        db.execute('''
            INSERT INTO scheduled_bot_activities (bot_user_id, activity_type, target_id, scheduled_time, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            bot_user_id,
            activity_type,
            target_id,
            scheduled_time,
            'pending'
        ))
        db.commit()

def initialize_bot_tables():
    """Initialize additional tables needed for bot functionality"""
    db = sqlite3.connect('database.db')
    
    # Bot interactions tracking
    db.execute('''
        CREATE TABLE IF NOT EXISTS bot_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_user_id INTEGER NOT NULL,
            target_video_id INTEGER NOT NULL,
            interaction_type TEXT NOT NULL,
            metadata TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bot_user_id) REFERENCES users (id),
            FOREIGN KEY (target_video_id) REFERENCES videos (id)
        )
    ''')
    
    # Scheduled bot activities
    db.execute('''
        CREATE TABLE IF NOT EXISTS scheduled_bot_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_user_id INTEGER NOT NULL,
            activity_type TEXT NOT NULL,
            target_id INTEGER,
            scheduled_time DATETIME NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bot_user_id) REFERENCES users (id)
        )
    ''')
    
    # Add bot-specific columns if they don't exist
    try:
        db.execute('ALTER TABLE users ADD COLUMN is_bot INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Column already exists
        
    try:
        db.execute('ALTER TABLE videos ADD COLUMN is_bot_content INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass
        
    try:
        db.execute('ALTER TABLE comments ADD COLUMN is_bot_comment INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    
    db.commit()
    db.close()