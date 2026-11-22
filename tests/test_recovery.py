"""Process-level recovery tests using disposable fictional ledgers only."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing

from test_finance_cli import CLI, EXPENSE, ROOT, CliTests
import unittest


class RecoveryTests(unittest.TestCase):
    setUp = CliTests.setUp
    invoke = CliTests.invoke

    def prepare(self, key="recovery-key"):
        code, reply = self.invoke("prepare-add", {**EXPENSE, "idempotency_key": key})
        self.assertEqual(code, 0, reply)
        return reply["data"]

    def rows(self):
        with closing(sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True)) as conn:
            return conn.execute("SELECT id, amount_rupiah FROM transactions").fetchall()

    def test_process_killed_after_commit_before_cli_confirmation(self):
        op = self.prepare()
        # Stop at the exact boundary after Store returns and before JSON output.
        script = """
import time
import finance_cli as cli
original_emit = cli._emit
def pause(status, **kwargs):
    if status == 0:
        print('committed-before-response', flush=True)
        time.sleep(30)
    return original_emit(status, **kwargs)
cli._emit = pause
raise SystemExit(cli.main())
"""
        with subprocess.Popen([sys.executable, "-B", "-c", script, "--ledger", self.ledger, "commit-add"],
                              cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) as child:
            assert child.stdin is not None and child.stdout is not None
            child.stdin.write(json.dumps({"operation_id": op["operation_id"]}).encode())
            child.stdin.close()
            try:
                # Read the synchronization marker with a bounded wait.
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=1) as pool:
                    try:
                        self.assertEqual(pool.submit(child.stdout.readline).result(timeout=10).strip(),
                                         b"committed-before-response")
                    finally:
                        child.kill()
                        child.wait(timeout=10)
                self.assertEqual(child.stdout.read(), b"")
            finally:
                if child.poll() is None:
                    child.kill()
        code, reply = self.invoke("operation-status", {"operation_id": op["operation_id"]})
        self.assertEqual(code, 0, reply)
        saved = reply["data"]
        self.assertEqual(saved["status"], "committed")
        self.assertEqual(self.invoke("operation-status", {"idempotency_key": "recovery-key"})[1]["data"], saved)
        self.assertEqual(self.invoke("commit-add", {"operation_id": op["operation_id"]})[1]["data"], saved)
        self.assertEqual(self.rows(), [(saved["transaction"]["id"], 25_000)])

    def test_failed_insert_does_not_lose_preparation(self):
        op = self.prepare()
        with closing(sqlite3.connect(self.db, autocommit=True)) as conn:
            conn.execute("""CREATE TRIGGER recovery_test_fault AFTER INSERT ON transactions
                          BEGIN SELECT RAISE(FAIL, 'synthetic write failure'); END""")
        code, reply = self.invoke("commit-add", {"operation_id": op["operation_id"]})
        self.assertEqual((code, reply["error"]["code"]), (5, "storage_error"))
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.invoke("operation-status", {"operation_id": op["operation_id"]})[1]["data"], op)
        with closing(sqlite3.connect(self.db, autocommit=True)) as conn:
            conn.execute("DROP TRIGGER recovery_test_fault")
        self.assertEqual(self.prepare(), op)
        code, reply = self.invoke("commit-add", {"operation_id": op["operation_id"]})
        self.assertEqual(code, 0, reply)
        self.assertEqual(len(self.rows()), 1)

    def test_identical_distinct_intents_are_candidates_not_duplicates(self):
        first, second = self.prepare("first-op"), self.prepare("second-op")
        self.assertNotEqual(first["operation_id"], second["operation_id"])
        for op in (first, second):
            self.assertEqual(self.invoke("commit-add", {"operation_id": op["operation_id"]})[0], 0)
        code, reply = self.invoke("find-add", {"amount_rupiah": 25_000, "category": "Makanan"})
        self.assertEqual(code, 0, reply)
        self.assertEqual(reply["data"]["match"], "multiple")
        self.assertEqual({c["operation_id"] for c in reply["data"]["candidates"]},
                         {first["operation_id"], second["operation_id"]})
        self.assertEqual(len(self.rows()), 2)

    def test_validation_and_legacy_key_interop(self):
        code, reply = self.invoke("add", EXPENSE)
        self.assertEqual(code, 0, reply)
        existing = reply["data"]
        data = self.invoke("operation-status", {"idempotency_key": EXPENSE["idempotency_key"]})[1]["data"]
        self.assertEqual((data["status"], data["operation_id"], data["transaction"]), ("committed", None, existing))
        op = self.prepare()
        self.assertEqual(self.invoke("add", {**EXPENSE, "idempotency_key": "recovery-key", "amount_rupiah": 1})[0], 3)
        self.assertEqual(self.invoke("prepare-add", {**EXPENSE, "idempotency_key": "recovery-key", "category": "Lain"})[0], 3)
        self.assertEqual(self.invoke("operation-status", {})[0], 2)
        self.assertEqual(self.invoke("operation-status", {"operation_id": None, "idempotency_key": "recovery-key"})[0], 2)
        self.assertEqual(self.invoke("find-add", {"amount_rupiah": False})[0], 2)
        code, reply = self.invoke("add", {**EXPENSE, "idempotency_key": "recovery-key"})
        self.assertEqual(code, 0, reply)
        self.assertEqual(self.invoke("operation-status", {"operation_id": op["operation_id"]})[1]["data"]["transaction"], reply["data"])
        self.assertEqual(len(self.rows()), 2)


del CliTests  # unittest discovery should not re-run the imported suite.
