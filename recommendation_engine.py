import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import StandardScaler
from datetime import datetime, timedelta
import pickle
import os
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class RecommendationEngine:
    def __init__(self):
        self.content_vectorizer = TfidfVectorizer(max_features=5000, stop_words='english')
        self.collaborative_model = TruncatedSVD(n_components=50, random_state=42)
        self.scaler = StandardScaler()
        self.content_features = None
        self.user_item_matrix = None
        self.video_features = pd.DataFrame()
        self.user_interactions = pd.DataFrame()
        self.trending_cache = {}
        self.model_path = 'models/'
        
        # Create models directory if it doesn't exist
        os.makedirs(self.model_path, exist_ok=True)
    
    def prepare_video_features(self, videos_df: pd.DataFrame) -> None:
        """Prepare video features for content-based recommendations"""
        try:
            # Combine textual features
            videos_df['combined_features'] = (
                videos_df.get('title', '').fillna('') + ' ' +
                videos_df.get('description', '').fillna('') + ' ' +
                videos_df.get('tags', '').fillna('') + ' ' +
                videos_df.get('category', '').fillna('')
            )
            
            # Add numeric features
            numeric_features = ['view_count', 'like_count', 'comment_count', 'duration']
            for feature in numeric_features:
                if feature not in videos_df.columns:
                    videos_df[feature] = 0
            
            # Calculate engagement rate
            videos_df['engagement_rate'] = (
                (videos_df['like_count'] + videos_df['comment_count']) / 
                (videos_df['view_count'] + 1)
            )
            
            # Calculate recency score (newer videos get higher scores)
            if 'upload_date' in videos_df.columns:
                videos_df['upload_date'] = pd.to_datetime(videos_df['upload_date'])
                now = datetime.now()
                videos_df['days_since_upload'] = (now - videos_df['upload_date']).dt.days
                videos_df['recency_score'] = np.exp(-videos_df['days_since_upload'] / 30)
            else:
                videos_df['recency_score'] = 1.0
            
            self.video_features = videos_df
            
            # Create TF-IDF features for content
            if len(videos_df) > 0:
                self.content_features = self.content_vectorizer.fit_transform(
                    videos_df['combined_features']
                )
            
            logger.info(f"Prepared features for {len(videos_df)} videos")
            
        except Exception as e:
            logger.error(f"Error preparing video features: {str(e)}")
            raise
    
    def prepare_user_interactions(self, interactions_df: pd.DataFrame) -> None:
        """Prepare user interaction data for collaborative filtering"""
        try:
            # Create user-item interaction matrix
            required_cols = ['user_id', 'video_id', 'interaction_type', 'timestamp']
            for col in required_cols:
                if col not in interactions_df.columns:
                    logger.warning(f"Missing column: {col}")
                    return
            
            # Weight different interaction types
            interaction_weights = {
                'view': 1.0,
                'like': 3.0,
                'comment': 2.0,
                'share': 4.0,
                'subscribe': 5.0
            }
            
            interactions_df['weight'] = interactions_df['interaction_type'].map(
                interaction_weights
            ).fillna(1.0)
            
            # Calculate recency weights (recent interactions matter more)
            interactions_df['timestamp'] = pd.to_datetime(interactions_df['timestamp'])
            now = datetime.now()
            days_diff = (now - interactions_df['timestamp']).dt.days
            interactions_df['recency_weight'] = np.exp(-days_diff / 30)
            
            # Combine weights
            interactions_df['final_weight'] = (
                interactions_df['weight'] * interactions_df['recency_weight']
            )
            
            # Create pivot table
            self.user_item_matrix = interactions_df.pivot_table(
                index='user_id',
                columns='video_id',
                values='final_weight',
                aggfunc='sum',
                fill_value=0
            )
            
            self.user_interactions = interactions_df
            
            # Fit collaborative filtering model
            if self.user_item_matrix.shape[0] > 0 and self.user_item_matrix.shape[1] > 0:
                scaled_matrix = self.scaler.fit_transform(self.user_item_matrix)
                self.collaborative_model.fit(scaled_matrix)
            
            logger.info(f"Prepared interactions: {self.user_item_matrix.shape[0]} users, {self.user_item_matrix.shape[1]} videos")
            
        except Exception as e:
            logger.error(f"Error preparing user interactions: {str(e)}")
            raise
    
    def content_based_recommendations(self, user_id: str, num_recommendations: int = 10) -> List[Dict]:
        """Generate content-based recommendations"""
        try:
            if self.content_features is None or len(self.video_features) == 0:
                return []
            
            # Get user's interaction history
            user_videos = self.user_interactions[
                self.user_interactions['user_id'] == user_id
            ]['video_id'].unique()
            
            if len(user_videos) == 0:
                # New user - return trending videos
                return self.get_trending_recommendations(num_recommendations)
            
            # Calculate user profile based on interacted videos
            user_video_indices = []
            for video_id in user_videos:
                if video_id in self.video_features['video_id'].values:
                    idx = self.video_features[
                        self.video_features['video_id'] == video_id
                    ].index[0]
                    user_video_indices.append(idx)
            
            if not user_video_indices:
                return []
            
            # Create user profile as average of interacted video features
            user_profile = np.mean(self.content_features[user_video_indices], axis=0)
            
            # Calculate similarity with all videos
            similarities = cosine_similarity(user_profile, self.content_features).flatten()
            
            # Get video indices sorted by similarity (excluding already interacted)
            video_sim_pairs = list(enumerate(similarities))
            video_sim_pairs.sort(key=lambda x: x[1], reverse=True)
            
            recommendations = []
            for idx, similarity in video_sim_pairs:
                video_data = self.video_features.iloc[idx]
                
                # Skip if user already interacted with this video
                if video_data['video_id'] in user_videos:
                    continue
                
                recommendations.append({
                    'video_id': video_data['video_id'],
                    'score': float(similarity),
                    'reason': 'content_based',
                    'title': video_data.get('title', ''),
                    'channel': video_data.get('channel', ''),
                    'view_count': int(video_data.get('view_count', 0)),
                    'engagement_rate': float(video_data.get('engagement_rate', 0))
                })
                
                if len(recommendations) >= num_recommendations:
                    break
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error in content-based recommendations: {str(e)}")
            return []
    
    def collaborative_filtering_recommendations(self, user_id: str, num_recommendations: int = 10) -> List[Dict]:
        """Generate collaborative filtering recommendations"""
        try:
            if self.user_item_matrix is None or user_id not in self.user_item_matrix.index:
                return []
            
            # Get user vector
            user_vector = self.user_item_matrix.loc[user_id].values.reshape(1, -1)
            user_scaled = self.scaler.transform(user_vector)
            
            # Transform to latent space
            user_latent = self.collaborative_model.transform(user_scaled)
            
            # Get all user latent representations
            all_users_scaled = self.scaler.transform(self.user_item_matrix.values)
            all_users_latent = self.collaborative_model.transform(all_users_scaled)
            
            # Calculate user similarities
            user_similarities = cosine_similarity(user_latent, all_users_latent).flatten()
            
            # Find similar users (excluding self)
            similar_users_indices = np.argsort(user_similarities)[::-1][1:11]  # Top 10 similar users
            similar_users = self.user_item_matrix.index[similar_users_indices]
            
            # Get videos liked by similar users
            user_videos = set(self.user_item_matrix.loc[user_id][
                self.user_item_matrix.loc[user_id] > 0
            ].index)
            
            video_scores = {}
            for similar_user in similar_users:
                similar_user_videos = self.user_item_matrix.loc[similar_user]
                similar_user_videos = similar_user_videos[similar_user_videos > 0]
                
                for video_id, score in similar_user_videos.items():
                    if video_id not in user_videos:  # User hasn't interacted with this video
                        similarity_weight = user_similarities[
                            self.user_item_matrix.index.get_loc(similar_user)
                        ]
                        video_scores[video_id] = video_scores.get(video_id, 0) + (
                            score * similarity_weight
                        )
            
            # Sort videos by score
            sorted_videos = sorted(video_scores.items(), key=lambda x: x[1], reverse=True)
            
            recommendations = []
            for video_id, score in sorted_videos[:num_recommendations]:
                video_data = self.video_features[
                    self.video_features['video_id'] == video_id
                ]
                
                if len(video_data) > 0:
                    video_data = video_data.iloc[0]
                    recommendations.append({
                        'video_id': video_id,
                        'score': float(score),
                        'reason': 'collaborative_filtering',
                        'title': video_data.get('title', ''),
                        'channel': video_data.get('channel', ''),
                        'view_count': int(video_data.get('view_count', 0)),
                        'engagement_rate': float(video_data.get('engagement_rate', 0))
                    })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error in collaborative filtering: {str(e)}")
            return []
    
    def get_trending_recommendations(self, num_recommendations: int = 10) -> List[Dict]:
        """Generate trending video recommendations"""
        try:
            if len(self.video_features) == 0:
                return []
            
            # Calculate trending score based on recent engagement
            now = datetime.now()
            recent_cutoff = now - timedelta(days=7)  # Last 7 days
            
            # Get recent interactions
            recent_interactions = self.user_interactions[
                pd.to_datetime(self.user_interactions['timestamp']) >= recent_cutoff
            ]
            
            if len(recent_interactions) == 0:
                # Fallback to view count if no recent interactions
                trending_videos = self.video_features.nlargest(
                    num_recommendations, 'view_count'
                )
            else:
                # Calculate trending score
                trending_scores = recent_interactions.groupby('video_id').agg({
                    'final_weight': 'sum',
                    'user_id': 'nunique'
                }).rename(columns={'user_id': 'unique_users'})
                
                # Normalize by time since upload
                video_scores = []
                for video_id, scores in trending_scores.iterrows():
                    video_data = self.video_features[
                        self.video_features['video_id'] == video_id
                    ]
                    
                    if len(video_data) > 0:
                        video_data = video_data.iloc[0]
                        
                        # Trending score combines engagement and recency
                        trending_score = (
                            scores['final_weight'] * 
                            scores['unique_users'] * 
                            video_data.get('recency_score', 1.0)
                        )
                        
                        video_scores.append({
                            'video_id': video_id,
                            'trending_score': trending_score,
                            'video_data': video_data
                        })
                
                # Sort by trending score
                video_scores.sort(key=lambda x: x['trending_score'], reverse=True)
                trending_videos = [item['video_data'] for item in video_scores[:num_recommendations]]
            
            recommendations = []
            for _, video_data in (trending_videos.iterrows() if hasattr(trending_videos, 'iterrows') else enumerate(trending_videos)):
                if isinstance(video_data, dict):
                    video_row = video_data
                else:
                    video_row = video_data
                
                recommendations.append({
                    'video_id': video_row.get('video_id') if hasattr(video_row, 'get') else video_row['video_id'],
                    'score': 1.0,  # Placeholder score for trending
                    'reason': 'trending',
                    'title': video_row.get('title', '') if hasattr(video_row, 'get') else video_row.get('title', ''),
                    'channel': video_row.get('channel', '') if hasattr(video_row, 'get') else video_row.get('channel', ''),
                    'view_count': int(video_row.get('view_count', 0) if hasattr(video_row, 'get') else video_row.get('view_count', 0)),
                    'engagement_rate': float(video_row.get('engagement_rate', 0) if hasattr(video_row, 'get') else video_row.get('engagement_rate', 0))
                })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error in trending recommendations: {str(e)}")
            return []
    
    def hybrid_recommendations(self, user_id: str, num_recommendations: int = 20) -> List[Dict]:
        """Generate hybrid recommendations combining all approaches"""
        try:
            # Get recommendations from each approach
            content_recs = self.content_based_recommendations(user_id, num_recommendations)
            collab_recs = self.collaborative_filtering_recommendations(user_id, num_recommendations)
            trending_recs = self.get_trending_recommendations(num_recommendations)
            
            # Combine and weight recommendations
            all_recs = {}
            
            # Weight different approaches
            weights = {
                'content_based': 0.4,
                'collaborative_filtering': 0.4,
                'trending': 0.2
            }
            
            # Add content-based recommendations
            for rec in content_recs:
                video_id = rec['video_id']
                if video_id not in all_recs:
                    all_recs[video_id] = rec.copy()
                    all_recs[video_id]['combined_score'] = 0
                
                all_recs[video_id]['combined_score'] += rec['score'] * weights['content_based']
            
            # Add collaborative filtering recommendations
            for rec in collab_recs:
                video_id = rec['video_id']
                if video_id not in all_recs:
                    all_recs[video_id] = rec.copy()
                    all_recs[video_id]['combined_score'] = 0
                
                all_recs[video_id]['combined_score'] += rec['score'] * weights['collaborative_filtering']
            
            # Add trending recommendations
            for rec in trending_recs:
                video_id = rec['video_id']
                if video_id not in all_recs:
                    all_recs[video_id] = rec.copy()
                    all_recs[video_id]['combined_score'] = 0
                
                all_recs[video_id]['combined_score'] += rec['score'] * weights['trending']
            
            # Sort by combined score
            sorted_recs = sorted(
                all_recs.values(), 
                key=lambda x: x['combined_score'], 
                reverse=True
            )
            
            return sorted_recs[:num_recommendations]
            
        except Exception as e:
            logger.error(f"Error in hybrid recommendations: {str(e)}")
            return []
    
    def save_model(self, filename: str = 'recommendation_model.pkl') -> None:
        """Save the trained model"""
        try:
            model_data = {
                'content_vectorizer': self.content_vectorizer,
                'collaborative_model': self.collaborative_model,
                'scaler': self.scaler,
                'content_features': self.content_features,
                'user_item_matrix': self.user_item_matrix,
                'video_features': self.video_features,
            }
            
            filepath = os.path.join(self.model_path, filename)
            with open(filepath, 'wb') as f:
                pickle.dump(model_data, f)
            
            logger.info(f"Model saved to {filepath}")
            
        except Exception as e:
            logger.error(f"Error saving model: {str(e)}")
            raise
    
    def load_model(self, filename: str = 'recommendation_model.pkl') -> None:
        """Load a pre-trained model"""
        try:
            filepath = os.path.join(self.model_path, filename)
            
            if not os.path.exists(filepath):
                logger.warning(f"Model file not found: {filepath}")
                return
            
            with open(filepath, 'rb') as f:
                model_data = pickle.load(f)
            
            self.content_vectorizer = model_data.get('content_vectorizer', TfidfVectorizer())
            self.collaborative_model = model_data.get('collaborative_model', TruncatedSVD())
            self.scaler = model_data.get('scaler', StandardScaler())
            self.content_features = model_data.get('content_features')
            self.user_item_matrix = model_data.get('user_item_matrix')
            self.video_features = model_data.get('video_features', pd.DataFrame())
            
            logger.info(f"Model loaded from {filepath}")
            
        except Exception as e:
            logger.error(f"Error loading model: {str(e)}")
            raise
    
    def update_user_interaction(self, user_id: str, video_id: str, interaction_type: str) -> None:
        """Update user interaction in real-time"""
        try:
            new_interaction = pd.DataFrame([{
                'user_id': user_id,
                'video_id': video_id,
                'interaction_type': interaction_type,
                'timestamp': datetime.now()
            }])
            
            self.user_interactions = pd.concat([
                self.user_interactions, new_interaction
            ], ignore_index=True)
            
            # Periodically retrain the model with new interactions
            if len(self.user_interactions) % 100 == 0:
                self.prepare_user_interactions(self.user_interactions)
            
        except Exception as e:
            logger.error(f"Error updating user interaction: {str(e)}")