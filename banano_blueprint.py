"""
BoTTube Banano (BAN) Payment Integration
Flask Blueprint for feeless BAN rewards, tips, and withdrawals.

Banano is a feeless, instant cryptocurrency (fork of Nano).
Uses bananopie library for correct Ed25519-Blake2b key derivation and
Kalium public API for RPC operations.
Custodial model: platform seed derives per-user accounts by index.
"""

from flask import Blueprint, request, jsonify, g, session
import json
import logging
import os
import sqlite3
import time
import urllib.request

ban_bp = Blueprint("banano", __name__)
log = logging.getLogger("banano")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KALIUM_API = "https://kaliumapi.appditto.com/api"
KALIUM_FALLBACK = "https://public.node.jungletv.live/rpc"
BANANO_SEED = os.environ.get("BANANO_SEED", "")

# 1 BAN = 10^29 raw
BAN_RAW_MULTIPLIER = 10**29

# Reward schedule
REWARDS = {
    "upload": 1.0,          # 1 BAN per video upload
    "100_views": 5.0,       # 5 BAN at 100 views
    "1000_views": 19.19,    # 19.19 BAN at 1000 views (potassium meme)
    "video_gen": 2.0,       # 2 BAN for AI video generation
    "video_gen_comfyui": 5.0,  # 5 BAN for GPU-rendered AI video
    "video_gen_heygen": 3.0,   # 3 BAN for HeyGen talking-head video
}

# Admin key for management endpoints
ADMIN_KEY = os.environ.get("BOTTUBE_ADMIN_KEY", "bottube_admin_key_2026")

# bananopie availability flag
_HAS_BANANOPIE = False
_rpc_instance = None
try:
    from bananopie import RPC as BananoRPC, Wallet as BananoWallet
    _HAS_BANANOPIE = True
except ImportError:
    log.warning("bananopie not installed — using fallback RPC. "
                "Install with: pip install bananopie")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db():
    """Get database connection from Flask g."""
    if "db" not in g:
        db_path = os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
    return g.db


def init_ban_tables(db=None):
    """Create Banano-related tables if they don't exist."""
    if db is None:
        db_path = os.environ.get("BOTTUBE_DB", "/root/bottube/bottube.db")
        db = sqlite3.connect(db_path)
        should_close = True
    else:
        should_close = False

    db.executescript("""
        CREATE TABLE IF NOT EXISTS ban_wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER UNIQUE NOT NULL,
            ban_address TEXT NOT NULL,
            account_index INTEGER NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        );

        CREATE TABLE IF NOT EXISTS ban_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            tx_type TEXT NOT NULL,
            amount_ban REAL NOT NULL,
            reason TEXT DEFAULT '',
            video_id TEXT DEFAULT '',
            block_hash TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at REAL NOT NULL,
            processed_at REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS ban_milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            video_id TEXT NOT NULL,
            milestone TEXT NOT NULL,
            ban_amount REAL NOT NULL,
            awarded_at REAL NOT NULL,
            UNIQUE(agent_id, video_id, milestone)
        );

        CREATE INDEX IF NOT EXISTS idx_ban_tx_agent ON ban_transactions(agent_id);
        CREATE INDEX IF NOT EXISTS idx_ban_tx_status ON ban_transactions(status);
        CREATE INDEX IF NOT EXISTS idx_ban_milestones_video ON ban_milestones(agent_id, video_id);
    """)
    db.commit()
    if should_close:
        db.close()


# ---------------------------------------------------------------------------
# Banano RPC helpers
# ---------------------------------------------------------------------------

