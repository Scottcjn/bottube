import sqlite3

def migrate():
    """Add tables for recommendation system"""
    conn = sqlite3.connect('bottube.db')
    cursor = conn.cursor()

    # Create view_history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS view_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            video_id INTEGER NOT NULL,
            watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            watch_duration INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (video_id) REFERENCES videos(id),
            UNIQUE(user_id, video_id, watched_at)
        )
    """)

    # Create recommendations_feedback table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recommendations_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            video_id INTEGER NOT NULL,
            feedback_type TEXT NOT NULL CHECK(feedback_type IN ('like', 'dislike', 'not_interested')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (video_id) REFERENCES videos(id),
            UNIQUE(user_id, video_id)
        )
    """)

    # Create indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_view_history_user ON view_history(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_view_history_video ON view_history(video_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_view_history_watched_at ON view_history(watched_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_user ON recommendations_feedback(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_video ON recommendations_feedback(video_id)")

    conn.commit()
    conn.close()
    print("Recommendations tables created successfully")

if __name__ == '__main__':
    migrate()
