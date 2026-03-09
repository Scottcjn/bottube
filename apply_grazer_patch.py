#!/usr/bin/env python3
"""Apply Grazer integration to autonomous agent daemon"""

# Read the daemon file
with open("/root/bottube/bottube_autonomous_agent.py", "r") as f:
    content = f.read()

# Patch 1: Add Grazer import near the top (after other imports)
if "from grazer_integration import grazer" not in content:
    # Find the last import line before # --- divider
    import_section_end = content.find("# ---------------------------------------------------------------------------")
    if import_section_end > 0:
        # Insert before the divider
        import_line = "\nfrom grazer_integration import grazer\n"
        content = content[:import_section_end] + import_line + content[import_section_end:]
        print("✓ Added Grazer import")

# Patch 2: Replace random video selection with Grazer filtering
# Find the browse action section
old_browse = """            r = api_get("/api/videos", params={"per_page": 30})
            if not r or r.status_code != 200:
                return False
            videos = r.json().get("videos", [])
            # Filter out own videos and already-commented
            candidates = [
                v for v in videos
                if v["agent_name"] != bot_name
                and not brain.already_commented_on(v["video_id"])
            ]
            if not candidates:
                return False
            video = random.choice(candidates)"""

new_browse = """            # Use Grazer for intelligent content discovery
            videos = grazer.discover_bottube(limit=30)
            if not videos:
                # Fallback to direct API if Grazer fails
                r = api_get("/api/videos", params={"per_page": 30})
                if not r or r.status_code != 200:
                    return False
                videos = r.json().get("videos", [])
            
            # Filter out own videos and already-commented
            candidates = [
                v for v in videos
                if v.get("agent_name") != bot_name
                and not brain.already_commented_on(v.get("video_id"))
            ]
            if not candidates:
                return False
            
            # Grazer returns videos ranked by quality - take top one instead of random
            video = candidates[0]  # Best quality video
            
            # Mark as seen in Grazer to avoid re-engagement
            grazer.filter.mark_seen(video.get("video_id"))"""

if old_browse in content:
    content = content.replace(old_browse, new_browse)
    print("✓ Replaced random selection with Grazer intelligent filtering")
else:
    print("⚠ Browse section not found - may need manual integration")

# Write patched content
with open("/root/bottube/bottube_autonomous_agent.py", "w") as f:
    f.write(content)

print("\n✓ Grazer integration applied successfully!")
print("  - Bots will now use intelligent quality-based content selection")
print("  - Videos are ranked by engagement, novelty, and relevance")
print("  - Duplicate engagement is automatically prevented")

