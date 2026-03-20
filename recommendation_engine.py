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
        self.stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
            'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should'
        }

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
        dot_product = sum(
            vec1.get(word, 0) * vec2.get(word, 0)
            for word in set(vec1.keys()).union(set(vec2.keys()))
        )

        magnitude1 = math.sqrt(sum(value ** 2 for value in vec1.values()))
        magnitude2 = math.sqrt(sum(value ** 2 for value in vec2.values()))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0

        return dot_product / (magnitude1 * magnitude2)

    def get_content_similarity_score(self, video1, video2):
        """Calculate content similarity between two videos"""
        text1 = f"{video1.get('title', '')} {video1.get('description', '') or ''} {video1.get('tags', '') or ''}"
        text2 = f"{video2.get('title', '')} {video2.get('description', '') or ''} {video2.get('tags', '') or ''}"

        words1 = set(self.tokenize_text(text1))
        words2 = set(self.tokenize_text(text2))

        if not words1 or not words2:
            return 0

        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        return intersection / union if union > 0 else 0

    def calculate_engagement_score(self, video):
        """Calculate engagement score for a video"""
        views = video.get('views', 0)
        likes = video.get('likes', 0)
        comments = video.get('comments', 0)

        if views == 0:
            return 0

        engagement_rate = (likes + comments * 2) / views

        # Time decay factor
        try:
            upload_date = datetime.fromisoformat(video.get('upload_date', datetime.now().isoformat()))
            days_old = (datetime.now() - upload_date).days
            time_factor = math.exp(-days_old / 7.0)
        except (ValueError, TypeError):
            time_factor = 0.5

        return engagement_rate * time_factor * 100

    def get_user_preferences(self, user_id):
        """Analyze user preferences based on watch history"""
        db = get_db()
        cursor = db.execute("""
            SELECT v.category, COUNT(*) as watch_count,
                   AVG(vh.watch_duration) as avg_watch_time
            FROM view_history vh
            JOIN videos v ON vh.video_id = v.id
            WHERE vh.user_id = ?
            GROUP BY v.category
            ORDER BY watch_count DESC
        """, (user_id,))

        preferences = cursor.fetchall()
        return {row['category']: row['watch_count'] for row in preferences}

    def recommend_videos(self, user_id, limit=20):
        """Generate personalized video recommendations"""
        db = get_db()

        # Get user's watch history
        watched_videos = db.execute("""
            SELECT DISTINCT video_id FROM view_history WHERE user_id = ?
        """, (user_id,)).fetchall()
        watched_ids = {row[0] for row in watched_videos}

        # Get candidate videos (not watched)
        candidates = db.execute("""
            SELECT v.*, u.username as uploader_name
            FROM videos v
            JOIN users u ON v.uploader_id = u.id
            WHERE v.id NOT IN ({})
            ORDER BY v.upload_date DESC
            LIMIT 100
        """.format(','.join(['?'] * len(watched_ids)) if watched_ids else '0'),
        list(watched_ids) if watched_ids else []).fetchall()

        if not candidates:
            return []

        # Get user preferences
        preferences = self.get_user_preferences(user_id)

        # Score each candidate
        scored_videos = []
        for video in candidates:
            video_dict = dict(video)

            # Content preference score
            category_score = preferences.get(video['category'], 0) * 0.3

            # Engagement score
            engagement_score = self.calculate_engagement_score(video_dict) * 0.4

            # Recency bonus
            try:
                upload_date = datetime.fromisoformat(video['upload_date'])
                days_old = (datetime.now() - upload_date).days
                recency_score = max(0, (7 - days_old) / 7) * 0.3
            except (ValueError, TypeError):
                recency_score = 0

            total_score = category_score + engagement_score + recency_score

            video_dict['recommendation_score'] = total_score
            scored_videos.append(video_dict)

        # Sort by score and return top recommendations
        scored_videos.sort(key=lambda x: x['recommendation_score'], reverse=True)
        return scored_videos[:limit]

    def get_trending_videos(self, limit=20):
        """Get trending videos based on recent engagement"""
        db = get_db()
        cursor = db.execute("""
            SELECT v.*, u.username as uploader_name,
                   COUNT(vh.id) as recent_views
            FROM videos v
            JOIN users u ON v.uploader_id = u.id
            LEFT JOIN view_history vh ON v.id = vh.video_id
                AND vh.watched_at >= datetime('now', '-7 days')
            GROUP BY v.id
            ORDER BY recent_views DESC, v.upload_date DESC
            LIMIT ?
        """, (limit,))

        return cursor.fetchall()

    def get_similar_videos(self, video_id, limit=10):
        """Find videos similar to a given video"""
        db = get_db()

        # Get the target video
        target_video = db.execute("""
            SELECT * FROM videos WHERE id = ?
        """, (video_id,)).fetchone()

        if not target_video:
            return []

        # Get candidate videos from same category
        candidates = db.execute("""
            SELECT v.*, u.username as uploader_name
            FROM videos v
            JOIN users u ON v.uploader_id = u.id
            WHERE v.category = ? AND v.id != ?
            ORDER BY v.upload_date DESC
            LIMIT 50
        """, (target_video['category'], video_id)).fetchall()

        # Calculate similarity scores
        target_dict = dict(target_video)
        similar_videos = []

        for candidate in candidates:
            candidate_dict = dict(candidate)
            similarity_score = self.get_content_similarity_score(target_dict, candidate_dict)
            candidate_dict['similarity_score'] = similarity_score
            similar_videos.append(candidate_dict)

        # Sort by similarity and return top matches
        similar_videos.sort(key=lambda x: x['similarity_score'], reverse=True)
        return similar_videos[:limit]
