"""Opt-in Hermes v0.23.3 hook wiring for a fictional, isolated fixture.

Not an auto-loaded plugin, an agent tool, or a service launcher. Call only
from trusted gateway code; use the peer-checked IPC client on Linux.
"""

import asyncio
import logging

from finance_telegram_bridge import FinanceIngress, _owner_id

log = logging.getLogger(__name__)


def register(ctx, owner, dispatch, *, enabled=False, message_class=None):
    """Wire an operator-owned hook; message_class is for offline SDK fixtures."""
    if enabled is not True or not _owner_id(owner):
        return False

    from agent.estop import is_engaged
    from gateway.config import Platform
    from plugins.platforms.telegram.adapter import TelegramAdapter

    if message_class is None:
        from telegram import Message  # pyright: ignore[reportMissingImports]  # Optional Hermes SDK
        message_class = Message

    def connected_bot(gateway):
        adapter = gateway.adapters.get(Platform.TELEGRAM)
        return adapter._bot if isinstance(adapter, TelegramAdapter) else None

    def permit(gateway, source):
        # pre_gateway_dispatch runs before runner auth, ESTOP and drain gates.
        return (getattr(gateway, '_running', None) is True
                and getattr(gateway, '_draining', None) is False
                and getattr(gateway, '_external_drain_active', False) is False
                and not is_engaged() and connected_bot(gateway) is not None
                and gateway._is_user_authorized_for_source(source) is True)

    async def reply(gateway, chat, text):
        # Use the existing adapter's connected Bot API client. Adapter.send
        # interprets Markdown and can split or upload a document instead.
        # Bound the plain-text reply conservatively in UTF-16 code units.
        try:
            if len(text.encode('utf-16-le')) // 2 > 4096:
                raise ValueError('preview too long')
            bot = connected_bot(gateway)
            if bot is None:
                raise RuntimeError('Telegram adapter disconnected')
            async with asyncio.timeout(5):
                await bot.send_message(chat_id=int(chat), text=text, parse_mode=None,
                                       disable_web_page_preview=True)
        except Exception:
            # No transport details, payload or automatic resend. A missing final
            # reply does not undo a commit; a new status message can recover it.
            log.warning('Finance reply delivery unverified')

    FinanceIngress(owner, message_class, Platform.TELEGRAM, dispatch).register(ctx, reply, permit=permit)
    return True
