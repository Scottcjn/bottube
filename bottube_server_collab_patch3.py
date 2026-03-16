import re

with open("bottube_server.py", "r") as f:
    content = f.read()

# Make sure collaborator fields are in SELECT query
if "collaborator_ids" not in content.split("def web_tip_video(video_id):")[1].split("FROM videos")[0]:
    content = content.replace(
        '"SELECT v.agent_id, v.title, a.agent_name AS creator_name, "\n        "       a.rtc_wallet AS creator_rtc_wallet, a.rtc_address AS creator_rtc_address "\n        "FROM videos v JOIN agents a ON v.agent_id = a.id WHERE v.video_id = ?"',
        '"SELECT v.agent_id, v.title, v.collaborator_ids, a.agent_name AS creator_name, "\n        "       a.rtc_wallet AS creator_rtc_wallet, a.rtc_address AS creator_rtc_address "\n        "FROM videos v JOIN agents a ON v.agent_id = a.id WHERE v.video_id = ?"'
    )

# Fix web_tip_video split logic
def repl_web_tip(m):
    return m.group(1) + """
        # Distribute off-chain tips equally among uploader and collaborators
        import json
        collaborator_ids = json.loads(video["collaborator_ids"] or "[]")
        total_recipients = 1 + len(collaborator_ids)
        split_amount = amount / total_recipients
        
        db.execute("UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ?", (amount, g.user["id"]))
        db.execute("UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?", (split_amount, video["agent_id"]))
        
        for col_id in collaborator_ids:
            try:
                db.execute("UPDATE agents SET rtc_balance = rtc_balance + ? WHERE agent_name = ?", (split_amount, col_id))
            except Exception:
                pass
        """ + m.group(2)

content = re.sub(
    r'(db\.execute\("UPDATE agents SET rtc_balance = rtc_balance - \? WHERE id = \?", \(amount, g\.user\["id"\]\)\)\s*db\.execute\("UPDATE agents SET rtc_balance = rtc_balance \+ \? WHERE id = \?", \(amount, video\["agent_id"\]\)\))(.*?)',
    repl_web_tip,
    content,
    flags=re.DOTALL
)

with open("bottube_server.py", "w") as f:
    f.write(content)

print("Applied web tip split logic")

