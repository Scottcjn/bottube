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
        
        norm1 = math.sqrt(sum(val * val for val in vec1.values()))
        norm2 = math.sqrt(sum(val * val for val in vec2.values()))
        
        if norm1 == 0 or norm2 == 0:
            return 0
        
        return dot_product / (norm1 * norm2)

    def get_user_watch_history(self, user_id):
        db = get_db()
        cursor = db.execute('''
            SELECT v.id, v.title, v.description, v.tags, vh.watch_time, vh.created_at
            FROM view_history vh
            JOIN videos v ON vh.video_id = v.id
            WHERE vh.user_id = ?
            ORDER BY vh.created_at DESC
            LIMIT 100
        ''', (user_id,))
        return cursor.fetchall()

    def get_all_videos(self):
        db = get_db()
        cursor = db.execute('''
            SELECT id, title, description, tags, created_at, view_count, like_count, comment_count
            FROM videos
            WHERE status = 'active'
            ORDER BY created_at DESC
        ''')
        return cursor.fetchall()

    def content_based_recommendations(self, user_id, limit=10):
        watch_history = self.get_user_watch_history(user_id)
        if not watch_history:
            return []

        all_videos = self.get_all_videos()
        watched_video_ids = {video['id'] for video in watch_history}
        
        tfidf_vectors = self.compute_tf_idf(all_videos)
        
        user_profile = defaultdict(float)
        total_weight = 0
        
        for watched_video in watch_history:
            video_id = watched_video['id']
            if video_id in tfidf_vectors:
                weight = min(watched_video['watch_time'] / 60.0, 1.0)
                total_weight += weight
                
                for word, score in tfidf_vectors[video_id].items():
                    user_profile[word] += score * weight

        if total_weight > 0:
            for word in user_profile:
                user_profile[word] /= total_weight

        recommendations = []
        for video in all_videos:
            if video['id'] not in watched_video_ids:
                similarity = self.cosine_similarity(dict(user_profile), tfidf_vectors.get(video['id'], {}))
                if similarity > 0:
                    recommendations.append({
                        'video': dict(video),
                        'score': similarity,
                        'reason': 'content_similarity'
                    })

        recommendations.sort(key=lambda x: x['score'], reverse=True)
        return recommendations[:limit]

    def collaborative_filtering(self, user_id, limit=10):
        db = get_db()
        
        cursor = db.execute('''
            SELECT vh1.video_id as video1, vh2.video_id as video2, COUNT(*) as cooccurrence
            FROM view_history vh1
            JOIN view_history vh2 ON vh1.user_id = vh2.user_id AND vh1.video_id != vh2.video_id
            WHERE vh1.user_id IN (
                SELECT DISTINCT vh.user_id
                FROM view_history vh
                WHERE vh.video_id IN (
                    SELECT video_id FROM view_history WHERE user_id = ?
                )
            )
            GROUP BY vh1.video_id, vh2.video_id
            HAVING cooccurrence >= 2
        ''', (user_id,))
        
        cooccurrences = cursor.fetchall()
        
        user_videos = set()
        cursor = db.execute('SELECT video_id FROM view_history WHERE user_id = ?', (user_id,))
        for row in cursor:
            user_videos.add(row['video_id'])

        recommendations = defaultdict(float)
        
        for item in cooccurrences:
            video1, video2 = item['video1'], item['video2']
            weight = item['cooccurrence']
            
            if video1 in user_videos and video2 not in user_videos:
                recommendations[video2] += weight
            elif video2 in user_videos and video1 not in user_videos:
                recommendations[video1] += weight

        results = []
        for video_id, score in sorted(recommendations.items(), key=lambda x: x[1], reverse=True)[:limit]:
            cursor = db.execute('SELECT * FROM videos WHERE id = ? AND status = "active"', (video_id,))
            video = cursor.fetchone()
            if video:
                results.append({
                    'video': dict(video),
                    'score': score,
                    'reason': 'collaborative_filtering'
                })

        return results

    def calculate_trending_score(self, video):
        now = datetime.utcnow()
        created_at = datetime.fromisoformat(video['created_at'])
        hours_old = (now - created_at).total_seconds() / 3600

        time_decay = math.exp(-hours_old / 168)
        
        views = max(video['view_count'] or 0, 1)
        likes = video['like_count'] or 0
        comments = video['comment_count'] or 0
        
        engagement_rate = (likes + comments * 2) / views
        
        new_content_boost = 1.5 if hours_old < 24 else 1.0
        
        trending_score = (views * 0.4 + engagement_rate * 100 * 0.4 + time_decay * 50 * 0.2) * new_content_boost
        
        return trending_score

    def get_trending_videos(self, limit=20):
        all_videos = self.get_all_videos()
        
        trending_videos = []
        for video in all_videos:
            score = self.calculate_trending_score(video)
            trending_videos.append({
                'video': dict(video),
                'score': score,
                'reason': 'trending'
            })

        trending_videos.sort(key=lambda x: x['score'], reverse=True)
        return trending_videos[:limit]

    def get_similar_videos(self, video_id, limit=10):
        db = get_db()
        cursor = db.execute('SELECT * FROM videos WHERE id = ? AND status = "active"', (video_id,))
        target_video = cursor.fetchone()
        
        if not target_video:
            return []

        all_videos = self.get_all_videos()
        all_videos = [v for v in all_videos if v['id'] != video_id]
        
        videos_for_similarity = [dict(target_video)] + [dict(v) for v in all_videos]
        tfidf_vectors = self.compute_tf_idf(videos_for_similarity)

        target_vector = tfidf_vectors.get(video_id, {})
        
        similarities = []
        for video in all_videos:
            similarity = self.cosine_similarity(target_vector, tfidf_vectors.get(video['id'], {}))
            if similarity > 0:
                similarities.append({
                    'video': dict(video),
                    'score': similarity,
                    'reason': 'content_similarity'
                })

        similarities.sort(key=lambda x: x['score'], reverse=True)
        return similarities[:limit]

    def get_personalized_recommendations(self, user_id, limit=20):
        content_recs = self.content_based_recommendations(user_id, limit // 2)
        collab_recs = self.collaborative_filtering(user_id, limit // 2)
        trending_recs = self.get_trending_videos(limit // 4)

        all_recommendations = content_recs + collab_recs + trending_recs[:5]
        
        seen_videos = set()
        final_recs = []
        
        for rec in all_recommendations:
            video_id = rec['video']['id']
            if video_id not in seen_videos:
                seen_videos.add(video_id)
                final_recs.append(rec)
                
                if len(final_recs) >= limit:
                    break

        return final_recs