"""Offline scheduled analysis against disposable fictional ledgers."""

import json
import sqlite3
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

from finance_budgets import BudgetStore
from finance_emergency import EmergencyFundStore
from finance_savings import SavingsStore
from finance_storage import TransactionStore

ROOT = Path(__file__).resolve().parents[1]
NOW = '2026-01-05T02:00:00Z'
WEEK = '2025-12-29'
QUARTER = '2026-Q1'
MODULES = ('finance_analysis.py', 'finance_cli.py', 'finance_storage.py', 'finance_budgets.py',
           'finance_emergency.py', 'finance_savings.py')


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        sandbox = TemporaryDirectory()
        self.addCleanup(sandbox.cleanup)
        self.root = Path(sandbox.name)
        self.db = self.root / 'data' / 'finance-cli' / 'fixture.db'
        self.transactions = TransactionStore(self.db)

    def engine(self, now=NOW):
        from finance_analysis import AnalysisStore
        return AnalysisStore(self.db, clock=lambda: datetime.fromisoformat(now))

    def saved(self, kind, period):
        result = self.engine().status(kind, period)
        assert result is not None, (kind, period)
        return result

    def add(self, key, when, amount, kind='expense', category='Makan'):
        return self.transactions.add_transaction(transaction_type=kind, amount_rupiah=amount,
                                                 occurred_at=when, idempotency_key=key, category=category)

    def test_effective_week_exclusive_bounds_and_monthly_budget_split(self):
        self.add('before', '2025-12-28T16:59:59.999999Z', 999)
        self.add('first', '2025-12-28T17:00:00Z', 10, category='mAKan')
        self.add('last', '2026-01-04T16:59:59.999999Z', 100, 'income')
        self.add('after', '2026-01-04T17:00:00Z', 999)
        self.add('outside-week', '2025-12-01T17:00:00Z', 999)
        moved = self.add('rev', '2025-12-01T17:00:00Z', 999, 'income', 'Lain')
        self.transactions.correct_transaction(moved.id, expected_version=0, changes={
            'occurred_at': '2025-12-31T17:00:00Z', 'transaction_type': 'expense',
            'amount_rupiah': 40, 'category': 'Makan',
        }, reason='Koreksi fiktif', idempotency_key='correction')
        self.transactions.prepare_add(transaction_type='expense', category='Makan', amount_rupiah=999,
                                      occurred_at='2026-01-02T09:00:00+07:00', idempotency_key='prepared')
        budgets = BudgetStore(self.db)
        for period in ('2025-12', '2026-01', '2026-02'):
            budgets.create_budget(period=period, category='Makan', amount_rupiah=200, idempotency_key=period)
        budgets.update_budget(period='2026-01', category='Makan', amount_rupiah=100,
                              expected_version=0, confirmed=True, reason='Uji', idempotency_key='budget-revision')
        store = self.engine()
        store.run_due()
        result = self.saved('weekly', WEEK)['result']
        self.assertEqual(result['start_at'], '2025-12-29T00:00:00+07:00')
        self.assertEqual(result['end_at_exclusive'], '2026-01-05T00:00:00+07:00')
        self.assertEqual(result['cash_flow'], dict(total_income=100, total_expense=50,
                                                   net_cash_flow=50, transaction_count=3))
        self.assertNotIn('balance_rupiah', result)
        self.assertEqual([(b['period'], b['weekly_spent_rupiah'], b['weekly_usage_percent'])
                          for b in result['budgets']], [('2025-12', 10, 5.0), ('2026-01', 40, 40.0)])

    def test_empty_week_and_unconfigured_fund(self):
        store = self.engine()
        store.run_due()
        week = self.saved('weekly', WEEK)['result']
        self.assertEqual(week['cash_flow'], dict(total_income=0, total_expense=0,
                                                 net_cash_flow=0, transaction_count=0))
        self.assertEqual(week['budgets'], [])
        self.assertIsNone(self.saved('quarterly', QUARTER)['result']['fund']['balance_rupiah'])

    def test_quarter_snapshot_is_observed_now_and_financial_tables_are_unchanged(self):
        self.add('transaction', '2025-12-28T17:00:00Z', 10)
        fund = EmergencyFundStore(self.db)
        fund.configure(essential_rupiah=100, target_months=3, idempotency_key='configure')
        fund.set_opening(amount_rupiah=25, idempotency_key='opening')
        fund.move(direction='deposit', amount_rupiah=125, idempotency_key='deposit')
        SavingsStore(self.db).create(name='Tujuan fiktif', target_rupiah=100, idempotency_key='goal')
        BudgetStore(self.db).create_budget(period='2026-01', category='Makan', amount_rupiah=90,
                                           idempotency_key='budget')
        with closing(sqlite3.connect(self.db)) as conn:
            before = set(conn.iterdump())
            store = self.engine()
            self.assertEqual(len(store.check_due()), 5)
            self.assertEqual(store.history(), [])
            self.assertEqual(set(conn.iterdump()), before)
            store.run_due()
            self.assertTrue(before <= set(conn.iterdump()))
            self.assertEqual({line for line in conn.iterdump() if 'analysis_runs' not in line}, before)
        job = self.saved('quarterly', QUARTER)
        self.assertEqual(job['due_at'], '2026-01-01T09:00:00+07:00')
        self.assertEqual(job['observed_at'], '2026-01-05T09:00:00.000000+07:00')
        self.assertEqual(job['result']['snapshot_basis'], 'current_at_execution_not_historical')
        metrics = job['result']['fund']
        self.assertEqual([metrics[k] for k in ('balance_rupiah', 'target_rupiah', 'coverage_months',
                                               'progress_percent', 'shortfall_rupiah')], [150, 300, 1.5, 50, 150])
        self.assertEqual(list(self.root.rglob('*.xlsx')), [])

    def test_run_rejects_journal_trigger_before_any_financial_change(self):
        self.add('transaction', '2025-12-28T17:00:00Z', 10)
        self.engine().run_due()
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute('''CREATE TRIGGER unexpected_analysis_insert AFTER INSERT ON analysis_runs
                            BEGIN UPDATE transactions SET amount_rupiah = 20; END''')
            conn.commit()
            before = list(conn.iterdump())
            with self.assertRaises(sqlite3.DatabaseError):
                self.engine('2026-01-12T02:00:00Z').run_due()
            self.assertEqual(list(conn.iterdump()), before)

    def test_concurrent_runners_calculate_each_unique_job_once(self):
        import finance_analysis as analysis

        start = Barrier(2)
        with patch.object(analysis, '_calculate', wraps=analysis._calculate) as calculate:
            def worker():
                start.wait(timeout=10)
                return self.engine().run_due()

            with ThreadPoolExecutor(max_workers=2) as pool:
                first, second = pool.submit(worker), pool.submit(worker)
                first.result(timeout=20)
                second.result(timeout=20)
            self.assertEqual(calculate.call_count, 5)
        store = self.engine()
        self.assertEqual(store.run_due(), [])
        self.assertEqual(len(store.history()), 5)
        self.assertTrue(all(job['status'] == 'completed' and job['attempts'] == 1 for job in store.history()))
        self.assertEqual(store.check_due(), [])

    def test_failure_is_persisted_and_retry_is_explicit_and_capped(self):
        import finance_analysis as analysis

        store = self.engine()
        with patch.object(analysis, '_calculate', side_effect=sqlite3.DatabaseError('internal text')):
            store.run_due()
            self.assertEqual(store.run_due(), [])
            self.assertEqual(self.saved('weekly', WEEK)['attempts'], 1)
            for _ in range(2):
                self.engine().run_due(resume=('weekly', WEEK))
        job = self.saved('weekly', WEEK)
        self.assertEqual(job['status'], 'failed')
        self.assertIsNone(job['result'])
        self.assertEqual([item['attempt'] for item in job['failures']], [1, 2, 3])
        self.assertNotIn('internal text', json.dumps(job))
        self.assertEqual(store.run_due(resume=('weekly', WEEK)), [])
        self.assertEqual(store.run_due(resume=('quarterly', QUARTER))[0]['status'], 'completed')
        self.assertEqual(self.saved('quarterly', QUARTER)['failures'][0]['attempt'], 1)

    def test_restart_recovers_interrupted_sqlite_transaction_without_new_attempt(self):
        # Stop the process from inside calculation, after running was committed.
        code = """
import os
from datetime import datetime
from pathlib import Path
import finance_analysis as a
a._calculate = lambda *args: os._exit(27)
a.AnalysisStore(Path('data/finance-cli/fixture.db'), clock=lambda: datetime.fromisoformat(%r)).run_due()
""" % NOW
        for name in MODULES:
            copyfile(ROOT / name, self.root / name)
        stopped = subprocess.run([sys.executable, '-B', '-c', code], cwd=self.root, timeout=15)
        self.assertEqual(stopped.returncode, 27)
        running = self.engine().history()
        self.assertEqual(sum(job['status'] == 'running' for job in running), 1)
        self.assertEqual(sum(job['status'] == 'pending' for job in running), 4)
        self.assertEqual(self.engine().run_due()[0]['attempts'], 1)
        self.assertTrue(all(job['status'] == 'completed' for job in self.engine().history()))
        # The exact same application logic on another launch must report no reruns.
        cli = self.launch('run-due')
        self.assertEqual(cli['data'], [])
        self.assertEqual(len(self.launch('history')['data']), 5)

    def launch(self, *args, cwd=None):
        # Inject time only in this offline process, not through production CLI inputs.
        code = """
import sys
from datetime import datetime
sys.path.insert(0, sys.argv.pop(1))
def offline(event, args):
    if event.startswith('socket.'):
        raise AssertionError(event)
    if event == 'import' and args[0].split('.')[0] in {'openpyxl', 'finance_reporting', 'openai', 'anthropic', 'hermes'}:
        raise AssertionError(args[0])
sys.addaudithook(offline)
import finance_analysis as a
a._now = lambda: datetime.fromisoformat(%r)
raise SystemExit(a.main())
""" % NOW
        process = subprocess.run([sys.executable, '-B', '-c', code, str(self.root), '--ledger', 'fixture', *args],
                                 cwd=cwd or self.root, capture_output=True, check=True, timeout=15)
        return json.loads(process.stdout)

    def test_cli_uses_repo_relative_named_ledger_and_persists_bounded_backlog(self):
        for name in MODULES:
            copyfile(ROOT / name, self.root / name)
        self.assertEqual(len(self.launch('check-due', cwd=self.db.parent)['data']), 5)
        self.assertEqual(len(self.launch('run-due')['data']), 5)
        self.assertEqual(self.launch('status', 'weekly', WEEK)['data']['status'], 'completed')
        self.assertEqual(self.launch('run-due')['data'], [])
        self.assertEqual(len(self.launch('history', '--limit', '2')['data']), 2)
        self.assertFalse((self.root / 'data' / 'finance.db').exists())
        self.assertEqual(list(self.root.rglob('*.xlsx')), [])


