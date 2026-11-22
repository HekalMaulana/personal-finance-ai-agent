"""Correction tests against isolated fictional databases."""

import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from typing import Any

from finance_storage import CashFlow, IdempotencyConflict, StaleVersion, TransactionStore


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / "data"
        root.mkdir(exist_ok=True)
        directory = self.enterContext(TemporaryDirectory(prefix=".correction-test-", dir=root))
        self.path = Path(directory) / "ledger.db"
        self.store = TransactionStore(self.path)
        self.original = self.store.add_transaction(
            transaction_type="expense", amount_rupiah=250_000, category="Makanan",
            description="Makan siang simulasi", occurred_at="2026-11-02T12:00:00+07:00",
            idempotency_key="fixture-add",
        )

    def correct(self, *, key: Any = "fixture-correct", version: Any = 0,
                changes: Any = None, reason: Any = "Salah input"):
        return self.store.correct_transaction(
            self.original.id, expected_version=version, idempotency_key=key,
            changes={"amount_rupiah": 25_000} if changes is None else changes, reason=reason,
        )

    def test_effective_amount_and_persistent_audit(self):
        self.assertEqual(self.store.cash_flow(), CashFlow(0, 250_000, -250_000, 1))
        revision = self.correct()
        self.assertEqual((revision.before.amount_rupiah, revision.after.amount_rupiah), (250_000, 25_000))
        self.assertEqual(revision.version, 1)
        self.assertEqual(revision.reason, "Salah input")
        self.assertTrue(revision.corrected_at.endswith("+07:00"))
        self.assertEqual(self.store.cash_flow(), CashFlow(0, 25_000, -25_000, 1))
        reopened = TransactionStore(self.path, read_only=True)
        self.assertEqual(reopened.get_transaction(self.original.id), revision.after)
        self.assertEqual(reopened.get_versioned_transaction(self.original.id), (revision.after, 1))
        self.assertEqual(reopened.list_transactions(), [revision.after])
        history = reopened.transaction_history(self.original.id)
        self.assertEqual(history, (self.original, [revision]))

    def test_retry_even_after_later_revision_and_conflicting_payload(self):
        first = self.correct()
        second = self.correct(key="second", version=1, changes={"category": "Konsumsi"})
        self.assertNotEqual(first.operation_id, second.operation_id)
        self.assertEqual(second.before, first.after)
        self.assertEqual(self.correct(), first)
        for kwargs in ({"changes": {"amount_rupiah": 50_000}}, {"reason": "Berbeda"}, {"version": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(IdempotencyConflict):
                self.correct(**kwargs)
        self.assertEqual(self.store.transaction_history(self.original.id), (self.original, [first, second]))

    def test_type_time_category_and_description_use_only_effective_values(self):
        revised = self.correct(changes={"transaction_type": "income", "category": "Lainnya",
                                        "occurred_at": "2026-11-02T17:00:00Z", "description": None})
        self.assertIsNone(revised.after.description)
        self.assertEqual(revised.after.category, "Lainnya")
        self.assertEqual(self.store.list_transactions(transaction_type="expense"), [])
        self.assertEqual(self.store.list_transactions(end_date="2026-11-02"), [])
        self.assertEqual(self.store.list_transactions(start_date="2026-11-03", transaction_type="income"), [revised.after])
        self.assertEqual(self.store.cash_flow(start_date="2026-11-03"), CashFlow(250_000, 0, 250_000, 1))

    def test_concurrent_writers_with_same_version(self):
        barrier = Barrier(2)

        def run(index):
            barrier.wait(timeout=5)
            try:
                return self.correct(key=f"parallel-{index}")
            except StaleVersion:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(len(self.store.transaction_history(self.original.id)[1]), 1)
        self.assertEqual(self.store.cash_flow().total_expense, 25_000)

    def test_invalid_and_stale_requests_and_rollback_on_database_failure(self):
        for kwargs in ({"version": True}, {"version": -1}, {"reason": " "}, {"key": " "}, {"changes": []},
                       {"changes": {}}, {"changes": {"amount_rupiah": 0}}, {"changes": {"category": None}},
                       {"changes": {"occurred_at": "tomorrow"}}, {"changes": {"transaction_type": "transfer"}},
                       {"changes": {"id": "ignored"}}, {"changes": {"amount_rupiah": 250_000}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.correct(**kwargs)
        with self.assertRaises(StaleVersion):
            self.correct(version=1)
        with closing(sqlite3.connect(self.path, autocommit=True)) as conn:
            conn.execute("""CREATE TRIGGER testing_abort AFTER INSERT ON transaction_corrections
                          BEGIN SELECT RAISE(FAIL, 'simulated write failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.correct()
        self.assertEqual(self.store.transaction_history(self.original.id), (self.original, []))
        self.assertEqual(self.store.cash_flow(), CashFlow(0, 250_000, -250_000, 1))
        with closing(sqlite3.connect(self.path, autocommit=True)) as conn:
            conn.execute("DROP TRIGGER testing_abort")
        self.assertEqual(self.correct().version, 1)

    def test_legacy_read_does_not_migrate_and_first_correction_is_additive(self):
        with closing(sqlite3.connect(self.path, autocommit=True)) as conn:
            conn.execute("DROP TABLE transaction_corrections")
        before = self.path.read_bytes()
        old = TransactionStore(self.path, read_only=True)
        self.assertEqual(old.transaction_history(self.original.id), (self.original, []))
        self.assertEqual(old.get_versioned_transaction(self.original.id), (self.original, 0))
        self.assertEqual(old.cash_flow().total_expense, 250_000)
        self.assertEqual(self.path.read_bytes(), before)
        revised = self.correct()
        self.assertEqual(old.transaction_history(self.original.id), (self.original, [revised]))
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT amount_rupiah FROM transactions").fetchall(), [(250_000,)])

    def test_original_add_retry_is_unchanged_by_correction(self):
        self.correct()
        self.assertEqual(self.store.add_transaction(
            transaction_type="expense", amount_rupiah=250_000, category="Makanan",
            description="Makan siang simulasi", occurred_at=self.original.occurred_at,
            idempotency_key="fixture-add",
        ), self.original)
        self.assertEqual(self.store.get_transaction(self.original.id).amount_rupiah, 25_000)
