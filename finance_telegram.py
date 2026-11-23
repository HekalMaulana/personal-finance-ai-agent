"""Offline Telegram action boundary. Not a Hermes tool, plugin or CLI.

Only a trusted caller may construct source from the actual inbound private
message (never model output, shell environment, session history or quotes).
This repository ships no production caller; tests simulate that boundary.
"""

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from finance_storage import (
    DEFAULT_DB_PATH, TransactionStore, _ADD_FIELDS, _add_payload, _operation_id,
    reject_hardlinked_ledger,
)

_TTL_SECONDS = 300
_PROCESS_CLOCK_EPOCH = str(uuid4())


def _clock_epoch() -> str:
    # Include PID so even a fork cannot extend the lifetime of a pending approval.
    return f"{os.getpid()}:{_PROCESS_CLOCK_EPOCH}"


_ADD_REQUIRED = set(_ADD_FIELDS) - {"description"}
_SCHEMA = """
CREATE TABLE IF NOT EXISTS telegram_financial_operations (
    operation_id TEXT PRIMARY KEY NOT NULL,
    owner_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    prepared_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    prepared_monotonic REAL NOT NULL,
    clock_epoch TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'prepared' CHECK (state IN ('prepared', 'committed', 'canceled')),
    decided_at REAL,
    transaction_id TEXT UNIQUE REFERENCES transactions(id)
)
"""


class ActionRejected(ValueError):
    """A fail-closed decision; the message is a stable error code."""


@dataclass(frozen=True)
class TelegramSource:
    """Trusted adapter input, not proof by itself. message_text must be original."""

    user_id: str
    chat_id: str
    chat_type: str
    message_text: str


