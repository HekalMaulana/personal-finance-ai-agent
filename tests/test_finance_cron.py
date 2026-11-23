"""Offline fixtures for the portable Hermes trigger."""
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from finance_storage import TransactionStore

ROOT = Path(__file__).resolve().parents[1]


class RunnerTests(unittest.TestCase):
    def setUp(self):
        sandbox = TemporaryDirectory(prefix='fictional cron ')
        self.addCleanup(sandbox.cleanup)
        self.root = Path(sandbox.name)
        for source in ROOT.glob('finance_*.py'):
            shutil.copyfile(source, self.root / source.name)
        self.db = self.root / 'data/finance-cli/demo.db'
        TransactionStore(self.db).add_transaction(
            transaction_type='income', amount_rupiah=120, category='simulated-private-label',
            occurred_at='2025-12-29T09:00:00+07:00', idempotency_key='fictitious',
        )
        self.clock('2026-01-05T02:00:00Z')

    def clock(self, value):
        # Inject a fixed clock only in this copied CLI. The real engine and database remain in use.
        engine = self.root / 'finance_analysis.py'
        engine.write_text((ROOT / engine.name).read_text(encoding='utf-8').replace(
            "if __name__ == '__main__':", f"_now = lambda: datetime.fromisoformat({value!r})\n\nif __name__ == '__main__':",
        ), encoding='utf-8')

    def runner(self, *args, ledger='demo'):
        return subprocess.run([sys.executable, '-B', str(self.root / 'finance_cron_runner.py'),
                               '--ledger', ledger, *args], cwd=self.root.parent, capture_output=True, timeout=20)

    def test_preview_due_and_silent_replay(self):
        before = self.db.read_bytes()
        preview = self.runner('dry-run')
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual(json.loads(preview.stdout)['runnable'], 5)
        self.assertEqual(preview.stderr, b'')
        self.assertEqual(before, self.db.read_bytes())
        run = self.runner('run')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(b'2025-12-29', run.stdout)
        self.assertIn(b'120', run.stdout)
        self.assertIn(b'2026-Q1', run.stdout)
        self.assertNotIn(b'simulated-private-label', run.stdout)
        self.assertEqual(run.stderr, b'')
        replay = self.runner('run')
        self.assertEqual((replay.returncode, replay.stdout, replay.stderr), (0, b'', b''))
        self.assertEqual(list(self.root.rglob('*.xlsx')), [])

    def test_not_yet_due_is_silent_after_previous_work(self):
        self.clock('2026-01-05T01:59:59Z')
        self.assertEqual(self.runner('run').returncode, 0)
        replay = self.runner('run')
        self.assertEqual((replay.returncode, replay.stdout, replay.stderr), (0, b'', b''))
        self.clock('2026-01-05T02:00:00Z')
        self.assertIn(b'2025-12-29', self.runner('run').stdout)

    def test_mixed_batch_keeps_completed_report_and_reports_failure_on_stderr(self):
        # A malformed optional fund schema fails only the quarterly calculation.
        import sqlite3
        from contextlib import closing

        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute('CREATE TABLE emergency_movements (fixture INTEGER)')
            conn.commit()
        run = self.runner('run')
        self.assertEqual(run.returncode, 1)
        self.assertIn(b'Minggu 2025-12-29:', run.stdout)
        self.assertIn(b'Analisis gagal', run.stderr)
        self.assertNotIn(b'emergency_movements', run.stderr)
        replay = self.runner('run')
        self.assertEqual((replay.returncode, replay.stdout, replay.stderr), (0, b'', b''))

    def test_error_does_not_relay_child_output_or_path(self):
        (self.root / 'finance_analysis.py').write_text(
            "import sys\nprint('private-engine-path', file=sys.stderr)\nprint('private-engine-json')\n",
            encoding='utf-8',
        )
        run = self.runner('run')
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(run.stdout, b'')
        self.assertTrue(run.stderr)
        self.assertNotIn(b'private-engine', run.stderr)
        self.assertNotIn(self.root.name.encode(), run.stderr)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        from finance_cron import Scheduler

        sandbox = TemporaryDirectory(prefix='hermes cron fixture ')
        self.addCleanup(sandbox.cleanup)
        self.root = Path(sandbox.name)
        self.home = self.root / 'profile'
        self.home.mkdir()
        self.database = self.home / 'cron/jobs.json'
        self.database.parent.mkdir()
        self.jobs = []
        self.calls = []
        self.checkout = self.root / 'checkout'
        self.checkout.mkdir()
        for source in ROOT.glob('finance_*.py'):
            shutil.copyfile(source, self.checkout / source.name)
        TransactionStore(self.checkout / 'data/finance-cli/demo.db')
        self.scheduler = Scheduler(self.home, self.checkout, Path(sys.executable), self.cli)

    def cli(self, *args):
        self.calls.append(args)
        operation = args[0]
        if '--help' in args:
            return '--no-agent --script --interpreter --timezone --paused --deliver --failure-deliver --catch-up --no-wrap-response'
        if operation == 'create':
            self.jobs.append(dict(id='123456abcdef', name=args[args.index('--name') + 1],
                                  script=args[args.index('--script') + 1], enabled=False, state='paused',
                                  timezone='Asia/Pontianak', wrap_response=False, next_run_at=None, schedule={'kind': 'cron', 'expr': '0 9 * * *'},
                                  catch_up=True, no_agent=True, deliver='local', failure_deliver='local',
                                  interpreter=args[args.index('--interpreter') + 1], repeat={'times': None}))
        elif operation in ('resume', 'pause'):
            job = next(job for job in self.jobs if job['id'] == args[1])
            job.update(enabled=operation == 'resume', state='scheduled' if operation == 'resume' else 'paused',
                       next_run_at='2026-01-06T02:00:00+00:00' if operation == 'resume' else None)
        elif operation == 'remove':
            self.jobs[:] = [job for job in self.jobs if job['id'] != args[1]]
        elif operation == 'edit':
            self.jobs[0]['interpreter'] = args[args.index('--interpreter') + 1]
        self.database.write_text(json.dumps({'jobs': self.jobs}), encoding='utf-8')
        return 'Created job: 123456abcdef\n' if operation == 'create' else ''

    def test_opt_in_reinstall_pause_resume_and_uninstall(self):
        self.assertEqual(self.scheduler.apply('status')['state'], 'absent')
        with self.assertRaises(ValueError):
            self.scheduler.apply('install', ledger='demo')
        self.assertEqual(self.calls, [])
        with patch('finance_cron.engine', return_value=[]):
            self.assertEqual(self.scheduler.apply('install', ledger='demo', confirm=True)['state'], 'paused')
            self.assertEqual(self.scheduler.apply('install', ledger='demo', confirm=True)['state'], 'paused')
        self.assertEqual(sum(call[0] == 'create' and '--help' not in call for call in self.calls), 1)
        with self.assertRaises(ValueError):
            self.scheduler.apply('resume')
        self.assertEqual(self.scheduler.apply('resume', confirm=True)['state'], 'active')
        self.assertEqual(self.scheduler.apply('resume', confirm=True)['state'], 'active')
        self.assertEqual(self.scheduler.apply('pause')['state'], 'paused')
        self.assertEqual(self.scheduler.apply('pause')['state'], 'paused')
        self.assertEqual(self.scheduler.apply('uninstall')['state'], 'absent')
        self.assertEqual(self.scheduler.apply('uninstall')['state'], 'absent')
        self.assertFalse(self.scheduler.script.exists())
        self.assertEqual(sum(call[0] == 'resume' for call in self.calls), 1)

    def test_active_job_cannot_be_rebound_and_foreign_collision_is_refused(self):
        with patch('finance_cron.engine', return_value=[]):
            self.scheduler.apply('install', ledger='demo', confirm=True)
            self.scheduler.apply('resume', confirm=True)
            original = self.scheduler.script.read_bytes()
            with self.assertRaises(ValueError):
                self.scheduler.apply('install', ledger='different', confirm=True)
            self.assertEqual(self.scheduler.script.read_bytes(), original)
            self.scheduler.apply('pause')
            self.scheduler.apply('install', ledger='different', confirm=True)
            self.assertNotEqual(self.scheduler.script.read_bytes(), original)
            self.assertEqual(len(self.jobs), 1)
        self.jobs.append(dict(self.jobs[0], id='abcdef123456'))
        self.database.write_text(json.dumps({'jobs': self.jobs}), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.scheduler.apply('uninstall')
        self.assertEqual(len(self.jobs), 2)

    def test_foreign_job_at_reserved_name_is_never_adopted(self):
        from finance_cron import NAME, SCRIPT

        self.jobs.append({'id': 'abcdef123456', 'name': NAME, 'script': SCRIPT, 'enabled': False})
        self.database.write_text(json.dumps({'jobs': self.jobs}), encoding='utf-8')
        with patch('finance_cron.engine', return_value=[]), self.assertRaises(ValueError):
            self.scheduler.apply('install', ledger='demo', confirm=True)
        with self.assertRaises(ValueError):
            self.scheduler.apply('uninstall')
        self.assertEqual(len(self.jobs), 1)

    def test_renamed_owned_job_blocks_duplicate_install(self):
        self.scheduler.apply('install', ledger='demo', confirm=True)
        self.jobs[0].update(name='renamed', script='renamed.py')
        self.database.write_text(json.dumps({'jobs': self.jobs}), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.scheduler.apply('install', ledger='demo', confirm=True)
        self.assertEqual(len(self.jobs), 1)

    def test_pause_contains_damaged_runner_and_resume_checks_ledger(self):
        with patch('finance_cron.engine', return_value=[]):
            self.scheduler.apply('install', ledger='demo', confirm=True)
            self.scheduler.apply('resume', confirm=True)
            self.scheduler.script.write_text('foreign replacement', encoding='utf-8')
            self.assertEqual(self.scheduler.apply('status')['state'], 'drifted')
            self.assertEqual(self.scheduler.apply('pause')['state'], 'paused')
            self.assertIs(self.jobs[0]['enabled'], False)
            self.scheduler.script.unlink()
            self.scheduler.apply('install', ledger='demo', confirm=True)
        with patch('finance_cron.engine', side_effect=OSError('missing ledger')), self.assertRaises(ValueError):
            self.scheduler.apply('resume', confirm=True)
        self.assertIs(self.jobs[0]['enabled'], False)

    def test_missing_capability_does_not_stage_script(self):
        self.scheduler.cli = lambda *args: '--script'
        with patch('finance_cron.engine', return_value=[]), self.assertRaises(ValueError):
            self.scheduler.apply('install', ledger='demo', confirm=True)
        self.assertFalse(self.scheduler.script.exists())
        self.assertFalse(self.database.exists())
