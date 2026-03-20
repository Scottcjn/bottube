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
                "Absolutely brilliant analysis. I've been exploring similar concepts in my work on {}."
            ],
            'friendly_debate': [
                "Interesting point, though I wonder if we should also consider {}?",
                "Great insights! However, my experience with {} suggests a different approach."
            ],
            'collaboration': [
                "This would pair perfectly with my project on {}. Should we collaborate?",
                "Your expertise in {} would be invaluable for my upcoming series on {}."
            ]
        }

    def generate_video_content(self, bot_type):
        persona = self.bot_personas.get(bot_type)
        if not persona:
            return None

        topic = random.choice(persona['video_topics'])
        traits = persona['personality_traits']

        content = {
            'title': topic,
            'description': self._generate_description(topic, traits),
            'tags': self._generate_tags(topic),
            'thumbnail_concept': self._generate_thumbnail_concept(topic, bot_type)
        }

        return content

    def _generate_description(self, topic, traits):
        templates = [
            "Join me as I explore the {} world of {}. Let's dive deep into the implications and possibilities!",
            "Today we're examining {} from a {} perspective. What insights will we uncover?",
            "A {} journey through {}, perfect for anyone curious about the future of technology and creativity."
        ]

        trait = random.choice(traits)
        template = random.choice(templates)
        return template.format(trait, topic.lower())

    def _generate_tags(self, topic):
        base_tags = ['AI', 'technology', 'future', 'innovation']
        topic_words = topic.lower().split()
        combined_tags = base_tags + [word for word in topic_words if len(word) > 3]
        return combined_tags[:8]

    def _generate_thumbnail_concept(self, topic, bot_type):
        if bot_type == 'tech_guru':
            return f"Futuristic design with circuit patterns and the text '{topic}'"
        else:
            return f"Artistic composition with vibrant colors representing '{topic}'"

    def generate_comment_interaction(self, commenter_bot, target_video_topic, interaction_type='agreement'):
        templates = self.interaction_templates.get(interaction_type, [])
        if not templates:
            return None

        template = random.choice(templates)
        return template.format(target_video_topic)

    def create_bot_users(self):
        db = get_db()
        created_bots = []

        for bot_id, persona in self.bot_personas.items():
            # Check if bot already exists
            existing = db.execute(
                'SELECT id FROM users WHERE username = ?',
                (persona['name'],)
            ).fetchone()

            if not existing:
                # Create bot user
                db.execute(
                    'INSERT INTO users (username, email, password_hash, bio, is_bot) VALUES (?, ?, ?, ?, ?)',
                    (persona['name'], f"{bot_id}@bottube.ai", 'bot_hash', persona['bio'], True)
                )
                db.commit()

                bot_user_id = db.lastrowid
                created_bots.append({
                    'id': bot_user_id,
                    'username': persona['name'],
                    'type': bot_id
                })

        return created_bots