class ScheduleTests(unittest.TestCase):
    def test_weekly_monday_gate_and_year_boundary(self):
        from finance_analysis import due_jobs

        weekly = lambda value: [job for job in due_jobs(datetime.fromisoformat(value)) if job.kind == 'weekly']
        before = weekly('2026-01-05T01:59:59Z')[-1]
        latest = weekly('2026-01-05T02:00:00Z')[-1]
        self.assertEqual(before.period, '2025-12-22')
        self.assertEqual(latest.period, '2025-12-29')
        self.assertEqual(latest.due_at.isoformat(), '2026-01-05T09:00:00+07:00')

    def test_quarterly_local_gate(self):
        from finance_analysis import due_jobs

        for year, month, previous in [(2026, 1, '2025-Q4'), (2026, 4, '2026-Q1'),
                                      (2026, 7, '2026-Q2'), (2026, 10, '2026-Q3')]:
            with self.subTest(month=month):
                def quarter(time):
                    return next(job for job in due_jobs(datetime.fromisoformat(
                        f'{year}-{month:02}-01T{time}Z')) if job.kind == 'quarterly')
                self.assertEqual(quarter('01:59:59').period, previous)
                job = quarter('02:00:00')
                self.assertEqual(job.period, f'{year}-Q{(month - 1) // 3 + 1}')
                self.assertEqual(job.due_at.hour, 9)
                self.assertEqual(job.due_at.tzname(), 'Asia/Pontianak')

    def test_catchup_candidates_are_bounded(self):
        from finance_analysis import due_jobs

        jobs = due_jobs(datetime.fromisoformat('2026-11-23T09:00:00+07:00'))
        self.assertEqual([job.period for job in jobs if job.kind == 'weekly'],
                         ['2026-10-26', '2026-11-02', '2026-11-09', '2026-11-16'])
        self.assertEqual([job.period for job in jobs if job.kind == 'quarterly'], ['2026-Q4'])
        with self.assertRaises(ValueError):
            due_jobs(datetime(2026, 11, 23, 9))
