import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity, linear_kernel
from sklearn.decomposition import TruncatedSVD
from sklearn.neighbors import NearestNeighbors
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Tuple, Optional
import joblib
import os

class RecommendationEngine:
    def __init__(self, model_path: str = "models/"):
        """Initialize the recommendation engine with configurable model storage path."""
        self.model_path = model_path
        self.content_model = None
        self.collaborative_model = None
        self.tfidf_vectorizer = None
        self.content_similarity_matrix = None
        self.user_item_matrix = None
        self.item_features = None
        self.trending_weights = {
            'views': 0.3,
            'likes': 0.25,
            'comments': 0.2,
            'shares': 0.15,
            'recency': 0.1
        }
        
        # Ensure model directory exists
        os.makedirs(model_path, exist_ok=True)
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def prepare_content_features(self, videos_df: pd.DataFrame) -> np.ndarray:
        """Prepare content features for content-based filtering."""
        # Combine text features
        videos_df['combined_features'] = (
            videos_df['title'].fillna('') + ' ' +
            videos_df['description'].fillna('') + ' ' +
            videos_df['tags'].fillna('') + ' ' +
            videos_df['category'].fillna('')
        )
        
        # Initialize TF-IDF vectorizer
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.8
        )
        
        # Fit and transform text features
        content_features = self.tfidf_vectorizer.fit_transform(videos_df['combined_features'])
        
        # Add numerical features
        numerical_features = videos_df[['duration', 'view_count', 'like_count']].fillna(0)
        
        # Normalize numerical features
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        numerical_features_scaled = scaler.fit_transform(numerical_features)
        
        # Combine text and numerical features
        from scipy.sparse import hstack, csr_matrix
        combined_features = hstack([
            content_features,
            csr_matrix(numerical_features_scaled)
        ])
        
        return combined_features

    def build_content_based_model(self, videos_df: pd.DataFrame):
        """Build content-based recommendation model."""
        self.logger.info("Building content-based recommendation model...")
        
        # Prepare features
        content_features = self.prepare_content_features(videos_df)
        
        # Compute similarity matrix
        self.content_similarity_matrix = cosine_similarity(content_features)
        
        # Store item features for future use
        self.item_features = videos_df[['video_id', 'title', 'category', 'creator_id']].copy()
        
        # Save model
        joblib.dump({
            'similarity_matrix': self.content_similarity_matrix,
            'tfidf_vectorizer': self.tfidf_vectorizer,
            'item_features': self.item_features
        }, os.path.join(self.model_path, 'content_model.pkl'))
        
        self.logger.info("Content-based model built successfully")

    def build_collaborative_model(self, interactions_df: pd.DataFrame):
        """Build collaborative filtering model using matrix factorization."""
        self.logger.info("Building collaborative filtering model...")
        
        # Create user-item matrix
        self.user_item_matrix = interactions_df.pivot_table(
            index='user_id',
            columns='video_id',
            values='rating',
            fill_value=0
        )
        
        # Apply SVD for dimensionality reduction
        svd = TruncatedSVD(n_components=50, random_state=42)
        user_factors = svd.fit_transform(self.user_item_matrix)
        item_factors = svd.components_
        
        # Build KNN model for finding similar users
        self.collaborative_model = NearestNeighbors(
            n_neighbors=20,
            metric='cosine',
            algorithm='brute'
        )
        self.collaborative_model.fit(user_factors)
        
        # Save model
        joblib.dump({
            'svd_model': svd,
            'knn_model': self.collaborative_model,
            'user_item_matrix': self.user_item_matrix,
            'user_factors': user_factors,
            'item_factors': item_factors
        }, os.path.join(self.model_path, 'collaborative_model.pkl'))
        
        self.logger.info("Collaborative filtering model built successfully")

    def load_models(self):
        """Load pre-trained models from disk."""
        try:
            # Load content-based model
            content_model_path = os.path.join(self.model_path, 'content_model.pkl')
            if os.path.exists(content_model_path):
                content_data = joblib.load(content_model_path)
                self.content_similarity_matrix = content_data['similarity_matrix']
                self.tfidf_vectorizer = content_data['tfidf_vectorizer']
                self.item_features = content_data['item_features']
                self.logger.info("Content-based model loaded successfully")
            
            # Load collaborative model
            collaborative_model_path = os.path.join(self.model_path, 'collaborative_model.pkl')
            if os.path.exists(collaborative_model_path):
                collab_data = joblib.load(collaborative_model_path)
                self.collaborative_model = collab_data['knn_model']
                self.user_item_matrix = collab_data['user_item_matrix']
                self.logger.info("Collaborative filtering model loaded successfully")
                
        except Exception as e:
            self.logger.error(f"Error loading models: {str(e)}")

    def get_content_recommendations(self, video_id: str, n_recommendations: int = 10) -> List[Dict]:
        """Get content-based recommendations for a given video."""
        if self.content_similarity_matrix is None or self.item_features is None:
            return []
        
        try:
            # Find video index
            video_indices = self.item_features[self.item_features['video_id'] == video_id].index
            if len(video_indices) == 0:
                return []
            
            video_idx = video_indices[0]
            
            # Get similarity scores
            similarity_scores = list(enumerate(self.content_similarity_matrix[video_idx]))
            
            # Sort by similarity (excluding the video itself)
            similarity_scores = sorted(similarity_scores, key=lambda x: x[1], reverse=True)[1:n_recommendations+1]
            
            # Get recommended videos
            recommendations = []
            for idx, score in similarity_scores:
                video_info = self.item_features.iloc[idx]
                recommendations.append({
                    'video_id': video_info['video_id'],
                    'title': video_info['title'],
                    'category': video_info['category'],
                    'creator_id': video_info['creator_id'],
                    'similarity_score': float(score),
                    'recommendation_type': 'content_based'
                })
            
            return recommendations
            
        except Exception as e:
            self.logger.error(f"Error in content-based recommendations: {str(e)}")
            return []

    def get_collaborative_recommendations(self, user_id: str, n_recommendations: int = 10) -> List[Dict]:
        """Get collaborative filtering recommendations for a user."""
        if self.collaborative_model is None or self.user_item_matrix is None:
            return []
        
        try:
            # Check if user exists in the matrix
            if user_id not in self.user_item_matrix.index:
                return []
            
            # Get user's rating vector
            user_ratings = self.user_item_matrix.loc[user_id].values.reshape(1, -1)
            
            # Find similar users
            distances, indices = self.collaborative_model.kneighbors(user_ratings, n_neighbors=20)
            
            # Get recommendations based on similar users' preferences
            similar_users = self.user_item_matrix.index[indices[0]]
            
            # Calculate weighted average ratings for unrated items
            user_rated_items = set(self.user_item_matrix.loc[user_id][self.user_item_matrix.loc[user_id] > 0].index)
            
            recommendations = []
            item_scores = {}
            
            for similar_user in similar_users:
                similar_user_ratings = self.user_item_matrix.loc[similar_user]
                weight = 1.0  # Could be based on distance/similarity
                
                for item, rating in similar_user_ratings.items():
                    if rating > 0 and item not in user_rated_items:
                        if item not in item_scores:
                            item_scores[item] = []
                        item_scores[item].append(rating * weight)
            
            # Calculate average scores and sort
            for item, scores in item_scores.items():
                avg_score = np.mean(scores)
                recommendations.append({
                    'video_id': item,
                    'predicted_rating': float(avg_score),
                    'recommendation_type': 'collaborative'
                })
            
            # Sort by predicted rating and return top N
            recommendations = sorted(recommendations, key=lambda x: x['predicted_rating'], reverse=True)
            return recommendations[:n_recommendations]
            
        except Exception as e:
            self.logger.error(f"Error in collaborative recommendations: {str(e)}")
            return []

    def calculate_trending_score(self, video_data: Dict, current_time: datetime = None) -> float:
        """Calculate trending score based on engagement metrics and recency."""
        if current_time is None:
            current_time = datetime.now()
        
        # Parse upload time
        upload_time = video_data.get('upload_time')
        if isinstance(upload_time, str):
            upload_time = datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
        
        # Calculate time decay (more recent = higher score)
        time_diff = current_time - upload_time
        hours_old = time_diff.total_seconds() / 3600
        recency_score = max(0, 1 - (hours_old / (7 * 24)))  # Decay over 7 days
        
        # Normalize engagement metrics
        views = video_data.get('view_count', 0)
        likes = video_data.get('like_count', 0)
        comments = video_data.get('comment_count', 0)
        shares = video_data.get('share_count', 0)
        
        # Calculate engagement rate
        engagement_rate = (likes + comments + shares) / max(views, 1)
        
        # Calculate weighted trending score
        trending_score = (
            self.trending_weights['views'] * min(views / 10000, 1.0) +
            self.trending_weights['likes'] * min(likes / 1000, 1.0) +
            self.trending_weights['comments'] * min(comments / 100, 1.0) +
            self.trending_weights['shares'] * min(shares / 50, 1.0) +
            self.trending_weights['recency'] * recency_score +
            0.1 * min(engagement_rate * 100, 1.0)  # Engagement bonus
        )
        
        return min(trending_score, 1.0)

    def get_trending_recommendations(self, videos_df: pd.DataFrame, n_recommendations: int = 20) -> List[Dict]:
        """Get trending video recommendations."""
        try:
            # Calculate trending scores for all videos
            trending_videos = []
            
            for _, video in videos_df.iterrows():
                trending_score = self.calculate_trending_score(video.to_dict())
                
                trending_videos.append({
                    'video_id': video['video_id'],
                    'title': video['title'],
                    'category': video['category'],
                    'creator_id': video['creator_id'],
                    'trending_score': trending_score,
                    'view_count': video.get('view_count', 0),
                    'like_count': video.get('like_count', 0),
                    'recommendation_type': 'trending'
                })
            
            # Sort by trending score
            trending_videos = sorted(trending_videos, key=lambda x: x['trending_score'], reverse=True)
            
            return trending_videos[:n_recommendations]
            
        except Exception as e:
            self.logger.error(f"Error in trending recommendations: {str(e)}")
            return []

    def get_hybrid_recommendations(self, user_id: str, videos_df: pd.DataFrame, 
                                 user_history: List[str] = None, n_recommendations: int = 20) -> List[Dict]:
        """Get hybrid recommendations combining all methods."""
        recommendations = []
        
        # Get collaborative recommendations (40% weight)
        collab_recs = self.get_collaborative_recommendations(user_id, n_recommendations)
        for rec in collab_recs:
            rec['hybrid_score'] = rec.get('predicted_rating', 0.5) * 0.4
            recommendations.append(rec)
        
        # Get content-based recommendations (35% weight)
        if user_history:
            for video_id in user_history[-5:]:  # Use last 5 videos
                content_recs = self.get_content_recommendations(video_id, n_recommendations // 2)
                for rec in content_recs:
                    rec['hybrid_score'] = rec.get('similarity_score', 0.5) * 0.35
                    recommendations.append(rec)
        
        # Get trending recommendations (25% weight)
        trending_recs = self.get_trending_recommendations(videos_df, n_recommendations)
        for rec in trending_recs:
            rec['hybrid_score'] = rec.get('trending_score', 0.5) * 0.25
            recommendations.append(rec)
        
        # Remove duplicates and combine scores
        unique_recs = {}
        for rec in recommendations:
            video_id = rec['video_id']
            if video_id in unique_recs:
                unique_recs[video_id]['hybrid_score'] += rec['hybrid_score']
            else:
                unique_recs[video_id] = rec
        
        # Sort by hybrid score
        final_recs = sorted(unique_recs.values(), key=lambda x: x['hybrid_score'], reverse=True)
        
        # Add diversity by ensuring category distribution
        diverse_recs = self._add_diversity(final_recs, n_recommendations)
        
        return diverse_recs

    def _add_diversity(self, recommendations: List[Dict], n_recommendations: int) -> List[Dict]:
        """Add diversity to recommendations by balancing categories."""
        if not recommendations:
            return []
        
        category_counts = {}
        diverse_recs = []
        max_per_category = max(2, n_recommendations // 5)  # Limit videos per category
        
        for rec in recommendations:
            category = rec.get('category', 'other')
            current_count = category_counts.get(category, 0)
            
            if current_count < max_per_category:
                diverse_recs.append(rec)
                category_counts[category] = current_count + 1
                
                if len(diverse_recs) >= n_recommendations:
                    break
        
        # If we need more recommendations, fill with remaining items
        if len(diverse_recs) < n_recommendations:
            remaining = [rec for rec in recommendations if rec not in diverse_recs]
            diverse_recs.extend(remaining[:n_recommendations - len(diverse_recs)])
        
        return diverse_recs

    def train_models(self, videos_df: pd.DataFrame, interactions_df: pd.DataFrame):
        """Train all recommendation models."""
        self.logger.info("Starting model training...")
        
        # Build content-based model
        self.build_content_based_model(videos_df)
        
        # Build collaborative filtering model
        self.build_collaborative_model(interactions_df)
        
        self.logger.info("All models trained successfully")

    def get_user_recommendations(self, user_id: str, videos_df: pd.DataFrame, 
                               user_history: List[str] = None, method: str = 'hybrid', 
                               n_recommendations: int = 20) -> List[Dict]:
        """Main method to get recommendations for a user."""
        if method == 'content':
            if user_history:
                return self.get_content_recommendations(user_history[-1], n_recommendations)
            return []
        elif method == 'collaborative':
            return self.get_collaborative_recommendations(user_id, n_recommendations)
        elif method == 'trending':
            return self.get_trending_recommendations(videos_df, n_recommendations)
        else:  # hybrid
            return self.get_hybrid_recommendations(user_id, videos_df, user_history, n_recommendations)