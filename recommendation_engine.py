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

        norm1 = math.sqrt(sum(v**2 for v in vec1.values()))
        norm2 = math.sqrt(sum(v**2 for v in vec2.values()))

        if norm1 == 0 or norm2 == 0:
            return 0

        return dot_product / (norm1 * norm2)

    def get_content_recommendations(self, user_id, limit=10):
        """Get content-based recommendations using TF-IDF similarity"""
        db = get_db()

        # Get user's watch history
        cursor = db.execute("""
            SELECT v.id, v.title, v.description, v.tags
            FROM videos v
            JOIN view_history vh ON v.id = vh.video_id
            WHERE vh.user_id = ?
            ORDER BY vh.watched_at DESC
            LIMIT 10
        """, (user_id,))

        watched_videos = cursor.fetchall()
        if not watched_videos:
            return []

        watched_video_ids = [v['id'] for v in watched_videos]

        # Get all videos except watched ones
        placeholders = ','.join('?' * len(watched_video_ids))
        cursor = db.execute(f"""
            SELECT id, title, description, tags, upload_date
            FROM videos
            WHERE id NOT IN ({placeholders})
            ORDER BY upload_date DESC
            LIMIT 100
        """, watched_video_ids)

        candidate_videos = cursor.fetchall()
        if not candidate_videos:
            return []

        # Compute TF-IDF vectors for all videos
        all_videos = list(watched_videos) + list(candidate_videos)
        tfidf_vectors = self.compute_tf_idf(all_videos)

        # Calculate average vector for watched videos (user profile)
        user_vector = defaultdict(float)
        for video in watched_videos:
            video_vector = tfidf_vectors[video['id']]
            for word, score in video_vector.items():
                user_vector[word] += score

        # Normalize user vector
        for word in user_vector:
            user_vector[word] /= len(watched_videos)

        # Score candidate videos by similarity to user profile
        recommendations = []
        for video in candidate_videos:
            video_vector = tfidf_vectors[video['id']]
            similarity = self.cosine_similarity(dict(user_vector), video_vector)

            if similarity > 0:
                recommendations.append({
                    'id': video['id'],
                    'title': video['title'],
                    'description': video['description'],
                    'tags': video['tags'],
                    'upload_date': video['upload_date'],
                    'similarity_score': similarity
                })

        # Sort by similarity score and return top recommendations
        recommendations.sort(key=lambda x: x['similarity_score'], reverse=True)
        return recommendations[:limit]
