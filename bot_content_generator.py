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
            'question': [
                "Intriguing! Have you considered how {} might impact this?",
                "What are your thoughts on the relationship between {} and your approach?",
                "I'm curious about your take on {} in this context."
            ],
            'counterpoint': [
                "Interesting perspective, though I wonder if {} might offer an alternative view.",
                "While I appreciate this angle, I've found {} presents some compelling counterpoints.",
                "This is thought-provoking, and it makes me think about {} as well."
            ]
        }
    
    def generate_video_idea(self, bot_type):
        """Generate a video idea for a specific bot persona"""
        if bot_type not in self.bot_personas:
            return None
            
        persona = self.bot_personas[bot_type]
        topic = random.choice(persona['video_topics'])
        
        return {
            'title': topic,
            'description': f"A deep dive into {topic.lower()} from the perspective of {persona['name']}",
            'tags': self._generate_tags(topic),
            'estimated_duration': random.randint(8, 15)
        }
    
    def generate_comment(self, bot_type, context_topic=None):
        """Generate a comment based on bot persona"""
        if bot_type not in self.bot_personas:
            return None
            
        persona = self.bot_personas[bot_type]
        template_type = random.choice(list(self.interaction_templates.keys()))
        template = random.choice(self.interaction_templates[template_type])
        
        if context_topic:
            comment = template.format(context_topic)
        else:
            comment = template.replace(' {}', '').replace('{}', 'this topic')
            
        return {
            'text': comment,
            'style': persona['comment_style'],
            'template_type': template_type
        }
    
    def _generate_tags(self, topic):
        """Generate relevant tags for a video topic"""
        base_tags = ['AI', 'technology', 'future', 'innovation']
        topic_words = topic.lower().split()
        
        # Add topic-specific tags
        for word in topic_words:
            if len(word) > 3 and word not in ['the', 'and', 'for', 'with']:
                base_tags.append(word)
                
        return base_tags[:8]  # Limit to 8 tags
    
    def create_interaction_scenario(self):
        """Create a scenario where both bots interact"""
        tech_idea = self.generate_video_idea('tech_guru')
        creative_idea = self.generate_video_idea('creative_soul')
        
        # Generate cross-comments
        tech_comment_on_creative = self.generate_comment('tech_guru', creative_idea['title'])
        creative_comment_on_tech = self.generate_comment('creative_soul', tech_idea['title'])
        
        return {
            'tech_bot_content': tech_idea,
            'creative_bot_content': creative_idea,
            'interactions': {
                'tech_on_creative': tech_comment_on_creative,
                'creative_on_tech': creative_comment_on_tech
            }
        }