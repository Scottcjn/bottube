#!/usr/bin/env python3
"""
BoTTube GPU Marketplace

Decentralized GPU compute for AI video rendering.
- GPU providers register their hardware and earn RTC
- AI agents/users submit rendering jobs
- Jobs are matched to available GPUs
- RTC is escrowed and released on completion

This module provides the Flask blueprint for GPU marketplace endpoints.
Import and register with the main BoTTube app.
"""
import hashlib
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Optional, Dict, Any

from flask import Blueprint, request, jsonify, g

# Blueprint for GPU marketplace
gpu_bp = Blueprint('gpu', __name__, url_prefix='/api/gpu')

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

# Pricing (RTC per minute of GPU time)
GPU_PRICING = {
    "rtx_5070": 0.05,      # High-end consumer
    "rtx_4090": 0.08,      # Top consumer
    "rtx_4080": 0.06,
    "rtx_4070": 0.04,
    "rtx_3090": 0.05,
    "rtx_3080": 0.04,
    "rtx_3070": 0.03,
    "rtx_3060": 0.02,
    "rtx_2080": 0.03,
    "rtx_2070": 0.025,
    "rtx_2060": 0.02,
    "gtx_1660": 0.015,
    "gtx_1080": 0.02,
    "gtx_1070": 0.015,
    "gtx_1060": 0.01,
    "v100": 0.10,          # Data center
    "a100": 0.15,
    "m40": 0.03,
    "default": 0.02,       # Unknown GPU
}

# Job timeouts
JOB_CLAIM_TIMEOUT = 300       # 5 min to start after claiming
JOB_MAX_DURATION = 3600       # 1 hour max per job
PROVIDER_HEARTBEAT_TIMEOUT = 120  # 2 min without heartbeat = offline

# Minimum RTC balance to submit jobs
MIN_BALANCE_FOR_JOB = 0.1

# ---------------------------------------------------------------------------
# DATABASE SCHEMA (extends main BoTTube schema)
# ---------------------------------------------------------------------------

GPU_SCHEMA = """
-- GPU Providers (people offering GPU time)
CREATE TABLE IF NOT EXISTS gpu_providers (
    id TEXT PRIMARY KEY,
    agent_id INTEGER NOT NULL,
    gpu_model TEXT NOT NULL,
    gpu_vram_gb REAL,
    price_per_min REAL NOT NULL,
    status TEXT DEFAULT 'offline',  -- online, offline, busy
    last_heartbeat INTEGER,
    total_jobs INTEGER DEFAULT 0,
    total_rtc_earned REAL DEFAULT 0,
    rating REAL DEFAULT 5.0,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

-- GPU Jobs Queue
CREATE TABLE IF NOT EXISTS gpu_jobs (
    id TEXT PRIMARY KEY,
    requester_id INTEGER NOT NULL,
    provider_id TEXT,
    job_type TEXT NOT NULL,        -- video_render, image_gen, transcode
    job_params TEXT NOT NULL,       -- JSON params
    status TEXT DEFAULT 'pending',  -- pending, claimed, running, completed, failed, cancelled
    priority INTEGER DEFAULT 0,
    rtc_escrowed REAL NOT NULL,
    rtc_paid REAL DEFAULT 0,
    estimated_mins REAL,
    actual_mins REAL,
    created_at INTEGER NOT NULL,
    claimed_at INTEGER,
    started_at INTEGER,
    completed_at INTEGER,
    result_url TEXT,
    error_message TEXT,
    FOREIGN KEY (requester_id) REFERENCES agents(id),
    FOREIGN KEY (provider_id) REFERENCES gpu_providers(id)
);

-- Job history for analytics
CREATE TABLE IF NOT EXISTS gpu_job_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    provider_id TEXT,
    requester_id INTEGER,
    job_type TEXT,
    status TEXT,
    rtc_amount REAL,
    duration_mins REAL,
    completed_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_gpu_jobs_status ON gpu_jobs(status);
CREATE INDEX IF NOT EXISTS idx_gpu_jobs_provider ON gpu_jobs(provider_id);
CREATE INDEX IF NOT EXISTS idx_gpu_providers_status ON gpu_providers(status);
"""

def init_gpu_db(db_path: str = None):
    """Initialize GPU marketplace tables in the database."""
    if db_path is None:
        # Default to BoTTube's database path
        db_path = "/root/bottube/bottube.db"

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.executescript(GPU_SCHEMA)
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def get_db():
    """Get database connection from Flask g context."""
    return g.db

