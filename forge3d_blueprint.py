# SPDX-License-Identifier: Apache-2.0
# Author: @Scottcjn (Elyan Labs)
"""
Forge3D — Studio's 3D generation line (Meshy-class), RTC-billed.

This blueprint owns the 3D JOB lifecycle with its OWN per-type schema (design §7:
do not reuse the video-shaped job/result). The RTC debit happens in
studio_blueprint (shared atomic rails); this module runs the async generation and
**refunds on terminal failure** (job-scoped, fired once) — the async-refund
contract §7 requires for every long job.

  start_job(agent_id, prompt, cost) -> job_id        (called by studio_blueprint)
  GET /api/studio/3d/status/<job_id>                 (poll; type-specific result)

Output GLB is written to the shared Studio media dir and served by the existing
/studio/media/<fname> route.
"""
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, render_template

forge3d_bp = Blueprint("forge3d", __name__)

STUDIO_MEDIA_DIR = os.environ.get("STUDIO_MEDIA_DIR",
                                  str(Path(os.environ.get("BOTTUBE_BASE_DIR",
                                      str(Path(__file__).resolve().parent))) / "studio_media"))


def _db_path():
    base = os.environ.get("BOTTUBE_BASE_DIR", str(Path(__file__).resolve().parent))
    return os.environ.get("BOTTUBE_DB_PATH", str(Path(base) / "bottube.db"))


def _conn():
    c = sqlite3.connect(_db_path(), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    return c


def init_forge3d_tables(db_path: str = None):
    c = sqlite3.connect(db_path or _db_path(), timeout=30)
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS forge3d_jobs (
                id          TEXT PRIMARY KEY,
                agent_id    INTEGER NOT NULL,
                prompt      TEXT,
                status      TEXT NOT NULL DEFAULT 'queued',
                glb_fname   TEXT,
                formats     TEXT,
                error       TEXT,
                charged_rtc REAL DEFAULT 0,
                refunded    INTEGER NOT NULL DEFAULT 0,
                created_at  REAL,
                updated_at  REAL
            )""")
        c.commit()
    finally:
        c.close()


def _set(job_id, **kw):
    if not kw:
        return
    kw["updated_at"] = time.time()
    cols = ", ".join(f"{k}=?" for k in kw)
    c = _conn()
    try:
        c.execute(f"UPDATE forge3d_jobs SET {cols} WHERE id=?", (*kw.values(), job_id))
        c.commit()
    finally:
        c.close()


def _refund_once(job_id, agent_id, cost):
    """Refund the RTC exactly once for this job (atomic guard on `refunded`)."""
    c = _conn()
    try:
        cur = c.execute("UPDATE forge3d_jobs SET refunded=1 WHERE id=? AND refunded=0", (job_id,))
        if cur.rowcount == 1:
            c.execute("UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id=?", (cost, agent_id))
            try:  # draw the refund from the shared BoTTube refund reserve
                from studio_blueprint import _ensure_reserve
                rid = _ensure_reserve(c)
                c.execute("UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id=?", (cost, rid))
            except Exception as e:
                print(f"[forge3d] reserve draw failed: {e}", flush=True)
        c.commit()
        return cur.rowcount == 1
    finally:
        c.close()


def _save_glb(data: bytes) -> str:
    Path(STUDIO_MEDIA_DIR).mkdir(parents=True, exist_ok=True)
    fname = uuid.uuid4().hex + ".glb"
    with open(os.path.join(STUDIO_MEDIA_DIR, fname), "wb") as f:
        f.write(data)
    return fname


def _worker(job_id, agent_id, prompt, cost):
    _set(job_id, status="generating")
    try:
        from forge3d_provider import generate_3d
        glb, meta = generate_3d(prompt)
        if not glb or len(glb) < 256:
            raise RuntimeError("empty_model")
        fname = _save_glb(glb)
        _set(job_id, status="completed", glb_fname=fname,
             formats=",".join(meta.get("formats", []) or []))
        print(f"[forge3d] job {job_id} completed ({len(glb)} bytes, {meta.get('backend')})", flush=True)
    except Exception as e:
        _set(job_id, status="failed", error=str(e)[:200])
        refunded = _refund_once(job_id, agent_id, cost)
        print(f"[forge3d] job {job_id} failed: {e} (refunded={refunded})", flush=True)


def start_job(agent_id: int, prompt: str, cost: float) -> str:
    """Create a 3D job row and kick off the async worker. RTC already debited upstream."""
    job_id = uuid.uuid4().hex
    now = time.time()
    c = _conn()
    try:
        c.execute("INSERT INTO forge3d_jobs (id, agent_id, prompt, status, charged_rtc, created_at, updated_at) "
                  "VALUES (?,?,?,?,?,?,?)", (job_id, agent_id, prompt[:1000], "queued", cost, now, now))
        c.commit()
    finally:
        c.close()
    threading.Thread(target=_worker, args=(job_id, agent_id, prompt, cost), daemon=True).start()
    return job_id


@forge3d_bp.route("/studio/models")
def forge3d_gallery():
    """Public gallery of recently generated 3D models (browse + view + download)."""
    c = _conn()
    try:
        rows = c.execute(
            "SELECT f.id, f.prompt, f.glb_fname, f.created_at, "
            "       a.agent_name, a.display_name "
            "FROM forge3d_jobs f LEFT JOIN agents a ON a.id = f.agent_id "
            "WHERE f.status='completed' AND f.glb_fname IS NOT NULL AND f.glb_fname != '' "
            "ORDER BY f.rowid DESC LIMIT 60").fetchall()
    finally:
        c.close()
    models = [{
        "prompt": r["prompt"] or "",
        "url": f"/studio/media/{r['glb_fname']}",
        "creator": (r["display_name"] or r["agent_name"] or "anon"),
    } for r in rows]
    return render_template("forge3d_models.html", models=models)


@forge3d_bp.route("/api/studio/3d/status/<job_id>")
def forge3d_status(job_id):
    c = _conn()
    try:
        row = c.execute("SELECT * FROM forge3d_jobs WHERE id=?", (job_id,)).fetchone()
    finally:
        c.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    out = {"type": "model", "status": row["status"]}
    if row["status"] == "completed" and row["glb_fname"]:
        out["model_url"] = f"/studio/media/{row['glb_fname']}"
        out["formats"] = (row["formats"] or "").split(",") if row["formats"] else ["glb"]
    elif row["status"] == "failed":
        out["error"] = row["error"] or "generation failed"
    return jsonify(out)
