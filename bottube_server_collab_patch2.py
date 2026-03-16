import re

with open("bottube_server.py", "r") as f:
    content = f.read()

# Make sure collaborator fields are inserted in videos table
if "collaborator_ids TEXT" not in content:
    content = content.replace("    created_at REAL NOT NULL,", "    collaborator_ids TEXT DEFAULT '[]',\n    response_to_video_id TEXT DEFAULT '',\n    created_at REAL NOT NULL,")

# Look for tip route
tip_route_regex = re.compile(r'(@app\.route\("/api/tip".*?def api_tip\(\):[\s\S]*?)(return cors_json\({"status": "tipped")', re.DOTALL)

def repl_tip(m):
    return m.group(1).replace(
        "video = db.execute(\"SELECT agent_id FROM videos WHERE video_id = ?\", (video_id,)).fetchone()",
        "video = db.execute(\"SELECT agent_id, collaborator_ids FROM videos WHERE video_id = ?\", (video_id,)).fetchone()"
    ).replace(
        "recipient_id = video[0]",
        "recipient_id = video[0]\n        collaborator_ids = json.loads(video[1] or '[]')"
    ).replace(
        "db.execute(\"UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?\", (tip_amount, recipient_id))",
        """
        # Distribute tips equally among uploader and collaborators
        total_recipients = 1 + len(collaborator_ids)
        split_amount = tip_amount / total_recipients
        
        db.execute("UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?", (split_amount, recipient_id))
        for col_id in collaborator_ids:
            try:
                db.execute("UPDATE agents SET rtc_balance = rtc_balance + ? WHERE agent_name = ?", (split_amount, col_id))
            except Exception:
                pass
        """
    ) + m.group(2)

content = tip_route_regex.sub(repl_tip, content)

with open("bottube_server.py", "w") as f:
    f.write(content)

print("Applied tip split logic")

