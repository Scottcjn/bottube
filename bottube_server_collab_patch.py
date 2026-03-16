import re

with open("bottube_server.py", "r") as f:
    content = f.read()

# 1. Update the videos table schema
videos_table_regex = re.compile(r'(CREATE TABLE IF NOT EXISTS videos \([\s\S]*?)(created_at REAL NOT NULL,[\s\S]*?\);)')
def repl_videos_table(m):
    return m.group(1) + "    collaborator_ids TEXT DEFAULT '[]',\n    response_to_video_id TEXT DEFAULT '',\n    " + m.group(2)
content = videos_table_regex.sub(repl_videos_table, content)

# 2. Add playlists table and playlist_members table
playlists_sql = """
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY,
    playlist_id TEXT UNIQUE NOT NULL,
    agent_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_public INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS playlist_members (
    id INTEGER PRIMARY KEY,
    playlist_id TEXT NOT NULL,
    agent_id INTEGER NOT NULL,
    role TEXT DEFAULT 'editor', -- 'owner' or 'editor'
    added_at REAL NOT NULL,
    UNIQUE(playlist_id, agent_id)
);
"""

if "CREATE TABLE IF NOT EXISTS playlists" not in content:
    init_db_regex = re.compile(r'(CREATE TABLE IF NOT EXISTS watch_history \([\s\S]*?\);)')
    def repl_init_db(m):
        return m.group(1) + "\n" + playlists_sql
    content = init_db_regex.sub(repl_init_db, content)


with open("bottube_server.py", "w") as f:
    f.write(content)
print("Applied DB schema modifications.")

