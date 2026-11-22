"""Exercise the CLI as separate processes against fictional ledgers only."""

import ast
import hashlib
import json
import sqlite3
import subprocess
import sys
import unittest
from contextlib import closing
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "finance_cli.py"
INCOME = dict(transaction_type="income", amount_rupiah=5_000_000,
              category="Gaji", occurred_at="2026-11-01T08:00:00+07:00",
              idempotency_key="fixture-income")
EXPENSE = dict(transaction_type="expense", amount_rupiah=25_000,
               category="Makanan", description="Makan siang simulasi",
               occurred_at="2026-11-01T12:00:00+07:00", idempotency_key="fixture-expense")


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = "test-" + uuid4().hex
        self.db = ROOT / "data" / "finance-cli" / (self.ledger + ".db")
        self.addCleanup(self.db.unlink, missing_ok=True)

    def invoke(self, operation: str, payload=None, *, raw=None, ledger=None):
        args = [sys.executable, "-B", str(CLI), "--ledger", ledger or self.ledger, operation]
        result = subprocess.run(args, input=raw if raw is not None else json.dumps(payload if payload is not None else {}).encode(),
                                capture_output=True, cwd=ROOT, shell=False, timeout=15)
        self.assertEqual(result.stderr, b"", result)
        response = json.loads(result.stdout)
        self.assertEqual(response["ok"], result.returncode == 0, response)
        return result.returncode, response

    def added(self, payload):
        status, result = self.invoke("add", payload)
        self.assertEqual(status, 0, result)
        return result["data"]

    def test_add_get_and_read_persistence_in_new_process(self) -> None:
        row = self.added(EXPENSE)
        self.assertEqual(row["amount_rupiah"], 25_000)
        self.assertEqual(row["category"], "Makanan")
        self.assertTrue(row["occurred_at"].endswith("+07:00"))
        self.assertEqual(self.invoke("get", {"id": row["id"]})[1]["data"], row)
        with closing(sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True)) as conn:
            self.assertEqual(conn.execute("SELECT id FROM transactions").fetchall(), [(row["id"],)])

    def test_list_and_summary_read_existing_ledger_without_changing_it(self) -> None:
        income, expense = self.added(INCOME), self.added(EXPENSE)
        before = (hashlib.sha256(self.db.read_bytes()).digest(), self.db.stat().st_mtime_ns)
        self.assertEqual(self.invoke("list")[1]["data"], [income, expense])
        self.assertEqual(self.invoke("list", {"transaction_type": "expense", "start_date": "2026-11-01",
                                              "end_date": "2026-11-01"})[1]["data"], [expense])
        self.assertEqual(self.invoke("summary")[1]["data"], dict(total_income=5_000_000, total_expense=25_000,
                                                               net_cash_flow=4_975_000, transaction_count=2))
        self.assertEqual(self.invoke("summary", {"start_date": "2026-11-02"})[1]["data"]["transaction_count"], 0)
        self.assertEqual((hashlib.sha256(self.db.read_bytes()).digest(), self.db.stat().st_mtime_ns), before)

    def test_read_missing_database_does_not_create_it(self) -> None:
        for operation, args in (("list", {}), ("summary", {}), ("get", {"id": str(uuid4())})):
            with self.subTest(operation=operation):
                status, result = self.invoke(operation, args)
                self.assertEqual((status, result["error"]["code"]), (4, "database_not_found"))
        self.assertFalse(self.db.exists())

    def test_unknown_transaction(self) -> None:
        self.added(INCOME)
        status, result = self.invoke("get", {"id": str(uuid4())})
        self.assertEqual((status, result["error"]["code"]), (4, "transaction_not_found"))

    def test_invalid_input_is_json_error(self) -> None:
        for operation, payload, raw in (
            ("add", {**INCOME, "amount_rupiah": 0}, None), ("add", {**INCOME, "amount_rupiah": True}, None),
            ("add", {**INCOME, "category": " "}, None), ("add", {**INCOME, "occurred_at": "tomorrow"}, None),
            ("add", {**INCOME, "transaction_type": "transfer"}, None), ("add", {}, None),
            ("list", {"sql": "SELECT 1"}, None), ("remove", {}, None),
            ("list", None, b"[]"), ("list", None, b"not json"),
            ("list", None, b'{"start_date":null,"start_date":"2026-11-01"}'),
            ("summary", None, b"\xff"), ("summary", None, b" " * 8193),
        ):
            with self.subTest(operation=operation, payload=payload, raw=bool(raw)):
                status, result = self.invoke(operation, payload, raw=raw)
                self.assertEqual((status, result["error"]["code"]), (2, "invalid_input"))
        self.assertFalse(self.db.exists())
        self.assertEqual(self.invoke("summary", ledger="../finance")[0], 2)

    def test_retry_and_conflict(self) -> None:
        first = self.added(INCOME)
        self.assertEqual(self.added(INCOME), first)
        status, result = self.invoke("add", {**INCOME, "amount_rupiah": 12})
        self.assertEqual((status, result["error"]["code"]), (3, "idempotency_conflict"))
        self.assertEqual(self.invoke("list")[1]["data"], [first])

    def test_text_with_shell_and_sql_punctuation_round_trips_literally(self) -> None:
        text = "Paket 'A'; $() `contoh` & | < > \"simulasi\""
        row = self.added({**EXPENSE, "description": text})
        self.assertEqual(self.invoke("get", {"id": row["id"]})[1]["data"]["description"], text)
        self.assertEqual(self.invoke("summary")[1]["data"]["transaction_count"], 1)
        tree = ast.parse(CLI.read_text(encoding="utf-8"))
        self.assertFalse(any(isinstance(node, ast.Name) and node.id in {"eval", "exec", "__import__"}
                             or isinstance(node, ast.Attribute) and node.attr in {"system", "popen", "execute", "executescript"}
                             or isinstance(node, ast.alias) and node.name.split(".")[0] in {"subprocess", "ctypes", "importlib"}
                             for node in ast.walk(tree)))

    def test_invalid_database_has_structured_error(self) -> None:
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self.db.write_bytes(b"not SQLite; fictional test fixture")
        status, result = self.invoke("summary")
        self.assertEqual((status, result["error"]["code"]), (5, "storage_error"))
        self.assertEqual(self.db.read_bytes(), b"not SQLite; fictional test fixture")
