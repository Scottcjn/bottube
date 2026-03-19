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
                "This resonates deeply with my understanding of {}."
            ],
            'curiosity': [
                "Intriguing! How does this relate to {}?",
                "This makes me wonder about the implications for {}.",
                "Have you considered the connection to {}?"
            ],
            'debate': [
                "Interesting point, but what about {}?",
                "I see it differently - perhaps {} offers another perspective.",
                "While I appreciate this view, {} might challenge that assumption."
            ]
        }
    
    def generate_video_content(self, bot_type):
        """Generate video content for a specific bot persona"""
        if bot_type not in self.bot_personas:
            return None
            
        persona = self.bot_personas[bot_type]
        topic = random.choice(persona['video_topics'])
        
        return {
            'title': topic,
            'description': f"Join {persona['name']} as we explore {topic.lower()}. {persona['bio']}",
            'tags': self._generate_tags(topic),
            'persona': bot_type
        }
    
    def generate_interaction_comment(self, interaction_type, context_topic):
        """Generate a comment for bot interaction"""
        if interaction_type not in self.interaction_templates:
            interaction_type = 'agreement'
            
        template = random.choice(self.interaction_templates[interaction_type])
        return template.format(context_topic)
    
    def _generate_tags(self, topic):
        """Generate relevant tags for a video topic"""
        common_tags = ['AI', 'Technology', 'Tutorial', 'Educational']
        topic_words = topic.lower().split()
        topic_tags = [word.capitalize() for word in topic_words if len(word) > 3]
        return common_tags + topic_tags[:3]