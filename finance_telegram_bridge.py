"""Lesson 7C offline bridge components. No CLI, model tool or auto-loaded plugin.

Only the trusted Hermes gateway process may run the ingress callback; the
local ledger endpoint must never trust a client sharing an agent tool's UID.
"""

import asyncio
import json
import re
import sqlite3
import time
from datetime import datetime

from finance_telegram import ActionRejected, TelegramActions, TelegramSource

_PREFIX = re.compile(r'^/finance(?=\s|$|@)', re.IGNORECASE)
_MAX_TEXT = 4096
_MAX_AGE = 300


def _owner_id(value):
    return type(value) is int and 0 < value < 2**52


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON field')
        result[key] = value
    return result


class FinanceIngress:
    """Convert an original gateway MessageEvent, not a session or prompt, to a request."""

    def __init__(self, owner, message_class, platform, dispatch):
        self._owner = owner if _owner_id(owner) else None
        self._message_class = message_class
        self._platform = platform
        self._dispatch = dispatch

    def receive(self, event):
        raw = getattr(event, 'raw_message', None)
        text = getattr(raw, 'text', None)
        routed_text = getattr(event, 'text', None)
        if not any(type(t) is str and _PREFIX.match(t) for t in (text, routed_text)):
            return False, None
        source = getattr(event, 'source', None)
        sender = getattr(raw, 'from_user', None)
        chat = getattr(raw, 'chat', None)
        uid, chat_id = getattr(sender, 'id', None), getattr(chat, 'id', None)
        serial, update = getattr(raw, 'message_id', None), getattr(event, 'platform_update_id', None)
        date = getattr(raw, 'date', None)
        if (self._owner is None or not isinstance(raw, self._message_class)
                or not _owner_id(uid) or not _owner_id(chat_id) or uid != chat_id or uid != self._owner
                or getattr(sender, 'is_bot', None) is not False or getattr(chat, 'type', None) != 'private'
                or getattr(source, 'platform', None) != self._platform or getattr(source, 'chat_type', None) != 'dm'
                or getattr(source, 'user_id', None) != str(uid) or getattr(source, 'chat_id', None) != str(chat_id)
                or getattr(source, 'thread_id', None) is not None or getattr(source, 'is_bot', None) is not False
                or getattr(event, 'internal', None) is not False or getattr(event, 'edit_revision', None) is not None
                or getattr(event, 'allow_gateway_control', True) is not True
                or any(getattr(raw, key, None) is not None for key in (
                    'edit_date', 'forward_origin', 'forward_date', 'sender_chat', 'via_bot',
                    'business_connection_id', 'guest_query_id', 'message_thread_id', 'reply_to_message',
                    'external_reply', 'quote'))
                or not _owner_id(serial) or not _owner_id(update) or event.message_id != str(serial)
                or type(date) is not datetime or date.utcoffset() is None
                or type(text) is not str or text != routed_text or not _PREFIX.match(text)):
            return True, None
        return True, self._dispatch({'user': uid, 'chat': chat_id, 'message': serial, 'update': update,
                                     'sent_at': date.timestamp(), 'text': text})

    def register(self, ctx, reply):
        """Trusted operator/harness wiring for Hermes's official pre-dispatch hook.

        `reply` is a trusted async transport function (gateway, chat ID, JSON).
        A handled finance message is consumed even when IPC or delivery fails.
        """
        async def hook(*, event, gateway, **_):
            try:
                consumed, result = await asyncio.to_thread(self.receive, event)
                if not consumed:
                    return None
                if result is not None:
                    await reply(gateway, str(self._owner), json.dumps(result, ensure_ascii=True))
            except Exception:
                # Do not let the SDK, socket or error details reach a model or the reply.
                pass
            return {'action': 'skip'}

        ctx.register_hook('pre_gateway_dispatch', hook)


class LedgerRequests:
    """Only callable behind the authenticated local endpoint, never through a tool."""

    def __init__(self, path, owner, *, clock=time.time):
        self._owner = owner if _owner_id(owner) else None
        self._clock = clock
        self._actions = TelegramActions(path, owners={str(self._owner)}, clock=clock)

    def dispatch(self, envelope):
        try:
            return self._dispatch(envelope)
        except ActionRejected as exc:
            return {'error': str(exc)}
        except (ValueError, OverflowError, RecursionError):
            return {'error': 'invalid_request'}
        except (OSError, sqlite3.Error):
            return {'error': 'ledger_unavailable'}

    def _dispatch(self, envelope):
        if type(envelope) is not dict or envelope.keys() != {'user', 'chat', 'message', 'update', 'sent_at', 'text'}:
            raise ActionRejected('invalid_envelope')
        uid, chat, serial, update, sent, text = (envelope[key] for key in (
            'user', 'chat', 'message', 'update', 'sent_at', 'text'))
        if (self._owner is None or not _owner_id(uid) or uid != self._owner or not _owner_id(chat) or chat != uid
                or not _owner_id(serial) or not _owner_id(update)):
            raise ActionRejected('unauthorized_source')
        if type(sent) not in (int, float) or not -5 <= self._clock() - sent < _MAX_AGE:
            raise ActionRejected('stale_message')
        if type(text) is not str or len(text) > _MAX_TEXT or not text.startswith('/finance '):
            raise ActionRejected('invalid_request')
        original = text[len('/finance '):]
        action, _, args = original.partition(' ')
        if action == 'prepare':
            request = {'operation_type': 'transaction.add', 'parameters': json.loads(args, object_pairs_hook=_unique_object)}
        elif action in ('status', 'confirm', 'cancel'):
            fields = args.split(' ')
            if len(fields) != (2 if action == 'confirm' else 1) or not all(fields):
                raise ActionRejected('invalid_request')
            request = {'operation_id': fields[0]}
            if action == 'confirm':
                request['preview_digest'] = fields[1]
        else:
            raise ActionRejected('unsupported_action')

        # Claim before acting. A crash between claim and action burns the message;
        # never redo an uncertain write. Ask with a new status message instead.
        with self._actions._store()._connection(existing=True) as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('''CREATE TABLE IF NOT EXISTS telegram_bridge_receipts (
                chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL,
                PRIMARY KEY (chat_id, message_id))''')
            if not conn.execute('INSERT OR IGNORE INTO telegram_bridge_receipts VALUES (?, ?)', (chat, serial)).rowcount:
                raise ActionRejected('replayed_message')
        return self._actions.handle(action, request, source=TelegramSource(str(uid), str(chat), 'dm', original))