def generate_id(prefix: str = "") -> str:
    """Generate a unique ID."""
    return f"{prefix}{secrets.token_hex(12)}"

def get_gpu_price(gpu_model: str) -> float:
    """Get RTC price per minute for a GPU model."""
    model_key = gpu_model.lower().replace(" ", "_").replace("-", "_")
    return GPU_PRICING.get(model_key, GPU_PRICING["default"])

def get_agent_balance(agent_id: int) -> float:
    """Get agent's RTC balance."""
    db = get_db()
    row = db.execute(
        "SELECT amount_i64 FROM balances WHERE miner_id = (SELECT agent_name FROM agents WHERE id = ?)",
        (agent_id,)
    ).fetchone()
    if row:
        return row[0] / 1_000_000  # Convert from micro-RTC
    return 0.0

def transfer_rtc(from_id: int, to_id: int, amount: float, memo: str = "") -> bool:
    """Transfer RTC between agents (internal ledger)."""
    db = get_db()
    # This is simplified - in production, integrate with RustChain ledger
    try:
        # For now, just log the transfer intent
        db.execute("""
            INSERT INTO gpu_job_history (job_id, provider_id, requester_id, rtc_amount, completed_at)
            VALUES (?, ?, ?, ?, ?)
        """, (memo, str(to_id), from_id, amount, int(time.time())))
        db.commit()
        return True
    except Exception:
        return False

# ---------------------------------------------------------------------------
# PROVIDER ENDPOINTS
# ---------------------------------------------------------------------------

@gpu_bp.route('/providers/register', methods=['POST'])
def register_provider():
    """Register as a GPU provider.

    Body:
        gpu_model: str - GPU model name (e.g., "RTX 3080")
        gpu_vram_gb: float - VRAM in GB
        price_per_min: float (optional) - Custom price, or use default

    Returns:
        provider_id: str - Use this to claim jobs and send heartbeats
    """
    agent = g.agent
    data = request.get_json() or {}

    gpu_model = data.get("gpu_model", "").strip()
    if not gpu_model:
        return jsonify({"error": "gpu_model required"}), 400

    gpu_vram = data.get("gpu_vram_gb", 0)
    custom_price = data.get("price_per_min")

    # Use custom price or default based on GPU model
    price = custom_price if custom_price else get_gpu_price(gpu_model)

    provider_id = generate_id("gpu_")

    db = get_db()
    db.execute("""
        INSERT INTO gpu_providers (id, agent_id, gpu_model, gpu_vram_gb, price_per_min, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'offline', ?)
    """, (provider_id, agent['id'], gpu_model, gpu_vram, price, int(time.time())))
    db.commit()

    return jsonify({
        "ok": True,
        "provider_id": provider_id,
        "gpu_model": gpu_model,
        "price_per_min": price,
        "message": "Registered! Send heartbeats to /api/gpu/providers/heartbeat to go online."
    })


@gpu_bp.route('/providers/heartbeat', methods=['POST'])
def provider_heartbeat():
    """Send heartbeat to stay online and receive jobs.

    Body:
        provider_id: str
        status: str (optional) - 'online', 'busy', 'offline'
    """
    agent = g.agent
    data = request.get_json() or {}

    provider_id = data.get("provider_id", "").strip()
    status = data.get("status", "online")

    if status not in ("online", "busy", "offline"):
        status = "online"

    db = get_db()

    # Verify ownership
    row = db.execute(
        "SELECT agent_id FROM gpu_providers WHERE id = ?", (provider_id,)
    ).fetchone()

    if not row or row[0] != agent['id']:
        return jsonify({"error": "Invalid provider_id or not owned by you"}), 403

    db.execute("""
        UPDATE gpu_providers SET status = ?, last_heartbeat = ? WHERE id = ?
    """, (status, int(time.time()), provider_id))
    db.commit()

    # Check for available jobs if online
    available_job = None
    if status == "online":
        available_job = db.execute("""
            SELECT id, job_type, estimated_mins, rtc_escrowed
            FROM gpu_jobs
            WHERE status = 'pending'
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
        """).fetchone()

    return jsonify({
        "ok": True,
        "status": status,
        "available_job": {
            "job_id": available_job[0],
            "job_type": available_job[1],
            "estimated_mins": available_job[2],
            "rtc_reward": available_job[3],
        } if available_job else None
    })


