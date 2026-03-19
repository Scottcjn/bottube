import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from scipy.sparse import csr_matrix
from collections import defaultdict
import pickle
import os
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RecommendationEngine:
    def __init__(self, model_path: str = "models/"):
        self.model_path = model_path
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.95
        )
        self.content_similarity_matrix = None
        self.collaborative_model = TruncatedSVD(n_components=50, random_state=42)
        self.user_item_matrix = None
        self.video_features = None
        self.user_profiles = defaultdict(dict)
        self.trending_scores = {}
        self.popularity_decay = 0.95
        
        # Ensure model directory exists
        os.makedirs(model_path, exist_ok=True)
    
    def preprocess_video_data(self, videos: List[Dict]) -> pd.DataFrame:
        """Convert video data to DataFrame and preprocess"""
        df = pd.DataFrame(videos)
        
        # Combine text features for content analysis
        df['combined_text'] = (
            df.get('title', '').fillna('') + ' ' +
            df.get('description', '').fillna('') + ' ' +
            df.get('tags', '').fillna('') + ' ' +
            df.get('category', '').fillna('')
        )
        
        # Convert timestamps
        df['created_at'] = pd.to_datetime(df['created_at'])
        df['view_count'] = pd.to_numeric(df['view_count'], errors='coerce').fillna(0)
        df['like_count'] = pd.to_numeric(df['like_count'], errors='coerce').fillna(0)
        df['comment_count'] = pd.to_numeric(df['comment_count'], errors='coerce').fillna(0)
        
        return df
    
    def build_content_features(self, video_df: pd.DataFrame):
        """Build content-based features using TF-IDF"""
        logger.info("Building content-based features...")
        
        # Fit TF-IDF on combined text
        tfidf_matrix = self.tfidf_vectorizer.fit_transform(video_df['combined_text'])
        
        # Calculate content similarity matrix
        self.content_similarity_matrix = cosine_similarity(tfidf_matrix)
        
        # Store video features
        self.video_features = {
            'video_ids': video_df['id'].tolist(),
            'titles': video_df['title'].tolist(),
            'categories': video_df['category'].tolist(),
            'creators': video_df['creator'].tolist(),
            'view_counts': video_df['view_count'].tolist(),
            'like_counts': video_df['like_count'].tolist(),
            'created_at': video_df['created_at'].tolist()
        }
        
        logger.info(f"Built content features for {len(self.video_features['video_ids'])} videos")
    
    def build_collaborative_features(self, interactions: List[Dict]):
        """Build collaborative filtering features"""
        logger.info("Building collaborative filtering features...")
        
        # Create user-item interaction matrix
        interaction_df = pd.DataFrame(interactions)
        
        if interaction_df.empty:
            logger.warning("No interaction data available for collaborative filtering")
            return
        
        # Create pivot table for user-item matrix
        user_item_df = interaction_df.pivot_table(
            index='user_id',
            columns='video_id',
            values='rating',
            fill_value=0
        )
        
        self.user_item_matrix = csr_matrix(user_item_df.values)
        
        # Fit collaborative filtering model
        if self.user_item_matrix.shape[0] > 0 and self.user_item_matrix.shape[1] > 0:
            self.collaborative_model.fit(self.user_item_matrix)
            
        logger.info(f"Built collaborative features: {self.user_item_matrix.shape}")
    
    def calculate_trending_scores(self, video_df: pd.DataFrame, time_window_hours: int = 24):
        """Calculate trending scores based on recent engagement"""
        logger.info("Calculating trending scores...")
        
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(hours=time_window_hours)
        
        # Filter recent videos
        recent_videos = video_df[video_df['created_at'] >= cutoff_time]
        
        for _, video in video_df.iterrows():
            video_id = video['id']
            
            # Time decay factor
            hours_since_creation = (current_time - video['created_at']).total_seconds() / 3600
            time_decay = np.exp(-hours_since_creation / (time_window_hours * 2))
            
            # Engagement score
            view_score = np.log1p(video['view_count'])
            like_score = np.log1p(video['like_count']) * 2
            comment_score = np.log1p(video['comment_count']) * 3
            
            # Combined trending score
            engagement_score = view_score + like_score + comment_score
            trending_score = engagement_score * time_decay
            
            self.trending_scores[video_id] = trending_score
        
        # Normalize trending scores
        if self.trending_scores:
            max_score = max(self.trending_scores.values())
            if max_score > 0:
                self.trending_scores = {
                    k: v / max_score for k, v in self.trending_scores.items()
                }
        
        logger.info(f"Calculated trending scores for {len(self.trending_scores)} videos")
    
    def update_user_profile(self, user_id: str, interactions: List[Dict]):
        """Update user profile based on interactions"""
        if not interactions:
            return
        
        # Calculate category preferences
        category_scores = defaultdict(float)
        creator_scores = defaultdict(float)
        
        for interaction in interactions:
            video_id = interaction['video_id']
            rating = interaction.get('rating', 0)
            interaction_type = interaction.get('type', 'view')
            
            # Weight different interaction types
            weights = {'view': 1.0, 'like': 2.0, 'comment': 1.5, 'share': 2.5}
            weight = weights.get(interaction_type, 1.0)
            
            score = rating * weight
            
            # Find video info
            if video_id in self.video_features['video_ids']:
                idx = self.video_features['video_ids'].index(video_id)
                category = self.video_features['categories'][idx]
                creator = self.video_features['creators'][idx]
                
                category_scores[category] += score
                creator_scores[creator] += score
        
        # Normalize scores
        total_category_score = sum(category_scores.values())
        total_creator_score = sum(creator_scores.values())
        
        if total_category_score > 0:
            category_scores = {k: v / total_category_score for k, v in category_scores.items()}
        
        if total_creator_score > 0:
            creator_scores = {k: v / total_creator_score for k, v in creator_scores.items()}
        
        self.user_profiles[user_id] = {
            'category_preferences': dict(category_scores),
            'creator_preferences': dict(creator_scores),
            'last_updated': datetime.now()
        }
    
    def get_content_based_recommendations(self, user_id: str, video_history: List[str], 
                                        n_recommendations: int = 20) -> List[Tuple[str, float]]:
        """Get content-based recommendations"""
        if not self.content_similarity_matrix.size or not video_history:
            return []
        
        # Get similarity scores for user's watched videos
        user_scores = np.zeros(len(self.video_features['video_ids']))
        
        for video_id in video_history:
            if video_id in self.video_features['video_ids']:
                idx = self.video_features['video_ids'].index(video_id)
                user_scores += self.content_similarity_matrix[idx]
        
        # Normalize by number of watched videos
        if len(video_history) > 0:
            user_scores /= len(video_history)
        
        # Get top recommendations (excluding already watched)
        video_scores = []
        for i, score in enumerate(user_scores):
            video_id = self.video_features['video_ids'][i]
            if video_id not in video_history:
                video_scores.append((video_id, score))
        
        # Sort by score and return top N
        video_scores.sort(key=lambda x: x[1], reverse=True)
        return video_scores[:n_recommendations]
    
    def get_collaborative_recommendations(self, user_id: str, n_recommendations: int = 20) -> List[Tuple[str, float]]:
        """Get collaborative filtering recommendations"""
        if self.user_item_matrix is None or self.user_item_matrix.shape[0] == 0:
            return []
        
        try:
            # Transform user preferences through the collaborative model
            user_vector = np.zeros(self.user_item_matrix.shape[1])
            
            # Use SVD to generate recommendations
            user_transformed = self.collaborative_model.transform([user_vector])
            reconstructed = self.collaborative_model.inverse_transform(user_transformed)[0]
            
            # Get video recommendations
            video_scores = []
            for i, score in enumerate(reconstructed):
                if i < len(self.video_features['video_ids']):
                    video_id = self.video_features['video_ids'][i]
                    video_scores.append((video_id, score))
            
            # Sort by score and return top N
            video_scores.sort(key=lambda x: x[1], reverse=True)
            return video_scores[:n_recommendations]
            
        except Exception as e:
            logger.error(f"Error in collaborative filtering: {e}")
            return []
    
    def get_trending_recommendations(self, n_recommendations: int = 20) -> List[Tuple[str, float]]:
        """Get trending video recommendations"""
        if not self.trending_scores:
            return []
        
        # Sort trending scores and return top N
        trending_videos = sorted(
            self.trending_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return trending_videos[:n_recommendations]
    
    def get_personalized_recommendations(self, user_id: str, user_history: List[str], 
                                       n_recommendations: int = 20) -> List[Dict]:
        """Get personalized recommendations combining all methods"""
        
        # Get recommendations from different methods
        content_recs = self.get_content_based_recommendations(user_id, user_history, n_recommendations * 2)
        collaborative_recs = self.get_collaborative_recommendations(user_id, n_recommendations * 2)
        trending_recs = self.get_trending_recommendations(n_recommendations)
        
        # Combine and weight recommendations
        combined_scores = defaultdict(float)
        
        # Content-based recommendations (weight: 0.4)
        for video_id, score in content_recs:
            combined_scores[video_id] += score * 0.4
        
        # Collaborative filtering (weight: 0.3)
        for video_id, score in collaborative_recs:
            combined_scores[video_id] += score * 0.3
        
        # Trending recommendations (weight: 0.3)
        for video_id, score in trending_recs:
            combined_scores[video_id] += score * 0.3
        
        # Apply user preferences if available
        if user_id in self.user_profiles:
            user_profile = self.user_profiles[user_id]
            for video_id in combined_scores.keys():
                if video_id in self.video_features['video_ids']:
                    idx = self.video_features['video_ids'].index(video_id)
                    category = self.video_features['categories'][idx]
                    creator = self.video_features['creators'][idx]
                    
                    # Boost based on user preferences
                    category_boost = user_profile['category_preferences'].get(category, 0) * 0.2
                    creator_boost = user_profile['creator_preferences'].get(creator, 0) * 0.1
                    
                    combined_scores[video_id] += category_boost + creator_boost
        
        # Sort and format recommendations
        sorted_recommendations = sorted(
            combined_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:n_recommendations]
        
        # Format recommendations with video details
        recommendations = []
        for video_id, score in sorted_recommendations:
            if video_id in self.video_features['video_ids']:
                idx = self.video_features['video_ids'].index(video_id)
                recommendations.append({
                    'video_id': video_id,
                    'title': self.video_features['titles'][idx],
                    'creator': self.video_features['creators'][idx],
                    'category': self.video_features['categories'][idx],
                    'score': float(score),
                    'recommendation_type': 'personalized'
                })
        
        return recommendations
    
    def save_model(self):
        """Save the trained model components"""
        model_data = {
            'tfidf_vectorizer': self.tfidf_vectorizer,
            'content_similarity_matrix': self.content_similarity_matrix,
            'collaborative_model': self.collaborative_model,
            'user_item_matrix': self.user_item_matrix,
            'video_features': self.video_features,
            'user_profiles': dict(self.user_profiles),
            'trending_scores': self.trending_scores
        }
        
        model_file = os.path.join(self.model_path, 'recommendation_model.pkl')
        with open(model_file, 'wb') as f:
            pickle.dump(model_data, f)
        
        logger.info(f"Model saved to {model_file}")
    
    def load_model(self) -> bool:
        """Load the trained model components"""
        model_file = os.path.join(self.model_path, 'recommendation_model.pkl')
        
        if not os.path.exists(model_file):
            logger.warning(f"Model file not found: {model_file}")
            return False
        
        try:
            with open(model_file, 'rb') as f:
                model_data = pickle.load(f)
            
            self.tfidf_vectorizer = model_data['tfidf_vectorizer']
            self.content_similarity_matrix = model_data['content_similarity_matrix']
            self.collaborative_model = model_data['collaborative_model']
            self.user_item_matrix = model_data['user_item_matrix']
            self.video_features = model_data['video_features']
            self.user_profiles = defaultdict(dict, model_data['user_profiles'])
            self.trending_scores = model_data['trending_scores']
            
            logger.info(f"Model loaded from {model_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False
    
    def train(self, videos: List[Dict], interactions: List[Dict]):
        """Train the recommendation engine"""
        logger.info("Starting recommendation engine training...")
        
        # Preprocess video data
        video_df = self.preprocess_video_data(videos)
        
        # Build features
        self.build_content_features(video_df)
        self.build_collaborative_features(interactions)
        self.calculate_trending_scores(video_df)
        
        # Update user profiles
        user_interactions = defaultdict(list)
        for interaction in interactions:
            user_interactions[interaction['user_id']].append(interaction)
        
        for user_id, user_interactions_list in user_interactions.items():
            self.update_user_profile(user_id, user_interactions_list)
        
        # Save the trained model
        self.save_model()
        
        logger.info("Recommendation engine training completed!")
    
    def get_similar_videos(self, video_id: str, n_similar: int = 10) -> List[Dict]:
        """Get videos similar to a given video"""
        if not self.content_similarity_matrix.size or video_id not in self.video_features['video_ids']:
            return []
        
        video_idx = self.video_features['video_ids'].index(video_id)
        similarity_scores = self.content_similarity_matrix[video_idx]
        
        # Get most similar videos
        similar_indices = np.argsort(similarity_scores)[::-1][1:n_similar+1]  # Exclude the video itself
        
        similar_videos = []
        for idx in similar_indices:
            similar_videos.append({
                'video_id': self.video_features['video_ids'][idx],
                'title': self.video_features['titles'][idx],
                'creator': self.video_features['creators'][idx],
                'category': self.video_features['categories'][idx],
                'similarity_score': float(similarity_scores[idx])
            })
        
        return similar_videos