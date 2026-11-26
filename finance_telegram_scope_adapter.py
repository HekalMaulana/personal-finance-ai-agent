"""Offline-only, alternative Hermes Telegram adapter for Lesson 8A.

Reuse Hermes's transport, not its general gateway/agent dispatch. Not an
installed plugin, launcher or replacement for the Lesson 7 ledger fixture.
"""
import asyncio
import logging

from plugins.platforms.telegram.adapter import TelegramAdapter

from finance_telegram_scope import reply_for_text

log = logging.getLogger(__name__)


class FinanceScopeTelegramAdapter(TelegramAdapter):
    def __init__(self, config, *, owner: int):
        if type(owner) is not int or not 0 < owner < 2**52:
            raise ValueError('One numeric Telegram owner is required')
        super().__init__(config)
        self._finance_owner = owner

    def _wire_plugin_handlers(self, native=None):
        # Don't load additional native Telegram handlers into this route.
        return None

    def _start_post_connect_housekeeping(self):
        # No Hermes slash menus, auto-topics or status indicator.
        return None

    async def handle_message(self, event):
        # A synthetic or delayed event must never reach the gateway callback.
        return None

    def _register_handlers(self, app):
        from telegram import Message, Update  # pyright: ignore[reportMissingImports]  # Optional Hermes SDK
        from telegram.ext import TypeHandler  # pyright: ignore[reportMissingImports]

        if not isinstance(app.handlers, dict) or app.handlers:
            raise RuntimeError('Finance scope requires an empty Telegram handler table')

        async def receive(update, context):
            raw = getattr(update, 'message', None)  # Never use effective_message: includes edits and guests.
            if not isinstance(update, Update) or not isinstance(raw, Message):
                return
            sender, chat, text = (getattr(raw, key, None) for key in ('from_user', 'chat', 'text'))
            uid, chat_id = getattr(sender, 'id', None), getattr(chat, 'id', None)
            if (type(uid) is not int or type(chat_id) is not int or uid != self._finance_owner or chat_id != uid
                    or getattr(sender, 'is_bot', None) is not False or getattr(chat, 'type', None) != 'private'
                    or any(getattr(raw, key, None) is not None for key in (
                        'edit_date', 'forward_origin', 'forward_date', 'sender_chat', 'via_bot',
                        'business_connection_id', 'guest_query_id', 'message_thread_id', 'reply_to_message',
                        'external_reply', 'quote')) or type(text) is not str):
                return
            # Only pure, fixed finance calculations are reachable; no model or tool executor.
            try:
                if self._bot is not None:
                    async with asyncio.timeout(5):
                        await self._bot.send_message(chat_id=uid, text=reply_for_text(text),
                                                     parse_mode=None, disable_web_page_preview=True)
            except Exception:
                log.warning('Finance scope reply delivery unverified')

        # Every update is routed here instead of the inherited command/media/etc. handlers.
        app.add_handler(TypeHandler(Update, receive, block=True))
