from flask import g, request
import sqlite3
import math
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import re

def get_db():
    if not hasattr(g, 'database'):
        g.database = sqlite3.connect('bottube.db')
        g.database.row_factory = sqlite3.Row
    return g.database

class RecommendationEngine:
    def __init__(self):
        self.stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should'}

    def tokenize_text(self, text):
        if not text:
            return []
        words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
        return [word for word in words if word not in self.stopwords]

    def compute_tf_idf(self, videos):
        docs = {}
        all_words = set()
        
        for video in videos:
            video_id = video['id']
            text = f"{video['title']} {video['description'] or ''} {video.get('tags', '') or ''}"
            words = self.tokenize_text(text)
            
            word_counts = Counter(words)
            docs[video_id] = word_counts
            all_words.update(words)
        
        vocab_size = len(docs)
        tfidf_vectors = {}
        
        for video_id, word_counts in docs.items():
            vector = {}
            total_words = sum(word_counts.values())
            
            for word in all_words:
                tf = word_counts.get(word, 0) / max(total_words, 1)
                
                doc_freq = sum(1 for doc in docs.values() if word in doc)
                idf = math.log(vocab_size / max(doc_freq, 1))
                
                vector[word] = tf * idf
            
            tfidf_vectors[video_id] = vector
        
        return tfidf_vectors

    def cosine_similarity(self, vec1, vec2):
        dot_product = sum(vec1.get(word, 0) * vec2.get(word, 0) for word in set(vec1.keys()) | set(vec2.keys()))
        
        norm1 = math.sqrt(sum(val ** 2 for val in vec1.values()))
        norm2 = math.sqrt(sum(val ** 2 for val in vec2.values()))
        
        if norm1 == 0 or norm2 == 0:
            return 0
        
        return dot_product / (norm1 * norm2)

    def get_user_preferences(self, user_id):
        """Analyze user's viewing patterns to build preference profile"""
        db = get_db()
        
        # Get user's watch history with engagement data
        cursor = db.execute("""
            SELECT v.id, v.title, v.description, v.tags, v.category, v.upload_date,
                   vh.watched_at, vh.watch_duration,
                   COUNT(l.id) as likes_count,
                   COUNT(c.id) as comments_count
            FROM view_history vh
            JOIN videos v ON vh.video_id = v.id
            LEFT JOIN likes l ON v.id = l.video_id AND l.user_id = ?
            LEFT JOIN comments c ON v.id = c.video_id AND c.user_id = ?
            WHERE vh.user_id = ?
            GROUP BY v.id, vh.watched_at, vh.watch_duration
            ORDER BY vh.watched_at DESC
            LIMIT 100
        """, (user_id, user_id, user_id))
        
        watch_history = cursor.fetchall()
        
        if not watch_history:
            return {}
        
        # Build preference profile
        category_scores = defaultdict(float)
        keyword_scores = defaultdict(float)
        
        for video in watch_history:
            # Weight by engagement
            engagement_weight = 1.0
            if video['likes_count'] > 0:
                engagement_weight += 0.5
            if video['comments_count'] > 0:
                engagement_weight += 0.3
            
            # Category preference
            if video['category']:
                category_scores[video['category']] += engagement_weight
            
            # Keyword preferences from title and tags
            text = f"{video['title']} {video.get('tags', '') or ''}"
            keywords = self.tokenize_text(text)
            for keyword in keywords:
                keyword_scores[keyword] += engagement_weight
        
        return {
            'categories': dict(category_scores),
            'keywords': dict(keyword_scores)
        }

    def get_recommendations(self, user_id, limit=20):
        """Generate personalized video recommendations"""
        db = get_db()
        
        # Get user preferences
        user_prefs = self.get_user_preferences(user_id)
        
        # Get videos user hasn't watched
        cursor = db.execute("""
            SELECT v.id, v.title, v.description, v.tags, v.category,
                   v.upload_date, v.views, v.duration,
                   COUNT(l.id) as total_likes,
                   COUNT(c.id) as total_comments
            FROM videos v
            LEFT JOIN view_history vh ON v.id = vh.video_id AND vh.user_id = ?
            LEFT JOIN likes l ON v.id = l.video_id
            LEFT JOIN comments c ON v.id = c.video_id
            WHERE vh.video_id IS NULL
            GROUP BY v.id
            ORDER BY v.upload_date DESC
            LIMIT 1000
        """, (user_id,))
        
        candidate_videos = cursor.fetchall()
        
        if not candidate_videos:
            return []
        
        # Score each video
        scored_videos = []
        
        for video in candidate_videos:
            score = 0.0
            
            # Category matching score
            if video['category'] and video['category'] in user_prefs.get('categories', {}):
                score += user_prefs['categories'][video['category']] * 0.3
            
            # Keyword matching score
            text = f"{video['title']} {video.get('tags', '') or ''}"
            keywords = self.tokenize_text(text)
            keyword_score = 0
            for keyword in keywords:
                if keyword in user_prefs.get('keywords', {}):
                    keyword_score += user_prefs['keywords'][keyword]
            score += keyword_score * 0.4
            
            # Popularity/engagement score
            if video['views'] > 0:
                engagement_rate = (video['total_likes'] + video['total_comments'] * 2) / video['views']
                score += engagement_rate * 0.2
            
            # Recency bonus
            try:
                upload_date = datetime.fromisoformat(video['upload_date'])
                days_old = (datetime.now() - upload_date).days
                recency_score = max(0, 1 - (days_old / 30.0))  # Decay over 30 days
                score += recency_score * 0.1
            except (ValueError, TypeError):
                pass
            
            scored_videos.append((score, video))
        
        # Sort by score and return top recommendations
        scored_videos.sort(key=lambda x: x[0], reverse=True)
        
        recommendations = []
        for score, video in scored_videos[:limit]:
            recommendations.append({
                'id': video['id'],
                'title': video['title'],
                'description': video['description'],
                'upload_date': video['upload_date'],
                'views': video['views'],
                'duration': video['duration'],
                'score': score
            })
        
        return recommendations

    def get_trending_videos(self, limit=20, time_window_days=7):
        """Get trending videos based on recent engagement"""
        db = get_db()
        
        cutoff_date = datetime.now() - timedelta(days=time_window_days)
        
        cursor = db.execute("""
            SELECT v.id, v.title, v.description, v.upload_date, v.views, v.duration,
                   COUNT(DISTINCT vh.user_id) as recent_viewers,
                   COUNT(DISTINCT l.user_id) as recent_likes,
                   COUNT(DISTINCT c.user_id) as recent_comments
            FROM videos v
            LEFT JOIN view_history vh ON v.id = vh.video_id AND vh.watched_at >= ?
            LEFT JOIN likes l ON v.id = l.video_id AND l.created_at >= ?
            LEFT JOIN comments c ON v.id = c.video_id AND c.created_at >= ?
            GROUP BY v.id
            HAVING recent_viewers > 0
            ORDER BY (recent_viewers + recent_likes * 2 + recent_comments * 3) DESC
            LIMIT ?
        """, (cutoff_date.isoformat(), cutoff_date.isoformat(), cutoff_date.isoformat(), limit))
        
        trending_videos = cursor.fetchall()
        
        result = []
        for video in trending_videos:
            engagement_score = video['recent_viewers'] + video['recent_likes'] * 2 + video['recent_comments'] * 3
            result.append({
                'id': video['id'],
                'title': video['title'],
                'description': video['description'],
                'upload_date': video['upload_date'],
                'views': video['views'],
                'duration': video['duration'],
                'engagement_score': engagement_score
            })
        
        return result

    def get_similar_videos(self, video_id, limit=10):
        """Find videos similar to the given video"""
        db = get_db()
        
        # Get the target video
        cursor = db.execute("""
            SELECT id, title, description, tags, category
            FROM videos
            WHERE id = ?
        """, (video_id,))
        
        target_video = cursor.fetchone()
        if not target_video:
            return []
        
        # Get candidate videos
        cursor = db.execute("""
            SELECT id, title, description, tags, category, views, upload_date
            FROM videos
            WHERE id != ? AND category = ?
            ORDER BY upload_date DESC
            LIMIT 100
        """, (video_id, target_video['category']))
        
        candidate_videos = cursor.fetchall()
        
        if not candidate_videos:
            return []
        
        # Compute TF-IDF vectors
        all_videos = [target_video] + list(candidate_videos)
        tfidf_vectors = self.compute_tf_idf(all_videos)
        
        target_vector = tfidf_vectors[target_video['id']]
        
        # Calculate similarities
        similarities = []
        for video in candidate_videos:
            similarity = self.cosine_similarity(target_vector, tfidf_vectors[video['id']])
            similarities.append((similarity, video))
        
        # Sort by similarity
        similarities.sort(key=lambda x: x[0], reverse=True)
        
        result = []
        for similarity, video in similarities[:limit]:
            result.append({
                'id': video['id'],
                'title': video['title'],
                'description': video['description'],
                'upload_date': video['upload_date'],
                'views': video['views'],
                'similarity_score': similarity
            })
        
        return result