import re

with open("bottube_server.py", "r") as f:
    content = f.read()

# Add response_to_video_id and collaborator_ids to /upload_page logic
def repl_upload_page(m):
    return """db.execute(
            "INSERT INTO videos (video_id, agent_id, title, description, filename, category, tags, is_human_upload, collaborator_ids, response_to_video_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (video_id, g.user["id"], title, description, secure_filename, category, tags_json, request.form.get("collaborator_ids", "[]"), request.form.get("response_to_video_id", ""), time.time()),
        )"""

content = re.sub(r'db\.execute\(\s*"INSERT INTO videos \(video_id, agent_id, title, description, filename, category, tags, is_human_upload, created_at\) "\s*"VALUES \(\?, \?, \?, \?, \?, \?, \?, 1, \?\)",\s*\(video_id, g\.user\["id"\], title, description, secure_filename, category, tags_json, time\.time\(\)\),\s*\)', repl_upload_page, content)

with open("bottube_server.py", "w") as f:
    f.write(content)

print("Applied upload page param logic")

