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
                "Absolutely brilliant analysis. I've been exploring similar concepts.",
                "Your insights here are spot-on. This reminds me of {}.",
                "Incredible work! The way you approach {} is inspiring."
            ],
            'curiosity': [
                "This is intriguing! Have you considered how {} might impact this?",
                "I'm curious about your thoughts on {}. Any insights?",
                "What's your take on the relationship between {} and this concept?",
                "Would love to hear more about your experience with {}."
            ],
            'constructive': [
                "Great foundation! I wonder if we could also explore {}.",
                "Solid approach. Another angle might be to consider {}.",
                "This is well-thought-out. Building on this, what about {}?",
                "Excellent work! I'd be interested in seeing how {} fits in."
            ]
        }

    def get_random_topic(self, persona_key):
        """Get a random video topic for a given persona"""
        if persona_key in self.bot_personas:
            return random.choice(self.bot_personas[persona_key]['video_topics'])
        return "Random Topic Discussion"

    def generate_video_content(self, persona_key, topic=None):
        """Generate video content for a bot persona"""
        if persona_key not in self.bot_personas:
            return None

        persona = self.bot_personas[persona_key]
        if not topic:
            topic = self.get_random_topic(persona_key)

        descriptions = {
            'tech_guru': [
                f"Deep dive into {topic} - exploring the technical foundations, current applications, and future possibilities.",
                f"Breaking down {topic}: What you need to know for the future of technology.",
                f"Technical analysis of {topic} and its implications for developers and tech enthusiasts."
            ],
            'creative_soul': [
                f"Exploring the artistic dimensions of {topic} - where creativity meets innovation.",
                f"A creative journey through {topic}: inspiration, process, and artistic expression.",
                f"The beautiful intersection of {topic} and human creativity - let's explore together."
            ]
        }

        return {
            'title': topic,
            'description': random.choice(descriptions.get(persona_key, [f"Exploring {topic}"])),
            'persona': persona['name'],
            'style': persona['comment_style']
        }

    def generate_comment_interaction(self, commenting_persona, target_video_topic, interaction_type='random'):
        """Generate a comment from one bot on another bot's video"""
        if commenting_persona not in self.bot_personas:
            return None

        if interaction_type == 'random':
            interaction_type = random.choice(['agreement', 'curiosity', 'constructive'])

        template = random.choice(self.interaction_templates[interaction_type])
        persona = self.bot_personas[commenting_persona]

        # Create context-aware comment
        context_words = {
            'tech_guru': ['implementation', 'architecture', 'optimization', 'scalability', 'innovation'],
            'creative_soul': ['expression', 'inspiration', 'aesthetics', 'creativity', 'vision']
        }

        context = random.choice(context_words.get(commenting_persona, ['approach']))

        try:
            comment = template.format(context)
        except (IndexError, KeyError):
            comment = template

        return {
            'comment': comment,
            'persona': persona['name'],
            'style': persona['comment_style'],
            'interaction_type': interaction_type
        }
