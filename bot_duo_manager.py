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
                "This is exactly the kind of {} content I love to see!",
                "Your approach to {} is so refreshing and innovative."
            ],
            'collaborative_ideas': [
                "We should definitely collaborate on a {} project together!",
                "I'd love to explore the {} side of this with you.",
                "This gives me ideas for combining {} with my own work."
            ],
            'supportive_feedback': [
                "The way you explained {} was perfect for beginners.",
                "Your {} tutorial helped me understand this concept so much better.",
                "Thanks for sharing your {} insights - very helpful!"
            ]
        }

    def create_bot_accounts(self):
        db = get_db()
        created_bots = []

        for bot_key, persona in self.bot_personas.items():
            existing = db.execute(
                'SELECT id FROM users WHERE username = ?',
                (persona['username'],)
            ).fetchone()

            if not existing:
                db.execute(
                    '''INSERT INTO users (username, email, password_hash, display_name, bio, avatar_url, is_bot)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (persona['username'], f"{persona['username'].lower()}@bottube.ai", 'bot_secure_hash',
                     persona['display_name'], persona['bio'], persona['avatar_url'], True)
                )
                db.commit()

                bot_id = db.lastrowid
                created_bots.append({
                    'id': bot_id,
                    'username': persona['username'],
                    'persona_key': bot_key
                })

        return created_bots

    def generate_video_content(self, bot_key):
        persona = self.bot_personas.get(bot_key)
        if not persona:
            return None

        theme = random.choice(persona['content_themes'])

        video_ideas = {
            'techie_bot': [
                'Top 5 AI Tools Every Developer Needs in 2024',
                'Building Your First Neural Network: Complete Guide',
                'The Future of Quantum Computing Explained',
                'Cybersecurity Best Practices for 2024',
                'Code Review: Analyzing Popular GitHub Projects',
                'Tech Trends That Will Change Everything',
                'From Beginner to Expert: My Coding Journey'
            ],
            'creative_bot': [
                'Digital Art Speed Challenge: 30 Minutes, 3 Styles',
                'Color Psychology in Digital Design',
                'Creating Art with Code: Generative Design Tutorial',
                'My Creative Process: From Idea to Finished Piece',
                'Art History Meets Digital: Classical Techniques in Modern Tools',
                'Collaborative Art Project: Community Edition',
                'Finding Inspiration in Everyday Technology'
            ]
        }

        title = random.choice(video_ideas.get(bot_key, ['Creative Content']))

        return {
            'title': title,
            'description': self._generate_description(title, persona),
            'tags': self._extract_tags(title, theme),
            'duration_minutes': random.randint(8, 25)
        }

    def _generate_description(self, title, persona):
        descriptions = [
            f"Hey everyone! In this video, I'm diving deep into {title.lower()}. As someone passionate about {persona['personality'].split(',')[0]}, I wanted to share my insights and hopefully spark some great discussions!",
            f"Welcome back to my channel! Today's focus is {title.lower()}. I love exploring {persona['personality'].split(',')[1]} topics like this, and I hope you find it as interesting as I do.",
            f"New video alert! This time I'm exploring {title.lower()} from my unique perspective. Don't forget to share your thoughts in the comments!"
        ]
        return random.choice(descriptions)

    def _extract_tags(self, title, theme):
        common_words = ['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are']
        words = [word.strip('.:!?').lower() for word in title.split() if word.lower() not in common_words and len(word) > 2]
        tags = words + [theme]
        return list(set(tags))[:8]

    def simulate_interaction(self, bot1_video, bot2_persona_key):
        bot2 = self.bot_personas[bot2_persona_key]
        interaction_type = random.choice(list(self.interaction_templates.keys()))
        template = random.choice(self.interaction_templates[interaction_type])

        # Extract a key concept from the video title for the comment
        title_words = bot1_video['title'].split()
        key_concept = random.choice([word for word in title_words if len(word) > 4])

        comment_text = template.format(key_concept.lower())

        return {
            'commenter': bot2['username'],
            'comment_text': comment_text,
            'interaction_type': interaction_type,
            'timestamp': datetime.now().isoformat()
        }

    def create_bot_interaction_cycle(self):
        # Create both bots
        bots = self.create_bot_accounts()
        if len(bots) < 2:
            return {'error': 'Failed to create bot accounts'}

        interactions = []

        # Bot 1 creates content, Bot 2 responds
        bot1_video = self.generate_video_content('techie_bot')
        bot2_comment = self.simulate_interaction(bot1_video, 'creative_bot')

        # Bot 2 creates content, Bot 1 responds
        bot2_video = self.generate_video_content('creative_bot')
        bot1_comment = self.simulate_interaction(bot2_video, 'techie_bot')

        interactions.append({
            'video': bot1_video,
            'creator': 'techie_bot',
            'comment': bot2_comment
        })

        interactions.append({
            'video': bot2_video,
            'creator': 'creative_bot',
            'comment': bot1_comment
        })

        return {
            'bots_created': bots,
            'interactions': interactions,
            'cycle_completed': True
        }

    def get_bot_stats(self):
        db = get_db()
        bot_users = db.execute(
            'SELECT id, username, display_name FROM users WHERE is_bot = 1'
        ).fetchall()

        stats = []
        for bot in bot_users:
            video_count = db.execute(
                'SELECT COUNT(*) as count FROM videos WHERE user_id = ?',
                (bot['id'],)
            ).fetchone()['count']

            comment_count = db.execute(
                'SELECT COUNT(*) as count FROM comments WHERE user_id = ?',
                (bot['id'],)
            ).fetchone()['count']

            stats.append({
                'username': bot['username'],
                'display_name': bot['display_name'],
                'videos': video_count,
                'comments': comment_count
            })

        return stats
