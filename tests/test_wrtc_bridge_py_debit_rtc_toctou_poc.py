# SPDX-License-Identifier: MIT
"""Regression test for the TOCTOU race in wrtc_bridge.py's ``_debit_rtc``
(bottube#1620, follow-up).

``ergo_bridge_blueprint.py`` had this exact bug and it was fixed in #1711 by
moving the balance comparison into the ``UPDATE ... WHERE rtc_balance >= ?``
clause so read-and-write become one atomic statement (see
``tests/test_rtc_debit_balance_guard.py::test_guarded_update_is_atomic_against_a_stale_read``,
whose two-connection pattern this test mirrors). ``wrtc_bridge.py`` kept its
own separate copy of ``_debit_rtc`` with the original check-then-update shape
(a SELECT to check the balance, then an unconditional UPDATE) -- flagged by
@Scottcjn directly when closing #1636: "``_debit_rtc`` in
``wrtc_bridge.py:152`` still has the original check-then-update shape...
Same race, different file."

NOTE ON LIVE IMPACT: ``wrtc_bridge.py`` is not imported anywhere in the
current tree (grepped ``import wrtc_bridge`` / ``from wrtc_bridge import``
across every non-test .py file -- zero hits). The blueprint actually
registered by ``bottube_server.py`` as ``wrtc_bp`` comes from the
similarly-named ``wrtc_bridge_blueprint.py``, which already does the atomic
``UPDATE ... WHERE id = ? AND rtc_balance >= ?`` inline (no separate
``_debit_rtc`` helper) -- so the live withdrawal path is NOT vulnerable
today. Fixing this anyway because the maintainer asked for it directly and
an orphaned module carrying a known-bad pattern under the same function name
as a since-fixed sibling is a landmine for whoever next copies from it or
wires it in.

FAILS on unmodified ``wrtc_bridge.py``: two connections that both observe the
same starting balance (the classic TOCTOU window) both succeed at debiting
it, driving the balance negative.
PASSES with the fix: the comparison moves into the UPDATE's WHERE clause, so
only the first debit's statement actually matches a row; the second sees
``rowcount == 0`` / returns False and the balance never goes negative.
"""

import os
import sqlite3
import sys
import tempfile
import unittest

NODE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if NODE_DIR not in sys.path:
    sys.path.insert(0, NODE_DIR)

import wrtc_bridge  # noqa: E402


class TestWrtcBridgePyDebitRtcAtomic(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        setup = sqlite3.connect(self.path)
        setup.execute("CREATE TABLE agents (id INTEGER PRIMARY KEY, rtc_balance REAL)")
        setup.execute("INSERT INTO agents (id, rtc_balance) VALUES (1, 60.0)")
        setup.commit()
        setup.close()

        self.conn_a = sqlite3.connect(self.path, timeout=5)
        self.conn_a.row_factory = sqlite3.Row
        self.conn_b = sqlite3.connect(self.path, timeout=5)
        self.conn_b.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn_a.close()
        self.conn_b.close()
        os.unlink(self.path)

    def test_two_stale_readers_racing_for_the_same_balance_cannot_both_debit(self):
        # Both connections observe the same balance BEFORE either writes --
        # exactly the window two concurrent /wrtc/withdraw requests would hit.
        bal_a = self.conn_a.execute("SELECT rtc_balance FROM agents WHERE id=1").fetchone()["rtc_balance"]
        bal_b = self.conn_b.execute("SELECT rtc_balance FROM agents WHERE id=1").fetchone()["rtc_balance"]
        self.assertEqual(bal_a, 60.0)
        self.assertEqual(bal_b, 60.0)

        first_ok = wrtc_bridge._debit_rtc(self.conn_a, 1, 60.0)
        second_ok = wrtc_bridge._debit_rtc(self.conn_b, 1, 60.0)

        self.assertTrue(first_ok, "the first debit against the real balance must succeed")
        self.assertFalse(
            second_ok,
            "the second debit raced against a stale 60.0 read and must be rejected once "
            "the first debit already spent the funds -- not overdraw the account",
        )

        final = self.conn_b.execute("SELECT rtc_balance FROM agents WHERE id=1").fetchone()["rtc_balance"]
        self.assertGreaterEqual(final, 0.0, f"balance went negative ({final}) -- double-spend succeeded")
        self.assertEqual(final, 0.0)

    def test_sufficient_single_debit_still_succeeds(self):
        self.assertTrue(wrtc_bridge._debit_rtc(self.conn_a, 1, 60.0))
        final = self.conn_a.execute("SELECT rtc_balance FROM agents WHERE id=1").fetchone()["rtc_balance"]
        self.assertEqual(final, 0.0)

    def test_insufficient_balance_rejected_up_front(self):
        self.assertFalse(wrtc_bridge._debit_rtc(self.conn_a, 1, 999.0))
        final = self.conn_a.execute("SELECT rtc_balance FROM agents WHERE id=1").fetchone()["rtc_balance"]
        self.assertEqual(final, 60.0, "a rejected debit must not touch the balance")


if __name__ == "__main__":
    unittest.main()
