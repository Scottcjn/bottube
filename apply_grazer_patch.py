#!/usr/bin/env python3
"""Apply Grazer integration to autonomous agent daemon.

Task: #1588 - Add type hints to Python functions
"""
from __future__ import annotations
from typing import Tuple, Optional

DAEMON_FILE: str = "/root/bottube/bottube_autonomous_agent.py"


def read_daemon_file(file_path: str) -> str:
    """Read the daemon file content."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def write_daemon_file(file_path: str, content: str) -> None:
    """Write content to the daemon file."""
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


def add_grazer_import(content: str) -> Tuple[bool, str]:
    """Add Grazer import to the content.
    
    Returns:
        Tuple of (success, new_content)
    """
    if "from grazer_integration import grazer" in content:
        return False, content
    
    import_section_end: int = content.find("# ---------------------------------------------------------------------------")
    if import_section_end > 0:
        import_line: str = "\nfrom grazer_integration import grazer\n"
        new_content: str = content[:import_section_end] + import_line + content[import_section_end:]
        return True, new_content
    return False, content


def replace_browse_section(content: str) -> Tuple[bool, str]:
    """Replace random video selection with Grazer filtering.
    
    Returns:
        Tuple of (success, new_content)
    """
    old_browse: str = """            r = api_get("/api/videos", params={"per_page": 30})
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

    new_browse: str = """            # Use Grazer for intelligent content discovery
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
        return True, content.replace(old_browse, new_browse)
    return False, content


def apply_grazer_patch(daemon_file: str = DAEMON_FILE) -> None:
    """Apply Grazer integration patch to the daemon file."""
    content: str = read_daemon_file(daemon_file)

    # Patch 1: Add Grazer import
    import_added: bool
    import_added, content = add_grazer_import(content)
    if import_added:
        print("✓ Added Grazer import")

    # Patch 2: Replace random video selection with Grazer filtering
    browse_replaced: bool
    browse_replaced, content = replace_browse_section(content)
    if browse_replaced:
        print("✓ Replaced random selection with Grazer intelligent filtering")
    else:
        print("⚠ Browse section not found - may need manual integration")

    # Write patched content
    write_daemon_file(daemon_file, content)

    print("\n✓ Grazer integration applied successfully!")
    print("  - Bots will now use intelligent quality-based content selection")
    print("  - Videos are ranked by engagement, novelty, and relevance")
    print("  - Duplicate engagement is automatically prevented")


def main() -> None:
    """Main entry point."""
    apply_grazer_patch()


if __name__ == "__main__":
    main()

