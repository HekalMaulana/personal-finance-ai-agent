import json
import sqlite3
import subprocess
import sys
import unittest
from contextlib import closing
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from finance_storage import TransactionStore

ROOT = Path(__file__).resolve().parents[1]


class EmergencyCalculationTests(unittest.TestCase):
    def test_partial_inputs_do_not_invent_balance_or_coverage(self):
        from finance_emergency import calculate_fund

        self.assertEqual(calculate_fund(5_000_000, 3, None, 1_000_000), (15_000_000, None, None, None, None))
        self.assertEqual(calculate_fund(None, 3, 0, 1_000_000), (None, None, None, None, None))
        self.assertEqual(calculate_fund(5_000_000, None, 7_000_000, None), (None, 1.4, None, None, None))

    def test_eta_rounds_up_and_zero_contribution_does_not_create_estimate(self):
        from finance_emergency import calculate_fund

        self.assertEqual(calculate_fund(100, 3, 191, 50)[-2:], (109, 3))
        self.assertEqual(calculate_fund(100, 3, 191, 0)[-2:], (109, None))
        self.assertEqual(calculate_fund(100, 3, 300, None)[-2:], (0, 0))


class EmergencyCliTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for source in ROOT.glob('finance_*.py'):
            copyfile(source, self.root / source.name)
        self.db = self.root / 'data/finance-cli/emergency-test.db'
        TransactionStore(self.db)
        self.xlsx = self.root / 'reports/laporan-keuangan.xlsx'

    def cli(self, op, payload=None, exit_code=0):
        export = op == 'export'
        process = subprocess.run(
            [sys.executable, '-B', 'finance_reporting.py' if export else 'finance_cli.py',
             '--ledger', 'emergency-test', op], input=b'' if export else json.dumps(payload or {}).encode(),
            capture_output=True, cwd=self.root, timeout=20,
        )
        self.assertEqual(process.returncode, exit_code, (process.stdout, process.stderr))
        result = json.loads(process.stdout)
        self.assertEqual(result['ok'], exit_code == 0)
        return result['data'] if exit_code == 0 else result['error']['code']

    def config(self, **fields):
        return self.cli('emergency-configure', dict(idempotency_key='config', essential_rupiah=5_000_000,
                                                    target_months=3) | fields)

    def opening(self, amount=6_000_000):
        return self.cli('emergency-opening', {'amount_rupiah': amount, 'idempotency_key': 'opening'})

    def move(self, direction='deposit', amount: object = 1_000_000, key='deposit', exit_code=0):
        return self.cli('emergency-move', dict(direction=direction, amount_rupiah=amount, idempotency_key=key), exit_code)

    def test_main_scenario_persists_and_does_not_create_expense(self):
        self.config()
        self.opening()
        self.move()
        result = self.cli('emergency-summary', {'monthly_contribution_rupiah': 3_000_000})
        actual = tuple(result[k] for k in ('balance_rupiah', 'target_rupiah', 'coverage_months',
                                            'progress_percent', 'shortfall_rupiah', 'months_to_target'))
        self.assertEqual(actual[:3], (7_000_000, 15_000_000, 1.4))
        self.assertAlmostEqual(actual[3], 46.6666666666667)
        self.assertEqual(actual[4:], (8_000_000, 3))
        self.assertEqual(self.cli('summary')['transaction_count'], 0)
        with closing(sqlite3.connect(self.db.as_uri() + '?mode=ro', uri=True)) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM transactions').fetchone(), (0,))
            self.assertEqual(conn.execute('SELECT kind, amount_rupiah, balance_after_rupiah FROM emergency_movements '
                                          'ORDER BY revision').fetchall(),
                             [('opening', 6_000_000, 6_000_000), ('deposit', 1_000_000, 7_000_000)])
        self.assertFalse(self.xlsx.exists())

    def test_retries_and_overdraft(self):
        original = self.opening()
        deposit = self.move()
        withdrawal = self.move('withdrawal', 500_000, 'withdraw')
        self.assertEqual(self.opening(), original)
        self.assertEqual(self.move(), deposit)
        self.assertEqual(self.move('withdrawal', 500_000, 'withdraw'), withdrawal)
        self.assertEqual(self.move('withdrawal', 8_000_000, 'overdraft', 9), 'insufficient_fund')
        self.assertEqual(self.move('withdrawal', 1, 'withdraw', 3), 'idempotency_conflict')
        self.assertEqual(self.cli('emergency-opening', dict(amount_rupiah=6_000_000, idempotency_key='different'), 6),
                         'stale_version')
        movements = self.cli('emergency-history')['movements']
        self.assertEqual(movements, [original, deposit, withdrawal])
        self.assertEqual(self.cli('emergency-opening', movements[0]['request']), original)
        for saved in movements[1:]:
            self.assertEqual(self.cli('emergency-move', saved['request']), saved)
        self.assertEqual(self.cli('emergency-history')['movements'], movements)

    def test_partial_configuration_and_confirmed_replacement(self):
        row = self.cli('emergency-configure', {'target_months': 3, 'idempotency_key': 'target'})
        self.assertIsNone(self.cli('emergency-summary')['coverage_months'])
        complete = self.cli('emergency-configure', {'essential_rupiah': 5_000_000, 'idempotency_key': 'essential',
                                                    'expected_version': row['version']})
        update = dict(essential_rupiah=4_000_000, target_months=4, expected_version=complete['version'],
                      reason='Uji fiktif', idempotency_key='replace')
        self.assertEqual(self.cli('emergency-configure', update, 2), 'invalid_input')
        self.cli('emergency-configure', update | {'confirmed': True})
        self.assertEqual(self.cli('emergency-summary')['target_rupiah'], 16_000_000)
        opening = self.opening()
        self.move()
        replacement = dict(amount_rupiah=5_000_000, expected_revision=opening['revision'], reason='Uji fiktif',
                           idempotency_key='fix-opening')
        self.assertEqual(self.cli('emergency-opening', replacement, 2), 'invalid_input')
        self.assertEqual(self.cli('emergency-opening', replacement | {'confirmed': True}, 6), 'stale_version')
        version = self.cli('emergency-summary')['balance_revision']
        result = self.cli('emergency-opening', replacement | {'confirmed': True, 'expected_revision': version})
        self.assertEqual(result['kind'], 'opening_adjustment')
        self.assertEqual(result['balance_after_rupiah'], 6_000_000)
        self.assertEqual(len(self.cli('emergency-history')['configurations']), 3)

    def test_history_preserves_partial_request_for_cross_process_retry(self):
        current = self.config()
        request = dict(target_months=4, expected_version=current['version'], confirmed=True,
                       reason='Uji fiktif', idempotency_key='target-only')
        updated = self.cli('emergency-configure', request)
        history = self.cli('emergency-history')
        restored = history['configurations'][-1]['request']
        self.assertEqual(restored, request)
        self.assertEqual(updated['essential_rupiah'], 5_000_000)
        self.assertEqual(self.cli('emergency-configure', restored), updated)
        self.assertEqual(self.cli('emergency-configure', restored | {'essential_rupiah': 5_000_000}, 3),
                         'idempotency_conflict')
        self.assertEqual(self.cli('emergency-history'), history)

    def test_zero_missing_and_invalid_input(self):
        before = self.db.read_bytes()
        self.assertIsNone(self.cli('emergency-summary')['balance_rupiah'])
        self.assertEqual(self.cli('emergency-history'), {'configurations': [], 'movements': []})
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.move(exit_code=6), 'stale_version')
        for val in (0, -1, True, '1', 1.5, 2**63):
            self.assertEqual(self.move(amount=val, exit_code=2), 'invalid_input')
            self.assertEqual(self.cli('emergency-configure', {'essential_rupiah': val, 'idempotency_key': 'bad'}, 2),
                             'invalid_input')
        self.config()
        self.opening(0)
        self.assertEqual(self.cli('emergency-summary', {'monthly_contribution_rupiah': 0})['coverage_months'], 0)
        self.assertIsNone(self.cli('emergency-summary', {'monthly_contribution_rupiah': 0})['months_to_target'])
        self.move(amount=20_000_000)
        stats = self.cli('emergency-summary')
        self.assertEqual((stats['shortfall_rupiah'], stats['months_to_target']), (0, 0))
        self.assertGreater(stats['progress_percent'], 100)

    def test_concurrent_withdrawals_cannot_overdraw(self):
        from concurrent.futures import ThreadPoolExecutor
        from finance_emergency import EmergencyFundStore, InsufficientFund

        self.opening(100)

        def withdraw(key):
            try:
                EmergencyFundStore(self.db).move(direction='withdrawal', amount_rupiah=75, idempotency_key=key)
                return 'ok'
            except InsufficientFund:
                return 'rejected'

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(withdraw, ['concurrent-1', 'concurrent-2']), ['ok', 'rejected'])
        self.assertEqual(self.cli('emergency-summary')['balance_rupiah'], 25)

    def test_opening_adjustment_cannot_overdraw(self):
        self.opening(100)
        move = self.move('withdrawal', 75, 'withdraw')
        payload = dict(amount_rupiah=50, expected_revision=move['revision'], confirmed=True, reason='Uji',
                       idempotency_key='adjustment')
        self.assertEqual(self.cli('emergency-opening', payload, 9), 'insufficient_fund')
        result = self.cli('emergency-summary')
        self.assertEqual((result['opening_rupiah'], result['balance_rupiah']), (100, 25))

    def test_workbook_refreshed_only_on_demand(self):
        from openpyxl import load_workbook

        self.cli('export')
        with closing(load_workbook(self.xlsx, read_only=True)) as wb:
            self.assertEqual(wb['Dana Darurat']['A4'].value, 'Belum dikonfigurasi')
        before = self.xlsx.read_bytes(), self.xlsx.stat().st_mtime_ns
        self.config()
        self.opening()
        self.move()
        self.cli('emergency-summary')
        self.assertEqual((self.xlsx.read_bytes(), self.xlsx.stat().st_mtime_ns), before)
        db_before = self.db.read_bytes(), self.db.stat().st_mtime_ns
        self.assertTrue(self.cli('export')['verified'])
        self.assertEqual((self.db.read_bytes(), self.db.stat().st_mtime_ns), db_before)
        with closing(load_workbook(self.xlsx, read_only=True)) as wb:
            sheet = wb['Dana Darurat']
            values = list(sheet.values)[4]
            self.assertEqual(values[:4], (7_000_000, 5_000_000, 3, 15_000_000))
            progress = values[4]
            assert isinstance(progress, float)
            self.assertAlmostEqual(progress, 7 / 15)
            self.assertEqual(values[5:], (1.4, 8_000_000))
            self.assertEqual(sheet['E5'].number_format, '0.00%')
