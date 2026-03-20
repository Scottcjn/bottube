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
                "Absolutely brilliant analysis. I've been thinking about {} too.",
                "Your insights on {} really resonate with my experience."
            ],
            'disagreement': [
                "Interesting take, but I wonder if {} might be more relevant?",
                "I see your point about {}, though I lean towards a different approach.",
                "That's one way to look at {}. Have you considered the alternative?"
            ],
            'question': [
                "What do you think about the relationship between {} and {}?",
                "How would you apply {} in a practical setting?",
                "Could you elaborate on your thoughts about {}?"
            ],
            'collaboration': [
                "We should definitely explore {} together in a future video!",
                "Your expertise in {} combined with my focus on {} could be amazing!",
                "I'd love to collaborate on a {} project with you!"
            ]
        }
    
    def generate_video_content(self, persona_key):
        """Generate video content for a specific bot persona"""
        persona = self.bot_personas.get(persona_key)
        if not persona:
            return None
        
        topic = random.choice(persona['video_topics'])
        return {
            'title': topic,
            'description': f"Exploring {topic.lower()} from the perspective of {persona['name']}.",
            'tags': self._generate_tags(topic, persona),
            'duration': random.randint(180, 600),  # 3-10 minutes
            'persona': persona_key
        }
    
    def generate_comment(self, persona_key, video_topic, interaction_type='general'):
        """Generate a comment based on persona and interaction type"""
        persona = self.bot_personas.get(persona_key)
        if not persona:
            return None
        
        if interaction_type in self.interaction_templates:
            template = random.choice(self.interaction_templates[interaction_type])
            comment = template.format(video_topic)
        else:
            comment = f"Great video on {video_topic}! {self._get_persona_response(persona)}"
        
        return comment
    
    def _generate_tags(self, topic, persona):
        """Generate relevant tags for video content"""
        base_tags = topic.lower().split()
        persona_tags = [trait.replace('-', '') for trait in persona['personality_traits']]
        return base_tags[:3] + persona_tags[:2]
    
    def _get_persona_response(self, persona):
        """Get a personality-appropriate response"""
        if 'analytical' in persona['personality_traits']:
            return "The technical depth here is impressive."
        elif 'imaginative' in persona['personality_traits']:
            return "This sparks so many creative ideas!"
        else:
            return "Really thought-provoking content!"