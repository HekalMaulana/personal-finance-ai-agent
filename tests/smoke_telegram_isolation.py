"""Disposable Linux UID/SQLite/IPC acceptance probe. Run as root on native FS."""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE, GATEWAY, AGENT = 1, 33, 65534  # Existing Ubuntu test identities; no accounts created.
OWNER = 123


def run_as(uid, *args, gid=None, **kwargs):
    return subprocess.run(['setpriv', '--reuid', str(uid), '--regid', str(uid if gid is None else gid), '--clear-groups',
                           '--no-new-privs', sys.executable, '-IB', '-c', *args],
                          capture_output=True, text=True, check=True, timeout=15, **kwargs).stdout.strip()


def main():
    if not sys.platform.startswith('linux') or not __debug__ or os.geteuid() != 0:
        raise SystemExit('Run as Linux root without Python optimization, with an administrator-owned tmp dir.')
    with tempfile.TemporaryDirectory(prefix='finance-7c-') as temp:
        root = Path(temp)
        root.chmod(0o755)
        for name in ('finance_storage.py', 'finance_telegram.py', 'finance_telegram_bridge.py', 'finance_telegram_ipc.py'):
            shutil.copyfile(ROOT / name, root / name)
        private, endpoint = root / 'private', root / 'endpoint'
        private.mkdir(mode=0o700)
        os.chown(private, SERVICE, SERVICE)  # pyright: ignore[reportAttributeAccessIssue]
        endpoint.mkdir()
        os.chown(endpoint, SERVICE, GATEWAY)  # pyright: ignore[reportAttributeAccessIssue]
        endpoint.chmod(0o2750)
        db, sock = private / 'fictional.db', endpoint / 'ledger.sock'
        prefix = f'import sys; sys.path.insert(0, {temp!r}); from pathlib import Path; '
        run_as(SERVICE, prefix + f'from finance_storage import TransactionStore; TransactionStore(Path({str(db)!r}))')
        db.chmod(0o600)
        # Advance only the operation's monotonic clock, not incoming message timestamps.
        expire = root / 'advance-clock'
        service = prefix + f'''
import time
import finance_telegram_bridge as bridge
from finance_telegram_ipc import serve
class FixtureActions(bridge.TelegramActions):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, monotonic_clock=lambda: time.monotonic() + 301 * Path({str(expire)!r}).exists(), **kwargs)
bridge.TelegramActions = FixtureActions
serve(Path({str(sock)!r}), Path({str(db)!r}), owner={OWNER}, gateway_uid={GATEWAY})
'''
        client = prefix + (f'import json; from finance_telegram_ipc import request; '
                           f'print(json.dumps(request(Path({str(sock)!r}), {SERVICE}, json.loads(sys.argv[1]))))')

        def start():
            proc = subprocess.Popen(['setpriv', '--reuid', str(SERVICE), '--regid', str(SERVICE), '--clear-groups',
                                     '--no-new-privs', sys.executable, '-IB', '-c', service])
            for _ in range(100):
                if sock.is_socket() or proc.poll() is not None:
                    break
                time.sleep(.02)
            if not sock.is_socket() or proc.poll() is not None:
                proc.kill()
                proc.wait()
                raise AssertionError('Service did not start')
            return proc

        def payload(text, seq):
            return json.dumps(dict(user=OWNER, chat=OWNER, message=seq, update=seq, sent_at=time.time(), text=text))

        gateway = prefix + f'''
import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from finance_telegram_bridge import FinanceIngress
from finance_telegram_ipc import request
class RawMessage(NS):
    pass
item = json.loads(sys.argv[1])
serial = item['message']
raw = RawMessage(text=item['text'], chat=NS(id={OWNER}, type='private'),
                 from_user=NS(id={OWNER}, is_bot=False), message_id=serial,
                 date=datetime.fromtimestamp(item['sent_at'], timezone.utc))
source = NS(platform='telegram', user_id=str({OWNER}), chat_id=str({OWNER}),
            chat_type='dm', is_bot=False, thread_id=None)
event = NS(source=source, text=raw.text, raw_message=raw, internal=False,
           edit_revision=None, message_id=str(serial), platform_update_id=serial)
ingress = FinanceIngress({OWNER}, RawMessage, 'telegram',
                         lambda data: request(Path({str(sock)!r}), {SERVICE}, data))
class Hooks:
    def register_hook(self, name, callback):
        assert name == 'pre_gateway_dispatch'
        self.callback = callback
hooks = Hooks()
replies = []
async def reply(gateway, chat, text):
    assert chat == str({OWNER})
    replies.append(json.loads(text))
ingress.register(hooks, reply)
assert asyncio.run(hooks.callback(event=event, gateway=None)) == {{'action': 'skip'}}
assert len(replies) == 1
print(json.dumps(replies[0]))
'''

        def call(text, seq):
            return json.loads(run_as(GATEWAY, gateway, payload(text, seq)))

        def stop(proc):
            proc.terminate()
            proc.wait(timeout=5)
            sock.unlink()

        proc = start()
        try:
            for uid in (AGENT, GATEWAY):
                for mode, statement in (('ro', 'SELECT COUNT(*) FROM transactions'), ('rw', 'BEGIN IMMEDIATE')):
                    uri = db.as_uri() + '?mode=' + mode
                    script = f'__import__("sqlite3").connect({uri!r}, uri=True).execute({statement!r})'
                    result = subprocess.run(['setpriv', '--reuid', str(uid), '--regid', str(uid), '--clear-groups',
                                             '--no-new-privs', sys.executable, '-IB', '-c', script],
                                            capture_output=True, text=True, timeout=10)
                    assert result.returncode != 0 and ('Permission denied' in result.stderr
                                                      or 'unable to open database file' in result.stderr)
            prep = '/finance prepare {"transaction_type":"expense","amount_rupiah":25000,"category":"Fiktif","occurred_at":"2026-01-01T12:00:00+07:00"}'
            assert json.loads(run_as(AGENT, client, payload(prep, 1))) == {'error': 'ledger_unavailable'}
            # Even a different UID deliberately given socket-group access is refused.
            assert json.loads(run_as(AGENT, client, payload(prep, 1), gid=GATEWAY)) == {'error': 'ledger_unavailable'}
            wrong_server = client.replace(f', {SERVICE}, json.loads', f', {AGENT}, json.loads')
            assert json.loads(run_as(GATEWAY, wrong_server, payload(prep, 1))) == {'error': 'ledger_unavailable'}
            preview = call(prep, 1)
            assert preview['status'] == 'prepared' and preview['parameters']['amount_rupiah'] == 25000
            with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as conn:
                assert conn.execute('SELECT COUNT(*) FROM transactions').fetchone() == (0,)
            def confirm(op):
                return f"/finance confirm {op['operation_id']} {op['preview_digest']}"

            confirmation = confirm(preview)
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(lambda seq: call(confirmation, seq), (2, 3)))
            assert sorted(r.get('status', r.get('error')) for r in outcomes) == ['committed', 'operation_committed']
            committed = next(r for r in outcomes if r.get('status') == 'committed')
            canceled = call(prep, 4)
            assert call(f"/finance cancel {canceled['operation_id']}", 5)['status'] == 'canceled'
            assert call(confirm(canceled), 6) == {'error': 'operation_canceled'}
            expired = call(prep, 7)
            expire.touch()
            assert call(confirm(expired), 8) == {'error': 'operation_expired'}
            expire.unlink()
            pending = call(prep, 9)
            assert pending['status'] == 'prepared'
        finally:
            stop(proc)
        proc = start()
        try:
            assert call(confirmation, 2) == {'error': 'replayed_message'}
            result = call(f"/finance status {committed['operation_id']}", 10)
            assert result['status'] == 'committed' and result['transaction_id'] == committed['transaction_id']
            assert call(confirm(pending), 11) == {'error': 'operation_expired'}
            with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as conn:
                assert conn.execute('SELECT id, amount_rupiah FROM transactions').fetchall() == [
                    (committed['transaction_id'], 25000)]
            assert not list(root.rglob('*.xlsx'))
        finally:
            stop(proc)
    print('Linux isolation: Rp25,000 commit, cancel, expiry, concurrent confirm, replay and restart OK; SQLite/IPC denied to agent')


if __name__ == '__main__':
    main()