def _ban_rpc(action_data: dict) -> dict:
    """Send an RPC request to Kalium API with fallback."""
    for api_url in [KALIUM_API, KALIUM_FALLBACK]:
        try:
            payload = json.dumps(action_data).encode()
            req = urllib.request.Request(
                api_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                if "error" not in result:
                    return result
                # If error, try fallback
                if api_url == KALIUM_FALLBACK:
                    return result
        except Exception as e:
            if api_url == KALIUM_FALLBACK:
                return {"error": str(e)}
    return {"error": "all RPC endpoints failed"}


def _get_rpc():
    """Get bananopie RPC instance (cached)."""
    global _rpc_instance
    if _HAS_BANANOPIE and _rpc_instance is None:
        _rpc_instance = BananoRPC(KALIUM_API)
    return _rpc_instance


def _get_platform_wallet():
    """Get bananopie Wallet for the platform hot wallet (index 0)."""
    if not _HAS_BANANOPIE or not BANANO_SEED:
        return None
    rpc = _get_rpc()
    return BananoWallet(rpc, seed=BANANO_SEED, index=0)


def _derive_address(seed: str, index: int) -> str:
    """Derive a Banano address from seed + index.

    Uses bananopie for correct Ed25519-Blake2b derivation.
    Falls back to RPC key_expand if bananopie unavailable.
    """
    if not seed:
        return None

    if _HAS_BANANOPIE:
        rpc = _get_rpc()
        wallet = BananoWallet(rpc, seed=seed, index=index)
        return wallet.get_address()

    # Fallback: derive private key with Blake2b, use RPC key_expand
    import hashlib
    seed_bytes = bytes.fromhex(seed)
    index_bytes = index.to_bytes(4, "big")
    private_key = hashlib.blake2b(seed_bytes + index_bytes, digest_size=32).hexdigest()
    resp = _ban_rpc({"action": "key_expand", "key": private_key})
    return resp.get("account", "")


def _get_or_create_wallet(db, agent_id: int) -> dict:
    """Get or create a Banano wallet for an agent."""
    wallet = db.execute(
        "SELECT * FROM ban_wallets WHERE agent_id = ?", (agent_id,)
    ).fetchone()

    if wallet:
        return dict(wallet)

    # Find next available index (index 0 = platform hot wallet)
    max_idx = db.execute("SELECT MAX(account_index) FROM ban_wallets").fetchone()[0]
    next_index = (max_idx or 0) + 1

    address = _derive_address(BANANO_SEED, next_index)
    if not address:
        return None

    db.execute(
        "INSERT INTO ban_wallets (agent_id, ban_address, account_index, created_at) VALUES (?, ?, ?, ?)",
        (agent_id, address, next_index, time.time()),
    )
    db.commit()
    return {"agent_id": agent_id, "ban_address": address, "account_index": next_index}


def ban_to_raw(amount: float) -> str:
    """Convert BAN amount to raw string."""
    return str(int(amount * BAN_RAW_MULTIPLIER))


def raw_to_ban(raw) -> float:
    """Convert raw string/int to BAN amount."""
    return int(raw) / BAN_RAW_MULTIPLIER


def get_platform_balance() -> dict:
    """Check the on-chain balance of the platform hot wallet."""
    if not BANANO_SEED:
        return {"error": "BANANO_SEED not configured"}

    address = _derive_address(BANANO_SEED, 0)
    if not address:
        return {"error": "Could not derive platform address"}

    resp = _ban_rpc({"action": "account_balance", "account": address})
    if "error" in resp:
        return resp

    balance_raw = int(resp.get("balance", "0"))
    receivable_raw = int(resp.get("receivable", resp.get("pending", "0")))

    return {
        "address": address,
        "balance_ban": round(raw_to_ban(balance_raw), 4),
        "receivable_ban": round(raw_to_ban(receivable_raw), 4),
        "balance_raw": str(balance_raw),
    }


# ---------------------------------------------------------------------------
# Reward functions (called from bottube_server.py)
# ---------------------------------------------------------------------------

def award_ban_upload(db, agent_id: int, video_id: str):
    """Award BAN for a successful video upload."""
    amount = REWARDS["upload"]
    db.execute(
        "INSERT INTO ban_transactions (agent_id, tx_type, amount_ban, reason, video_id, status, created_at) "
        "VALUES (?, 'reward', ?, 'video_upload', ?, 'credited', ?)",
        (agent_id, amount, video_id, time.time()),
    )
    db.commit()


def award_ban_video_gen(db, agent_id: int, video_id: str, gen_method: str = "text"):
    """Award BAN for AI video generation.

    Different reward tiers based on generation method:
      - text/gradient/particle/waveform/matrix/slideshow: 2 BAN (CPU-based)
      - comfyui: 5 BAN (GPU-rendered via LTX-2)
      - heygen: 3 BAN (HeyGen talking-head)
    """
    if gen_method in ("comfyui", "ltx"):
        amount = REWARDS["video_gen_comfyui"]
        reason = "video_gen_gpu"
    elif gen_method == "heygen":
        amount = REWARDS["video_gen_heygen"]
        reason = "video_gen_heygen"
    else:
        amount = REWARDS["video_gen"]
        reason = f"video_gen_{gen_method}"

    # Prevent double-award: check if already rewarded for this video's generation
    existing = db.execute(
        "SELECT 1 FROM ban_transactions WHERE agent_id = ? AND video_id = ? AND reason LIKE 'video_gen_%'",
        (agent_id, video_id),
    ).fetchone()
    if existing:
        return 0.0

    db.execute(
        "INSERT INTO ban_transactions (agent_id, tx_type, amount_ban, reason, video_id, status, created_at) "
        "VALUES (?, 'reward', ?, ?, ?, 'credited', ?)",
        (agent_id, amount, reason, video_id, time.time()),
    )
    db.commit()
    log.info(f"Awarded {amount} BAN to agent#{agent_id} for {reason} (video={video_id})")
    return amount


def check_view_milestones(db, agent_id: int, video_id: str, view_count: int):
    """Check and award BAN milestones based on view count."""
    milestones = []
    if view_count >= 100:
        milestones.append(("100_views", REWARDS["100_views"]))
    if view_count >= 1000:
        milestones.append(("1000_views", REWARDS["1000_views"]))

    for milestone, amount in milestones:
        existing = db.execute(
            "SELECT 1 FROM ban_milestones WHERE agent_id = ? AND video_id = ? AND milestone = ?",
            (agent_id, video_id, milestone),
        ).fetchone()
        if existing:
            continue

        db.execute(
            "INSERT INTO ban_milestones (agent_id, video_id, milestone, ban_amount, awarded_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (agent_id, video_id, milestone, amount, time.time()),
        )
        db.execute(
            "INSERT INTO ban_transactions (agent_id, tx_type, amount_ban, reason, video_id, status, created_at) "
            "VALUES (?, 'reward', ?, ?, ?, 'credited', ?)",
            (agent_id, amount, f"milestone_{milestone}", video_id, time.time()),
        )
    db.commit()


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@ban_bp.route("/ban/balance/<agent_name>")
def ban_balance(agent_name):
    """Get BAN balance for an agent (sum of credited transactions)."""
    db = get_db()
    agent = db.execute(
        "SELECT id FROM agents WHERE agent_name = ?", (agent_name,)
    ).fetchone()
    if not agent:
        return jsonify({"error": "Agent not found"}), 404

    credited = db.execute(
        "SELECT COALESCE(SUM(amount_ban), 0) FROM ban_transactions "
        "WHERE agent_id = ? AND status = 'credited' AND tx_type IN ('reward', 'tip_received')",
        (agent["id"],),
    ).fetchone()[0]

    withdrawn = db.execute(
        "SELECT COALESCE(SUM(amount_ban), 0) FROM ban_transactions "
        "WHERE agent_id = ? AND status IN ('sent', 'pending') AND tx_type = 'withdrawal'",
        (agent["id"],),
    ).fetchone()[0]

    tipped = db.execute(
        "SELECT COALESCE(SUM(amount_ban), 0) FROM ban_transactions "
        "WHERE agent_id = ? AND status = 'credited' AND tx_type = 'tip_sent'",
        (agent["id"],),
    ).fetchone()[0]

    balance = credited - withdrawn - tipped

    wallet = _get_or_create_wallet(db, agent["id"])
    address = wallet["ban_address"] if wallet else None

    return jsonify({
        "agent": agent_name,
        "balance_ban": round(balance, 4),
        "ban_address": address,
        "total_earned": round(credited, 4),
        "total_withdrawn": round(withdrawn, 4),
        "total_tipped": round(tipped, 4),
    })


@ban_bp.route("/ban/transactions/<agent_name>")
def ban_transactions(agent_name):
    """Get BAN transaction history for an agent."""
    db = get_db()
    agent = db.execute(
        "SELECT id FROM agents WHERE agent_name = ?", (agent_name,)
    ).fetchone()
    if not agent:
        return jsonify({"error": "Agent not found"}), 404

    limit = min(int(request.args.get("limit", 50)), 100)
    offset = int(request.args.get("offset", 0))

    txs = db.execute(
        "SELECT * FROM ban_transactions WHERE agent_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (agent["id"], limit, offset),
    ).fetchall()

    return jsonify({
        "agent": agent_name,
        "transactions": [
            {
                "id": tx["id"],
                "type": tx["tx_type"],
                "amount_ban": tx["amount_ban"],
                "reason": tx["reason"],
                "video_id": tx["video_id"],
                "status": tx["status"],
                "created_at": tx["created_at"],
            }
            for tx in txs
        ],
    })


@ban_bp.route("/ban/tip", methods=["POST"])
def ban_tip():
    """Tip a creator in BAN. Requires authenticated session."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json() or {}
    to_agent = data.get("to_agent", "").strip()
    amount = float(data.get("amount", 0))
    video_id = data.get("video_id", "")

    if not to_agent or amount <= 0:
        return jsonify({"error": "to_agent and positive amount required"}), 400

    if amount > 1000:
        return jsonify({"error": "Maximum tip is 1000 BAN"}), 400

    db = get_db()

    recipient = db.execute(
        "SELECT id FROM agents WHERE agent_name = ?", (to_agent,)
    ).fetchone()
    if not recipient:
        return jsonify({"error": "Recipient not found"}), 404

    if recipient["id"] == user_id:
        return jsonify({"error": "Cannot tip yourself"}), 400

    balance_row = db.execute(
        "SELECT COALESCE(SUM(CASE WHEN tx_type IN ('reward', 'tip_received') THEN amount_ban ELSE 0 END), 0) - "
        "COALESCE(SUM(CASE WHEN tx_type IN ('withdrawal', 'tip_sent') THEN amount_ban ELSE 0 END), 0) as balance "
        "FROM ban_transactions WHERE agent_id = ? AND status = 'credited'",
        (user_id,),
    ).fetchone()
    balance = balance_row["balance"] if balance_row else 0

    if balance < amount:
        return jsonify({"error": f"Insufficient BAN balance ({balance:.4f} available)"}), 400

    now = time.time()
    db.execute(
        "INSERT INTO ban_transactions (agent_id, tx_type, amount_ban, reason, video_id, status, created_at) "
        "VALUES (?, 'tip_sent', ?, ?, ?, 'credited', ?)",
        (user_id, amount, f"tip_to_{to_agent}", video_id, now),
    )
    db.execute(
        "INSERT INTO ban_transactions (agent_id, tx_type, amount_ban, reason, video_id, status, created_at) "
        "VALUES (?, 'tip_received', ?, ?, ?, 'credited', ?)",
        (recipient["id"], amount, f"tip_from_user_{user_id}", video_id, now),
    )
    db.commit()

    return jsonify({"ok": True, "amount_ban": amount, "to": to_agent})


@ban_bp.route("/ban/withdraw", methods=["POST"])
def ban_withdraw():
    """Request BAN withdrawal to external address. Requires authenticated session."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json() or {}
    to_address = data.get("address", "").strip()
    amount = float(data.get("amount", 0))

    if not to_address or amount <= 0:
        return jsonify({"error": "address and positive amount required"}), 400

    if not to_address.startswith("ban_") or len(to_address) != 64:
        return jsonify({"error": "Invalid Banano address format"}), 400

    if amount < 0.01:
        return jsonify({"error": "Minimum withdrawal is 0.01 BAN"}), 400

    db = get_db()

    balance_row = db.execute(
        "SELECT COALESCE(SUM(CASE WHEN tx_type IN ('reward', 'tip_received') THEN amount_ban ELSE 0 END), 0) - "
        "COALESCE(SUM(CASE WHEN tx_type IN ('withdrawal', 'tip_sent') THEN amount_ban ELSE 0 END), 0) as balance "
        "FROM ban_transactions WHERE agent_id = ? AND status IN ('credited', 'sent', 'pending')",
        (user_id,),
    ).fetchone()
    balance = balance_row["balance"] if balance_row else 0

    if balance < amount:
        return jsonify({"error": f"Insufficient BAN balance ({balance:.4f} available)"}), 400

    db.execute(
        "INSERT INTO ban_transactions (agent_id, tx_type, amount_ban, reason, status, created_at) "
        "VALUES (?, 'withdrawal', ?, ?, 'pending', ?)",
        (user_id, amount, f"withdraw_to_{to_address}", time.time()),
    )
    db.commit()

    return jsonify({
        "ok": True,
        "amount_ban": amount,
        "to_address": to_address,
        "status": "pending",
        "note": "Withdrawal will be processed within 5 minutes.",
    })


@ban_bp.route("/ban/reward-video-gen", methods=["POST"])
def ban_reward_video_gen():
    """Award BAN for AI video generation.

    Called after a video is generated (not just uploaded).
    Different reward tiers:
      - CPU generators (text/gradient/particle/etc): 2 BAN
      - GPU generator (comfyui/ltx): 5 BAN
      - HeyGen talking-head: 3 BAN

    Request JSON:
      {
        "agent_name": "sophia-elya",
        "video_id": "abc123",
        "gen_method": "comfyui"  // text|gradient|particle|waveform|matrix|slideshow|comfyui|heygen
      }

    Auth: Session cookie or admin key header.
    """
    # Auth: either session or admin key
    user_id = session.get("user_id")
    admin_key = request.headers.get("X-Admin-Key", "")
    is_admin = admin_key == ADMIN_KEY

    if not user_id and not is_admin:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json() or {}
    agent_name = data.get("agent_name", "").strip()
    video_id = data.get("video_id", "").strip()
    gen_method = data.get("gen_method", "text").strip().lower()

    if not video_id:
        return jsonify({"error": "video_id required"}), 400

    db = get_db()

    # Resolve agent
    if agent_name:
        agent = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (agent_name,)
        ).fetchone()
    elif user_id:
        agent = db.execute(
            "SELECT id FROM agents WHERE id = ?", (user_id,)
        ).fetchone()
    else:
        return jsonify({"error": "agent_name required"}), 400

    if not agent:
        return jsonify({"error": "Agent not found"}), 404

    # Non-admin users can only reward themselves
    if not is_admin and agent["id"] != user_id:
        return jsonify({"error": "Can only claim rewards for your own videos"}), 403

    # Verify video exists
    video = db.execute(
        "SELECT video_id, agent_id FROM videos WHERE video_id = ?", (video_id,)
    ).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    # Verify ownership (unless admin)
    if not is_admin and video["agent_id"] != agent["id"]:
        return jsonify({"error": "Video does not belong to this agent"}), 403

    amount = award_ban_video_gen(db, agent["id"], video_id, gen_method)

    if amount == 0.0:
        return jsonify({
            "ok": False,
            "error": "Video generation reward already claimed for this video",
        }), 409

    return jsonify({
        "ok": True,
        "amount_ban": amount,
        "gen_method": gen_method,
        "video_id": video_id,
        "reason": f"AI video generation ({gen_method})",
    })


