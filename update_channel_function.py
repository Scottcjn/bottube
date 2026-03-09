#!/usr/bin/env python3
"""Update channel() function to include beacon data"""

SERVER_FILE = "/root/bottube/bottube_server.py"

def main():
    with open(SERVER_FILE, 'r') as f:
        content = f.read()

    # Find and update the channel function
    # Look for the specific return render_template block
    old_return = """    return render_template(
        "channel.html",
        agent=agent,
        videos=videos,
        total_views=total_views,
        subscriber_count=subscriber_count,
        is_following=is_following,
        playlists=playlists,
    )"""

    new_return = """    beacon_data = get_agent_beacon(agent_name)

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

    if old_return in content:
        content = content.replace(old_return, new_return)
        with open(SERVER_FILE, 'w') as f:
            f.write(content)
        print("✅ Updated channel() function with beacon data")
    else:
        print("❌ Could not find exact match for channel() return statement")
        print("📝 May need manual update")

if __name__ == "__main__":
    main()
