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

        norm1 = math.sqrt(sum(val ** 2 for val in vec1.values()))
        norm2 = math.sqrt(sum(val ** 2 for val in vec2.values()))

        if norm1 == 0 or norm2 == 0:
            return 0

        return dot_product / (norm1 * norm2)

    def get_content_recommendations(self, user_id, limit=10):
        """Get recommendations based on content similarity to user's watch history"""
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
        watched_videos = [dict(row) for row in history_cursor.fetchall()]

        if not watched_videos:
            return self.get_trending_videos(limit)

        # Get all available videos (excluding watched ones)
        watched_ids = [v['id'] for v in watched_videos]
        placeholders = ','.join('?' * len(watched_ids))
        candidates_cursor = db.execute(f"""
            SELECT id, title, description, tags
            FROM videos
            WHERE id NOT IN ({placeholders})
            AND is_active = 1
            ORDER BY upload_date DESC
            LIMIT 100
        """, watched_ids)
        candidate_videos = [dict(row) for row in candidates_cursor.fetchall()]

        if not candidate_videos:
            return []

        # Compute TF-IDF for all videos
        all_videos = watched_videos + candidate_videos
        tfidf_vectors = self.compute_tf_idf(all_videos)

        # Create user profile vector (average of watched videos)
        user_vector = defaultdict(float)
        for video in watched_videos:
            video_vector = tfidf_vectors.get(video['id'], {})
            for word, score in video_vector.items():
                user_vector[word] += score

        # Normalize user vector
        if user_vector:
            total_watched = len(watched_videos)
            user_vector = {word: score / total_watched for word, score in user_vector.items()}

        # Calculate similarities and score candidates
        recommendations = []
        for video in candidate_videos:
            video_vector = tfidf_vectors.get(video['id'], {})
            similarity = self.cosine_similarity(user_vector, video_vector)

            recommendations.append({
                'video_id': video['id'],
                'score': similarity,
                'type': 'content_based'
            })

        # Sort by score and return top recommendations
        recommendations.sort(key=lambda x: x['score'], reverse=True)
        return recommendations[:limit]

    def get_trending_videos(self, limit=10):
        """Get trending videos as fallback recommendations"""
        db = get_db()
        cursor = db.execute("""
            SELECT v.id as video_id,
                   (COALESCE(v.views, 0) + COALESCE(v.likes, 0) * 2) as score
            FROM videos v
            WHERE v.is_active = 1
            AND v.upload_date >= datetime('now', '-30 days')
            ORDER BY score DESC
            LIMIT ?
        """, (limit,))

        return [{
            'video_id': row['video_id'],
            'score': row['score'],
            'type': 'trending'
        } for row in cursor.fetchall()]

    def get_recommendations_for_user(self, user_id, limit=10):
        """Main method to get personalized recommendations for a user"""
        recommendations = self.get_content_recommendations(user_id, limit)

        if len(recommendations) < limit:
            # Fill remaining slots with trending videos
            trending = self.get_trending_videos(limit - len(recommendations))
            recommendations.extend(trending)

        return recommendations[:limit]
