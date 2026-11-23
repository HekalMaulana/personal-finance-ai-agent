"""Opt-in integration smoke: disposable paused job, never starts a gateway."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from finance_cron import hermes_env
from finance_storage import TransactionStore


def main():
    executable = os.environ.get('FINANCE_HERMES_EXECUTABLE')
    if not executable or not Path(executable).is_absolute():
        raise SystemExit('Set FINANCE_HERMES_EXECUTABLE to the tested Hermes executable first.')
    with TemporaryDirectory(prefix='finance-cron-smoke-') as sandbox:
        root, home = Path(sandbox) / 'fictional clone', Path(sandbox) / 'profile'
        root.mkdir()
        home.mkdir()
        for source in ROOT.glob('finance_*.py'):
            shutil.copyfile(source, root / source.name)
        TransactionStore(root / 'data/finance-cli/demo.db')
        clock = root / 'finance_analysis.py'
        clock.write_text(clock.read_text(encoding='utf-8').replace(
            "if __name__ == '__main__':", "_now = lambda: datetime.fromisoformat('2026-01-05T02:00:00Z')\n\n"
            "if __name__ == '__main__':"), encoding='utf-8')
        env = hermes_env(home)
        env.update(FINANCE_HERMES_EXECUTABLE=executable, TZ='UTC')
        tool = (sys.executable, '-B', str(root / 'finance_cron.py'))

        def call(*args):
            proc = subprocess.run(args, cwd=root, env=env, capture_output=True, timeout=90)
            if proc.returncode:
                raise SystemExit(f'Temporary smoke failed at {args[-1] if args[-1] in ("--confirm", "uninstall") else "cron run"}.')
            return proc.stdout

        install = (*tool, 'install', '--ledger', 'demo', '--confirm')
        assert json.loads(call(*install))['state'] == 'paused'
        assert json.loads(call(*install))['state'] == 'paused'
        store = home / 'cron/jobs.json'
        job, = json.loads(store.read_text(encoding='utf-8'))['jobs']
        assert job['enabled'] is False and job['no_agent'] is True and job['timezone'] == 'Asia/Pontianak'
        assert job['deliver'] == 'local' and job['failure_deliver'] == 'local'
        # This Hermes build refuses manual dispatch of paused jobs. Keep the job paused and
        # exercise exactly its interpreter/script pair, without arming any scheduler.
        assert b'paused/disabled' in call(executable, 'cron', 'run', job['id'])
        script = home / 'scripts' / job['script']
        assert b'Minggu 2025-12-29:' in call(job['interpreter'], str(script))
        assert call(job['interpreter'], str(script)) == b''
        assert json.loads(store.read_text(encoding='utf-8'))['jobs'][0]['enabled'] is False
        assert not list(root.rglob('*.xlsx'))
        assert json.loads(call(*tool, 'uninstall'))['state'] == 'absent'
        assert not json.loads(store.read_text(encoding='utf-8'))['jobs']
        print('Hermes smoke: paused install/reinstall, local execution, silent replay, removal OK')


if __name__ == '__main__':
    main()
