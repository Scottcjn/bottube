import re

filepath = "bottube_templates/channel.html"
with open(filepath, "r") as f:
    html = f.read()

# Add pinned video section before the video-grid
pinned_patch = """
{% if agent.pinned_video_id %}
    {% set pinned = None %}
    {% for v in videos %}
        {% if v.video_id == agent.pinned_video_id %}
            {% set pinned = v %}
        {% endif %}
    {% endfor %}
    
    {% if pinned %}
    <h3 style="margin-top:20px; margin-bottom:10px;">📌 Pinned Video</h3>
    <div style="margin-bottom:30px; border:2px solid var(--accent); border-radius:8px; overflow:hidden;">
        <a href="{{ P }}/watch/{{ pinned.video_id }}" style="text-decoration:none; color:inherit;">
            <div style="display:flex; flex-wrap:wrap;">
                <div style="flex:1; min-width:300px;">
                    <img src="{{ P }}/thumbnails/{{ pinned.thumbnail }}" alt="Video thumbnail: {{ pinned.title }}" style="width:100%; height:auto; display:block;">
                </div>
                <div style="flex:1; min-width:300px; padding:20px; background:var(--bg-card);">
                    <h2 style="margin-bottom:10px;">{{ pinned.title }}</h2>
                    <div style="color:var(--text-muted); font-size:14px; margin-bottom:10px;">{{ pinned.views | format_views }} views &middot; {{ pinned.created_at | human_time }}</div>
                    <div style="color:var(--text-secondary); font-size:14px;">{{ pinned.description | truncate(150) }}</div>
                </div>
            </div>
        </a>
    </div>
    <h3 style="margin-bottom:10px;">All Videos</h3>
    {% endif %}
{% endif %}

<div class="video-grid">
"""

html = html.replace('<div class="video-grid">', pinned_patch)

with open(filepath, "w") as f:
    f.write(html)

print("Pinned video patched")
