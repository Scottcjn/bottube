from flask import Blueprint, request, jsonify
from models.database import db
from models.models import Video, User, View, Like
from sqlalchemy import func, desc, and_, or_
from datetime import datetime, timedelta
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import logging

recommendations = Blueprint('recommendations', __name__)
logger = logging.getLogger(__name__)

class RecommendationEngine:
    def __init__(self):
        self.tfidf_vectorizer = None
        self.video_features = None
        self.video_ids = None
        
    def update_video_features(self):
        """Update TF-IDF features for all videos"""
        try:
            videos = Video.query.filter_by(is_active=True).all()
            if not videos:
                return
                
            # Combine title, description, and tags for feature extraction
            video_texts = []
            self.video_ids = []
            
            for video in videos:
                text = f"{video.title} {video.description or ''} {' '.join(video.tags) if video.tags else ''}"
                video_texts.append(text)
                self.video_ids.append(video.id)
            
            # Create TF-IDF features
            self.tfidf_vectorizer = TfidfVectorizer(
                max_features=1000,
                stop_words='english',
                ngram_range=(1, 2)
            )
            self.video_features = self.tfidf_vectorizer.fit_transform(video_texts)
            
        except Exception as e:
            logger.error(f"Error updating video features: {e}")

    def get_user_preferences(self, user_id):
        """Analyze user's viewing history to understand preferences"""
        try:
            # Get user's viewed videos with engagement scores
            viewed_videos = db.session.query(
                Video,
                func.count(View.id).label('view_count'),
                func.count(Like.id).label('like_count')
            ).join(View, Video.id == View.video_id)\
             .outerjoin(Like, and_(Video.id == Like.video_id, Like.user_id == user_id))\
             .filter(View.user_id == user_id)\
             .group_by(Video.id)\
             .order_by(desc('view_count'))\
             .limit(50).all()
            
            if not viewed_videos:
                return {}
                
            # Calculate preference scores based on categories and tags
            category_scores = {}
            tag_scores = {}
            
            for video, view_count, like_count in viewed_videos:
                engagement_score = view_count + (like_count * 2)
                
                # Category preferences
                if video.category:
                    category_scores[video.category] = category_scores.get(video.category, 0) + engagement_score
                
                # Tag preferences
                if video.tags:
                    for tag in video.tags:
                        tag_scores[tag] = tag_scores.get(tag, 0) + engagement_score
            
            return {
                'categories': category_scores,
                'tags': tag_scores,
                'total_videos': len(viewed_videos)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing user preferences: {e}")
            return {}

    def get_content_similarity_scores(self, target_video_id, limit=20):
        """Get videos similar to target video based on content"""
        try:
            if self.video_features is None or target_video_id not in self.video_ids:
                return []
                
            target_index = self.video_ids.index(target_video_id)
            target_features = self.video_features[target_index]
            
            # Calculate cosine similarity
            similarities = cosine_similarity(target_features, self.video_features).flatten()
            
            # Get most similar videos (excluding the target video itself)
            similar_indices = np.argsort(similarities)[::-1][1:limit+1]
            
            similar_videos = []
            for idx in similar_indices:
                video_id = self.video_ids[idx]
                similarity_score = similarities[idx]
                if similarity_score > 0.1:  # Minimum similarity threshold
                    similar_videos.append({
                        'video_id': video_id,
                        'similarity_score': float(similarity_score)
                    })
            
            return similar_videos
            
        except Exception as e:
            logger.error(f"Error calculating content similarity: {e}")
            return []

# Initialize recommendation engine
rec_engine = RecommendationEngine()

@recommendations.route('/personalized/<int:user_id>')
def get_personalized_recommendations(user_id):
    """Get personalized video recommendations for a user"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        # Get user preferences
        user_prefs = rec_engine.get_user_preferences(user_id)
        
        if not user_prefs.get('categories') and not user_prefs.get('tags'):
            # New user - return trending videos
            return get_trending_videos()
        
        # Get videos user hasn't watched
        watched_video_ids = db.session.query(View.video_id)\
            .filter_by(user_id=user_id).distinct().subquery()
        
        # Build recommendation query
        query = Video.query.filter(
            Video.is_active == True,
            ~Video.id.in_(watched_video_ids)
        )
        
        # Apply preference-based filtering
        category_filters = []
        tag_filters = []
        
        if user_prefs.get('categories'):
            top_categories = sorted(user_prefs['categories'].items(), 
                                  key=lambda x: x[1], reverse=True)[:3]
            category_filters = [cat for cat, _ in top_categories]
        
        if user_prefs.get('tags'):
            top_tags = sorted(user_prefs['tags'].items(), 
                            key=lambda x: x[1], reverse=True)[:5]
            tag_filters = [tag for tag, _ in top_tags]
        
        # Apply filters
        if category_filters or tag_filters:
            conditions = []
            if category_filters:
                conditions.append(Video.category.in_(category_filters))
            if tag_filters:
                conditions.append(Video.tags.op('&&')(tag_filters))
            query = query.filter(or_(*conditions))
        
        # Add engagement-based ordering
        query = query.join(View, Video.id == View.video_id, isouter=True)\
                    .join(Like, Video.id == Like.video_id, isouter=True)\
                    .group_by(Video.id)\
                    .order_by(
                        desc(func.count(Like.id)),
                        desc(func.count(View.id)),
                        desc(Video.upload_date)
                    )
        
        # Paginate results
        videos = query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        video_list = []
        for video in videos.items:
            # Calculate engagement metrics
            views = db.session.query(func.count(View.id))\
                .filter_by(video_id=video.id).scalar() or 0
            likes = db.session.query(func.count(Like.id))\
                .filter_by(video_id=video.id).scalar() or 0
            
            video_list.append({
                'id': video.id,
                'title': video.title,
                'description': video.description,
                'thumbnail_url': video.thumbnail_url,
                'duration': video.duration,
                'upload_date': video.upload_date.isoformat(),
                'category': video.category,
                'tags': video.tags,
                'views': views,
                'likes': likes,
                'creator': {
                    'id': video.creator.id,
                    'username': video.creator.username
                } if video.creator else None
            })
        
        return jsonify({
            'videos': video_list,
            'pagination': {
                'page': page,
                'pages': videos.pages,
                'per_page': per_page,
                'total': videos.total
            },
            'recommendation_type': 'personalized'
        })
        
    except Exception as e:
        logger.error(f"Error getting personalized recommendations: {e}")
        return jsonify({'error': 'Failed to get recommendations'}), 500

@recommendations.route('/trending')
def get_trending_videos():
    """Get trending videos based on recent engagement"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        days = request.args.get('days', 7, type=int)
        
        # Define time window for trending calculation
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Calculate trending score based on views, likes, and recency
        trending_query = db.session.query(
            Video,
            (func.count(View.id) + func.count(Like.id) * 2).label('engagement_score'),
            func.count(View.id).label('view_count'),
            func.count(Like.id).label('like_count')
        ).join(View, Video.id == View.video_id, isouter=True)\
         .join(Like, Video.id == Like.video_id, isouter=True)\
         .filter(
             Video.is_active == True,
             Video.upload_date >= cutoff_date
         ).group_by(Video.id)\
          .order_by(desc('engagement_score'))
        
        # Paginate results
        results = trending_query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        video_list = []
        for video, engagement_score, view_count, like_count in results.items:
            video_list.append({
                'id': video.id,
                'title': video.title,
                'description': video.description,
                'thumbnail_url': video.thumbnail_url,
                'duration': video.duration,
                'upload_date': video.upload_date.isoformat(),
                'category': video.category,
                'tags': video.tags,
                'views': view_count or 0,
                'likes': like_count or 0,
                'engagement_score': engagement_score or 0,
                'creator': {
                    'id': video.creator.id,
                    'username': video.creator.username
                } if video.creator else None
            })
        
        return jsonify({
            'videos': video_list,
            'pagination': {
                'page': page,
                'pages': results.pages,
                'per_page': per_page,
                'total': results.total
            },
            'recommendation_type': 'trending',
            'time_window_days': days
        })
        
    except Exception as e:
        logger.error(f"Error getting trending videos: {e}")
        return jsonify({'error': 'Failed to get trending videos'}), 500

@recommendations.route('/similar/<int:video_id>')
def get_similar_videos(video_id):
    """Get videos similar to the specified video"""
    try:
        limit = min(request.args.get('limit', 10, type=int), 50)
        
        # Check if target video exists
        target_video = Video.query.filter_by(id=video_id, is_active=True).first()
        if not target_video:
            return jsonify({'error': 'Video not found'}), 404
        
        # Update video features if needed
        if rec_engine.video_features is None:
            rec_engine.update_video_features()
        
        # Get content-based similar videos
        similar_videos = rec_engine.get_content_similarity_scores(video_id, limit)
        
        if not similar_videos:
            # Fallback to category-based recommendations
            similar_query = Video.query.filter(
                Video.is_active == True,
                Video.id != video_id
            )
            
            if target_video.category:
                similar_query = similar_query.filter_by(category=target_video.category)
            
            similar_query = similar_query.join(View, Video.id == View.video_id, isouter=True)\
                .group_by(Video.id)\
                .order_by(desc(func.count(View.id)))\
                .limit(limit)
            
            similar_videos = [{'video_id': v.id, 'similarity_score': 0.0} for v in similar_query.all()]
        
        # Get video details
        video_details = []
        for item in similar_videos:
            video = Video.query.get(item['video_id'])
            if video and video.is_active:
                # Get engagement metrics
                views = db.session.query(func.count(View.id))\
                    .filter_by(video_id=video.id).scalar() or 0
                likes = db.session.query(func.count(Like.id))\
                    .filter_by(video_id=video.id).scalar() or 0
                
                video_details.append({
                    'id': video.id,
                    'title': video.title,
                    'description': video.description,
                    'thumbnail_url': video.thumbnail_url,
                    'duration': video.duration,
                    'upload_date': video.upload_date.isoformat(),
                    'category': video.category,
                    'tags': video.tags,
                    'views': views,
                    'likes': likes,
                    'similarity_score': item['similarity_score'],
                    'creator': {
                        'id': video.creator.id,
                        'username': video.creator.username
                    } if video.creator else None
                })
        
        return jsonify({
            'target_video': {
                'id': target_video.id,
                'title': target_video.title
            },
            'similar_videos': video_details,
            'recommendation_type': 'similar'
        })
        
    except Exception as e:
        logger.error(f"Error getting similar videos: {e}")
        return jsonify({'error': 'Failed to get similar videos'}), 500

@recommendations.route('/refresh-features', methods=['POST'])
def refresh_video_features():
    """Refresh the video feature vectors for content-based recommendations"""
    try:
        rec_engine.update_video_features()
        return jsonify({'message': 'Video features updated successfully'})
        
    except Exception as e:
        logger.error(f"Error refreshing video features: {e}")
        return jsonify({'error': 'Failed to refresh video features'}), 500

@recommendations.route('/categories')
def get_category_recommendations():
    """Get video recommendations by category"""
    try:
        category = request.args.get('category')
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        if not category:
            return jsonify({'error': 'Category parameter is required'}), 400
        
        # Get videos in specified category with engagement metrics
        query = db.session.query(
            Video,
            func.count(View.id).label('view_count'),
            func.count(Like.id).label('like_count')
        ).join(View, Video.id == View.video_id, isouter=True)\
         .join(Like, Video.id == Like.video_id, isouter=True)\
         .filter(
             Video.is_active == True,
             Video.category == category
         ).group_by(Video.id)\
          .order_by(
              desc('like_count'),
              desc('view_count'),
              desc(Video.upload_date)
          )
        
        # Paginate results
        results = query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        video_list = []
        for video, view_count, like_count in results.items:
            video_list.append({
                'id': video.id,
                'title': video.title,
                'description': video.description,
                'thumbnail_url': video.thumbnail_url,
                'duration': video.duration,
                'upload_date': video.upload_date.isoformat(),
                'category': video.category,
                'tags': video.tags,
                'views': view_count or 0,
                'likes': like_count or 0,
                'creator': {
                    'id': video.creator.id,
                    'username': video.creator.username
                } if video.creator else None
            })
        
        return jsonify({
            'category': category,
            'videos': video_list,
            'pagination': {
                'page': page,
                'pages': results.pages,
                'per_page': per_page,
                'total': results.total
            },
            'recommendation_type': 'category'
        })
        
    except Exception as e:
        logger.error(f"Error getting category recommendations: {e}")
        return jsonify({'error': 'Failed to get category recommendations'}), 500