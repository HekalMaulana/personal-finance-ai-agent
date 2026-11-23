"""Opt-in Hermes integration smoke: one paused job, no gateway."""
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from finance_cron import hermes_env
from finance_storage import TransactionStore


def main():
    if not __debug__ or len(sys.argv) != 1:
        raise SystemExit('Run this smoke without arguments or Python optimization.')
    executable = os.environ.get('FINANCE_HERMES_EXECUTABLE')
    if not executable or not Path(executable).is_absolute() or not Path(executable).is_file():
        raise SystemExit('Set FINANCE_HERMES_EXECUTABLE to the tested Hermes executable first.')
    with TemporaryDirectory(prefix='finance-cron-smoke-') as sandbox:
        root, home = Path(sandbox) / 'fictional clone', Path(sandbox) / 'profile'
        root.mkdir()
        home.mkdir()
        for source in ROOT.glob('finance_*.py'):
            shutil.copyfile(source, root / source.name)
        db = root / 'data/finance-cli/demo.db'
        TransactionStore(db).add_transaction(transaction_type='income', amount_rupiah=120,
            category='simulation', occurred_at='2025-12-29T09:00:00+07:00', idempotency_key='simulation')
        with closing(sqlite3.connect(db)) as conn:
            transactions = conn.execute('SELECT * FROM transactions').fetchall()
            conn.execute('CREATE TABLE emergency_movements (fixture INTEGER)')
        clock = root / 'finance_analysis.py'
        source = clock.read_text(encoding='utf-8')
        imports, entry = '\nimport json\n', "if __name__ == '__main__':"
        if source.count(imports) != 1 or source.count(entry) != 1:
            raise SystemExit('Analysis fixture injection points changed.')
        clock.write_text(source.replace(imports, '''
import sys
def _offline_fixture(event, args):
    if event.startswith('socket.') or (event == 'import' and args[0].split('.')[0] in
            {'openpyxl', 'finance_reporting', 'openai', 'anthropic', 'hermes', 'hermes_cli'}):
        raise AssertionError('Unexpected network or provider/reporting import in analysis')
sys.addaudithook(_offline_fixture)
import json
''').replace(entry, "_now = lambda: datetime.fromisoformat('2026-01-05T02:00:00Z')\n\n" + entry), encoding='utf-8')
        env = hermes_env(home)
        env.update(FINANCE_HERMES_EXECUTABLE=executable, TZ='UTC', HOME=sandbox, TMPDIR=sandbox,
                   USERPROFILE=sandbox, APPDATA=sandbox, LOCALAPPDATA=sandbox, TEMP=sandbox, TMP=sandbox)
        tool = (sys.executable, '-B', str(root / 'finance_cron.py'))

        def call(*args, expected=0):
            proc = subprocess.run(args, cwd=sandbox, env=env, stdin=subprocess.DEVNULL,
                                  capture_output=True, timeout=30)
            if proc.returncode != expected:
                step = args[3] if args[:3] == tool else 'Hermes or runner'
                detail = proc.stderr.decode('utf-8', errors='replace').strip() if args[:3] == tool else ''
                raise SystemExit(f'Temporary smoke failed at {step} (exit {proc.returncode}). {detail}')
            return proc.stderr if expected else proc.stdout

        install = (*tool, 'install', '--ledger', 'demo', '--confirm')
        store = home / 'cron/jobs.json'

        def read_job():
            job, = json.loads(store.read_text(encoding='utf-8'))['jobs']
            return job

        assert json.loads(call(*install))['state'] == 'paused'
        job = read_job()
        assert json.loads(call(*install))['state'] == 'paused'
        assert read_job()['id'] == job['id']
        assert job['enabled'] is False and job['no_agent'] is True and job['timezone'] == 'Asia/Pontianak'
        assert job['deliver'] == 'local' and job['failure_deliver'] == 'local'
        script = home / 'scripts' / job['script']
        assert Path(job['interpreter']) == Path(sys.executable).absolute()
        if os.name != 'nt':
            assert stat.S_IMODE(script.stat().st_mode) == 0o600
            assert stat.S_IMODE(script.parent.stat().st_mode) == 0o700

        call(executable, 'cron', 'tick')
        assert read_job()['last_run_at'] is None
        # Use the registered pair without activating even the disposable job.
        error = call(job['interpreter'], str(script), expected=1)
        assert b'Analisis gagal' in error and b'emergency_movements' not in error
        assert call(job['interpreter'], str(script)) == b''
        assert read_job()['enabled'] is False
        with closing(sqlite3.connect(db)) as conn:
            assert conn.execute('SELECT * FROM transactions').fetchall() == transactions
            assert conn.execute('SELECT kind, period, status, attempts FROM analysis_runs ORDER BY kind, period').fetchall() == [
                ('quarterly', '2026-Q1', 'failed', 1),
                *(('weekly', day, 'completed', 1) for day in ('2025-12-08', '2025-12-15', '2025-12-22', '2025-12-29')),
            ]
        assert not list(Path(sandbox).rglob('*.xlsx'))
        assert json.loads(call(*tool, 'uninstall'))['state'] == 'absent'
        assert not json.loads(store.read_text(encoding='utf-8'))['jobs']
        print('Hermes smoke: paused reinstall/tick, direct failure, bounded replay and removal OK')


if __name__ == '__main__':
    main()