class TelegramActions:
    """Bound actions on an existing, operator-selected fictional ledger.

    The owner set, path, source and clock are trusted caller inputs, separate
    from the request. Do not expose this constructor or source to agent tools.
    """

    def __init__(self, path: Path, *, owners: set[str] | None = None,
                 clock: Callable[[], float] = time.time,
                 monotonic_clock: Callable[[], float] = time.monotonic) -> None:
        self._path = path.absolute()
        self._owners = frozenset(owners or ())
        self._clock = clock
        self._monotonic_clock = monotonic_clock

    def handle(self, action: str, request: dict[str, Any], *,
               source: TelegramSource | None = None) -> dict[str, Any]:
        """Dispatch a strict request; require original explicit text for decisions."""
        if (type(source) is not TelegramSource or type(source.user_id) is not str
                or not re.fullmatch(r"[1-9][0-9]{0,19}", source.user_id)
                or source.user_id not in self._owners or type(source.chat_type) is not str
                or source.chat_type != "dm" or type(source.chat_id) is not str
                or source.chat_id != source.user_id or type(source.message_text) is not str):
            raise ActionRejected("unauthorized_source")
        if type(action) is not str or action not in ("prepare", "status", "confirm", "cancel"):
            raise ActionRejected("unsupported_action")
        if type(request) is not dict or any(type(key) is not str for key in request):
            raise ActionRejected("invalid_request")
        if action == "prepare":
            if (request.keys() != {"operation_type", "parameters"}
                    or type(request["operation_type"]) is not str
                    or request["operation_type"] != "transaction.add"):
                raise ActionRejected("invalid_request")
            parameters = request["parameters"]
            if (type(parameters) is not dict or any(type(key) is not str for key in parameters)
                    or not _ADD_REQUIRED <= parameters.keys() <= set(_ADD_FIELDS)):
                raise ActionRejected("invalid_parameters")
            payload = _add_payload(parameters["transaction_type"], parameters["amount_rupiah"],
                                   parameters["category"], parameters.get("description"), parameters["occurred_at"])
            return self._prepare(source, dict(zip(_ADD_FIELDS, payload)))

        fields = {"operation_id", "preview_digest"} if action == "confirm" else {"operation_id"}
        if request.keys() != fields or type(request["operation_id"]) is not str:
            raise ActionRejected("invalid_request")
        operation_id = _operation_id(request["operation_id"])
        digest = request.get("preview_digest")
        if action == "confirm":
            if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ActionRejected("invalid_request")
            if source.message_text != f"confirm {operation_id} {digest}":
                raise ActionRejected("explicit_confirmation_required")
        if action == "cancel" and source.message_text != f"cancel {operation_id}":
            raise ActionRejected("explicit_cancellation_required")
        return self._resolve(action, operation_id, digest, source)

    def _store(self, *, read_only: bool = False) -> TransactionStore:
        if self._path == DEFAULT_DB_PATH or self._path.resolve() != self._path:
            raise ActionRejected("invalid_ledger")
        reject_hardlinked_ledger(self._path)
        return TransactionStore(self._path, read_only=read_only, defer_init=True)

    def _prepare(self, source: TelegramSource, parameters: dict[str, Any]) -> dict[str, Any]:
        operation_id = str(uuid4())
        with self._store()._connection(existing=True) as conn:
            conn.execute("BEGIN IMMEDIATE")
            now, steady = self._clock(), self._monotonic_clock()
            conn.execute(_SCHEMA)
            row = conn.execute("""INSERT INTO telegram_financial_operations
                (operation_id, owner_id, chat_id, operation_type, parameters_json, prepared_at, expires_at,
                 prepared_monotonic, clock_epoch)
                VALUES (?, ?, ?, 'transaction.add', ?, ?, ?, ?, ?) RETURNING *""",
                (operation_id, source.user_id, source.chat_id, json.dumps(parameters, sort_keys=True),
                 now, now + _TTL_SECONDS, steady, _clock_epoch())).fetchone()
            return _view(row, steady)

    def _resolve(self, action: str, operation_id: str, digest: str | None,
                 source: TelegramSource) -> dict[str, Any]:
        with self._store(read_only=action == "status")._connection(existing=True) as conn:
            conn.execute("BEGIN" if action == "status" else "BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM sqlite_schema WHERE type = 'table' "
                            "AND name = 'telegram_financial_operations'").fetchone() is None:
                raise ActionRejected("operation_not_found")
            row = conn.execute("""SELECT * FROM telegram_financial_operations
                WHERE operation_id = ? AND owner_id = ? AND chat_id = ?""",
                (operation_id, source.user_id, source.chat_id)).fetchone()
            if row is None:
                raise ActionRejected("operation_not_found")
            now, steady = self._clock(), self._monotonic_clock()
            view = _view(row, steady)
            if action == "status":
                return view
            if view["status"] != "prepared":
                raise ActionRejected("operation_" + view["status"])
            transaction_id = None
            state = "canceled"
            if action == "confirm":
                if digest != view["preview_digest"]:
                    raise ActionRejected("preview_mismatch")
                if row["operation_type"] != "transaction.add":
                    raise ActionRejected("unsupported_operation")
                payload = _add_payload(**view["parameters"])
                transaction = TransactionStore._save_add(conn, "telegram:" + operation_id, payload)
                state, transaction_id = "committed", transaction.id
            updated = conn.execute("""UPDATE telegram_financial_operations
                SET state = ?, decided_at = ?, transaction_id = ? WHERE operation_id = ? RETURNING *""",
                (state, now, transaction_id, operation_id)).fetchone()
            return _view(updated, steady)


def _view(row, steady: float) -> dict[str, Any]:
    preview = {key: row[key] for key in ("operation_id", "operation_type", "prepared_at", "expires_at")}
    preview["parameters"] = json.loads(row["parameters_json"])
    binding = dict(preview, owner_id=row["owner_id"], chat_id=row["chat_id"])
    preview["preview_digest"] = hashlib.sha256(json.dumps(binding, sort_keys=True).encode("ascii")).hexdigest()
    state = row["state"]
    if state == "prepared" and (row["clock_epoch"] != _clock_epoch() or not math.isfinite(steady)
                                or not row["prepared_monotonic"] <= steady < row["prepared_monotonic"] + _TTL_SECONDS):
        state = "expired"
    return dict(preview, status=state, transaction_id=row["transaction_id"], decided_at=row["decided_at"])
