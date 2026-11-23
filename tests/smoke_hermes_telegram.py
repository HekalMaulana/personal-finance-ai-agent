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
    probe_finance_hook(root, adapter, dm, loop)


def probe_finance_hook(root, adapter, dm, loop):
    from datetime import datetime, timezone
    from unittest.mock import patch
    from gateway.platforms.event import MessageEvent, MessageType
    from gateway.run_inbound_hooks import GatewayInboundHooksMixin
    from hermes_cli.plugins import PluginManager
    from hermes_cli.plugins_context import PluginContext
    from hermes_cli.plugins_manifest import PluginManifest

    sys.path.insert(0, str(root))
    from finance_storage import TransactionStore
    from finance_telegram_bridge import FinanceIngress, LedgerRequests

    path = root / 'bridge-fictional.db'
    ledger = TransactionStore(path)
    service = LedgerRequests(path, int(OWNER))
    manager = PluginManager()
    ctx = PluginContext(PluginManifest(name='finance-offline-fixture'), manager)
    replies = []

    async def reply(gateway, chat, text):
        assert gateway is runner and chat == OWNER
        replies.append(json.loads(text))

    # The optional Telegram SDK is absent on some offline hosts. Use a typed
    # fixture for its raw Message; run the actual Hermes hook dispatcher below.
    class RawMessage(SimpleNamespace):
        pass

    ingress = FinanceIngress(int(OWNER), RawMessage, adapter.platform, service.dispatch)
    ingress.register(ctx, reply)
    runner = GatewayInboundHooksMixin()

    async def dispatch(text, n, user=OWNER, **raw_fields):
        source = dm(user)
        raw = RawMessage(text=text, message_id=n, date=datetime.now(timezone.utc),
                         from_user=SimpleNamespace(id=int(user), is_bot=False),
                         chat=SimpleNamespace(id=int(user), type='private'), **raw_fields)
        event = MessageEvent(text=text, message_type=MessageType.COMMAND, source=source,
                             raw_message=raw, message_id=str(n), platform_update_id=n)
        return await runner._hm_pre_gateway_dispatch_hook(event, source)

    async def exercise():
        prepare = '/finance prepare ' + json.dumps(dict(transaction_type='expense', amount_rupiah=120,
            category='Fiktif', occurred_at='2026-01-01T12:00:00+07:00'))
        assert await dispatch('simulation only', 1) is not None
        assert await dispatch(prepare, 2, STRANGER) is None
        assert await dispatch(prepare, 3, forward_origin=object()) is None
        assert not replies
        assert await dispatch(prepare, 4) is None
        preview, = replies
        assert preview['status'] == 'prepared' and ledger.cash_flow().transaction_count == 0
        confirm = f"/finance confirm {preview['operation_id']} {preview['preview_digest']}"
        assert await dispatch(confirm, 5) is None
        assert replies[-1]['status'] == 'committed' and ledger.cash_flow().total_expense == 120
        assert await dispatch(confirm, 5) is None
        assert replies[-1] == {'error': 'replayed_message'}

    with patch('hermes_cli.lifecycle.ainvoke_hook', manager.ainvoke_hook):
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
        print('Hermes Telegram smoke: offline access gates, project context/skills and fictional summary OK')


if __name__ == '__main__':
    main()
