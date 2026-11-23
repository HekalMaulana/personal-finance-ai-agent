"""Opt-in lifecycle for one local, script-only Hermes cron job per profile."""

import argparse
import ast
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, NoReturn

from finance_cron_runner import engine

NAME = 'personal-finance-hermes-6b'
SCRIPT = NAME + '.py'
SCHEDULE = '0 9 * * *'
ZONE = 'Asia/Pontianak'
_MARKER = b'# Managed by personal-finance-hermes Lesson 6B.\n'
_BINDING = '_INSTALLED: tuple[str, str] | None = None'


def _plain(path: Path, *, directory: bool = False) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    regular = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    if not regular or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError('Target Hermes bukan file atau direktori lokal biasa.')
    return True


@contextmanager
def _lock(home: Path) -> Iterator[None]:
    path = home / (NAME + '.lock')
    _plain(path)
    with path.open('a+b') as handle:
        handle.seek(0)
        if sys.platform == 'win32':
            import msvcrt
            # Windows permits locking one byte past EOF; closing releases it on exit/crash.
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


class Scheduler:
    def __init__(self, home: Path, root: Path, python: Path, cli: Callable[..., str]) -> None:
        self.home, self.root, self.python, self.cli = home, root, python, cli
        self.script = home / 'scripts' / SCRIPT
        self.owner = home / (NAME + '.id')

    def _job(self, *, created_id: str | None = None) -> dict[str, Any] | None:
        # The verified Hermes CLI has no JSON list option. Read its atomic store, never edit it.
        if not _plain(self.home / 'cron', directory=True):
            return None
        path = self.home / 'cron/jobs.json'
        if not _plain(path):
            return None
        doc = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(doc, dict) or not isinstance(doc.get('jobs'), list):
            raise ValueError('Format penyimpanan cron Hermes tidak didukung.')
        owner = created_id
        if owner is None and _plain(self.owner):
            owner = self.owner.read_text(encoding='ascii').strip()
            if not re.fullmatch(r'[0-9a-f]{12}', owner):
                raise ValueError('Catatan kepemilikan job tidak valid.')
        matches = []
        for job in doc['jobs']:
            if not isinstance(job, dict):
                raise ValueError('Format penyimpanan cron Hermes tidak didukung.')
            script = job.get('script')
            same_script = isinstance(script, str) and Path(script.replace('\\', '/')).name.casefold() == SCRIPT
            if (owner is not None and job.get('id') == owner) or str(job.get('name', '')).casefold() == NAME or same_script:
                matches.append(job)
        if not matches:
            return None
        if (len(matches) != 1 or matches[0].get('name') != NAME or matches[0].get('script') != SCRIPT
                or not re.fullmatch(r'[0-9a-f]{12}', str(matches[0].get('id', '')))):
            raise ValueError('Benturan nama atau skrip scheduler; periksa profil secara manual.')
        if owner != matches[0]['id']:
            raise ValueError('ID job tidak dikenal oleh installer; tidak diadopsi atau diubah.')
        return matches[0]

    def _current_script(self) -> bytes | None:
        if not _plain(self.script.parent, directory=True) or not _plain(self.script):
            return None
        current = self.script.read_bytes()
        if not current.startswith(_MARKER):
            raise ValueError('Skrip lokal bukan milik installer; tidak ditimpa.')
        return current

    def _payload(self, ledger: str) -> bytes:
        source = (self.root / 'finance_cron_runner.py').read_text(encoding='utf-8')
        if source.count(_BINDING) != 1:
            raise ValueError('Template runner tidak kompatibel.')
        return _MARKER + source.replace(_BINDING, f'_INSTALLED = {(str(self.root), ledger)!r}').encode('utf-8')

    def _bound_ledger(self, current: bytes) -> str | None:
        try:
            line, = (line for line in current.decode('utf-8').splitlines() if line.startswith('_INSTALLED = '))
            root, ledger = ast.literal_eval(line.removeprefix('_INSTALLED = '))
            if (root == str(self.root) and isinstance(ledger, str)
                    and re.fullmatch(r'[a-z][a-z0-9-]{0,47}', ledger) is not None
                    and current == self._payload(ledger)):
                return ledger
        except (SyntaxError, TypeError, ValueError):
            pass
        return None

    @staticmethod
    def _stage(target: Path, payload: bytes) -> None:
        target.parent.mkdir(mode=0o700, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            temp = Path(handle.name)
            try:
                handle.write(payload)
                handle.close()
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)

    @staticmethod
    def _safe(job: dict[str, Any]) -> bool:
        if job.get('enabled') is True and job.get('state') == 'scheduled':
            try:
                next_run = datetime.fromisoformat(job['next_run_at'])
                valid_state = (next_run.utcoffset() is not None and
                               next_run.astimezone(timezone(timedelta(hours=7))).strftime('%H:%M:%S') == '09:00:00')
            except (KeyError, TypeError, ValueError, OverflowError):
                valid_state = False
        else:
            valid_state = job.get('enabled') is False and job.get('state') == 'paused'
        return (valid_state and job.get('wrap_response') is False and job.get('no_agent') is True and job.get('deliver') in ('local', ['local'])
                and job.get('failure_deliver') == 'local' and job.get('timezone') == ZONE
                and job.get('catch_up') is True and job.get('state') in ('paused', 'scheduled')
                and isinstance(job.get('schedule'), dict) and job['schedule'].get('kind') == 'cron'
                and job['schedule'].get('expr') == SCHEDULE and isinstance(job.get('repeat'), dict)
                and job['repeat'].get('times') is None and not job.get('monitor_script') and not job.get('monitor_url'))

    def _status(self) -> dict[str, Any]:
        job = self._job()
        if job is None:
            return {'state': 'absent'}
        try:
            current = self._current_script()
            if (not self._safe(job) or not self.python.is_file() or job.get('interpreter') != str(self.python)
                    or current is None or self._bound_ledger(current) is None):
                return {'state': 'drifted'}
        except (OSError, ValueError):
            return {'state': 'drifted'}
        return {'state': 'active' if job.get('enabled') is True else 'paused',
                'schedule': SCHEDULE, 'timezone': ZONE, 'delivery': 'local'}

    def _preflight(self, ledger: str) -> None:
        if not self.python.is_file():
            raise ValueError('Interpreter proyek belum tersedia.')
        try:
            engine(self.root, ledger, 'check-due')
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise ValueError('Ledger fiktif tidak bisa diperiksa; jalankan dry-run.') from exc

    def apply(self, operation: str, *, ledger: str | None = None, confirm: bool = False) -> dict[str, Any]:
        if operation == 'status':
            return self._status()
        if operation in ('install', 'resume') and not confirm:
            raise ValueError('Gunakan --confirm untuk mengizinkan operasi ini.')
        if operation == 'install':
            if ledger is None:
                raise ValueError('Pilih ledger fiktif dengan --ledger.')
            self._preflight(ledger)
            help_text = self.cli('create', '--help')
            required = {'--no-agent', '--script', '--interpreter', '--timezone', '--paused', '--deliver',
                        '--failure-deliver', '--catch-up', '--no-wrap-response'}
            if not required <= set(re.findall(r'--[a-z-]+', help_text)):
                raise ValueError('Hermes cron tidak mendukung semua opsi aman; gunakan runner manual.')
        with _lock(self.home):
            return self._apply_locked(operation, ledger)

    def _apply_locked(self, operation: str, ledger: str | None) -> dict[str, Any]:
        job = self._job()
        if operation == 'pause':
            if job is None:
                return {'state': 'absent'}
            if job.get('enabled') is not False or job.get('state') != 'paused':
                self.cli('pause', job['id'])
            paused = self._job()
            if paused is None or paused.get('enabled') is not False or paused.get('state') != 'paused':
                raise ValueError('Pause tidak terverifikasi.')
            return {'state': 'paused'}
        current = self._current_script()
        if operation == 'install' and ledger is not None:
            payload = self._payload(ledger)
            if job is None:
                if current != payload:
                    self._stage(self.script, payload)
                _plain(self.owner)
                output = self.cli('create', SCHEDULE, '--name', NAME, '--script', SCRIPT, '--no-agent',
                         '--interpreter', str(self.python), '--timezone', ZONE, '--deliver', 'local',
                         '--failure-deliver', 'local', '--catch-up', 'on', '--no-wrap-response', '--paused')
                clean = re.sub(r'\x1b\[[0-9;]*m', '', output)
                match = re.search(r'^Created job: ([0-9a-f]{12})\s*$', clean, re.MULTILINE)
                created = self._job(created_id=match[1]) if match else None
                if created is None or not self._safe(created) or created.get('enabled') is not False:
                    raise ValueError('ID job paused tidak terverifikasi; periksa profil secara manual.')
                self._stage(self.owner, (created['id'] + '\n').encode('ascii'))
                expected = 'paused'
            else:
                if not self._safe(job):
                    raise ValueError('Konfigurasi job berubah; periksa atau uninstall sebelum memasang ulang.')
                if current != payload or job.get('interpreter') != str(self.python):
                    if job.get('enabled') is not False or job.get('state') != 'paused':
                        raise ValueError('Pause job sebelum mengganti clone, ledger, atau interpreter.')
                    if job.get('interpreter') != str(self.python):
                        self.cli('edit', job['id'], '--interpreter', str(self.python))
                    if current != payload:
                        self._stage(self.script, payload)
                expected = 'active' if job.get('enabled') is True else 'paused'
        elif operation == 'uninstall':
            if job is not None:
                if current is None:
                    raise ValueError('Skrip milik installer tidak ditemukan; periksa job di Hermes secara manual.')
                self.cli('remove', job['id'])
            if self._job() is not None:
                raise ValueError('Penghapusan job tidak terverifikasi; skrip dipertahankan.')
            if current is not None:
                self.script.unlink()
            if _plain(self.owner):
                self.owner.unlink()
            expected = 'absent'
        elif operation == 'resume':
            if job is None:
                raise ValueError('Job belum terpasang.')
            bound = self._bound_ledger(current) if current is not None else None
            if not self._safe(job) or bound is None or job.get('interpreter') != str(self.python):
                raise ValueError('Job tidak cocok dengan konfigurasi aman; pasang ulang sebelum resume.')
            self._preflight(bound)
            if job.get('enabled') is False:
                self.cli('resume', job['id'])
            expected = 'active'
        else:
            raise ValueError('Operasi scheduler tidak valid.')
        result = self._status()
        if result['state'] != expected:
            raise ValueError('Perubahan job tidak terverifikasi; periksa status sebelum mengulang.')
        return result


