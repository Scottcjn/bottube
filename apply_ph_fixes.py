#!/usr/bin/env python3
"""
Product Hunt launch fixes - 4 targeted patches:
1. Mobile horizontal scroll fix (search bar overflow)
2. Color contrast improvements (accessibility)
3. LCP featured image: remove loading=lazy, add fetchpriority=high
4. Footer badge images: add width/height attributes
"""
import re
import shutil
import os
from datetime import datetime

TEMPLATES = "/root/bottube/bottube_templates"
BASE = os.path.join(TEMPLATES, "base.html")
INDEX = os.path.join(TEMPLATES, "index.html")

ts = datetime.now().strftime("%Y%m%d_%H%M%S")

# Backup both files
for f in [BASE, INDEX]:
    backup = f + ".bak." + ts
    shutil.copy2(f, backup)
    print("[backup] {} -> {}".format(f, backup))

# ============================================================
# FIX 1 & 2: base.html - CSS additions before </style>
# ============================================================
with open(BASE, "r") as fh:
    base_content = fh.read()

# --- Fix 1: Mobile horizontal scroll ---
# --- Fix 2: Color contrast accessibility ---
css_additions = """
        /* === Product Hunt launch fixes (2026-02-07) === */

        /* Fix 1: Mobile horizontal scroll prevention */
        html, body { overflow-x: hidden; }
        @media (max-width: 768px) {
            .search-bar { max-width: calc(100vw - 120px); }
            .search-bar input { min-width: 0; }
        }

        /* Fix 2: Accessibility - improve color contrast (WCAG AA) */
        .video-stats { color: #9e9eb8 !important; }
        .badge-human-sm { color: #b0b0c8 !important; }
        .footer-featured-label { color: #9e9eb8 !important; }
        .footer-copy { color: #9e9eb8 !important; }
        footer a { color: #b0b0c8 !important; }
        #bottube-counters { color: #9e9eb8 !important; }
"""

# Insert right before </style>
old_close = "    </style>"
new_close = css_additions + "\n    </style>"

if old_close in base_content:
    base_content = base_content.replace(old_close, new_close, 1)
    print("[fix 1+2] CSS additions injected before </style>")
else:
    print("[ERROR] Could not find </style> insertion point in base.html")

# --- Fix 4: Footer badge images - add width/height ---
# Dofollow badge (SVG)
old_dofollow = '<img src="https://dofollow.tools/badge/badge_dark.svg" alt="Dofollow.Tools">'
new_dofollow = '<img src="https://dofollow.tools/badge/badge_dark.svg" alt="Dofollow.Tools" width="120" height="24">'
if old_dofollow in base_content:
    base_content = base_content.replace(old_dofollow, new_dofollow, 1)
    print("[fix 4a] Added width/height to Dofollow badge")
else:
    print("[SKIP] Dofollow badge already has dimensions or not found")

# Startup Fame badge (WebP)
old_startup = '<img src="https://startupfa.me/badges/featured-badge-small.webp" alt="Startup Fame">'
new_startup = '<img src="https://startupfa.me/badges/featured-badge-small.webp" alt="Startup Fame" width="120" height="24">'
if old_startup in base_content:
    base_content = base_content.replace(old_startup, new_startup, 1)
    print("[fix 4b] Added width/height to Startup Fame badge")
else:
    print("[SKIP] Startup Fame badge already has dimensions or not found")

with open(BASE, "w") as fh:
    fh.write(base_content)
print("[saved] {}".format(BASE))


# ============================================================
# FIX 3: index.html - LCP featured image optimization
# ============================================================
with open(INDEX, "r") as fh:
    index_content = fh.read()

# The featured card loop is: {% for video in trending[:2] %}
# The FIRST image in the loop is the LCP element.
# We need to handle only the first featured image, not all of them.
#
# Strategy: Split on the featured-row marker, replace only first
# loading="lazy" in that section with fetchpriority="high"

marker = '<div class="featured-row">'
if marker in index_content:
    parts = index_content.split(marker, 1)
    # parts[1] is everything after the featured-row div
    # Find and replace only the FIRST loading="lazy" in this section
    if 'loading="lazy">' in parts[1]:
        parts[1] = parts[1].replace(
            'loading="lazy">',
            'fetchpriority="high">',
            1  # only first occurrence (the LCP hero image)
        )
        index_content = marker.join(parts)
        print('[fix 3] Replaced loading="lazy" with fetchpriority="high" on first featured image')
    else:
        print("[SKIP] No loading=lazy found in featured section")
else:
    print("[ERROR] Could not find featured-row marker in index.html")

with open(INDEX, "w") as fh:
    fh.write(index_content)
print("[saved] {}".format(INDEX))

print("")
print("=== All fixes applied successfully ===")
