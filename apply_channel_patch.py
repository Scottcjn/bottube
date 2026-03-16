import re
import os

filepath = "/Users/allai/wtf/projects/deepfake-live/SOVEREIGN_BOUNTIES/bottube/bottube_templates/channel.html"

with open(filepath, "r") as f:
    html = f.read()

# 1. Update the header to include the banner and accent color
header_patch = """
{% if agent.banner_url %}
<div class="channel-banner" style="background-image: url('{{ agent.banner_url }}'); height: 200px; background-size: cover; background-position: center;"></div>
{% endif %}
<div class="channel-header" style="{% if agent.accent_color %}border-top: 4px solid {{ agent.accent_color }};{% endif %}">
"""

if "channel-banner" not in html:
    html = html.replace('<div class="channel-header">', header_patch)

# 2. Render Markdown Bio
# Assuming the bio exists like this: <div class="channel-bio">{{ agent.bio }}</div>
html = html.replace('<div class="channel-bio">{{ agent.bio }}</div>', '<div class="channel-bio">{{ agent.bio | markdown }}</div>')

with open(filepath, "w") as f:
    f.write(html)

print("Channel template patched")
