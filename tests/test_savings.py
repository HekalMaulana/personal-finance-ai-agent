import json
import subprocess
import sys
import unittest
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from finance_storage import TransactionStore

ROOT = Path(__file__).resolve().parents[1]


class SavingsTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for source in ROOT.glob('finance_*.py'):
            copyfile(source, self.root / source.name)
        self.db = self.root / 'data/finance-cli/savings-test.db'
        TransactionStore(self.db)
        self.xlsx = self.root / 'reports/laporan-keuangan.xlsx'

    def cli(self, op, payload=None, status=0, ledger='savings-test'):
        export = op == 'export'
        process = subprocess.run(
            [sys.executable, '-B', 'finance_reporting.py' if export else 'finance_cli.py', '--ledger', ledger, op],
            input=b'' if export else json.dumps(payload or {}).encode(), cwd=self.root, capture_output=True, timeout=20,
        )
        self.assertEqual(process.returncode, status, (process.stdout, process.stderr))
        result = json.loads(process.stdout)
        self.assertEqual(result['ok'], status == 0)
        if status == 0:
            self.assertEqual(result['operation'], op)
        return result['data'] if status == 0 else result['error']['code']

    def create(self, **fields):
        return self.cli('savings-create', dict(name='Laptop', target_rupiah=10_000_000,
                                               idempotency_key='create') | fields)

    def opening(self, goal, amount=2_000_000, key='opening'):
        payload = dict(id=goal['id'], amount_rupiah=amount)
        preview = self.cli('savings-preview', payload)
        return self.cli('savings-opening', payload | dict(expected_revision=preview['before']['revision'],
                        confirmed=True, reason='Saldo fiktif', idempotency_key=key))

    def move(self, goal, direction='deposit', amount=1_000_000, key='deposit', status=0):
        return self.cli('savings-move', dict(id=goal['id'], direction=direction,
                                            amount_rupiah=amount, idempotency_key=key), status)

    def test_laptop_scenario_persists_across_cli_processes(self):
        goal = self.create(due_date='2028-02-29')
        self.assertIsNone(goal['balance_rupiah'])
        self.opening(goal)
        self.move(goal)
        result = self.cli('savings-get', dict(id=goal['id'], monthly_contribution_rupiah=1_000_000))
        self.assertEqual(tuple(result[k] for k in ('balance_rupiah', 'progress_percent', 'shortfall_rupiah',
                                                  'months_to_target', 'due_date')),
                         (3_000_000, 30, 7_000_000, 7, '2028-02-29'))
        self.assertIsNone(self.cli('savings-get', {'id': goal['id']})['months_to_target'])
        self.assertEqual(self.cli('summary')['transaction_count'], 0)
        self.assertIsNone(self.cli('emergency-summary')['balance_rupiah'])
        self.assertFalse(self.xlsx.exists())

    def test_export_reopens_multiple_goals_only_on_request(self):
        from contextlib import closing
        from openpyxl import load_workbook

        self.assertTrue(self.cli('export')['verified'])
        with closing(load_workbook(self.xlsx, read_only=True)) as wb:
            self.assertEqual(wb['Target Tabungan']['A4'].value, 'Belum dikonfigurasi')
        before = self.xlsx.read_bytes(), self.xlsx.stat().st_mtime_ns
        laptop = self.create(due_date='2028-02-29')
        second = self.create(name='=1+1', target_rupiah=300, idempotency_key='second')
        self.opening(laptop)
        self.move(laptop)
        self.cli('savings-list')
        self.assertEqual((self.xlsx.read_bytes(), self.xlsx.stat().st_mtime_ns), before)
        db_before = self.db.read_bytes(), self.db.stat().st_mtime_ns
        self.assertTrue(self.cli('export')['verified'])
        self.assertEqual((self.db.read_bytes(), self.db.stat().st_mtime_ns), db_before)
        with closing(load_workbook(self.xlsx, read_only=True)) as wb:
            ws = wb['Target Tabungan']
            self.assertEqual(ws['B5'].data_type, 's')
            self.assertEqual(tuple(cell.value for cell in ws[5]),
                             (second['id'], '=1+1', None, 300, None, None, None))
            self.assertEqual(tuple(cell.value for cell in ws[6]),
                             (laptop['id'], 'Laptop', '2028-02-29', 10_000_000, 3_000_000, 0.3, 7_000_000))
            self.assertEqual(ws['F6'].number_format, '0.00%')

    def test_invalid_requests_leave_no_records(self):
        for value in (0, -1, 1.5, True, '1', 2**63):
            self.assertEqual(self.cli('savings-create', dict(name='Laptop', target_rupiah=value,
                                                            idempotency_key='bad'), 2), 'invalid_input')
        for date in ('2027-02-29', '20280229', '2028-02-29T10:00:00', ''):
            self.assertEqual(self.cli('savings-create', dict(name='Laptop', target_rupiah=1, due_date=date,
                                                            idempotency_key='bad'), 2), 'invalid_input')
        self.assertEqual(self.cli('savings-create', dict(name=' ', target_rupiah=1,
                                                        idempotency_key='bad'), 2), 'invalid_input')
        self.assertEqual(self.cli('savings-list'), [])
        self.assertEqual(self.cli('savings-list', status=4, ledger='absent'), 'database_not_found')
        self.assertFalse(self.db.with_name('absent.db').exists())
        goal = self.create()
        self.assertEqual(self.move(goal, status=2), 'invalid_input')
        self.opening(goal, 0)
        for amount in (0, -1, True):
            self.assertEqual(self.move(goal, amount=amount, status=2), 'invalid_input')
        self.assertIsNone(self.cli('savings-get', dict(id=goal['id'], monthly_contribution_rupiah=0))['months_to_target'])
        self.assertEqual(self.cli('savings-get', dict(id=goal['id'], monthly_contribution_rupiah=-1), 2), 'invalid_input')
        self.assertEqual(len(self.cli('savings-history', dict(id=goal['id']))), 2)

    def test_confirmed_revisions_preserve_history_and_existing_movements(self):
        goal = self.create(due_date='2028-02-29')
        self.opening(goal)
        change = dict(id=goal['id'], name='Laptop Baru', target_rupiah=12_000_000, due_date=None)
        before_bytes = self.db.read_bytes()
        preview = self.cli('savings-preview', change)
        self.assertEqual(preview['before']['due_date'], '2028-02-29')
        self.assertIsNone(preview['after']['due_date'])
        self.assertEqual(self.db.read_bytes(), before_bytes)
        write = preview['changes'] | dict(confirmed=False, reason='Uji revisi', idempotency_key='update')
        self.assertEqual(self.cli('savings-update', write, 2), 'invalid_input')
        self.move(goal)
        self.assertEqual(self.cli('savings-update', write | dict(confirmed=True), 6), 'stale_version')
        preview = self.cli('savings-preview', change)
        updated = self.cli('savings-update', write | preview['changes'] | dict(confirmed=True))
        self.assertEqual(updated['target_rupiah'], 12_000_000)
        self.assertIsNone(updated['due_date'])
        self.assertEqual(self.cli('savings-update', updated['request']), updated)
        adjusted = self.opening(goal, 1_000_000, 'adjust')
        self.assertEqual((adjusted['kind'], adjusted['balance_rupiah']), ('opening_adjustment', 2_000_000))
        self.assertEqual(self.cli('savings-opening', adjusted['request']), adjusted)
        self.assertEqual([row['kind'] for row in self.cli('savings-history', dict(id=goal['id']))],
                         ['create', 'opening', 'deposit', 'update', 'opening_adjustment'])

    def test_withdrawal_retries_conflicts_and_no_partial_changes(self):
        goal = self.create()
        other = self.create(idempotency_key='other')
        self.assertNotEqual(goal['id'], other['id'])
        opening = self.opening(goal, 100)
        self.opening(other, 500, 'other-opening')
        withdrawal = self.move(goal, 'withdrawal', 75, 'withdraw')
        self.assertEqual(self.cli('savings-create', goal['request']), goal)
        self.assertEqual(self.cli('savings-opening', opening['request']), opening)
        self.assertEqual(self.cli('savings-move', withdrawal['request']), withdrawal)
        self.assertEqual(self.move(other, 'withdrawal', 75, 'withdraw', 3), 'idempotency_conflict')
        self.assertEqual(self.move(goal, 'withdrawal', 74, 'withdraw', 3), 'idempotency_conflict')
        self.assertEqual(self.move(goal, 'withdrawal', 26, 'overdraft', 9), 'insufficient_fund')
        self.assertEqual(self.cli('savings-opening', dict(id=goal['id'], amount_rupiah=50, confirmed=True,
                         reason='Uji', expected_revision=withdrawal['revision'], idempotency_key='bad'), 9),
                         'insufficient_fund')
        self.assertEqual(self.cli('savings-history', dict(id=goal['id'])), [goal, opening, withdrawal])
        self.assertEqual({row['id']: row['balance_rupiah'] for row in self.cli('savings-list')},
                         {goal['id']: 25, other['id']: 500})

    def test_concurrent_retries_and_withdrawals(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from finance_savings import InsufficientFund, SavingsStore

        goal = self.create()
        self.opening(goal, 100)
        gate = Barrier(2)

        def move(request):
            gate.wait(timeout=5)
            try:
                return SavingsStore(self.db).move(id=goal['id'], **request)
            except InsufficientFund:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            deposit = dict(direction='deposit', amount_rupiah=10, idempotency_key='parallel-deposit')
            first, second = pool.map(move, [deposit, deposit])
            self.assertIsNotNone(first)
            self.assertEqual(first, second)
            results = list(pool.map(move, [dict(direction='withdrawal', amount_rupiah=75, idempotency_key=key)
                                           for key in ('first', 'second')]))
        self.assertEqual(sum(row is not None for row in results), 1)
        self.assertEqual(self.cli('savings-get', dict(id=goal['id']))['balance_rupiah'], 35)
        self.assertEqual(len(self.cli('savings-history', dict(id=goal['id']))), 4)
