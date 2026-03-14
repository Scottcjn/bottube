#!/usr/bin/env python3
"""Update channel() function to include beacon data.

Task: #1588 - Add type hints to Python functions
"""
from __future__ import annotations
from typing import Tuple, Optional

SERVER_FILE: str = "/root/bottube/bottube_server.py"


def read_server_file(file_path: str) -> str:
    """Read the server file content."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def write_server_file(file_path: str, content: str) -> None:
    """Write content to the server file."""
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


def find_and_replace(content: str, old_str: str, new_str: str) -> Tuple[bool, str]:
    """Find and replace a string in content.
    
    Returns:
        Tuple of (success, new_content)
    """
    if old_str in content:
        return True, content.replace(old_str, new_str)
    return False, content


def update_channel_function(server_file: str = SERVER_FILE) -> None:
    """Update the channel() function to include beacon data."""
    content: str = read_server_file(server_file)

    old_return: str = """    return render_template(
        "channel.html",
        agent=agent,
        videos=videos,
        total_views=total_views,
        subscriber_count=subscriber_count,
        is_following=is_following,
        playlists=playlists,
    )"""

    new_return: str = """    beacon_data = get_agent_beacon(agent_name)

    return render_template(
        "channel.html",
        agent=agent,
        videos=videos,
        total_views=total_views,
        subscriber_count=subscriber_count,
        is_following=is_following,
        playlists=playlists,
        beacon=beacon_data,
    )"""

    success, new_content = find_and_replace(content, old_return, new_return)
    
    if success:
        write_server_file(server_file, new_content)
        print("✅ Updated channel() function with beacon data")
    else:
        print("❌ Could not find exact match for channel() return statement")
        print("📝 May need manual update")


def main() -> None:
    """Main entry point."""
    update_channel_function()


if __name__ == "__main__":
    main()
