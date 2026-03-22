"""
Database migration for BoTTube Creator Collaboration Features
Implements: Co-uploads, Duets/Responses, Shared Playlists

Issue: rustchain-bounties#2161 / bottube#427
Bounty: 25 RTC
"""

import sqlite3

DATABASE = 'bottube.db'

def migrate():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # 1. Add collaborator_ids to videos table (Co-uploads)
    c.execute('''
        ALTER TABLE videos ADD COLUMN collaborator_ids TEXT DEFAULT '[]'
    ''')
    print("✓ Added collaborator_ids to videos")
    
    # 2. Add response_to_video_id for duets/responses
    c.execute('''
        ALTER TABLE videos ADD COLUMN response_to_video_id INTEGER 
        REFERENCES videos(id) ON DELETE SET NULL
    ''')
    print("✓ Added response_to_video_id for duets")
    
    # 3. Create playlists table
    c.execute('''
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            creator_id INTEGER NOT NULL,
            is_collaborative BOOLEAN DEFAULT FALSE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✓ Created playlists table")
    
    # 4. Create playlist_videos junction table
    c.execute('''
        CREATE TABLE IF NOT EXISTS playlist_videos (
            playlist_id INTEGER REFERENCES playlists(id) ON DELETE CASCADE,
            video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            added_by INTEGER,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (playlist_id, video_id)
        )
    ''')
    print("✓ Created playlist_videos junction table")
    
    # 5. Create playlist_members for collaborative playlists
    c.execute('''
        CREATE TABLE IF NOT EXISTS playlist_members (
            playlist_id INTEGER REFERENCES playlists(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL,
            role TEXT DEFAULT 'editor',  -- owner, editor, viewer
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (playlist_id, user_id)
        )
    ''')
    print("✓ Created playlist_members table")
    
    # 6. Add split_tip_percent for co-upload tip splitting
    c.execute('''
        ALTER TABLE tips ADD COLUMN split_percent REAL DEFAULT 100.0
    ''')
    print("✓ Added split_percent to tips")
    
    conn.commit()
    conn.close()
    print("\n✅ Migration complete! Collaboration features ready.")

if __name__ == '__main__':
    migrate()
