#!/usr/bin/env python3
"""
BoTTube Syndication Routes — Issue #312 / #360
API endpoints for syndication tracking and outbound reporting.

Endpoints:
    POST   /api/syndication/run/start       - Start a new syndication run
    POST   /api/syndication/run/<id>/end    - End a syndication run
    POST   /api/syndication/item            - Log a syndication item
    PUT    /api/syndication/item/<id>       - Update item status (owner/admin only)
    GET    /api/syndication/run/<id>        - Get run details
    GET    /api/syndication/runs            - List recent runs
    GET    /api/syndication/runs/active     - List active runs
    GET    /api/syndication/report/daily    - Generate daily report (agent-scoped, admin network-wide)
    GET    /api/syndication/report/weekly   - Generate weekly report (agent-scoped, admin network-wide)
    GET    /api/syndication/report/outbound - Generate outbound network report (agent-scoped, admin network-wide)
    GET    /api/syndication/report/export   - Export report to JSON (inline, no file write)

Issue #360 Changes:
    - PUT /api/syndication/item/<id>: Enforce owner/admin authorization
    - Report endpoints: Agent-scoped by default, admin can access network-wide via ?scope=network
    - /report/export: Returns JSON directly without writing server files
"""

import json
import time
from functools import wraps
from pathlib import Path

from flask import Blueprint, jsonify, request

from syndication_tracker import SyndicationTracker, ReportGenerator

syndication_bp = Blueprint("syndication", __name__, url_prefix="/api/syndication")

# Initialize tracker and generator (db path configured by main app)
_tracker = None
_generator = None


def init_syndication(db_path: str) -> None:
    """Initialize syndication tracker with database path."""
    global _tracker, _generator
    _tracker = SyndicationTracker(db_path)
    _generator = ReportGenerator(db_path)


def get_tracker() -> SyndicationTracker:
    """Get the syndication tracker instance."""
    if _tracker is None:
        raise RuntimeError("Syndication tracker not initialized. Call init_syndication() first.")
    return _tracker


def get_generator() -> ReportGenerator:
    """Get the report generator instance."""
    if _generator is None:
        raise RuntimeError("Report generator not initialized. Call init_syndication() first.")
    return _generator


def _is_admin_request() -> bool:
    """Check if request has admin key authentication."""
    from bottube_server import ADMIN_KEY
    admin_key = request.headers.get("X-Admin-Key", "")
    return bool(ADMIN_KEY and admin_key == ADMIN_KEY)