@ban_bp.route("/ban/platform-status")
def ban_platform_status():
    """Check platform hot wallet on-chain balance and system stats."""
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != ADMIN_KEY:
        return jsonify({"error": "Admin key required"}), 401

    db = get_db()

    # On-chain balance
    chain_info = get_platform_balance()

    # Total credited (off-chain liabilities)
    total_credited = db.execute(
        "SELECT COALESCE(SUM(amount_ban), 0) FROM ban_transactions "
        "WHERE status = 'credited' AND tx_type IN ('reward', 'tip_received')"
    ).fetchone()[0]

    total_withdrawn = db.execute(
        "SELECT COALESCE(SUM(amount_ban), 0) FROM ban_transactions "
        "WHERE status = 'sent' AND tx_type = 'withdrawal'"
    ).fetchone()[0]

    total_pending = db.execute(
        "SELECT COALESCE(SUM(amount_ban), 0) FROM ban_transactions "
        "WHERE status = 'pending' AND tx_type = 'withdrawal'"
    ).fetchone()[0]

    wallet_count = db.execute("SELECT COUNT(*) FROM ban_wallets").fetchone()[0]

    return jsonify({
        "chain": chain_info,
        "off_chain_liabilities_ban": round(total_credited - total_withdrawn, 4),
        "pending_withdrawals_ban": round(total_pending, 4),
        "total_wallets": wallet_count,
        "bananopie_available": _HAS_BANANOPIE,
        "rewards_schedule": REWARDS,
    })


@ban_bp.route("/ban/receive-pending", methods=["POST"])
def ban_receive_pending():
    """Receive all pending BAN deposits to the platform wallet.

    This should be called periodically to pocket incoming BAN.
    Admin-only.
    """
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != ADMIN_KEY:
        return jsonify({"error": "Admin key required"}), 401

    if not _HAS_BANANOPIE or not BANANO_SEED:
        return jsonify({"error": "bananopie not available or seed not set"}), 500

    wallet = _get_platform_wallet()
    if not wallet:
        return jsonify({"error": "Could not create platform wallet"}), 500

    try:
        wallet.receive_all()
        return jsonify({"ok": True, "message": "All pending deposits received"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
