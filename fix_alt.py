import os
import glob
import re

base_dir = "/Users/allai/wtf/projects/deepfake-live/SOVEREIGN_BOUNTIES/bottube/bottube_templates"

for filepath in glob.glob(os.path.join(base_dir, "*.html")):
    with open(filepath, "r") as f:
        content = f.read()

    # Find img tags with thumbnails that have either empty alt="" or alt="{{ v.title }}" but might need prefix.
    # The requirement is descriptive alt text like "Video thumbnail: [video title]"
    
    # We will replace `alt="{{ video.title }}"` with `alt="Video thumbnail: {{ video.title }}"`
    content = content.replace('alt="{{ video.title }}"', 'alt="Video thumbnail: {{ video.title }}"')
    content = content.replace('alt="{{ v.title }}"', 'alt="Video thumbnail: {{ v.title }}"')
    content = content.replace('alt="{{ item.title }}"', 'alt="Video thumbnail: {{ item.title }}"')
    content = content.replace('alt="{{ rel.title }}"', 'alt="Video thumbnail: {{ rel.title }}"')
    
    with open(filepath, "w") as f:
        f.write(content)