def require_api_key(f):
    """Decorator to require API key authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return jsonify({"error": "Missing X-API-Key header"}), 401

        # Validate API key against database
        from bottube_server import get_db
        db = get_db()
        agent = db.execute(
            "SELECT id, agent_name FROM agents WHERE api_key = ?",
            (api_key,)
        ).fetchone()

        if not agent:
            return jsonify({"error": "Invalid API key"}), 403

        request.agent = agent
        request.is_admin = _is_admin_request()
        return f(*args, **kwargs)
    return decorated


@syndication_bp.route("/run/start", methods=["POST"])
@require_api_key
def start_run():
    """
    Start a new syndication run.
    
    Request JSON:
        run_type (str): Type of syndication (required)
        metadata (dict): Optional metadata
    
    Response:
        run_id (int): The new run ID
    """
    data = request.get_json() or {}
    
    run_type = data.get("run_type")
    if not run_type:
        return jsonify({"error": "run_type is required"}), 400
    
    metadata = data.get("metadata", {})
    
    try:
        tracker = get_tracker()
        run_id = tracker.start_run(
            run_type=run_type,
            agent_id=request.agent["id"],
            metadata=metadata
        )
        
        return jsonify({
            "ok": True,
            "run_id": run_id,
            "run_type": run_type,
            "started_at": time.time()
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@syndication_bp.route("/run/<int:run_id>/end", methods=["POST"])
@require_api_key
def end_run(run_id):
    """
    End a syndication run.
    
    Request JSON:
        status (str): Final status (completed, failed, partial, cancelled)
        metadata (dict): Optional final metadata
    
    Response:
        ok (bool): Success indicator
    """
    data = request.get_json() or {}
    
    status = data.get("status", "completed")
    if status not in ("completed", "failed", "partial", "cancelled"):
        return jsonify({"error": "Invalid status"}), 400
    
    metadata = data.get("metadata")
    
    try:
        tracker = get_tracker()
        run = tracker.get_run(run_id)
        
        if not run:
            return jsonify({"error": "Run not found"}), 404
        
        # Verify ownership
        if run.agent_id != request.agent["id"]:
            return jsonify({"error": "Access denied"}), 403
        
        tracker.end_run(run_id, status, metadata)
        
        return jsonify({
            "ok": True,
            "run_id": run_id,
            "status": status,
            "ended_at": time.time()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@syndication_bp.route("/item", methods=["POST"])
@require_api_key
def log_item():
    """
    Log a syndication item.
    
    Request JSON:
        run_id (int): Parent run ID (required)
        content_id (str): Content identifier (required)
        target_platform (str): Target platform (required)
        status (str): Item status (success, failed, pending, skipped)
        external_id (str): External platform content ID
        external_url (str): External platform content URL
        error_message (str): Error message if failed
        metadata (dict): Additional metadata
    
    Response:
        item_id (int): The new item ID
    """
    data = request.get_json() or {}
    
    run_id = data.get("run_id")
    content_id = data.get("content_id")
    target_platform = data.get("target_platform")
    
    if not run_id or not content_id or not target_platform:
        return jsonify({
            "error": "run_id, content_id, and target_platform are required"
        }), 400
    
    status = data.get("status", "pending")
    if status not in ("success", "failed", "pending", "skipped"):
        return jsonify({"error": "Invalid status"}), 400
    
    try:
        tracker = get_tracker()
        run = tracker.get_run(run_id)
        
        if not run:
            return jsonify({"error": "Run not found"}), 404
        
        # Verify ownership
        if run.agent_id != request.agent["id"]:
            return jsonify({"error": "Access denied"}), 403
        
        item_id = tracker.log_item(
            run_id=run_id,
            content_id=content_id,
            status=status,
            target_platform=target_platform,
            external_id=data.get("external_id"),
            external_url=data.get("external_url"),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {})
        )
        
        return jsonify({
            "ok": True,
            "item_id": item_id,
            "created_at": time.time()
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@syndication_bp.route("/item/<int:item_id>", methods=["PUT"])
@require_api_key
def update_item(item_id):
    """
    Update a syndication item status.

    Authorization: Only the owner of the item's run or an admin can update.

    Request JSON:
        status (str): New status (required)
        external_id (str): External platform content ID
        external_url (str): External platform content URL
        error_message (str): Error message if failed

    Response:
        ok (bool): Success indicator
    """
    data = request.get_json() or {}

    status = data.get("status")
    if not status or status not in ("success", "failed", "pending", "skipped"):
        return jsonify({"error": "Valid status is required"}), 400

    try:
        tracker = get_tracker()
        
        # Get the item to verify ownership
        conn = tracker._get_connection()
        try:
            item = conn.execute(
                """
                SELECT si.id, si.run_id, sr.agent_id
                FROM syndication_items si
                JOIN syndication_runs sr ON si.run_id = sr.id
                WHERE si.id = ?
                """,
                (item_id,)
            ).fetchone()
        finally:
            conn.close()
        
        if not item:
            return jsonify({"error": "Item not found"}), 404
        
        # Enforce owner/admin authorization (Issue #360)
        if not request.is_admin and item["agent_id"] != request.agent["id"]:
            return jsonify({"error": "Access denied: only item owner or admin can update"}), 403

        tracker.update_item_status(
            item_id=item_id,
            status=status,
            external_id=data.get("external_id"),
            external_url=data.get("external_url"),
            error_message=data.get("error_message")
        )

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@syndication_bp.route("/run/<int:run_id>", methods=["GET"])
@require_api_key
def get_run(run_id):
    """
    Get syndication run details.
    
    Response:
        run (dict): Run details
        items (list): List of syndication items
    """
    try:
        tracker = get_tracker()
        run = tracker.get_run(run_id)
        
        if not run:
            return jsonify({"error": "Run not found"}), 404
        
        # Verify ownership
        if run.agent_id != request.agent["id"]:
            return jsonify({"error": "Access denied"}), 403
        
        items = tracker.get_run_items(run_id)
        
        return jsonify({
            "run": {
                "run_id": run.run_id,
                "run_type": run.run_type,
                "agent_id": run.agent_id,
                "status": run.status,
                "started_at": run.started_at,
                "ended_at": run.ended_at,
                "total_items": run.total_items,
                "successful_items": run.successful_items,
                "failed_items": run.failed_items,
                "metadata": run.metadata
            },
            "items": [
                {
                    "item_id": item.item_id,
                    "content_id": item.content_id,
                    "target_platform": item.target_platform,
                    "status": item.status,
                    "created_at": item.created_at,
                    "external_id": item.external_id,
                    "external_url": item.external_url,
                    "error_message": item.error_message,
                    "metadata": item.metadata
                }
                for item in items
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@syndication_bp.route("/runs", methods=["GET"])
@require_api_key
def list_runs():
    """
    List recent syndication runs for the authenticated agent.
    
    Query params:
        limit (int): Max results (default: 50)
        days (int): Lookback days (default: 7)
    
    Response:
        runs (list): List of run summaries
    """
    try:
        limit = int(request.args.get("limit", 50))
        days = int(request.args.get("days", 7))
        
        tracker = get_tracker()
        runs = tracker.get_recent_runs(limit=limit, days=days)
        
        # Filter to agent's own runs
        agent_runs = [r for r in runs if r.agent_id == request.agent["id"]]
        
        return jsonify({
            "runs": [
                {
                    "run_id": r.run_id,
                    "run_type": r.run_type,
                    "status": r.status,
                    "started_at": r.started_at,
                    "ended_at": r.ended_at,
                    "total_items": r.total_items,
                    "successful_items": r.successful_items,
                    "failed_items": r.failed_items
                }
                for r in agent_runs
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@syndication_bp.route("/runs/active", methods=["GET"])
@require_api_key
def list_active_runs():
    """
    List currently active syndication runs.
    
    Response:
        runs (list): List of active runs
    """
    try:
        tracker = get_tracker()
        runs = tracker.get_active_runs()
        
        # Filter to agent's own runs
        agent_runs = [r for r in runs if r.agent_id == request.agent["id"]]
        
        return jsonify({
            "runs": [
                {
                    "run_id": r.run_id,
                    "run_type": r.run_type,
                    "started_at": r.started_at,
                    "total_items": r.total_items,
                    "successful_items": r.successful_items,
                    "failed_items": r.failed_items
                }
                for r in agent_runs
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@syndication_bp.route("/report/daily", methods=["GET"])
@require_api_key
def daily_report():
    """
    Generate daily syndication report.

    Query params:
        date (str): Date in YYYY-MM-DD format (default: today)
        scope (str): 'agent' (default) or 'network' (admin only)

    Response:
        report (dict): Daily report data (scoped to agent by default)
    """
    try:
        date_str = request.args.get("date")
        scope = request.args.get("scope", "agent")
        
        # Network-wide scope requires admin
        agent_id = None
        if scope == "network":
            if not request.is_admin:
                return jsonify({"error": "Admin access required for network-wide scope"}), 403
        else:
            agent_id = request.agent["id"]
        
        generator = get_generator()
        report = generator.generate_daily_report(date_str, agent_id=agent_id)

        return jsonify({"report": report})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@syndication_bp.route("/report/weekly", methods=["GET"])
@require_api_key
def weekly_report():
    """
    Generate weekly syndication report.

    Query params:
        end_date (str): End date in YYYY-MM-DD format (default: today)
        scope (str): 'agent' (default) or 'network' (admin only)

    Response:
        report (dict): Weekly report data (scoped to agent by default)
    """
    try:
        end_date = request.args.get("end_date")
        scope = request.args.get("scope", "agent")
        
        # Network-wide scope requires admin
        agent_id = None
        if scope == "network":
            if not request.is_admin:
                return jsonify({"error": "Admin access required for network-wide scope"}), 403
        else:
            agent_id = request.agent["id"]
        
        generator = get_generator()
        report = generator.generate_weekly_report(end_date, agent_id=agent_id)

        return jsonify({"report": report})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@syndication_bp.route("/report/outbound", methods=["GET"])
@require_api_key
def outbound_report():
    """
    Generate comprehensive outbound network report.

    This is the primary report for issue #312, showing all outbound
    syndication activity across the unified network.
    
    Issue #360: By default scoped to authenticated agent. Admin can
    access network-wide data via ?scope=network.

    Query params:
        days (int): Number of days to include (default: 30)
        scope (str): 'agent' (default) or 'network' (admin only)

    Response:
        report (dict): Outbound network report (scoped to agent by default)
    """
    try:
        days = int(request.args.get("days", 30))
        scope = request.args.get("scope", "agent")
        
        # Network-wide scope requires admin
        agent_id = None
        if scope == "network":
            if not request.is_admin:
                return jsonify({"error": "Admin access required for network-wide scope"}), 403
        else:
            agent_id = request.agent["id"]
        
        generator = get_generator()
        report = generator.generate_outbound_report(days=days, agent_id=agent_id)

        return jsonify({"report": report})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@syndication_bp.route("/report/export", methods=["GET"])
@require_api_key
def export_report():
    """
    Export syndication report to JSON.
    
    Issue #360: Returns JSON directly without writing server files.

    Query params:
        type (str): Report type (daily, weekly, outbound) (default: outbound)
        days (int): Days for outbound report (default: 30)
        date (str): Date for daily report (YYYY-MM-DD)
        end_date (str): End date for weekly report (YYYY-MM-DD)
        scope (str): 'agent' (default) or 'network' (admin only)

    Response:
        report (dict): Report data (returned inline, no file write)
    """
    try:
        report_type = request.args.get("type", "outbound")
        scope = request.args.get("scope", "agent")
        
        # Network-wide scope requires admin
        agent_id = None
        if scope == "network":
            if not request.is_admin:
                return jsonify({"error": "Admin access required for network-wide scope"}), 403
        else:
            agent_id = request.agent["id"]

        kwargs = {"agent_id": agent_id}
        if report_type == "daily":
            kwargs["date_str"] = request.args.get("date")
        elif report_type == "weekly":
            kwargs["end_date"] = request.args.get("end_date")
        else:
            kwargs["days"] = int(request.args.get("days", 30))

        generator = get_generator()
        
        # Issue #360: Return report directly without writing file
        report_data = generator.export_report_json(
            report_type=report_type,
            output_path=None,  # Return dict directly
            **kwargs
        )

        return jsonify({
            "ok": True,
            "scope": "network" if scope == "network" else "agent",
            "report": report_data
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
