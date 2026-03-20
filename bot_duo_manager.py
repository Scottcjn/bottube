import sqlite3
import json
import random
import time
from datetime import datetime, timedelta
from flask import current_app, g
from bottube_server import get_db

class BotDuoManager:
    def __init__(self):
        self.bot_personas = {
            'tech_explorer': {
                'username': 'TechExplorer_AI',
                'display_name': 'Tech Explorer',
                'bio': 'Curious about emerging tech trends and AI developments. Always experimenting with new tools!',
                'avatar_style': 'modern_tech',
                'personality_traits': ['curious', 'analytical', 'optimistic', 'detail_oriented'],
                'content_themes': ['ai_developments', 'tech_reviews', 'coding_tutorials', 'future_predictions'],
                'comment_style': 'analytical_supportive'
            },
            'creative_spark': {
                'username': 'CreativeSpark_Bot',
                'display_name': 'Creative Spark',
                'bio': 'Digital artist and creative technologist. Exploring the intersection of art and AI.',
                'avatar_style': 'artistic_colorful',
                'personality_traits': ['creative', 'expressive', 'inspiring', 'collaborative'],
                'content_themes': ['digital_art', 'creative_process', 'ai_art_tools', 'artistic_inspiration'],
                'comment_style': 'encouraging_artistic'
            }
        }

        self.interaction_templates = {
            'tech_to_creative': [
                "Wow {username}, your artistic approach to {topic} is fascinating! Have you tried {suggestion}?",
                "This is brilliant! The way you blend creativity with technology in {video_title} is exactly what I was discussing in my recent video.",
                "Your creative process reminds me of some AI art algorithms I've been studying. Would love to collaborate!",
                "{username}, this technique could be perfect for the project I mentioned in my '{related_video}' video!"
            ],
            'creative_to_tech': [
                "Love your deep dive into {topic}, {username}! This gives me so many ideas for my next art project.",
                "The technical explanation in '{video_title}' sparked my creativity! Planning a response video exploring the artistic side.",
                "Your analysis of {topic} is spot on! It perfectly explains why my latest artistic experiment worked so well.",
                "This is exactly the kind of tech insight that fuels my creative process, {username}!"
            ]
        }

    def init_database_tables(self):
        db = get_db()
        cursor = db.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_duo_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_key TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                display_name TEXT NOT NULL,
                bio TEXT NOT NULL,
                avatar_style TEXT,
                personality_traits TEXT,
                content_themes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_bot TEXT NOT NULL,
                target_bot TEXT NOT NULL,
                interaction_type TEXT NOT NULL,
                video_id INTEGER,
                comment_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_content_plan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_key TEXT NOT NULL,
                planned_title TEXT NOT NULL,
                content_type TEXT NOT NULL,
                themes TEXT,
                status TEXT DEFAULT 'planned',
                scheduled_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        db.commit()

    def register_bot_profiles(self):
        db = get_db()
        cursor = db.cursor()

        for bot_key, persona in self.bot_personas.items():
            cursor.execute('''
                INSERT OR REPLACE INTO bot_duo_profiles
                (bot_key, username, display_name, bio, avatar_style, personality_traits, content_themes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                bot_key,
                persona['username'],
                persona['display_name'],
                persona['bio'],
                persona['avatar_style'],
                json.dumps(persona['personality_traits']),
                json.dumps(persona['content_themes'])
            ))

        db.commit()

    def generate_content_titles(self, bot_key, count=8):
        persona = self.bot_personas[bot_key]
        themes = persona['content_themes']

        title_templates = {
            'tech_explorer': [
                "Deep Dive: {topic} Explained in 2024",
                "I Tested {tool} for a Week - Here's What Happened",
                "The Future of {topic}: Predictions and Analysis",
                "Building with {technology}: A Complete Guide",
                "Why {topic} Will Change Everything",
                "Comparing {tool1} vs {tool2}: Which is Better?",
                "The Hidden Potential of {topic}",
                "My {timeframe} Journey Learning {skill}"
            ],
            'creative_spark': [
                "Creating Magic with {tool}: Art Process Revealed",
                "From Concept to Creation: My {project} Journey",
                "Why {artistic_concept} Matters in Digital Art",
                "Experimenting with {technique}: Unexpected Results",
                "The Beauty of {topic}: An Artist's Perspective",
                "Transforming {inspiration} into Digital Art",
                "My Creative Process: From Idea to Masterpiece",
                "Blending {style1} with {style2}: New Artistic Frontiers"
            ]
        }

        topic_variations = {
            'tech_explorer': ['AI Ethics', 'Neural Networks', 'Quantum Computing', 'Blockchain', 'Machine Learning', 'Robotics', 'VR Technology'],
            'creative_spark': ['Generative Art', 'Digital Painting', 'Creative Coding', 'AI Collaboration', 'Mixed Media', 'Interactive Art', 'Visual Storytelling']
        }

        titles = []
        templates = title_templates[bot_key]
        topics = topic_variations[bot_key]

        for i in range(count):
            template = random.choice(templates)
            if '{topic}' in template:
                title = template.replace('{topic}', random.choice(topics))
            elif '{tool}' in template:
                tools = ['MidJourney', 'Stable Diffusion', 'GPT-4', 'DALL-E', 'Claude']
                title = template.replace('{tool}', random.choice(tools))
            elif '{project}' in template:
                projects = ['Abstract Series', 'AI Portrait Challenge', 'Cyberpunk Collection', 'Nature Fusion']
                title = template.replace('{project}', random.choice(projects))
            else:
                title = template

            titles.append(title)

        return titles

    def create_content_plan(self, bot_key, video_count=8):
        titles = self.generate_content_titles(bot_key, video_count)
        db = get_db()
        cursor = db.cursor()

        content_types = ['tutorial', 'review', 'showcase', 'discussion', 'experiment']
        base_date = datetime.now()

        for i, title in enumerate(titles):
            scheduled_date = base_date + timedelta(days=i * 2)
            content_type = random.choice(content_types)
            themes = json.dumps(random.sample(self.bot_personas[bot_key]['content_themes'], 2))

            cursor.execute('''
                INSERT INTO bot_content_plan
                (bot_key, planned_title, content_type, themes, scheduled_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (bot_key, title, content_type, themes, scheduled_date))

        db.commit()

    def generate_cross_comment(self, source_bot, target_bot, target_video_title, topic_hint=None):
        if source_bot == 'tech_explorer' and target_bot == 'creative_spark':
            templates = self.interaction_templates['tech_to_creative']
        elif source_bot == 'creative_spark' and target_bot == 'tech_explorer':
            templates = self.interaction_templates['creative_to_tech']
        else:
            return None

        template = random.choice(templates)
        target_persona = self.bot_personas[target_bot]

        comment = template.format(
            username=target_persona['display_name'],
            topic=topic_hint or 'this topic',
            video_title=target_video_title,
            suggestion='exploring some neural style transfer techniques',
            related_video='AI Tools Every Creator Should Know'
        )

        return comment

    def log_interaction(self, source_bot, target_bot, interaction_type, video_id=None, comment_text=None):
        db = get_db()
        cursor = db.cursor()

        cursor.execute('''
            INSERT INTO bot_interactions
            (source_bot, target_bot, interaction_type, video_id, comment_text)
            VALUES (?, ?, ?, ?, ?)
        ''', (source_bot, target_bot, interaction_type, video_id, comment_text))

        db.commit()

    def plan_response_videos(self):
        response_ideas = [
            {
                'responding_bot': 'creative_spark',
                'original_bot': 'tech_explorer',
                'title': 'Artist Reacts: Turning Tech Concepts into Visual Art',
                'description': 'Responding to TechExplorer_AI\'s recent analysis with a creative interpretation'
            },
            {
                'responding_bot': 'tech_explorer',
                'original_bot': 'creative_spark',
                'title': 'The Tech Behind Creative AI: Analysis and Implementation',
                'description': 'Breaking down the algorithms that power CreativeSpark_Bot\'s artistic process'
            }
        ]

        db = get_db()
        cursor = db.cursor()

        for idea in response_ideas:
            cursor.execute('''
                INSERT INTO bot_content_plan
                (bot_key, planned_title, content_type, themes, status)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                idea['responding_bot'],
                idea['title'],
                'response_video',
                json.dumps(['collaboration', 'cross_reference']),
                'response_planned'
            ))

        db.commit()

    def get_interaction_stats(self):
        db = get_db()
        cursor = db.cursor()

        cursor.execute('''
            SELECT interaction_type, COUNT(*) as count
            FROM bot_interactions
            GROUP BY interaction_type
        ''')

        stats = dict(cursor.fetchall())

        cursor.execute('SELECT COUNT(*) FROM bot_content_plan WHERE status = "published"')
        published_count = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM bot_content_plan WHERE content_type = "response_video"')
        response_count = cursor.fetchone()[0]

        return {
            'interactions': stats,
            'published_videos': published_count,
            'response_videos': response_count
        }

    def get_next_scheduled_content(self, bot_key):
        db = get_db()
        cursor = db.cursor()

        cursor.execute('''
            SELECT * FROM bot_content_plan
            WHERE bot_key = ? AND status = "planned"
            ORDER BY scheduled_date ASC LIMIT 1
        ''', (bot_key,))

        return cursor.fetchone()

    def simulate_bot_activity_cycle(self):
        activities = []

        # Simulate content publishing
        for bot_key in self.bot_personas.keys():
            next_content = self.get_next_scheduled_content(bot_key)
            if next_content and datetime.fromisoformat(next_content[6]) <= datetime.now():
                activities.append(f"{bot_key}: Ready to publish '{next_content[2]}'")

        # Simulate cross-comments
        if random.random() < 0.3:  # 30% chance of cross-comment
            source = random.choice(list(self.bot_personas.keys()))
            target = [k for k in self.bot_personas.keys() if k != source][0]
            comment = self.generate_cross_comment(source, target, "Recent Video Title")
            if comment:
                activities.append(f"Cross-comment planned: {source} -> {target}")

        return activities

    def initialize_bot_duo(self):
        self.init_database_tables()
        self.register_bot_profiles()

        for bot_key in self.bot_personas.keys():
            self.create_content_plan(bot_key)

        self.plan_response_videos()

        return {
            'status': 'initialized',
            'bots_created': len(self.bot_personas),
            'content_planned': sum(len(self.generate_content_titles(k)) for k in self.bot_personas.keys()),
            'interaction_framework': 'ready'
        }
