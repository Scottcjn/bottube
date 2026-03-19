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

    def get_content_based_recommendations(self, user_id, limit=10):
        db = get_db()

        # Get user's watch history
        history_cursor = db.execute("""
            SELECT DISTINCT v.id, v.title, v.description, v.tags
            FROM view_history vh
            JOIN videos v ON vh.video_id = v.id
            WHERE vh.user_id = ?
            ORDER BY vh.watched_at DESC
            LIMIT 20
        """, (user_id,))
        history = history_cursor.fetchall()

        if not history:
            return self.get_popular_videos(limit)

        # Get all videos (excluding watched ones)
        watched_ids = [str(v['id']) for v in history]
        placeholders = ','.join('?' * len(watched_ids))
        all_videos_cursor = db.execute(f"""
            SELECT id, title, description, tags, views, likes, comments, upload_date
            FROM videos
            WHERE id NOT IN ({placeholders})
            ORDER BY upload_date DESC
            LIMIT 1000
        """, watched_ids)
        all_videos = all_videos_cursor.fetchall()

        # Convert to dicts for TF-IDF
        history_dicts = [dict(v) for v in history]
        video_dicts = [dict(v) for v in all_videos]

        # Compute TF-IDF for all videos
        all_videos_tfidf = history_dicts + video_dicts
        tfidf_vectors = self.compute_tf_idf(all_videos_tfidf)

        # Calculate user profile (average of watched videos)
        user_profile = defaultdict(float)
        for video in history_dicts:
            video_vector = tfidf_vectors.get(video['id'], {})
            for word, score in video_vector.items():
                user_profile[word] += score

        # Normalize user profile
        if user_profile:
            profile_norm = math.sqrt(sum(val ** 2 for val in user_profile.values()))
            if profile_norm > 0:
                user_profile = {word: score / profile_norm for word, score in user_profile.items()}

        # Calculate similarities and scores
        recommendations = []
        for video in video_dicts:
            video_vector = tfidf_vectors.get(video['id'], {})
            similarity = self.cosine_similarity(dict(user_profile), video_vector)

            # Calculate engagement score
            engagement = self.calculate_engagement_score(
                video['views'] or 0,
                video['likes'] or 0,
                video['comments'] or 0,
                video['upload_date']
            )

            # Combined score
            score = similarity * 0.7 + engagement * 0.3

            recommendations.append({
                'video_id': video['id'],
                'title': video['title'],
                'similarity_score': similarity,
                'engagement_score': engagement,
                'combined_score': score
            })

        # Sort by combined score and return top recommendations
        recommendations.sort(key=lambda x: x['combined_score'], reverse=True)
        return recommendations[:limit]

    def calculate_engagement_score(self, views, likes, comments, upload_date):
        if views == 0:
            return 0

        engagement_rate = (likes + comments * 2) / views

        # Time decay factor
        try:
            days_old = (datetime.now() - datetime.fromisoformat(upload_date)).days
            time_factor = math.exp(-days_old / 7.0)
        except (ValueError, TypeError):
            time_factor = 0.5

        return engagement_rate * time_factor * 100

    def get_popular_videos(self, limit=10):
        db = get_db()
        cursor = db.execute("""
            SELECT id, title, views, likes, comments, upload_date
            FROM videos
            ORDER BY views DESC, likes DESC
            LIMIT ?
        """, (limit,))

        videos = cursor.fetchall()
        recommendations = []

        for video in videos:
            engagement = self.calculate_engagement_score(
                video['views'] or 0,
                video['likes'] or 0,
                video['comments'] or 0,
                video['upload_date']
            )

            recommendations.append({
                'video_id': video['id'],
                'title': video['title'],
                'similarity_score': 0,
                'engagement_score': engagement,
                'combined_score': engagement
            })

        return recommendations