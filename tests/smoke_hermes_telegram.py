"""Offline smoke against the installed Hermes Python; never runs the gateway."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
OWNER, STRANGER = '123456789', '123456790'
FAKE_TOKEN = 'offline-fixture-not-a-bot-token'


def probe(root):
    import asyncio

    with asyncio.Runner() as loop:
        loop.get_loop()  # On Windows asyncio creates a private loopback socketpair.
        probe_with_loop(root, loop)


def probe_with_loop(root, loop):
    def offline(event, args):
        if event.startswith('socket.') and event not in {'socket.__new__', 'socket.gethostname'}:
            raise AssertionError(f'Unexpected network operation: {event}')
        if event == 'subprocess.Popen':
            raise AssertionError('Unexpected child process in Hermes probe')

    sys.addaudithook(offline)
    import gateway.run  # Loads the profile .env and bridges terminal.cwd to TERMINAL_CWD.
    from gateway.run_bootstrap import _start_gateway_resolve_terminal_cwd
    from gateway.config import Platform, load_gateway_config
    from gateway.authz_mixin import GatewayAuthorizationMixin
    from gateway.session import SessionSource
    from gateway.slash_access import policy_for_source
    from plugins.platforms.telegram.adapter import TelegramAdapter
    from agent.system_prompt import _context_files_part
    from agent.skill_utils import get_project_skills_dirs
    from hermes_cli.config import load_config
    from hermes_cli.tools_config import _get_platform_tools
    from model_tools import _select_tool_names
    from tools.skills_tool import skill_view, skills_list
    from tools.write_approval import SKILLS, write_approval_enabled

    config = load_gateway_config(strict=True)
    telegram = config.platforms[Platform.TELEGRAM]
    assert telegram.enabled and telegram.token == FAKE_TOKEN
    assert not telegram.home_channel
    assert {p for p, settings in config.platforms.items() if settings.enabled} == {Platform.TELEGRAM}
    assert telegram.extra['drop_pending_on_cold_boot'] is True
    assert not config.multiplex_profiles

    auth = GatewayAuthorizationMixin()
    auth.config = config
    auth.adapters = {}

    def dm(uid):
        return SessionSource(Platform.TELEGRAM, uid, chat_type='dm', user_id=uid)

    assert auth._is_user_authorized(dm(OWNER))
    assert not auth._is_user_authorized(dm(STRANGER))
    assert auth._get_unauthorized_dm_behavior(Platform.TELEGRAM) == 'ignore'
    del os.environ['TELEGRAM_ALLOWED_USERS']
    assert not auth._is_user_authorized(dm(OWNER)), 'Missing allowlist must default to deny'

    adapter = TelegramAdapter(telegram)
    assert adapter._telegram_allowed_chats() == {OWNER}
    assert not adapter._telegram_guest_mode()
    for chat_type in ('group', 'supergroup', 'channel'):
        message = SimpleNamespace(chat=SimpleNamespace(id=-1001234567890, type=chat_type),
                                  from_user=SimpleNamespace(id=int(OWNER), is_bot=False), text='/help')
        assert not adapter._should_process_message(message, is_command=True), chat_type

    _start_gateway_resolve_terminal_cwd()
    assert Path(os.environ['TERMINAL_CWD']).resolve() == root
    assert Path.cwd() != root, 'The probe must not succeed by inheriting the clone as process cwd'
    assert get_project_skills_dirs() == [root / '.hermes/skills']
    agent = SimpleNamespace(platform='telegram', skip_context_files=False)
    assert 'Gateway Telegram opsional' in ''.join(_context_files_part(agent, None, True))
    cfg = load_config()
    toolsets = _get_platform_tools(cfg, 'telegram')
    tools = _select_tool_names(sorted(toolsets), cfg['agent']['disabled_toolsets'], quiet_mode=True)
    assert tools == {'skills_list', 'skill_view', 'skill_manage'}, tools
    assert write_approval_enabled(SKILLS) and cfg['skills']['inline_shell'] is False
    commands = policy_for_source(config, dm(OWNER))
    assert not commands.is_admin(OWNER) and commands.can_run(OWNER, 'help')
    for command in ('sethome', 'cron', 'skills', 'approve', 'config', 'restart'):
        assert not commands.can_run(OWNER, command), command
    result = json.loads(skills_list())
    assert result['success']
    expected = {
        'finance-budgets', 'finance-emergency', 'finance-reporting',
        'finance-savings', 'finance-transactions', 'personal-finance-analysis',
    }
    assert expected <= {entry['name'] for entry in result['skills']}
    skill = json.loads(skill_view('finance-transactions', preprocess=False))
    assert skill['success'] and '--ledger lesson3-demo summary' in skill['content']
    # Restore the fixture allowlist for the real adapter command intake test.
    os.environ['TELEGRAM_ALLOWED_USERS'] = OWNER
    probe_finance_hook(root, adapter, auth, loop)


def probe_finance_hook(root, adapter, auth, loop):
    from datetime import datetime, timezone
    from unittest.mock import patch
    from agent.estop import sentinel_path
    from gateway.run_inbound import GatewayInboundMixin
    from hermes_cli.plugins import PluginManager
    from hermes_cli.plugins_context import PluginContext
    from hermes_cli.plugins_manifest import PluginManifest

    sys.path.insert(0, str(root))
    from finance_storage import TransactionStore
    from finance_telegram_bridge import LedgerRequests
    from finance_telegram_gateway import register

    path = root / 'bridge-fictional.db'
    ledger = TransactionStore(path)
    service = LedgerRequests(path, int(OWNER))
    manager = PluginManager()
    ctx = PluginContext(PluginManifest(name='finance-offline-fixture'), manager)
    replies, events, requests, attempts = [], [], [], []

    class RawMessage(SimpleNamespace):
        reply_to_message = None

    class Bot:
        fail = False

        async def send_message(self, *, chat_id, text, parse_mode, disable_web_page_preview, **kwargs):
            assert chat_id == int(OWNER) and parse_mode is None and disable_web_page_preview is True
            assert not kwargs, 'Finance replies must not use a thread or alternate route'
            attempts.append(json.loads(text))
            if self.fail:
                raise RuntimeError('simulated transport failure')
            replies.append(attempts[-1])
            return SimpleNamespace(message_id=len(replies))

    class Runner(GatewayInboundMixin):
        adapters = {adapter.platform: adapter}
        _running = True
        _draining = _external_drain_active = False
        _is_user_authorized_for_source = staticmethod(auth._is_user_authorized)

        def _scale_to_zero_note_real_inbound(self):
            pass  # No idle monitor in this fixture.

    runner = Runner()
    adapter._bot = Bot()

    def dispatch_request(envelope):
        requests.append(envelope)
        return service.dispatch(envelope)

    async def handle(event):
        events.append(event)
        assert await runner._hm_admit_event(event) is None, 'finance escaped to agent'

    async def deliver(text, n, user=OWNER, **raw_fields):
        raw = RawMessage(text=text, message_id=n, date=datetime.now(timezone.utc), entities=(),
                         from_user=SimpleNamespace(id=int(user), is_bot=False, full_name='Fixture'),
                         chat=SimpleNamespace(id=int(user), type='private', title=None), **raw_fields)
        await adapter._handle_command(SimpleNamespace(message=raw, update_id=n + 100), None)

    async def exercise():
        prepare = '/finance prepare ' + json.dumps(dict(transaction_type='expense', amount_rupiah=25000,
            category='Fiktif', description='A_* [`uji`](https://example.invalid)',
            occurred_at='2026-01-01T12:00:00+07:00'))
        assert not register(ctx, int(OWNER), dispatch_request, message_class=RawMessage)
        assert register(ctx, int(OWNER), dispatch_request, enabled=True, message_class=RawMessage)
        await deliver(prepare, 1, STRANGER)
        assert not events
        await deliver(prepare, 2, forward_origin=object())
        runner._draining = True
        await deliver(prepare, 3)
        runner._draining = False
        pause = sentinel_path()
        pause.touch()
        try:
            await deliver(prepare, 4)
        finally:
            pause.unlink()
        assert not requests and not replies
        del os.environ['TELEGRAM_ALLOWED_USERS']
        try:
            await deliver(prepare, 5)
            assert not requests and not replies
        finally:
            os.environ['TELEGRAM_ALLOWED_USERS'] = OWNER
        await deliver(prepare, 5)
        preview, = replies
        assert requests[0]['update'] == 105 and requests[0]['message'] == 5
        assert preview['status'] == 'prepared' and ledger.cash_flow().transaction_count == 0
        assert preview['parameters']['description'] == 'A_* [`uji`](https://example.invalid)'
        confirm = f"/finance confirm {preview['operation_id']} {preview['preview_digest']}"
        adapter._bot.fail = True
        await deliver(confirm, 6)
        assert len(attempts) == 2 and attempts[-1]['status'] == 'committed'
        assert replies == [preview] and ledger.cash_flow().total_expense == 25000
        adapter._bot.fail = False
        await deliver(f"/finance status {preview['operation_id']}", 7)
        assert replies[-1]['status'] == 'committed' and replies[-1]['transaction_id'] == attempts[1]['transaction_id']

    with patch.object(adapter, 'handle_message', handle), patch('hermes_cli.lifecycle.ainvoke_hook', manager.ainvoke_hook):
        loop.run(exercise())


def main():
    if not __debug__:
        raise SystemExit('Run this smoke without Python optimization.')
    if len(sys.argv) == 3 and sys.argv[1] == '--probe':
        if os.environ.get('TELEGRAM_SMOKE_CHILD') != '1':
            raise SystemExit('Launch the smoke without arguments.')
        probe(Path(sys.argv[2]).resolve())
        return
    if len(sys.argv) != 1:
        raise SystemExit('Run this smoke without arguments.')
    with TemporaryDirectory(prefix='finance-telegram-smoke-') as temp:
        sandbox = Path(temp).resolve()
        root, home = sandbox / 'fictional clone', sandbox / 'profile'
        root.mkdir()
        home.mkdir()
        # Copy only known project inputs, never existing data, secrets or Hermes state.
        for source in [ROOT / 'AGENTS.md', *ROOT.glob('finance_*.py'), *ROOT.glob('.hermes/skills/*/SKILL.md')]:
            target = root / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        (root / '.git').mkdir()  # Hermes project discovery uses the Git marker.
        env = {k: v for k, v in os.environ.items() if k.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT'}}
        env.update(HERMES_HOME=str(home), TELEGRAM_SMOKE_CHILD='1',
                   **dict.fromkeys(('HOME', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'TMPDIR', 'TMP', 'TEMP'), temp))

        def run(*args, payload=None):
            return subprocess.run([sys.executable, '-B', *map(str, args)], cwd=sandbox, env=env,
                                  input=payload or b'', stdout=subprocess.PIPE, check=True, timeout=60).stdout

        for key, value, force in (
            ('terminal.backend', 'local', False), ('terminal.cwd', root, False),
            ('gateway.multiplex_profiles', 'false', False), ('unauthorized_dm_behavior', 'ignore', False),
            ('platform_toolsets.telegram', '[skills]', True), ('skills.inline_shell', 'false', False),
            ('skills.write_approval', 'true', False), ('platforms.telegram.extra.allow_admin_from', '[0]', True),
            ('platforms.telegram.extra.drop_pending_on_cold_boot', 'true', True), ('approvals.mode', 'manual', False),
        ):
            flags = ('--force',) if force else ()
            run('-m', 'hermes_cli.main', 'config', 'set', *flags, key, value)
        run('-m', 'hermes_cli.main', 'skills', 'trust', root)
        (home / '.env').write_text(
            f'TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nTELEGRAM_ALLOWED_USERS={OWNER}\nTELEGRAM_ALLOWED_CHATS={OWNER}\n',
            encoding='utf-8',
        )
        run(Path(__file__).resolve(), '--probe', root)

        cli = root / 'finance_cli.py'
        record = json.loads(run(cli, '--ledger', 'telegram-smoke', 'add', payload=json.dumps({
            'transaction_type': 'expense', 'amount_rupiah': 120, 'category': 'simulation',
            'occurred_at': '2026-01-01T12:00:00+07:00', 'idempotency_key': 'offline-fixture',
        }).encode()))
        assert record['ok']
        db = root / 'data/finance-cli/telegram-smoke.db'
        before = db.read_bytes()
        result = json.loads(run(cli, '--ledger', 'telegram-smoke', 'summary', payload=b'{}'))
        assert result['ok'] and result['data']['total_expense'] == 120 and result['data']['transaction_count'] == 1
        assert db.read_bytes() == before
        assert not list(sandbox.rglob('*.xlsx'))
        print('Hermes Telegram smoke: offline adapter intake, trusted reply routing and Rp25,000 status recovery OK')


if __name__ == '__main__':
    main()
