"""Lesson 7B: only a trusted test caller can simulate gateway context."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier
from typing import Any
from unittest.mock import patch

from finance_storage import TransactionStore
from finance_telegram import ActionRejected, TelegramActions, TelegramSource


class TelegramActionsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name).resolve() / "fictional.db"
        self.ledger = TransactionStore(self.path)

    def test_prepare_and_confirm_record_one_expense(self):
        actions = TelegramActions(self.path, owners={"123"})
        source = TelegramSource("123", "123", "dm", "Please record an expense")
        prepared = actions.handle("prepare", {"operation_type": "transaction.add", "parameters": {
            "transaction_type": "expense", "amount_rupiah": 15000,
            "category": " Makanan ", "occurred_at": "2026-01-01T05:00:00Z",
        }}, source=source)
        self.assertEqual(prepared["status"], "prepared")
        self.assertEqual(prepared["parameters"]["category"], "Makanan")
        self.assertEqual(self.ledger.cash_flow().total_expense, 0)
        request = {key: prepared[key] for key in ("operation_id", "preview_digest")}
        text = f"confirm {request['operation_id']} {request['preview_digest']}"
        result = actions.handle("confirm", request, source=TelegramSource("123", "123", "dm", text))
        self.assertEqual(result["status"], "committed")
        self.assertEqual(self.ledger.cash_flow().total_expense, 15000)
        original, corrections = self.ledger.transaction_history(result["transaction_id"])
        self.assertEqual(original.amount_rupiah, 15000)
        self.assertEqual(corrections, [])

    def service(self, clock=lambda: 100):
        return TelegramActions(self.path, owners={"123", "456"}, clock=clock, monotonic_clock=clock)

    def act(self, action, request, text="", owner="123", *, service=None):
        return (service or self.service()).handle(action, request, source=TelegramSource(owner, owner, "dm", text))

    def preview(self, **changes):
        return self.act("prepare", {"operation_type": "transaction.add", "parameters": {
            "transaction_type": "income", "amount_rupiah": 20000, "category": "Test",
            "occurred_at": "2026-01-01T05:00:00Z", **changes,
        }})

    def confirm(self, op, *, text=None, owner="123", service=None, **changes: Any):
        req = {key: op[key] for key in ("operation_id", "preview_digest")} | changes
        if text is None:
            text = f"confirm {req['operation_id']} {req['preview_digest']}"
        return self.act("confirm", req, text, owner, service=service)

    def test_unknown_and_model_claims_denied(self):
        mock = {"user_id": "123", "chat_id": "123", "confirmed": True}
        with patch.dict(os.environ, {"HERMES_SESSION_ACTOR_ID": "123", "HERMES_SESSION_PLATFORM": "telegram"}):
            with self.assertRaisesRegex(ActionRejected, "unauthorized_source"):
                self.service().handle("confirm", mock)
        for service, source in ((self.service(), TelegramSource("999", "999", "dm", "")),
                                (self.service(), TelegramSource("123", "123", "group", "")),
                                (TelegramActions(self.path), TelegramSource("123", "123", "dm", ""))):
            with self.assertRaisesRegex(ActionRejected, "unauthorized_source"):
                service.handle("prepare", mock, source=source)
        with self.assertRaisesRegex(ActionRejected, "invalid_request"):
            self.act("prepare", mock)

    def test_concurrent_and_replayed_confirm_commit_once(self):
        op = self.preview()
        gate = Barrier(4, timeout=10)

        def attempt(_):
            gate.wait()
            try:
                return self.confirm(op)["status"]
            except ActionRejected as exc:
                return str(exc)

        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertCountEqual(pool.map(attempt, range(4)), ["committed"] + ["operation_committed"] * 3)
        with self.assertRaisesRegex(ActionRejected, "operation_committed"):
            self.confirm(op)
        flow = self.ledger.cash_flow()
        self.assertEqual((flow.transaction_count, flow.total_income), (1, 20000))

    def test_confirm_rejects_wrong_owner_preview_message_and_parameters(self):
        first, second = self.preview(), self.preview()
        self.assertNotEqual(first["operation_id"], second["operation_id"])
        for code, kwargs in (("operation_not_found", {"owner": "456"}),
                             ("preview_mismatch", {"preview_digest": second["preview_digest"]}),
                             ("explicit_confirmation_required", {"text": "yes"}),
                             ("invalid_request", {"parameters": {"amount_rupiah": 1}})):
            with self.subTest(code=code), self.assertRaisesRegex(ActionRejected, code):
                self.confirm(first, **kwargs)
        self.assertEqual(self.ledger.cash_flow().transaction_count, 0)

    def test_expired_and_canceled_operations_cannot_commit(self):
        expired, canceled = self.preview(), self.preview()
        expired_ref = {"operation_id": expired["operation_id"]}
        later = self.service(clock=lambda: expired["expires_at"])
        before = self.path.read_bytes()
        self.assertEqual(self.act("status", expired_ref, service=later)["status"], "expired")
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaisesRegex(ActionRejected, "operation_expired"):
            self.confirm(expired, service=later)
        canceled_ref = {"operation_id": canceled["operation_id"]}
        with self.assertRaisesRegex(ActionRejected, "explicit_cancellation_required"):
            self.act("cancel", canceled_ref, "cancel")
        result = self.act("cancel", canceled_ref, f"cancel {canceled['operation_id']}")
        self.assertEqual(result["status"], "canceled")
        self.assertEqual(self.act("status", canceled_ref), result)
        with self.assertRaisesRegex(ActionRejected, "operation_canceled"):
            self.confirm(canceled)
        self.assertEqual(self.ledger.cash_flow().transaction_count, 0)

    def test_deadline_preserves_subseconds_and_wall_rollback_cannot_revive_it(self):
        wall, steady = 100.999, 600.999

        def service():
            return TelegramActions(self.path, owners={"123"}, clock=lambda: wall,
                                   monotonic_clock=lambda: steady)

        op = self.act("prepare", {"operation_type": "transaction.add", "parameters": {
            "transaction_type": "income", "amount_rupiah": 1, "category": "Test",
            "occurred_at": "2026-01-01T05:00:00Z",
        }}, service=service())
        ref = {"operation_id": op["operation_id"]}
        wall, steady = 400.0, 900.0
        self.assertEqual(self.act("status", ref, service=service())["status"], "prepared")
        wall, steady = 399.0, 901.0
        with self.assertRaisesRegex(ActionRejected, "operation_expired"):
            self.confirm(op, service=service())

    def test_dispatch_only_accepts_plain_strings(self):
        class NotAString:
            def __eq__(self, other):
                return True

        with self.assertRaisesRegex(ActionRejected, "unsupported_action"):
            self.act(NotAString(), {})
        with self.assertRaisesRegex(ActionRejected, "invalid_request"):
            self.act("prepare", {"operation_type": NotAString(), "parameters": {}})

    def test_only_validated_transaction_add_allowed(self):
        with self.assertRaisesRegex(ActionRejected, "unsupported_action"):
            self.act("correct", {})
        with self.assertRaisesRegex(ActionRejected, "invalid_request"):
            self.act("prepare", {"operation_type": "budget.create", "parameters": {}})
        with self.assertRaises(ValueError):
            self.preview(amount_rupiah=True)
        self.assertEqual(self.ledger.cash_flow().transaction_count, 0)

    def test_state_update_failure_rolls_back_transaction(self):
        op = self.preview()
        with closing(sqlite3.connect(self.path, autocommit=True)) as conn:
            conn.execute("""CREATE TRIGGER synthetic_fault BEFORE UPDATE ON telegram_financial_operations
                            BEGIN SELECT RAISE(FAIL, 'synthetic failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.confirm(op)
        self.assertEqual(self.ledger.cash_flow().transaction_count, 0)
        self.assertEqual(self.act("status", {"operation_id": op["operation_id"]}), op)

    def test_status_survives_restart_without_using_main_network_or_excel(self):
        op = self.preview()
        pending = self.preview()
        committed = self.confirm(op)
        fake_main = self.path.with_name("finance.db")
        fake_main.write_bytes(b"untouched fictional sentinel")
        code = """
import json, sys
from pathlib import Path
import finance_telegram as app
path, main = map(Path, sys.argv[1:3])
app.DEFAULT_DB_PATH = main

def offline(event, args):
    if event.startswith('socket.') or event == 'subprocess.Popen':
        raise AssertionError(event)
    if event == 'sqlite3.connect' and args[0] not in (str(path), path.as_uri() + '?mode=ro', path.as_uri() + '?mode=rw'):
        raise AssertionError('Unexpected ledger')
    if event == 'open' and str(args[0]).lower().endswith('.xlsx'):
        raise AssertionError('Unexpected workbook')

sys.addaudithook(offline)
ref = {'operation_id': sys.argv[3]}
source = app.TelegramSource('123', '123', 'dm', 'status')
try:
    app.TelegramActions(main, owners={'123'}).handle('status', ref, source=source)
except app.ActionRejected as exc:
    assert str(exc) == 'invalid_ledger'
else:
    raise AssertionError('Main ledger was not rejected')
actions = app.TelegramActions(path, owners={'123'}, clock=lambda: 101)
status = actions.handle('status', ref, source=source)
if status['status'] == 'expired':
    ref['preview_digest'] = status['preview_digest']
    text = f"confirm {ref['operation_id']} {ref['preview_digest']}"
    try:
        actions.handle('confirm', ref, source=app.TelegramSource('123', '123', 'dm', text))
    except app.ActionRejected as exc:
        assert str(exc) == 'operation_expired'
    else:
        raise AssertionError('Restart revived the pending approval')
print(json.dumps(status))
"""
        for expected in (committed, pending | {"status": "expired"}):
            out = subprocess.check_output([sys.executable, "-B", "-c", code, str(self.path), str(fake_main),
                                           expected["operation_id"]], cwd=Path(__file__).resolve().parents[1], timeout=15)
            self.assertEqual(json.loads(out), expected)
        self.assertEqual(self.ledger.cash_flow().transaction_count, 1)
        self.assertEqual(fake_main.read_bytes(), b"untouched fictional sentinel")
        self.assertFalse(list(self.path.parent.rglob("*.xlsx")))
