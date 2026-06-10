#!/usr/bin/env python3
"""Patch bottube_server.py to integrate CTR tracking."""
import sys

filepath = "/root/bottube/bottube_server.py"
with open(filepath, "r") as f:
    content = f.read()
lines = content.split("\n")

# 1. Add import + tracker init after THUMB_DIR line
thumb_idx = None
for i, line in enumerate(lines):
    if line.strip().startswith("THUMB_DIR"):
        thumb_idx = i
        break

if thumb_idx is None:
    print("ERROR: Could not find THUMB_DIR line")
    sys.exit(1)

insert_block = [
    "",
    "# ---------------------------------------------------------------------------",
    "# CTR / Thumbnail tracking (lazy-init to avoid import-time DB creation)",
    "# ---------------------------------------------------------------------------",
    "_ctr_tracker = None",
    "_ab_manager = None",
    "",
    "def _get_ctr_tracker():",
    "    global _ctr_tracker",
    "    if _ctr_tracker is None:",
    "        from thumbnails.ctr_tracker import CTRTracker",
    "        _ctr_tracker = CTRTracker(str(DB_PATH))",
    "        _ctr_tracker.init_db()",
    "    return _ctr_tracker",
    "",
    "def _get_ab_manager():",
    "    global _ab_manager",
    "    if _ab_manager is None:",
    "        from thumbnails.ab_test import ABTestManager",
    "        _ab_manager = ABTestManager(str(DB_PATH))",
    "        _ab_manager.init_db()",
    "    return _ab_manager",
    "",
]

for j, insert_line in enumerate(insert_block):
    lines.insert(thumb_idx + 1 + j, insert_line)

# Re-join and re-split to reset indices
content = "\n".join(lines)
lines = content.split("\n")

# 2. Add impression tracking in feed endpoint
feed_return_marker = '"videos": videos, "page": page, "mode": "latest"'
feed_inject_done = False
for i, line in enumerate(lines):
    if feed_return_marker in line and not feed_inject_done:
        impression_lines = [
            "    # CTR: Record impressions for videos shown in feed",
            "    try:",
            '        vid_ids = [v.get("video_id", "") for v in videos if v.get("video_id")]',
            "        if vid_ids:",
            "            _get_ctr_tracker().record_impressions_batch(vid_ids)",
            "    except Exception:",
            "        pass  # CTR tracking is best-effort",
            "",
        ]
        for j, il in enumerate(impression_lines):
            lines.insert(i + j, il)
        feed_inject_done = True
        break

if not feed_inject_done:
    print("WARNING: Could not inject feed impression tracking")

content = "\n".join(lines)
lines = content.split("\n")

# 3. Add click tracking in record_view before video_to_dict
in_record_view = False
view_inject_done = False
for i, line in enumerate(lines):
    if "def record_view(" in line:
        in_record_view = True
    if in_record_view and "d = video_to_dict(row)" in line.strip() and not view_inject_done:
        click_lines = [
            "    # CTR: Record click (video opened/watched)",
            "    try:",
            "        _get_ctr_tracker().record_click(video_id)",
            "    except Exception:",
            "        pass",
            "",
        ]
        for j, cl in enumerate(click_lines):
            lines.insert(i + j, cl)
        view_inject_done = True
        break

if not view_inject_done:
    print("WARNING: Could not inject view click tracking")

content = "\n".join(lines)
lines = content.split("\n")

# 4. Add CTR API endpoints before if __name__
main_idx = None
for i, line in enumerate(lines):
    if line.strip() == 'if __name__ == "__main__":':
        main_idx = i
        break

if main_idx is None:
    print("ERROR: Could not find if __name__ block")
    sys.exit(1)

endpoint_lines = [
    "",
    "# ---------------------------------------------------------------------------",
    "# CTR / Thumbnail Analytics API",
    "# ---------------------------------------------------------------------------",
    "",
    '@app.route("/api/ctr/stats")',
    "def ctr_global_stats():",
    '    """Get global CTR statistics."""',
    "    try:",
    "        summary = _get_ctr_tracker().get_global_summary()",
    '        return jsonify({"ok": True, **summary})',
    "    except Exception as e:",
    '        return jsonify({"ok": False, "error": str(e)}), 500',
    "",
    "",
    '@app.route("/api/ctr/top")',
    "def ctr_top_videos():",
    '    """Get top videos by CTR."""',
    '    limit = min(50, request.args.get("limit", 20, type=int))',
    '    min_imp = request.args.get("min_impressions", 10, type=int)',
    "    try:",
    "        top = _get_ctr_tracker().get_top_by_ctr(limit=limit, min_impressions=min_imp)",
    '        return jsonify({"ok": True, "videos": top})',
    "    except Exception as e:",
    '        return jsonify({"ok": False, "error": str(e)}), 500',
    "",
    "",
    '@app.route("/api/ctr/underperforming")',
    "def ctr_underperforming():",
    '    """Get videos with high impressions but low CTR."""',
    "    try:",
    "        videos = _get_ctr_tracker().get_underperforming()",
    '        return jsonify({"ok": True, "videos": videos})',
    "    except Exception as e:",
    '        return jsonify({"ok": False, "error": str(e)}), 500',
    "",
    "",
    '@app.route("/api/videos/<video_id>/ctr")',
    "def video_ctr_stats(video_id):",
    '    """Get CTR stats for a specific video."""',
    "    try:",
    "        stats = _get_ctr_tracker().get_stats(video_id)",
    "        if not stats:",
    '            return jsonify({"ok": True, "video_id": video_id, "impressions": 0, "clicks": 0, "ctr": 0})',
    '        return jsonify({"ok": True, **stats})',
    "    except Exception as e:",
    '        return jsonify({"ok": False, "error": str(e)}), 500',
    "",
    "",
    '@app.route("/api/videos/<video_id>/watch_time", methods=["POST"])',
    "def record_watch_time(video_id):",
    '    """Record watch time for a video (called by player on pause/close).',
    "",
    '    Body: {"seconds": 12.5}',
    '    """',
    "    try:",
    "        data = request.get_json(silent=True) or {}",
    '        seconds = float(data.get("seconds", 0))',
    "        if seconds > 0:",
    "            _get_ctr_tracker().record_watch_time(video_id, seconds)",
    '        return jsonify({"ok": True, "video_id": video_id, "seconds_recorded": seconds})',
    "    except Exception as e:",
    '        return jsonify({"ok": False, "error": str(e)}), 500',
    "",
    "",
    '@app.route("/api/videos/<video_id>/ab/variants")',
    "def video_ab_variants(video_id):",
    '    """Get A/B test variant stats for a video."""',
    "    try:",
    "        stats = _get_ab_manager().get_variant_stats(video_id)",
    "        winner = _get_ab_manager().get_winner(video_id)",
    '        return jsonify({"ok": True, "video_id": video_id, "variants": stats, "winner": winner})',
    "    except Exception as e:",
    '        return jsonify({"ok": False, "error": str(e)}), 500',
    "",
]

for j, el in enumerate(endpoint_lines):
    lines.insert(main_idx + j, el)

content = "\n".join(lines)
with open(filepath, "w") as f:
    f.write(content)

print("Patch applied successfully")
