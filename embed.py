from flask import render_template, abort
from database import get_db

def embed_video(video_id):
    """Render minimal iframe-friendly video player page."""
    db = get_db()
    video = db.execute(
        'SELECT * FROM videos WHERE id = ?', (video_id,)
    ).fetchone()

    if not video:
        abort(404)

    return render_template('embed.html', video=video)
