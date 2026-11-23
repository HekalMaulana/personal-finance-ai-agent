import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import uuid4

from finance_storage import TransactionStore
from finance_telegram_bridge import FinanceIngress, LedgerRequests

NOW = 1800000000
OWNER = 123
PREPARE = '/finance prepare ' + json.dumps({'transaction_type': 'expense', 'amount_rupiah': 15000,
    'category': 'Fiktif', 'occurred_at': '2026-01-01T12:00:00+07:00'})


class Message(NS):
    pass


def event(text, serial=1, **raw_changes):
    raw = Message(text=text, chat=NS(id=OWNER, type='private'), from_user=NS(id=OWNER, is_bot=False),
                  message_id=serial, date=datetime.fromtimestamp(NOW, timezone.utc))
    vars(raw).update(raw_changes)
    return NS(source=NS(platform='telegram', user_id=str(OWNER), chat_id=str(OWNER), chat_type='dm',
                        thread_id=None, is_bot=False), raw_message=raw, text=text, message_id=str(serial),
              platform_update_id=serial, internal=False, edit_revision=None)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name).resolve() / 'fictional.db'
        self.store = TransactionStore(self.path)
        self.service = LedgerRequests(self.path, OWNER, clock=lambda: NOW)
        self.ingress = FinanceIngress(OWNER, Message, 'telegram', self.service.dispatch)

    def send(self, text, serial):
        consumed, reply = self.ingress.receive(event(text, serial))
        self.assertTrue(consumed)
        return reply

    def test_bound_lifecycle_and_replay(self):
        before = self.send(PREPARE, 1)
        op, digest = before['operation_id'], before['preview_digest']
        self.assertEqual(before['parameters']['amount_rupiah'], 15000)
        self.assertEqual(self.store.cash_flow().transaction_count, 0)
        self.assertEqual(self.send(PREPARE, 1), {'error': 'replayed_message'})
        self.assertEqual(self.send(f'/finance status {op}', 2)['status'], 'prepared')
        self.assertEqual(self.send(f'/finance status {op}', 2), {'error': 'replayed_message'})
        self.assertEqual(self.send(f'/finance confirm {op} ' + '0' * 64, 3), {'error': 'preview_mismatch'})
        self.assertEqual(self.send(f'/finance confirm {op} {digest} 20000', 4), {'error': 'invalid_request'})
        with ThreadPoolExecutor(max_workers=3) as pool:
            replies = list(pool.map(lambda i: self.send(f'/finance confirm {op} {digest}', i), (5, 6, 7)))
        self.assertCountEqual([r.get('status', r.get('error')) for r in replies],
                              ['committed', 'operation_committed', 'operation_committed'])
        self.assertEqual(self.store.cash_flow().total_expense, 15000)
        other = self.send(PREPARE, 8)
        self.assertEqual(self.send(f"/finance cancel {other['operation_id']}", 9)['status'], 'canceled')
        self.assertEqual(self.send(f"/finance status {other['operation_id']}", 10)['status'], 'canceled')

    def test_spoofed_or_unsuitable_events_are_consumed_without_dispatch(self):
        for e in (event(PREPARE, from_user=NS(id=456, is_bot=False)), event(PREPARE, from_user=None),
                  event(PREPARE, from_user=NS(id=OWNER, is_bot=True)), event(PREPARE, chat=NS(id=OWNER, type='group')),
                  event(PREPARE, forward_origin=object()), event(PREPARE, edit_date=object()),
                  event(PREPARE, date=datetime.fromtimestamp(NOW - 301, timezone.utc))):
            # Freshness is enforced at the service; an authenticated stale event gets a generic rejection.
            consumed, reply = self.ingress.receive(e)
            self.assertTrue(consumed)
            self.assertIn(reply, (None, {'error': 'stale_message'}))
        e = event(PREPARE)
        e.raw_message = NS(**vars(e.raw_message))
        self.assertEqual(self.ingress.receive(e), (True, None))
        e = event(PREPARE)
        e.source.chat_id = '456'
        self.assertEqual(self.ingress.receive(e), (True, None))
        e = event(f'/finance status {uuid4()}')
        e.text = PREPARE
        self.assertEqual(self.ingress.receive(e), (True, None))
        self.assertEqual(self.ingress.receive(event('confirm 123')), (False, None))
        self.assertEqual(FinanceIngress(None, Message, 'telegram', self.service.dispatch).receive(event(PREPARE)),
                         (True, None))
        self.assertEqual(self.send(PREPARE[:-1] + ',"chat_id":123}', 80), {'error': 'invalid_parameters'})
        self.assertEqual(self.store.cash_flow().transaction_count, 0)