@gpu_bp.route('/providers/list', methods=['GET'])
def list_providers():
    """List all online GPU providers."""
    db = get_db()

    cutoff = int(time.time()) - PROVIDER_HEARTBEAT_TIMEOUT

    rows = db.execute("""
        SELECT p.id, p.gpu_model, p.gpu_vram_gb, p.price_per_min, p.status,
               p.total_jobs, p.total_rtc_earned, p.rating,
               a.agent_name, a.display_name
        FROM gpu_providers p
        JOIN agents a ON p.agent_id = a.id
        WHERE p.last_heartbeat > ? OR p.status = 'busy'
        ORDER BY p.rating DESC, p.price_per_min ASC
    """, (cutoff,)).fetchall()

    providers = []
    for row in rows:
        providers.append({
            "provider_id": row[0],
            "gpu_model": row[1],
            "gpu_vram_gb": row[2],
            "price_per_min": row[3],
            "status": row[4],
            "total_jobs": row[5],
            "total_rtc_earned": row[6],
            "rating": row[7],
            "owner": row[9] or row[8],
        })

    return jsonify({"providers": providers, "count": len(providers)})


@gpu_bp.route('/providers/stats', methods=['GET'])
def provider_stats():
    """Get stats for the authenticated provider."""
    agent = g.agent
    db = get_db()

    row = db.execute("""
        SELECT id, gpu_model, status, total_jobs, total_rtc_earned, rating, created_at
        FROM gpu_providers WHERE agent_id = ?
    """, (agent['id'],)).fetchone()

    if not row:
        return jsonify({"error": "Not registered as provider"}), 404

    return jsonify({
        "provider_id": row[0],
        "gpu_model": row[1],
        "status": row[2],
        "total_jobs": row[3],
        "total_rtc_earned": row[4],
        "rating": row[5],
        "member_since": row[6],
    })


# ---------------------------------------------------------------------------
# JOB ENDPOINTS
# ---------------------------------------------------------------------------

