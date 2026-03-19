import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import NMF
from sklearn.preprocessing import StandardScaler
from typing import List, Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class RecommendationEngine:
    def __init__(self):
        self.content_vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2),
            max_df=0.8,
            min_df=2
        )
        self.content_similarity_matrix = None
        self.content_features = None
        self.user_item_matrix = None
        self.nmf_model = None
        self.scaler = StandardScaler()
        self.videos_df = None
        self.interactions_df = None
        
    def prepare_content_features(self, videos_data: List[Dict]) -> None:
        """Prepare content-based features from video metadata"""
        try:
            self.videos_df = pd.DataFrame(videos_data)
            
            # Combine text features
            text_features = []
            for _, video in self.videos_df.iterrows():
                combined_text = f"{video.get('title', '')} {video.get('description', '')} {video.get('tags', '')}"
                text_features.append(combined_text)
            
            # Create TF-IDF features
            self.content_features = self.content_vectorizer.fit_transform(text_features)
            
            # Calculate content similarity matrix
            self.content_similarity_matrix = cosine_similarity(self.content_features)
            
            logger.info(f"Content features prepared for {len(videos_data)} videos")
            
        except Exception as e:
            logger.error(f"Error preparing content features: {e}")
            raise
    
    def prepare_collaborative_features(self, interactions_data: List[Dict]) -> None:
        """Prepare collaborative filtering features from user interactions"""
        try:
            self.interactions_df = pd.DataFrame(interactions_data)
            
            # Create user-item matrix
            self.user_item_matrix = self.interactions_df.pivot_table(
                index='user_id',
                columns='video_id',
                values='rating',
                fill_value=0
            )
            
            # Apply NMF for dimensionality reduction
            n_components = min(50, min(self.user_item_matrix.shape) - 1)
            self.nmf_model = NMF(n_components=n_components, random_state=42, max_iter=200)
            
            # Normalize the matrix
            normalized_matrix = self.scaler.fit_transform(self.user_item_matrix.values)
            self.nmf_model.fit(normalized_matrix)
            
            logger.info(f"Collaborative features prepared for {len(self.user_item_matrix)} users")
            
        except Exception as e:
            logger.error(f"Error preparing collaborative features: {e}")
            raise
    
    def get_content_based_recommendations(self, video_id: str, n_recommendations: int = 10) -> List[Dict]:
        """Generate content-based recommendations"""
        try:
            if self.content_similarity_matrix is None or self.videos_df is None:
                return []
            
            # Find video index
            video_indices = self.videos_df[self.videos_df['id'] == video_id].index
            if len(video_indices) == 0:
                return []
            
            video_idx = video_indices[0]
            
            # Get similarity scores
            similarity_scores = list(enumerate(self.content_similarity_matrix[video_idx]))
            similarity_scores = sorted(similarity_scores, key=lambda x: x[1], reverse=True)
            
            # Get top recommendations (excluding the input video)
            recommendations = []
            for i, score in similarity_scores[1:n_recommendations+1]:
                video_data = self.videos_df.iloc[i].to_dict()
                video_data['similarity_score'] = float(score)
                video_data['recommendation_type'] = 'content_based'
                recommendations.append(video_data)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating content-based recommendations: {e}")
            return []
    
    def get_collaborative_recommendations(self, user_id: str, n_recommendations: int = 10) -> List[Dict]:
        """Generate collaborative filtering recommendations"""
        try:
            if self.nmf_model is None or self.user_item_matrix is None or self.videos_df is None:
                return []
            
            # Check if user exists
            if user_id not in self.user_item_matrix.index:
                return []
            
            user_idx = self.user_item_matrix.index.get_loc(user_id)
            
            # Get user factors
            user_vector = self.scaler.transform([self.user_item_matrix.iloc[user_idx].values])
            user_factors = self.nmf_model.transform(user_vector)[0]
            
            # Generate predictions for all items
            item_factors = self.nmf_model.components_
            predicted_ratings = np.dot(user_factors, item_factors)
            
            # Get top recommendations for items not already rated
            user_ratings = self.user_item_matrix.iloc[user_idx]
            unrated_items = user_ratings[user_ratings == 0].index
            
            recommendations = []
            item_scores = []
            
            for item_id in unrated_items:
                if item_id in self.user_item_matrix.columns:
                    item_idx = self.user_item_matrix.columns.get_loc(item_id)
                    score = predicted_ratings[item_idx]
                    item_scores.append((item_id, score))
            
            # Sort by predicted score
            item_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Get video details
            for item_id, score in item_scores[:n_recommendations]:
                video_data = self.videos_df[self.videos_df['id'] == item_id]
                if not video_data.empty:
                    video_dict = video_data.iloc[0].to_dict()
                    video_dict['predicted_rating'] = float(score)
                    video_dict['recommendation_type'] = 'collaborative'
                    recommendations.append(video_dict)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating collaborative recommendations: {e}")
            return []
    
    def get_hybrid_recommendations(self, user_id: Optional[str] = None, video_id: Optional[str] = None, 
                                 n_recommendations: int = 10) -> List[Dict]:
        """Generate hybrid recommendations combining content and collaborative filtering"""
        try:
            content_recs = []
            collaborative_recs = []
            
            # Get content-based recommendations
            if video_id:
                content_recs = self.get_content_based_recommendations(video_id, n_recommendations)
            
            # Get collaborative recommendations
            if user_id:
                collaborative_recs = self.get_collaborative_recommendations(user_id, n_recommendations)
            
            # Combine and weight recommendations
            hybrid_recs = []
            seen_videos = set()
            
            # Content-based recommendations (weight: 0.4)
            for rec in content_recs:
                if rec['id'] not in seen_videos:
                    rec['hybrid_score'] = 0.4 * rec.get('similarity_score', 0)
                    hybrid_recs.append(rec)
                    seen_videos.add(rec['id'])
            
            # Collaborative recommendations (weight: 0.6)
            for rec in collaborative_recs:
                if rec['id'] not in seen_videos:
                    rec['hybrid_score'] = 0.6 * rec.get('predicted_rating', 0)
                    rec['recommendation_type'] = 'collaborative'
                    hybrid_recs.append(rec)
                    seen_videos.add(rec['id'])
                else:
                    # Boost score if video appears in both methods
                    for existing_rec in hybrid_recs:
                        if existing_rec['id'] == rec['id']:
                            existing_rec['hybrid_score'] += 0.6 * rec.get('predicted_rating', 0)
                            existing_rec['recommendation_type'] = 'hybrid'
                            break
            
            # Sort by hybrid score
            hybrid_recs.sort(key=lambda x: x.get('hybrid_score', 0), reverse=True)
            
            return hybrid_recs[:n_recommendations]
            
        except Exception as e:
            logger.error(f"Error generating hybrid recommendations: {e}")
            return []
    
    def get_trending_recommendations(self, time_window_hours: int = 24, n_recommendations: int = 10) -> List[Dict]:
        """Generate trending video recommendations based on recent interactions"""
        try:
            if self.interactions_df is None or self.videos_df is None:
                return []
            
            # Filter recent interactions
            current_time = pd.Timestamp.now()
            time_threshold = current_time - pd.Timedelta(hours=time_window_hours)
            
            if 'timestamp' in self.interactions_df.columns:
                recent_interactions = self.interactions_df[
                    pd.to_datetime(self.interactions_df['timestamp']) >= time_threshold
                ]
            else:
                recent_interactions = self.interactions_df
            
            # Calculate trending scores
            trending_scores = recent_interactions.groupby('video_id').agg({
                'rating': ['count', 'mean'],
                'user_id': 'nunique'
            }).reset_index()
            
            trending_scores.columns = ['video_id', 'interaction_count', 'avg_rating', 'unique_users']
            
            # Calculate trending score combining multiple factors
            trending_scores['trending_score'] = (
                trending_scores['interaction_count'] * 0.4 +
                trending_scores['avg_rating'] * 0.3 +
                trending_scores['unique_users'] * 0.3
            )
            
            trending_scores = trending_scores.sort_values('trending_score', ascending=False)
            
            # Get video details
            recommendations = []
            for _, row in trending_scores.head(n_recommendations).iterrows():
                video_data = self.videos_df[self.videos_df['id'] == row['video_id']]
                if not video_data.empty:
                    video_dict = video_data.iloc[0].to_dict()
                    video_dict['trending_score'] = float(row['trending_score'])
                    video_dict['interaction_count'] = int(row['interaction_count'])
                    video_dict['avg_rating'] = float(row['avg_rating'])
                    video_dict['recommendation_type'] = 'trending'
                    recommendations.append(video_dict)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating trending recommendations: {e}")
            return []
    
    def get_user_similarity(self, user_id1: str, user_id2: str) -> float:
        """Calculate similarity between two users based on their ratings"""
        try:
            if self.user_item_matrix is None:
                return 0.0
            
            if user_id1 not in self.user_item_matrix.index or user_id2 not in self.user_item_matrix.index:
                return 0.0
            
            user1_ratings = self.user_item_matrix.loc[user_id1].values.reshape(1, -1)
            user2_ratings = self.user_item_matrix.loc[user_id2].values.reshape(1, -1)
            
            similarity = cosine_similarity(user1_ratings, user2_ratings)[0][0]
            return float(similarity)
            
        except Exception as e:
            logger.error(f"Error calculating user similarity: {e}")
            return 0.0
    
    def update_user_interaction(self, user_id: str, video_id: str, rating: float, interaction_type: str = 'rating'):
        """Update user interaction data for real-time recommendations"""
        try:
            new_interaction = {
                'user_id': user_id,
                'video_id': video_id,
                'rating': rating,
                'interaction_type': interaction_type,
                'timestamp': pd.Timestamp.now()
            }
            
            if self.interactions_df is None:
                self.interactions_df = pd.DataFrame([new_interaction])
            else:
                self.interactions_df = pd.concat([
                    self.interactions_df,
                    pd.DataFrame([new_interaction])
                ], ignore_index=True)
            
            # Rebuild collaborative features if enough new interactions
            if len(self.interactions_df) % 100 == 0:  # Rebuild every 100 interactions
                self.prepare_collaborative_features(self.interactions_df.to_dict('records'))
            
            logger.info(f"Updated interaction for user {user_id} and video {video_id}")
            
        except Exception as e:
            logger.error(f"Error updating user interaction: {e}")