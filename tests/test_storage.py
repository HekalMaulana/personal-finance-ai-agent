"""Integration tests using only fictional transactions and isolated SQLite files."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest

from finance_storage import CashFlow, IdempotencyConflict, TransactionStore


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[1] / "data"
        root.mkdir(exist_ok=True)
        directory = self.enterContext(TemporaryDirectory(prefix=".lesson3-test-", dir=root))
        self.path = Path(directory) / "finance-test.db"
        self.store = TransactionStore(self.path)

    def add(self, **overrides):
        data = {
            "transaction_type": "income",
            "amount_rupiah": 5_000_000,
            "category": "Gaji",
            "description": "Gaji simulasi",
            "occurred_at": "2026-11-01T08:00:00+07:00",
            "idempotency_key": "sim-income",
        }
        data.update(overrides)
        return self.store.add_transaction(**data)

    def test_fictional_fixture_totals_and_unique_ids(self) -> None:
        income = self.add()
        lunch = self.add(transaction_type="expense", amount_rupiah=25_000,
                         category="Makanan", description="Makan siang simulasi",
                         occurred_at="2026-11-01T12:00:00+07:00", idempotency_key="sim-lunch")
        transport = self.add(transaction_type="expense", amount_rupiah=150_000,
                             category="Transportasi", description="Transportasi simulasi",
                             occurred_at="2026-11-01T18:00:00+07:00", idempotency_key="sim-ride")
        self.assertEqual(len({income.id, lunch.id, transport.id}), 3)
        self.assertEqual(self.store.list_transactions(), [income, lunch, transport])
        self.assertEqual(self.store.cash_flow(), CashFlow(5_000_000, 175_000, 4_825_000, 3))
        self.assertEqual(self.store.cash_flow(start_date="2026-11-02"), CashFlow(0, 0, 0, 0))

    def test_lookup_after_reopening_database(self) -> None:
        saved = self.add()
        del self.store
        self.assertGreater(self.path.stat().st_size, 0)
        reopened = TransactionStore(self.path)
        self.assertEqual(reopened.get_transaction(saved.id), saved)
        self.assertIsNone(reopened.get_transaction("00000000-0000-0000-0000-000000000000"))
        self.assertEqual(reopened.cash_flow(), CashFlow(5_000_000, 0, 5_000_000, 1))

    def test_amounts_must_be_positive_sqlite_integers(self) -> None:
        for invalid in (-1, 0, True, 1.0, "100", 2**63):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.add(amount_rupiah=invalid)
        self.assertEqual(self.store.list_transactions(), [])

    def test_unknown_type_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "income.*expense"):
            self.add(transaction_type="transfer")
        with self.assertRaises(ValueError):
            self.store.list_transactions(transaction_type="transfer")
        self.assertEqual(self.store.list_transactions(), [])

    def test_invalid_text_or_dates_are_rejected(self) -> None:
        for overrides in ({"category": " "}, {"category": "x" * 101}, {"category": None},
                          {"description": 7}, {"description": "\0"}, {"description": "\ud800"},
                          {"idempotency_key": " "}, {"idempotency_key": " sim-income"},
                          {"occurred_at": "2026-02-30T12:00:00+07:00"},
                          {"occurred_at": "2026-11-01T12:00:00"},
                          {"occurred_at": "2026-11-01T12:00:00+00:60"},
                          {"occurred_at": "9999-12-31T23:00:00Z"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.add(**overrides)
        for bounds in ({"start_date": "2026-02-30"}, {"end_date": "20261101"},
                       {"start_date": "2026-11-02", "end_date": "2026-11-01"}):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                self.store.cash_flow(**bounds)
        with self.assertRaises(ValueError):
            self.store.get_transaction("not-a-uuid")
        self.assertEqual(self.store.list_transactions(), [])

    def test_identical_retry_returns_original_with_no_duplicate(self) -> None:
        original = self.add()
        retry = self.add(occurred_at="2026-11-01T01:00:00Z")
        self.assertEqual(retry, original)
        self.assertEqual(self.store.list_transactions(), [original])

    def test_conflicting_retry_does_not_modify_original(self) -> None:
        original = self.add()
        with self.assertRaisesRegex(IdempotencyConflict, "Konflik.*idempotency key"):
            self.add(amount_rupiah=42)
        self.assertEqual(self.store.list_transactions(), [original])

    def test_concurrent_identical_retries_insert_only_one_row(self) -> None:
        gate = Barrier(2)

        def write():
            gate.wait(timeout=10)
            return self.add()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(lambda _: write(), range(2)))
        self.assertEqual(first, second)
        self.assertEqual(self.store.list_transactions(), [first])

    def test_local_day_includes_first_and_last_microsecond(self) -> None:
        def at(value: str, key: str, kind: str = "expense"):
            return self.add(occurred_at=value, idempotency_key=key,
                            transaction_type=kind, amount_rupiah=1, description=None)

        at("2026-10-31T16:59:59.999999Z", "before")
        start = at("2026-10-31T17:00:00Z", "midnight", "income")
        end = at("2026-11-01T16:59:59.999999Z", "end")
        at("2026-11-01T17:00:00Z", "after")
        self.assertEqual(start.occurred_at, "2026-11-01T00:00:00.000000+07:00")
        self.assertEqual(end.occurred_at, "2026-11-01T23:59:59.999999+07:00")
        self.assertEqual(datetime.fromisoformat(start.recorded_at).utcoffset(), timedelta(hours=7))
        self.assertIsNone(start.description)
        day = {"start_date": "2026-11-01", "end_date": "2026-11-01"}
        self.assertEqual(self.store.list_transactions(**day), [start, end])
        self.assertEqual(self.store.list_transactions(**day, transaction_type="expense"), [end])
        self.assertEqual(self.store.cash_flow(**day), CashFlow(1, 1, 0, 2))

    def test_punctuation_round_trips_as_text(self) -> None:
        description = "Makan di 'Warung'; paket A — simulasi"
        row = self.add(description=description)
        found = self.store.get_transaction(row.id)
        assert found is not None
        self.assertEqual(found.description, description)
        self.assertEqual(len(self.store.list_transactions()), 1)

    def test_totals_above_sqlite_integer_limit_use_python_integers(self) -> None:
        maximum = 2**63 - 1
        self.add(amount_rupiah=maximum)
        self.add(amount_rupiah=maximum, idempotency_key="sim-max-2")
        self.assertEqual(self.store.cash_flow(), CashFlow(2 * maximum, 0, 2 * maximum, 2))
