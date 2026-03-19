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
            for word in set(vec1.keys()) | set(vec2.keys())
        )

        norm1 = math.sqrt(sum(val ** 2 for val in vec1.values()))
        norm2 = math.sqrt(sum(val ** 2 for val in vec2.values()))

        if norm1 == 0 or norm2 == 0:
            return 0

        return dot_product / (norm1 * norm2)

    def get_user_preferences(self, user_id):
        db = get_db()
        cursor = db.execute("""
            SELECT v.category, COUNT(*) as watch_count,
                   AVG(CASE WHEN l.rating = 'like' THEN 1
                           WHEN l.rating = 'dislike' THEN -1
                           ELSE 0 END) as avg_rating
            FROM view_history vh
            JOIN videos v ON vh.video_id = v.id
            LEFT JOIN likes l ON l.video_id = v.id AND l.user_id = ?
            WHERE vh.user_id = ?
            GROUP BY v.category
            ORDER BY watch_count DESC
        """, (user_id, user_id))

        preferences = {}
        for row in cursor.fetchall():
            preferences[row['category']] = {
                'watch_count': row['watch_count'],
                'avg_rating': row['avg_rating'] or 0
            }

        return preferences

    def calculate_similarity_score(self, user_vector, video_vector):
        return self.cosine_similarity(user_vector, video_vector)

    def calculate_engagement_score(self, views, likes, comments, upload_date):
        if views == 0:
            return 0

        engagement_rate = (likes + comments * 2) / views

        try:
            if isinstance(upload_date, str):
                upload_dt = datetime.fromisoformat(upload_date)
            else:
                upload_dt = upload_date
            days_old = (datetime.now() - upload_dt).days
            time_factor = math.exp(-days_old / 7.0)
        except (ValueError, TypeError, AttributeError):
            time_factor = 0.5

        return engagement_rate * time_factor * 100

    def get_trending_videos(self, limit=20):
        db = get_db()
        cursor = db.execute("""
            SELECT v.*, COALESCE(l.like_count, 0) as likes,
                   COALESCE(c.comment_count, 0) as comments,
                   COALESCE(vh.view_count, 0) as views
            FROM videos v
            LEFT JOIN (
                SELECT video_id, COUNT(*) as like_count
                FROM likes WHERE rating = 'like'
                GROUP BY video_id
            ) l ON v.id = l.video_id
            LEFT JOIN (
                SELECT video_id, COUNT(*) as comment_count
                FROM comments
                GROUP BY video_id
            ) c ON v.id = c.video_id
            LEFT JOIN (
                SELECT video_id, COUNT(*) as view_count
                FROM view_history
                WHERE created_at > datetime('now', '-7 days')
                GROUP BY video_id
            ) vh ON v.id = vh.video_id
            ORDER BY views DESC, likes DESC
            LIMIT ?
        """, (limit,))

        return cursor.fetchall()

    def get_personalized_recommendations(self, user_id, limit=10):
        if not user_id:
            return self.get_trending_videos(limit)

        db = get_db()

        # Get user's watch history
        watched_videos = db.execute("""
            SELECT DISTINCT video_id FROM view_history WHERE user_id = ?
        """, (user_id,)).fetchall()
        watched_ids = {row['video_id'] for row in watched_videos}

        # Get user preferences
        preferences = self.get_user_preferences(user_id)

        # Get candidate videos (excluding watched)
        placeholders = ','.join('?' for _ in watched_ids) if watched_ids else ''
        exclude_clause = f"AND v.id NOT IN ({placeholders})" if watched_ids else ""

        query = f"""
            SELECT v.*, COALESCE(l.like_count, 0) as likes,
                   COALESCE(c.comment_count, 0) as comments,
                   COALESCE(vh.view_count, 0) as views
            FROM videos v
            LEFT JOIN (
                SELECT video_id, COUNT(*) as like_count
                FROM likes WHERE rating = 'like'
                GROUP BY video_id
            ) l ON v.id = l.video_id
            LEFT JOIN (
                SELECT video_id, COUNT(*) as comment_count
                FROM comments
                GROUP BY video_id
            ) c ON v.id = c.video_id
            LEFT JOIN (
                SELECT video_id, COUNT(*) as view_count
                FROM view_history
                GROUP BY video_id
            ) vh ON v.id = vh.video_id
            WHERE 1=1 {exclude_clause}
            LIMIT 100
        """

        params = list(watched_ids) if watched_ids else []
        candidates = db.execute(query, params).fetchall()

        # Score candidates
        scored_videos = []
        for video in candidates:
            # Base engagement score
            engagement = self.calculate_engagement_score(
                video['views'], video['likes'],
                video['comments'], video['upload_date']
            )

            # Category preference score
            category_score = 1.0
            if video['category'] in preferences:
                pref = preferences[video['category']]
                category_score = 1 + (pref['avg_rating'] * 0.5) + \
                                min(pref['watch_count'] / 10.0, 1.0)

            final_score = engagement * category_score
            scored_videos.append((video, final_score))

        # Sort by score and return top results
        scored_videos.sort(key=lambda x: x[1], reverse=True)
        return [video for video, score in scored_videos[:limit]]

    def get_similar_videos(self, video_id, limit=5):
        db = get_db()

        # Get target video
        target_video = db.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        if not target_video:
            return []

        # Get similar videos from same category
        similar_videos = db.execute("""
            SELECT v.*, COALESCE(vh.view_count, 0) as views
            FROM videos v
            LEFT JOIN (
                SELECT video_id, COUNT(*) as view_count
                FROM view_history
                GROUP BY video_id
            ) vh ON v.id = vh.video_id
            WHERE v.category = ? AND v.id != ?
            ORDER BY views DESC
            LIMIT ?
        """, (target_video['category'], video_id, limit)).fetchall()

        return similar_videos