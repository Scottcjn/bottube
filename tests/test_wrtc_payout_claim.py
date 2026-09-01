# SPDX-License-Identifier: MIT
"""Regression proof for Solana wRTC payout admission."""

import sqlite3

import wrtc_bridge


def test_only_one_worker_can_claim_a_pending_withdrawal():
    db = sqlite3.connect(":memory:")
    db.executescript(wrtc_bridge.WRTC_SCHEMA)
    db.execute(
        """
        INSERT INTO wrtc_withdrawals
            (agent_id, amount_wrtc, fee_wrtc, net_wrtc, to_address, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """,
        (1, 10.0, 0.5, 9.5, "11111111111111111111111111111111", 1.0),
    )
    withdrawal_id = db.execute("SELECT id FROM wrtc_withdrawals").fetchone()[0]

    assert wrtc_bridge._claim_wrtc_withdrawal(db, withdrawal_id) is True
    assert wrtc_bridge._claim_wrtc_withdrawal(db, withdrawal_id) is False
    assert db.execute(
        "SELECT status FROM wrtc_withdrawals WHERE id = ?", (withdrawal_id,)
    ).fetchone()[0] == "processing"
