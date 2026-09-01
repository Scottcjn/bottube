"""BAN payout rows must cross the irreversible send edge at most once."""

import sqlite3

import banano_payout


def _schema(db):
    db.executescript(
        """
        CREATE TABLE ban_transactions (
            id INTEGER PRIMARY KEY,
            agent_id INTEGER NOT NULL,
            tx_type TEXT NOT NULL,
            amount_ban REAL NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            block_hash TEXT DEFAULT '',
            created_at REAL NOT NULL,
            processed_at REAL DEFAULT 0
        );
        CREATE TABLE ban_wallets (
            agent_id INTEGER PRIMARY KEY,
            account_index INTEGER NOT NULL
        );
        """
    )
    db.execute(
        "INSERT INTO ban_transactions "
        "(id, agent_id, tx_type, amount_ban, reason, status, created_at) "
        "VALUES (1, 7, 'withdrawal', 5, ?, 'pending', 1)",
        ("withdraw_to_ban_" + "a" * 60,),
    )
    db.execute("INSERT INTO ban_wallets VALUES (7, 1)")
    db.commit()


def test_only_one_worker_can_claim_a_pending_withdrawal(tmp_path):
    db_path = tmp_path / "bottube.db"
    with sqlite3.connect(db_path) as setup:
        _schema(setup)

    first = sqlite3.connect(db_path, timeout=10)
    second = sqlite3.connect(db_path, timeout=10)
    try:
        assert banano_payout._claim_withdrawal(first, 1) is True
        assert banano_payout._claim_withdrawal(second, 1) is False
    finally:
        first.close()
        second.close()

    with sqlite3.connect(db_path) as verify:
        assert verify.execute(
            "SELECT status FROM ban_transactions WHERE id = 1"
        ).fetchone()[0] == "processing"


def test_uncertain_send_is_quarantined_instead_of_replayed(tmp_path, monkeypatch):
    db_path = tmp_path / "bottube.db"
    with sqlite3.connect(db_path) as setup:
        _schema(setup)

    class FakeRPC:
        def __init__(self, _url):
            pass

        def get_account_balance(self, _address):
            return {"balance": str(100 * banano_payout.BAN_RAW_MULTIPLIER)}

    class FakeWallet:
        send_calls = 0

        def __init__(self, _rpc, seed, index):
            pass

        def get_address(self):
            return "ban_" + "b" * 60

        def receive_all(self):
            return None

        def send(self, _address, _amount):
            type(self).send_calls += 1
            raise TimeoutError("RPC outcome unknown")

    monkeypatch.setattr(banano_payout, "DB_PATH", str(db_path))
    monkeypatch.setattr(banano_payout, "BANANO_SEED", "00" * 32)
    monkeypatch.setattr(banano_payout, "HAS_BANANOPIE", True)
    monkeypatch.setattr(banano_payout, "BananoRPC", FakeRPC, raising=False)
    monkeypatch.setattr(banano_payout, "BananoWallet", FakeWallet, raising=False)
    monkeypatch.setattr(banano_payout.time, "sleep", lambda _seconds: None)

    banano_payout.process_withdrawals()
    banano_payout.process_withdrawals()

    assert FakeWallet.send_calls == 1
    with sqlite3.connect(db_path) as verify:
        status, processed_at = verify.execute(
            "SELECT status, processed_at FROM ban_transactions WHERE id = 1"
        ).fetchone()
    assert status == "uncertain"
    assert processed_at > 0
