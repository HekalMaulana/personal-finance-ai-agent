import json
import sqlite3
import subprocess
import sys
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from finance_storage import TransactionStore

ROOT = Path(__file__).resolve().parents[1]


class BudgetIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        # Run real CLI entry points without allowing access to the actual workspace data.
        for name in ('finance_cli.py', 'finance_storage.py', 'finance_budgets.py', 'finance_emergency.py', 'finance_savings.py', 'finance_reporting.py'):
            if (ROOT / name).is_file():
                (self.root / name).write_bytes((ROOT / name).read_bytes())
        self.db = self.root / 'data' / 'finance-cli' / 'budget-test.db'
        self.store = TransactionStore(self.db)
        self.report = self.root / 'reports' / 'laporan-keuangan.xlsx'

    def cli(self, command, payload=None, *, script='finance_cli.py', status=0):
        proc = subprocess.run([sys.executable, '-B', script, '--ledger', 'budget-test', command],
                              cwd=self.root, input=json.dumps(payload).encode() if payload is not None else b'',
                              capture_output=True, timeout=15)
        self.assertEqual(proc.returncode, status, (proc.stdout, proc.stderr))
        reply = json.loads(proc.stdout)
        self.assertEqual(reply['ok'], status == 0)
        return reply['data'] if status == 0 else reply['error']['code']

    def create(self, period='2026-11', category='Makanan', amount_rupiah=1_000_000, key='create-nov'):
        return self.cli('budget-create', dict(period=period, category=category, amount_rupiah=amount_rupiah,
                                              idempotency_key=key))

    def expense(self, amount, key, *, category='Makanan', at='2026-11-15T12:00:00+07:00', kind='expense'):
        return self.store.add_transaction(transaction_type=kind, amount_rupiah=amount, category=category,
                                          occurred_at=at, idempotency_key=key)

    def summary(self, period='2026-11', **filters):
        return self.cli('budget-summary', dict(period=period, **filters))

    def test_effective_amount_changes_realization(self):
        self.create()
        first = self.expense(250_000, 'expense-1')
        self.expense(150_000, 'expense-2', category='  mAKANAN  ')
        row, = self.summary(category=' MAKANAN ')
        self.assertEqual((row['amount_rupiah'], row['spent_rupiah'], row['remaining_rupiah'],
                          row['usage_percent'], row['status']), (1_000_000, 400_000, 600_000, 40, 'normal'))
        self.store.correct_transaction(first.id, expected_version=0, changes={'amount_rupiah': 25_000},
                                       reason='Salah input', idempotency_key='correct-1')
        row, = self.summary()
        self.assertEqual((row['spent_rupiah'], row['remaining_rupiah'], row['usage_percent']), (175_000, 825_000, 17.5))
        with closing(sqlite3.connect(self.db.as_uri() + '?mode=ro', uri=True)) as conn:
            self.assertEqual(conn.execute('SELECT sum(amount_rupiah) FROM transactions').fetchone(), (400_000,))
            self.assertEqual(conn.execute('SELECT version, amount_rupiah FROM transaction_corrections').fetchall(),
                             [(1, 25_000)])
        self.assertFalse(self.report.exists())

    def test_normalization_uniqueness_and_month_boundary(self):
        created = self.create(category='  Makan   Siang ')
        self.assertEqual(created['category'], 'Makan Siang')
        self.assertEqual(created, self.create(category='mAKAN  siang'))
        fields = dict(period='2026-11', category='makan siang', amount_rupiah=50, idempotency_key='duplicate')
        self.assertEqual(self.cli('budget-create', fields, status=8), 'budget_exists')
        self.create('2026-10', 'Makan Siang', 100, 'oct')
        self.expense(40, 'before', category='Makan Siang', at='2026-10-31T16:59:59.999999Z')
        self.expense(60, 'at', category=' Makan   Siang ', at='2026-10-31T17:00:00Z')
        self.expense(99, 'income', category='Makan Siang', kind='income')
        self.expense(99, 'unconfigured')
        self.assertEqual(self.summary('2026-10')[0]['spent_rupiah'], 40)
        row, = self.summary()
        self.assertEqual(row['spent_rupiah'], 60)
        self.assertEqual(self.summary(category='Makanan'), [])
        self.assertEqual(self.summary('2026-12'), [])

    def test_effective_category_type_and_date(self):
        self.create(amount_rupiah=100)
        self.create('2026-11', 'Transportasi', 100, 'transport')
        self.create('2026-12', 'Transportasi', 100, 'transport-dec')
        transaction = self.expense(70, 'move')
        for version, (changes, november, december) in enumerate([
            ({'category': 'Transportasi'}, [0, 70], 0),
            ({'occurred_at': '2026-11-30T17:00:00Z'}, [0, 0], 70),
            ({'transaction_type': 'income'}, [0, 0], 0),
        ]):
            self.store.correct_transaction(transaction.id, expected_version=version, changes=changes,
                                           reason='Koreksi fiktif', idempotency_key=f'move-{version}')
            self.assertEqual([row['spent_rupiah'] for row in self.summary()], november)
            self.assertEqual(self.summary('2026-12')[0]['spent_rupiah'], december)

    def test_warning_threshold_and_over_budget(self):
        self.create(amount_rupiah=100)
        self.expense(90, 'exact-warning')
        self.assertEqual(self.summary()[0]['status'], 'mendekati batas')
        self.assertEqual(self.summary(above_warning=True), [])
        self.expense(10, 'full')
        self.assertEqual(self.summary(above_warning=True)[0]['status'], 'mendekati batas')
        self.expense(1, 'over')
        row, = self.summary(above_warning=True)
        self.assertEqual((row['usage_percent'], row['remaining_rupiah'], row['status']), (101, -1, 'melebihi batas'))

    def test_confirmation_stale_version_audit_and_retry(self):
        created = self.create()
        lookup = dict(period='2026-11', category='makanan')
        update = dict(**lookup, amount_rupiah=800_000, expected_version=0, confirmed=False,
                      reason='Penyesuaian fiktif', idempotency_key='update-1')
        for value in (False, 1, 'true', None):
            self.assertEqual(self.cli('budget-update', {**update, 'confirmed': value}, status=2), 'invalid_input')
        self.assertEqual(self.cli('budget-history', lookup), [created])
        update['confirmed'] = True
        saved = self.cli('budget-update', update)
        self.assertEqual(self.cli('budget-get', lookup), saved)
        self.assertEqual(self.cli('budget-update', {**update, 'idempotency_key': 'stale'}, status=6), 'stale_version')
        self.assertEqual(self.cli('budget-update', {**update, 'amount_rupiah': 7}, status=3), 'idempotency_conflict')
        newest = self.cli('budget-update', {**update, 'expected_version': 1, 'amount_rupiah': 900_000,
                                            'idempotency_key': 'update-2'})
        self.assertEqual(self.cli('budget-update', update), saved)
        self.assertEqual(self.create(), created)
        self.assertEqual(self.cli('budget-get', lookup), newest)
        self.assertEqual(self.cli('budget-history', lookup), [created, saved, newest])
        with closing(sqlite3.connect(self.db.as_uri() + '?mode=ro', uri=True)) as conn:
            self.assertEqual(conn.execute('SELECT version, previous_amount_rupiah, amount_rupiah FROM budget_revisions '
                                          'ORDER BY version').fetchall(),
                             [(0, None, 1_000_000), (1, 1_000_000, 800_000), (2, 800_000, 900_000)])
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_legacy_read_only_and_additive_schema(self):
        self.expense(10, 'legacy')
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute('DROP TABLE transaction_corrections')
        before = self.db.read_bytes(), self.db.stat().st_mtime_ns
        self.assertEqual(self.summary(), [])
        lookup = dict(period='2026-11', category='Makanan')
        self.assertEqual(self.cli('budget-get', lookup, status=4), 'budget_not_found')
        self.assertEqual(self.cli('budget-history', lookup), [])
        self.assertEqual((self.db.read_bytes(), self.db.stat().st_mtime_ns), before)
        self.create()
        self.assertEqual(self.summary()[0]['spent_rupiah'], 10)
        with closing(sqlite3.connect(self.db.as_uri() + '?mode=ro', uri=True)) as conn:
            self.assertEqual(conn.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name").fetchall(),
                             [('budget_revisions',), ('budgets',), ('transactions',)])

    def test_invalid_inputs_and_missing_ledger_do_not_write(self):
        base = dict(period='2026-11', category='Makanan', amount_rupiah=100, idempotency_key='validate')
        before = self.db.read_bytes()
        for fields in ({'period': '0000-11'}, {'period': '2026-13'}, {'period': '2026-1'}, {'category': '  '},
                       {'amount_rupiah': True}, {'amount_rupiah': 0}, {'amount_rupiah': 1.5},
                       {'amount_rupiah': 2**63}, {'idempotency_key': ' spaced '}, {'extra': 'field'}):
            self.assertEqual(self.cli('budget-create', {**base, **fields}, status=2), 'invalid_input')
        self.assertEqual(self.db.read_bytes(), before)
        self.db.unlink()
        self.assertEqual(self.cli('budget-create', base, status=4), 'database_not_found')
        self.assertEqual(self.cli('budget-summary', {'period': '2026-11'}, status=4), 'database_not_found')
        self.assertFalse(self.db.exists())

    def test_create_rolls_back_identity_when_revision_insert_fails(self):
        self.create()
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("CREATE TRIGGER fail_revision AFTER INSERT ON budget_revisions "
                         "BEGIN SELECT RAISE(FAIL, 'fixture'); END")
        payload = dict(period='2026-11', category='Transportasi', amount_rupiah=100, idempotency_key='rollback')
        self.assertEqual(self.cli('budget-create', payload, status=5), 'storage_error')
        with closing(sqlite3.connect(self.db)) as conn, conn:
            self.assertEqual(conn.execute('SELECT category FROM budgets').fetchall(), [('Makanan',)])
            self.assertEqual(conn.execute('SELECT count(*) FROM budget_revisions').fetchone(), (1,))
            conn.execute('DROP TRIGGER fail_revision')
        self.assertEqual(self.cli('budget-create', payload)['category'], 'Transportasi')

    def test_nonledger_schema_rejected_without_changes(self):
        self.db.unlink()
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute('CREATE TABLE transactions (id TEXT)')
        before = self.db.read_bytes()
        lookup = dict(period='2026-11', category='Makanan')
        for command in ('budget-get', 'budget-history', 'budget-summary'):
            self.assertEqual(self.cli(command, lookup, status=2), 'invalid_input')
        payload = dict(**lookup, amount_rupiah=100, idempotency_key='wrong-schema')
        self.assertEqual(self.cli('budget-create', payload, status=2), 'invalid_input')
        self.assertEqual(self.db.read_bytes(), before)

    def test_category_length_after_nfc_is_validated(self):
        # U+0344 decomposes to two combining characters even under NFC.
        payload = dict(period='2026-11', category='\u0344' * 51, amount_rupiah=100,
                       idempotency_key='nfc-expansion')
        before = self.db.read_bytes()
        self.assertEqual(self.cli('budget-create', payload, status=2), 'invalid_input')
        self.assertEqual(self.db.read_bytes(), before)

    def test_budget_api_rejects_hard_link(self):
        from unittest.mock import patch
        from finance_budgets import BudgetStore

        alias = self.root / 'alias.db'
        try:
            alias.hardlink_to(self.db)
        except OSError as exc:
            self.skipTest(f'Hard links unavailable: {exc}')
        before = self.db.read_bytes()
        with patch('finance_budgets.DEFAULT_DB_PATH', self.db.resolve()):
            with self.assertRaisesRegex(ValueError, 'tautan keras'):
                BudgetStore(alias)
        self.assertEqual(self.db.read_bytes(), before)

    def test_incompatible_corrections_schema_rejected_without_changes(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute('DROP TABLE transaction_corrections')
            conn.execute('CREATE TABLE transaction_corrections (transaction_id TEXT, version INTEGER)')
        before = self.db.read_bytes()
        lookup = dict(period='2026-11', category='Makanan')
        self.assertEqual(self.cli('budget-summary', lookup, status=2), 'invalid_input')
        self.assertEqual(self.cli('budget-create', {**lookup, 'amount_rupiah': 100,
                                                    'idempotency_key': 'bad-revisions'}, status=2), 'invalid_input')
        self.assertEqual(self.db.read_bytes(), before)

    def test_budget_api_rechecks_resolved_path_before_open(self):
        from unittest.mock import patch
        from finance_budgets import BudgetStore

        # Simulate path redirection without requiring Windows symlink privileges.
        source = self.db.resolve()
        protected = (self.root / 'mock-primary.db').resolve()
        TransactionStore(protected)
        before = protected.read_bytes()
        real_resolve = Path.resolve
        with patch('finance_budgets.DEFAULT_DB_PATH', protected):
            store = BudgetStore(source)
            with patch.object(Path, 'resolve', autospec=True, side_effect=lambda path: (
                protected if path == source else real_resolve(path)
            )), patch('sqlite3.connect') as connect:
                with self.assertRaises(ValueError):
                    store.get_budget(period='2026-11', category='Makanan')
                with self.assertRaises(ValueError):
                    store.create_budget(period='2026-11', category='Makanan', amount_rupiah=100,
                                        idempotency_key='redirected')
                connect.assert_not_called()
        self.assertEqual(protected.read_bytes(), before)

    def test_workbook_budget_readback_and_on_demand(self):
        from openpyxl import load_workbook

        self.cli('export', script='finance_reporting.py')
        with closing(load_workbook(self.report, read_only=True)) as wb:
            self.assertEqual(wb['Anggaran']['A4'].value, 'Belum dikonfigurasi')
        before = self.report.read_bytes(), self.report.stat().st_mtime_ns
        self.create()
        self.create('2026-12', '=1+1', 100, 'create-dec')
        self.expense(175_000, 'meal')
        payload = dict(period='2026-11', category='Makanan', amount_rupiah=500_000, expected_version=0,
                       confirmed=True, reason='Penyesuaian fiktif', idempotency_key='update-nov')
        self.cli('budget-update', payload)
        self.summary()
        self.assertEqual((self.report.read_bytes(), self.report.stat().st_mtime_ns), before)
        db_before = self.db.read_bytes(), self.db.stat().st_mtime_ns
        self.assertTrue(self.cli('export', script='finance_reporting.py')['verified'])
        self.assertEqual((self.db.read_bytes(), self.db.stat().st_mtime_ns), db_before)
        with closing(load_workbook(self.report, read_only=True)) as wb:
            ws = wb['Anggaran']
            self.assertEqual(list(ws.values)[4:], [
                ('2026-11', 'Makanan', 500_000, 175_000, 325_000, 0.35, 'normal'),
                ('2026-12', '=1+1', 100, 0, 100, 0, 'normal'),
            ])
            self.assertEqual(ws['B6'].data_type, 's')
            self.assertEqual(ws['F5'].number_format, '0.00%')