def hermes_env(home: Path) -> dict[str, str]:
    # Keep only process/platform essentials, never inherited credentials or session routing.
    allowed = {'PATH', 'HOME', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'SYSTEMROOT', 'WINDIR',
               'TEMP', 'TMP', 'TMPDIR', 'COMSPEC', 'PATHEXT', 'LANG', 'LC_ALL', 'TZ', 'XDG_RUNTIME_DIR'}
    return {**{key: value for key, value in os.environ.items() if key.upper() in allowed},
            'HERMES_HOME': str(home)}


def _cli(home: Path) -> Callable[..., str]:
    override = os.environ.get('FINANCE_HERMES_EXECUTABLE')
    executable = override or shutil.which('hermes.exe' if os.name == 'nt' else 'hermes')
    if not executable or not Path(executable).is_absolute() or not Path(executable).is_file():
        raise ValueError('Hermes CLI tidak tersedia; gunakan runner manual atau FINANCE_HERMES_EXECUTABLE absolut.')
    if os.name == 'nt' and Path(executable).suffix.casefold() != '.exe':
        raise ValueError('Di Windows gunakan executable Hermes .exe, bukan skrip shell.')
    env = hermes_env(home)

    def invoke(*args: str) -> str:
        try:
            process = subprocess.run([executable, 'cron', *args], env=env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError('Hermes cron gagal atau tidak mendukung operasi ini; periksa CLI lokal.') from exc
        return process.stdout.decode('utf-8', errors='replace')

    return invoke


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError('Argumen tidak valid; lihat --help.')


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent
    parser = _Parser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest='operation', required=True)
    for name in ('install', 'status', 'dry-run', 'pause', 'resume', 'uninstall'):
        command = commands.add_parser(name, allow_abbrev=False)
        if name in ('install', 'dry-run'):
            command.add_argument('--ledger', required=True)
        if name in ('install', 'resume'):
            command.add_argument('--confirm', action='store_true')
    try:
        args = parser.parse_args(argv)
        if args.operation == 'dry-run':
            from finance_cron_runner import main as runner
            return runner(['--ledger', args.ledger, 'dry-run'])
        value = os.environ.get('HERMES_HOME', '')
        if not value or not Path(value).is_absolute() or not Path(value).is_dir():
            raise ValueError('Tetapkan HERMES_HOME ke folder profil yang sudah ada (path absolut).')
        home = Path(value).resolve(strict=True)
        if home == root or root in home.parents:
            raise ValueError('Folder Hermes harus di luar clone.')
        python = Path(sys.executable).absolute()  # Do not resolve away a venv symlink.
        cli: Callable[..., str] = _status_only
        if args.operation != 'status':
            cli = _cli(home)
        scheduler = Scheduler(home, root, python, cli)
        result = scheduler.apply(args.operation, ledger=getattr(args, 'ledger', None),
                                 confirm=getattr(args, 'confirm', False))
    except json.JSONDecodeError:
        print('Penyimpanan cron Hermes bukan JSON yang valid; tidak diubah.', file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, RuntimeError):
        print('Akses scheduler gagal atau sedang dikunci; periksa profil secara lokal.', file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


def _status_only(*args: str) -> NoReturn:
    raise RuntimeError


if __name__ == '__main__':
    raise SystemExit(main())