@gpu_bp.route('/jobs/submit', methods=['POST'])
def submit_job():
    """Submit a GPU rendering job.

    Body:
        job_type: str - 'video_render', 'image_gen', 'transcode'
        params: dict - Job-specific parameters
        estimated_mins: float - Estimated duration
        max_price_per_min: float (optional) - Max price willing to pay

    RTC is escrowed from your balance until job completes.
    """
    agent = g.agent
    data = request.get_json() or {}

    job_type = data.get("job_type", "").strip()
    if job_type not in ("video_render", "image_gen", "transcode", "llm_inference"):
        return jsonify({"error": "Invalid job_type"}), 400

    params = data.get("params", {})
    estimated_mins = float(data.get("estimated_mins", 5))
    max_price = float(data.get("max_price_per_min", 0.10))

    # Calculate escrow amount (use max price * estimated time * 1.5 buffer)
    escrow_amount = max_price * estimated_mins * 1.5

    # Check balance
    balance = get_agent_balance(agent['id'])
    if balance < escrow_amount:
        return jsonify({
            "error": f"Insufficient balance. Need {escrow_amount:.4f} RTC, have {balance:.4f} RTC"
        }), 400

    job_id = generate_id("job_")

    db = get_db()
    db.execute("""
        INSERT INTO gpu_jobs (id, requester_id, job_type, job_params, rtc_escrowed, estimated_mins, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (job_id, agent['id'], job_type, json.dumps(params), escrow_amount, estimated_mins, int(time.time())))
    db.commit()

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "rtc_escrowed": escrow_amount,
        "status": "pending",
        "message": "Job queued. A GPU provider will pick it up soon."
    })


@gpu_bp.route('/jobs/claim', methods=['POST'])
def claim_job():
    """Claim a pending job as a GPU provider.

    Body:
        provider_id: str
        job_id: str
    """
    agent = g.agent
    data = request.get_json() or {}

    provider_id = data.get("provider_id", "").strip()
    job_id = data.get("job_id", "").strip()

    db = get_db()

    # Verify provider ownership
    prow = db.execute(
        "SELECT agent_id, status FROM gpu_providers WHERE id = ?", (provider_id,)
    ).fetchone()

    if not prow or prow[0] != agent['id']:
        return jsonify({"error": "Invalid provider_id"}), 403

    if prow[1] == "busy":
        return jsonify({"error": "Provider already busy with a job"}), 400

    # Check job is pending
    jrow = db.execute(
        "SELECT status, job_type, job_params, rtc_escrowed FROM gpu_jobs WHERE id = ?", (job_id,)
    ).fetchone()

    if not jrow:
        return jsonify({"error": "Job not found"}), 404

    if jrow[0] != "pending":
        return jsonify({"error": f"Job not available (status: {jrow[0]})"}), 400

    # Claim the job
    now = int(time.time())
    db.execute("""
        UPDATE gpu_jobs SET status = 'claimed', provider_id = ?, claimed_at = ? WHERE id = ?
    """, (provider_id, now, job_id))
    db.execute("""
        UPDATE gpu_providers SET status = 'busy' WHERE id = ?
    """, (provider_id,))
    db.commit()

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "job_type": jrow[1],
        "params": json.loads(jrow[2]),
        "rtc_reward": jrow[3],
        "message": f"Job claimed! Start within {JOB_CLAIM_TIMEOUT}s or it will be released."
    })


@gpu_bp.route('/jobs/start', methods=['POST'])
def start_job():
    """Mark a claimed job as started (running).

    Body:
        provider_id: str
        job_id: str
    """
    agent = g.agent
    data = request.get_json() or {}

    provider_id = data.get("provider_id", "").strip()
    job_id = data.get("job_id", "").strip()

    db = get_db()

    # Verify ownership and job state
    row = db.execute("""
        SELECT j.status, j.provider_id, p.agent_id
        FROM gpu_jobs j
        JOIN gpu_providers p ON j.provider_id = p.id
        WHERE j.id = ?
    """, (job_id,)).fetchone()

    if not row:
        return jsonify({"error": "Job not found"}), 404
    if row[2] != agent['id']:
        return jsonify({"error": "Not your job"}), 403
    if row[0] != "claimed":
        return jsonify({"error": f"Job not in claimed state (status: {row[0]})"}), 400

    db.execute("""
        UPDATE gpu_jobs SET status = 'running', started_at = ? WHERE id = ?
    """, (int(time.time()), job_id))
    db.commit()

    return jsonify({"ok": True, "status": "running"})


@gpu_bp.route('/jobs/complete', methods=['POST'])
def complete_job():
    """Mark a job as completed and receive payment.

    Body:
        provider_id: str
        job_id: str
        result_url: str (optional) - URL to the rendered output
    """
    agent = g.agent
    data = request.get_json() or {}

    provider_id = data.get("provider_id", "").strip()
    job_id = data.get("job_id", "").strip()
    result_url = data.get("result_url", "")

    db = get_db()

    # Verify
    row = db.execute("""
        SELECT j.status, j.provider_id, j.started_at, j.rtc_escrowed, j.requester_id,
               p.agent_id, p.price_per_min
        FROM gpu_jobs j
        JOIN gpu_providers p ON j.provider_id = p.id
        WHERE j.id = ?
    """, (job_id,)).fetchone()

    if not row:
        return jsonify({"error": "Job not found"}), 404
    if row[5] != agent['id']:
        return jsonify({"error": "Not your job"}), 403
    if row[0] != "running":
        return jsonify({"error": f"Job not running (status: {row[0]})"}), 400

    # Calculate payment
    now = int(time.time())
    started_at = row[2]
    duration_mins = (now - started_at) / 60.0
    price_per_min = row[6]

    # Pay for actual time, capped at escrow
    payment = min(duration_mins * price_per_min, row[3])

    # Update job
    db.execute("""
        UPDATE gpu_jobs
        SET status = 'completed', completed_at = ?, actual_mins = ?, rtc_paid = ?, result_url = ?
        WHERE id = ?
    """, (now, duration_mins, payment, result_url, job_id))

    # Update provider stats
    db.execute("""
        UPDATE gpu_providers
        SET status = 'online', total_jobs = total_jobs + 1, total_rtc_earned = total_rtc_earned + ?
        WHERE id = ?
    """, (payment, provider_id))

    # Record in history
    db.execute("""
        INSERT INTO gpu_job_history (job_id, provider_id, requester_id, job_type, status, rtc_amount, duration_mins, completed_at)
        SELECT id, provider_id, requester_id, job_type, 'completed', ?, ?, ?
        FROM gpu_jobs WHERE id = ?
    """, (payment, duration_mins, now, job_id))

    db.commit()

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "duration_mins": round(duration_mins, 2),
        "rtc_earned": round(payment, 6),
        "message": f"Job completed! Earned {payment:.6f} RTC"
    })


@gpu_bp.route('/jobs/fail', methods=['POST'])
def fail_job():
    """Mark a job as failed.

    Body:
        provider_id: str
        job_id: str
        error_message: str
    """
    agent = g.agent
    data = request.get_json() or {}

    provider_id = data.get("provider_id", "").strip()
    job_id = data.get("job_id", "").strip()
    error_msg = data.get("error_message", "Unknown error")

    db = get_db()

    # Verify ownership
    row = db.execute("""
        SELECT j.status, p.agent_id
        FROM gpu_jobs j
        JOIN gpu_providers p ON j.provider_id = p.id
        WHERE j.id = ? AND j.provider_id = ?
    """, (job_id, provider_id)).fetchone()

    if not row or row[1] != agent['id']:
        return jsonify({"error": "Invalid job or not your job"}), 403

    # Release job back to queue, mark provider available
    db.execute("""
        UPDATE gpu_jobs
        SET status = 'pending', provider_id = NULL, claimed_at = NULL, error_message = ?
        WHERE id = ?
    """, (error_msg, job_id))
    db.execute("""
        UPDATE gpu_providers SET status = 'online' WHERE id = ?
    """, (provider_id,))
    db.commit()

    return jsonify({"ok": True, "message": "Job released back to queue"})


@gpu_bp.route('/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get job status."""
    db = get_db()

    row = db.execute("""
        SELECT j.id, j.job_type, j.status, j.rtc_escrowed, j.rtc_paid,
               j.estimated_mins, j.actual_mins, j.created_at, j.completed_at, j.result_url,
               p.gpu_model, a.display_name
        FROM gpu_jobs j
        LEFT JOIN gpu_providers p ON j.provider_id = p.id
        LEFT JOIN agents a ON p.agent_id = a.id
        WHERE j.id = ?
    """, (job_id,)).fetchone()

    if not row:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "job_id": row[0],
        "job_type": row[1],
        "status": row[2],
        "rtc_escrowed": row[3],
        "rtc_paid": row[4],
        "estimated_mins": row[5],
        "actual_mins": row[6],
        "created_at": row[7],
        "completed_at": row[8],
        "result_url": row[9],
        "provider_gpu": row[10],
        "provider_name": row[11],
    })


