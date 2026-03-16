import re

with open("bottube_server.py", "r") as f:
    content = f.read()

# Add response_to_video_id and collaborator_ids to /upload logic
upload_save_regex = re.compile(r'db\.execute\(\s*"""\s*INSERT INTO videos \(\s*video_id, agent_id, title, description, filename,\s*thumbnail, duration_sec, width, height, tags, category,\s*created_at, is_human_upload\s*\)\s*VALUES \(\?, \?, \?, \?, \?, \?, \?, \?, \?, \?, \?, \?, \?\)\s*""",\s*\((.*?)\),\s*\)')

def repl_upload_save(m):
    return """db.execute(
            \"\"\"
            INSERT INTO videos (
                video_id, agent_id, title, description, filename,
                thumbnail, duration_sec, width, height, tags, category,
                collaborator_ids, response_to_video_id,
                created_at, is_human_upload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            \"\"\",
            (%s, request.form.get("collaborator_ids", "[]"), request.form.get("response_to_video_id", ""), %s),
        )""" % (m.group(1).rsplit(', ', 2)[0], m.group(1).rsplit(', ', 2)[1] + ", " + m.group(1).rsplit(', ', 2)[2])

content = upload_save_regex.sub(repl_upload_save, content)

with open("bottube_server.py", "w") as f:
    f.write(content)

print("Applied upload param logic")

