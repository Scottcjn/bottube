import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import StandardScaler
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Tuple, Optional
import pickle
import os
import json

class RecommendationEngine:
    def __init__(self, config: Dict = None):
        """Initialize the recommendation engine with configuration."""
        self.config = config or {}
        self.content_model = None
        self.collaborative_model = None
        self.tfidf_vectorizer = None
        self.content_features = None
        self.user_item_matrix = None
        self.scaler = StandardScaler()
        
        # Model paths
        self.models_dir = self.config.get('models_dir', 'models')
        os.makedirs(self.models_dir, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
        
    def load_data(self, videos_df: pd.DataFrame, interactions_df: pd.DataFrame, users_df: pd.DataFrame = None):
        """Load and preprocess data for recommendation models."""
        self.videos_df = videos_df.copy()
        self.interactions_df = interactions_df.copy()
        self.users_df = users_df.copy() if users_df is not None else None
        
        # Preprocess video data
        self.videos_df['combined_features'] = self.videos_df.apply(
            lambda row: f"{row.get('title', '')} {row.get('description', '')} {row.get('tags', '')} {row.get('category', '')}", 
            axis=1
        )
        
        # Add engagement metrics
        if 'views' not in self.videos_df.columns:
            self.videos_df['views'] = 0
        if 'likes' not in self.videos_df.columns:
            self.videos_df['likes'] = 0
        if 'shares' not in self.videos_df.columns:
            self.videos_df['shares'] = 0
        if 'created_at' not in self.videos_df.columns:
            self.videos_df['created_at'] = datetime.now()
            
        # Calculate engagement score
        self.videos_df['engagement_score'] = (
            self.videos_df['likes'] * 2 + 
            self.videos_df['shares'] * 3 + 
            self.videos_df['views'] * 0.1
        )
        
    def build_content_based_model(self):
        """Build content-based filtering model using TF-IDF and cosine similarity."""
        try:
            # Initialize TF-IDF vectorizer
            self.tfidf_vectorizer = TfidfVectorizer(
                max_features=5000,
                stop_words='english',
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.8
            )
            
            # Fit TF-IDF on video features
            tfidf_matrix = self.tfidf_vectorizer.fit_transform(self.videos_df['combined_features'])
            
            # Calculate cosine similarity matrix
            self.content_similarity_matrix = cosine_similarity(tfidf_matrix)
            
            # Store additional features for hybrid recommendations
            numeric_features = ['views', 'likes', 'shares', 'engagement_score']
            existing_features = [f for f in numeric_features if f in self.videos_df.columns]
            
            if existing_features:
                self.content_features = self.scaler.fit_transform(
                    self.videos_df[existing_features].fillna(0)
                )
            
            self.logger.info("Content-based model built successfully")
            
        except Exception as e:
            self.logger.error(f"Error building content-based model: {str(e)}")
            raise
            
    def build_collaborative_filtering_model(self, n_components: int = 50):
        """Build collaborative filtering model using matrix factorization."""
        try:
            if self.interactions_df.empty:
                self.logger.warning("No interaction data available for collaborative filtering")
                return
                
            # Create user-item matrix
            self.user_item_matrix = self.interactions_df.pivot_table(
                index='user_id',
                columns='video_id', 
                values='rating',
                fill_value=0
            )
            
            # Apply SVD for matrix factorization
            self.collaborative_model = TruncatedSVD(
                n_components=min(n_components, min(self.user_item_matrix.shape) - 1),
                random_state=42
            )
            
            # Fit the model
            self.user_factors = self.collaborative_model.fit_transform(self.user_item_matrix)
            self.item_factors = self.collaborative_model.components_.T
            
            self.logger.info("Collaborative filtering model built successfully")
            
        except Exception as e:
            self.logger.error(f"Error building collaborative filtering model: {str(e)}")
            raise
            
    def get_content_based_recommendations(self, video_id: str, n_recommendations: int = 10) -> List[Tuple[str, float]]:
        """Get content-based recommendations for a given video."""
        try:
            if self.content_similarity_matrix is None:
                raise ValueError("Content-based model not built")
                
            # Find video index
            if video_id not in self.videos_df['video_id'].values:
                return []
                
            video_idx = self.videos_df[self.videos_df['video_id'] == video_id].index[0]
            
            # Get similarity scores
            similarity_scores = self.content_similarity_matrix[video_idx]
            
            # Get top similar videos (excluding the input video)
            similar_indices = np.argsort(similarity_scores)[::-1][1:n_recommendations+1]
            
            recommendations = []
            for idx in similar_indices:
                recommended_video_id = self.videos_df.iloc[idx]['video_id']
                score = similarity_scores[idx]
                recommendations.append((recommended_video_id, score))
                
            return recommendations
            
        except Exception as e:
            self.logger.error(f"Error getting content-based recommendations: {str(e)}")
            return []
            
    def get_collaborative_recommendations(self, user_id: str, n_recommendations: int = 10) -> List[Tuple[str, float]]:
        """Get collaborative filtering recommendations for a user."""
        try:
            if self.collaborative_model is None or self.user_item_matrix is None:
                return []
                
            if user_id not in self.user_item_matrix.index:
                return []
                
            # Get user index
            user_idx = self.user_item_matrix.index.get_loc(user_id)
            
            # Get user factors
            user_vector = self.user_factors[user_idx]
            
            # Calculate predicted ratings for all items
            predicted_ratings = np.dot(user_vector, self.item_factors.T)
            
            # Get videos user hasn't interacted with
            user_interactions = self.user_item_matrix.loc[user_id]
            unrated_items = user_interactions[user_interactions == 0].index
            
            # Get recommendations from unrated items
            recommendations = []
            for video_id in unrated_items:
                if video_id in self.user_item_matrix.columns:
                    item_idx = self.user_item_matrix.columns.get_loc(video_id)
                    score = predicted_ratings[item_idx]
                    recommendations.append((video_id, score))
                    
            # Sort by predicted rating
            recommendations.sort(key=lambda x: x[1], reverse=True)
            
            return recommendations[:n_recommendations]
            
        except Exception as e:
            self.logger.error(f"Error getting collaborative recommendations: {str(e)}")
            return []
            
    def get_trending_recommendations(self, n_recommendations: int = 10, time_window: int = 7) -> List[Tuple[str, float]]:
        """Get trending videos based on recent engagement."""
        try:
            # Calculate trending score based on recent activity
            cutoff_date = datetime.now() - timedelta(days=time_window)
            
            # Filter recent videos
            recent_videos = self.videos_df[
                pd.to_datetime(self.videos_df['created_at']) >= cutoff_date
            ].copy()
            
            if recent_videos.empty:
                # Fallback to all videos if no recent ones
                recent_videos = self.videos_df.copy()
                
            # Calculate trending score with time decay
            def calculate_trending_score(row):
                days_old = (datetime.now() - pd.to_datetime(row['created_at'])).days
                time_decay = 1 / (1 + days_old * 0.1)  # Decay factor
                
                base_score = (
                    row['views'] * 0.4 + 
                    row['likes'] * 1.5 + 
                    row['shares'] * 3.0
                )
                
                return base_score * time_decay
                
            recent_videos['trending_score'] = recent_videos.apply(calculate_trending_score, axis=1)
            
            # Sort by trending score
            trending_videos = recent_videos.nlargest(n_recommendations, 'trending_score')
            
            recommendations = []
            for _, video in trending_videos.iterrows():
                recommendations.append((video['video_id'], video['trending_score']))
                
            return recommendations
            
        except Exception as e:
            self.logger.error(f"Error getting trending recommendations: {str(e)}")
            return []
            
    def get_hybrid_recommendations(self, user_id: str = None, video_id: str = None, 
                                 n_recommendations: int = 10, weights: Dict[str, float] = None) -> List[Tuple[str, float]]:
        """Get hybrid recommendations combining multiple approaches."""
        try:
            if weights is None:
                weights = {
                    'content': 0.4,
                    'collaborative': 0.4,
                    'trending': 0.2
                }
                
            all_recommendations = {}
            
            # Get content-based recommendations
            if video_id and weights.get('content', 0) > 0:
                content_recs = self.get_content_based_recommendations(video_id, n_recommendations * 2)
                for vid_id, score in content_recs:
                    if vid_id not in all_recommendations:
                        all_recommendations[vid_id] = 0
                    all_recommendations[vid_id] += score * weights['content']
                    
            # Get collaborative recommendations
            if user_id and weights.get('collaborative', 0) > 0:
                collab_recs = self.get_collaborative_recommendations(user_id, n_recommendations * 2)
                for vid_id, score in collab_recs:
                    if vid_id not in all_recommendations:
                        all_recommendations[vid_id] = 0
                    all_recommendations[vid_id] += score * weights['collaborative']
                    
            # Get trending recommendations
            if weights.get('trending', 0) > 0:
                trending_recs = self.get_trending_recommendations(n_recommendations * 2)
                max_trending_score = max([score for _, score in trending_recs]) if trending_recs else 1
                
                for vid_id, score in trending_recs:
                    normalized_score = score / max_trending_score  # Normalize trending scores
                    if vid_id not in all_recommendations:
                        all_recommendations[vid_id] = 0
                    all_recommendations[vid_id] += normalized_score * weights['trending']
                    
            # Sort by combined score
            sorted_recommendations = sorted(
                all_recommendations.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            return sorted_recommendations[:n_recommendations]
            
        except Exception as e:
            self.logger.error(f"Error getting hybrid recommendations: {str(e)}")
            return []
            
    def get_personalized_feed(self, user_id: str, n_recommendations: int = 20) -> List[Dict]:
        """Generate personalized feed for a user."""
        try:
            # Get user interaction history
            user_interactions = self.interactions_df[
                self.interactions_df['user_id'] == user_id
            ] if not self.interactions_df.empty else pd.DataFrame()
            
            # Determine weights based on user activity
            if len(user_interactions) > 10:
                weights = {'content': 0.3, 'collaborative': 0.5, 'trending': 0.2}
            elif len(user_interactions) > 0:
                weights = {'content': 0.4, 'collaborative': 0.3, 'trending': 0.3}
            else:
                # New user - rely more on trending content
                weights = {'content': 0.2, 'collaborative': 0.1, 'trending': 0.7}
                
            # Get most recent interaction for content-based recommendations
            recent_video_id = None
            if not user_interactions.empty:
                recent_interaction = user_interactions.sort_values('timestamp', ascending=False).iloc[0]
                recent_video_id = recent_interaction['video_id']
                
            # Get hybrid recommendations
            recommendations = self.get_hybrid_recommendations(
                user_id=user_id,
                video_id=recent_video_id,
                n_recommendations=n_recommendations,
                weights=weights
            )
            
            # Format recommendations with video details
            feed = []
            for video_id, score in recommendations:
                video_data = self.videos_df[self.videos_df['video_id'] == video_id]
                if not video_data.empty:
                    video_info = video_data.iloc[0].to_dict()
                    video_info['recommendation_score'] = score
                    video_info['recommendation_reason'] = self._get_recommendation_reason(
                        user_id, video_id, weights
                    )
                    feed.append(video_info)
                    
            return feed
            
        except Exception as e:
            self.logger.error(f"Error generating personalized feed: {str(e)}")
            return []
            
    def _get_recommendation_reason(self, user_id: str, video_id: str, weights: Dict) -> str:
        """Generate explanation for why a video was recommended."""
        reasons = []
        
        if weights.get('trending', 0) > 0.3:
            reasons.append("trending")
        if weights.get('collaborative', 0) > 0.3:
            reasons.append("similar users liked")
        if weights.get('content', 0) > 0.3:
            reasons.append("similar content")
            
        if not reasons:
            return "recommended for you"
            
        return f"Recommended because it's {' and '.join(reasons)}"
        
    def save_models(self):
        """Save trained models to disk."""
        try:
            models_to_save = {
                'content_similarity_matrix': self.content_similarity_matrix,
                'tfidf_vectorizer': self.tfidf_vectorizer,
                'collaborative_model': self.collaborative_model,
                'user_item_matrix': self.user_item_matrix,
                'content_features': self.content_features,
                'scaler': self.scaler
            }
            
            for model_name, model_obj in models_to_save.items():
                if model_obj is not None:
                    model_path = os.path.join(self.models_dir, f'{model_name}.pkl')
                    with open(model_path, 'wb') as f:
                        pickle.dump(model_obj, f)
                        
            self.logger.info("Models saved successfully")
            
        except Exception as e:
            self.logger.error(f"Error saving models: {str(e)}")
            
    def load_models(self):
        """Load trained models from disk."""
        try:
            model_files = [
                'content_similarity_matrix.pkl',
                'tfidf_vectorizer.pkl', 
                'collaborative_model.pkl',
                'user_item_matrix.pkl',
                'content_features.pkl',
                'scaler.pkl'
            ]
            
            for model_file in model_files:
                model_path = os.path.join(self.models_dir, model_file)
                if os.path.exists(model_path):
                    with open(model_path, 'rb') as f:
                        model_obj = pickle.load(f)
                        
                    model_name = model_file.replace('.pkl', '')
                    setattr(self, model_name, model_obj)
                    
            self.logger.info("Models loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Error loading models: {str(e)}")
            
    def update_models_incremental(self, new_videos_df: pd.DataFrame = None, 
                                new_interactions_df: pd.DataFrame = None):
        """Update models incrementally with new data."""
        try:
            # Update video data
            if new_videos_df is not None and not new_videos_df.empty:
                self.videos_df = pd.concat([self.videos_df, new_videos_df], ignore_index=True)
                self.videos_df = self.videos_df.drop_duplicates(subset=['video_id'], keep='last')
                
            # Update interaction data
            if new_interactions_df is not None and not new_interactions_df.empty:
                self.interactions_df = pd.concat([self.interactions_df, new_interactions_df], ignore_index=True)
                self.interactions_df = self.interactions_df.drop_duplicates(
                    subset=['user_id', 'video_id', 'timestamp'], keep='last'
                )
                
            # Rebuild models with updated data
            self.build_content_based_model()
            if not self.interactions_df.empty:
                self.build_collaborative_filtering_model()
                
            self.logger.info("Models updated incrementally")
            
        except Exception as e:
            self.logger.error(f"Error updating models incrementally: {str(e)}")
            
    def get_model_stats(self) -> Dict:
        """Get statistics about the recommendation models."""
        try:
            stats = {
                'total_videos': len(self.videos_df) if hasattr(self, 'videos_df') else 0,
                'total_interactions': len(self.interactions_df) if hasattr(self, 'interactions_df') else 0,
                'unique_users': self.interactions_df['user_id'].nunique() if hasattr(self, 'interactions_df') and not self.interactions_df.empty else 0,
                'content_model_built': self.content_similarity_matrix is not None,
                'collaborative_model_built': self.collaborative_model is not None,
                'models_dir': self.models_dir
            }
            
            if hasattr(self, 'user_item_matrix') and self.user_item_matrix is not None:
                stats['matrix_density'] = (self.user_item_matrix != 0).sum().sum() / (self.user_item_matrix.shape[0] * self.user_item_matrix.shape[1])
                
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting model stats: {str(e)}")
            return {}