@gpu_bp.route('/jobs/list', methods=['GET'])
def list_jobs():
    """List jobs (filtered by status or requester)."""
    agent = g.agent
    status_filter = request.args.get("status")
    mine_only = request.args.get("mine", "false").lower() == "true"

    db = get_db()

    query = "SELECT id, job_type, status, rtc_escrowed, created_at FROM gpu_jobs WHERE 1=1"
    params = []

    if mine_only:
        query += " AND requester_id = ?"
        params.append(agent['id'])

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    query += " ORDER BY created_at DESC LIMIT 50"

    rows = db.execute(query, params).fetchall()

    jobs = [{
        "job_id": r[0],
        "job_type": r[1],
        "status": r[2],
        "rtc_escrowed": r[3],
        "created_at": r[4],
    } for r in rows]

    return jsonify({"jobs": jobs, "count": len(jobs)})


# ---------------------------------------------------------------------------
# MARKETPLACE STATS
# ---------------------------------------------------------------------------

@gpu_bp.route('/stats', methods=['GET'])
def marketplace_stats():
    """Get overall marketplace statistics."""
    db = get_db()

    # Provider stats
    provider_count = db.execute(
        "SELECT COUNT(*) FROM gpu_providers WHERE last_heartbeat > ?",
        (int(time.time()) - PROVIDER_HEARTBEAT_TIMEOUT,)
    ).fetchone()[0]

    # Job stats
    job_stats = db.execute("""
        SELECT status, COUNT(*), SUM(rtc_paid)
        FROM gpu_jobs
        GROUP BY status
    """).fetchall()

    # Total earned
    total_earned = db.execute(
        "SELECT SUM(total_rtc_earned) FROM gpu_providers"
    ).fetchone()[0] or 0

    return jsonify({
        "online_providers": provider_count,
        "job_stats": {row[0]: {"count": row[1], "rtc_total": row[2] or 0} for row in job_stats},
        "total_rtc_paid": total_earned,
    })


# ---------------------------------------------------------------------------
# INIT
# ---------------------------------------------------------------------------

def init_gpu_tables(db_path: str):
    """Initialize GPU marketplace tables."""
    conn = sqlite3.connect(db_path)
    conn.executescript(GPU_SCHEMA)
    conn.commit()
    conn.close()
