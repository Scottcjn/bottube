import sqlite3
from pathlib import Path

import wrtc_bridge as wb


class _FakeG(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class _TimeoutRun:
    def __call__(self, *args, **kwargs):
        raise wb.subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 0))


def _make_db(tmp_path: Path):
    db_path = tmp_path / "bridge.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            rtc_balance REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE wrtc_withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            amount_wrtc REAL NOT NULL,
            fee_wrtc REAL NOT NULL,
            net_wrtc REAL NOT NULL,
            to_address TEXT NOT NULL,
            tx_signature TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL NOT NULL,
            completed_at REAL
        );
        INSERT INTO agents (id, rtc_balance) VALUES (1, 100.0);
        INSERT INTO wrtc_withdrawals (agent_id, amount_wrtc, fee_wrtc, net_wrtc, to_address, status, created_at)
        VALUES (1, 10.0, 0.5, 9.5, 'Ct8Aqbq7u3C8PWVmtrrbi7eeQt6MvK1311BbqSVmKGHi', 'pending', 1);
        UPDATE agents SET rtc_balance = rtc_balance - 10.0 WHERE id = 1;
        """
    )
    conn.commit()
    return conn


def test_process_withdrawals_refunds_timeout(monkeypatch, tmp_path):
    conn = _make_db(tmp_path)
    fake_g = _FakeG(db=conn)
    monkeypatch.setattr(wb, 'g', fake_g)
    monkeypatch.setattr(wb, '_is_admin', lambda: True)
    monkeypatch.setattr(wb, 'jsonify', lambda payload: payload)
    monkeypatch.setattr(wb.subprocess, 'run', _TimeoutRun())

    payload = wb.process_withdrawals()
    body = payload[0] if isinstance(payload, tuple) else payload
    assert body['processed'] == 1
    assert body['results'][0]['ok'] is False
    assert body['results'][0]['error'] == 'Timeout'

    status = conn.execute('SELECT status FROM wrtc_withdrawals WHERE id = 1').fetchone()[0]
    balance = conn.execute('SELECT rtc_balance FROM agents WHERE id = 1').fetchone()[0]
    assert status == 'failed'
    assert balance == 100.0
