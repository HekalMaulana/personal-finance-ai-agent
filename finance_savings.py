"""User-reported savings allocations, separate from cash flow and emergency funds."""

import sqlite3
from datetime import datetime
from json import dumps, loads
from pathlib import Path
from typing import Any
from uuid import uuid4

from finance_budgets import BudgetStore
from finance_emergency import InsufficientFund
from finance_storage import (MAX_AMOUNT, PONTIANAK, IdempotencyConflict, StaleVersion,
                             _amount, _day, _description, _local_iso, _text, _transaction_id)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS savings_events (
    id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 0),
    kind TEXT NOT NULL CHECK (kind IN ('create', 'update', 'opening', 'opening_adjustment', 'deposit', 'withdrawal')),
    name TEXT NOT NULL,
    target_rupiah INTEGER NOT NULL CHECK (typeof(target_rupiah) = 'integer' AND target_rupiah > 0),
    due_date TEXT,
    opening_rupiah INTEGER CHECK (opening_rupiah IS NULL OR (typeof(opening_rupiah) = 'integer' AND opening_rupiah >= 0)),
    balance_rupiah INTEGER CHECK (balance_rupiah IS NULL OR (typeof(balance_rupiah) = 'integer' AND balance_rupiah >= 0)),
    recorded_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    request_json TEXT NOT NULL,
    PRIMARY KEY (id, revision)
)
"""


class SavingsNotFound(ValueError):
    """No savings goal matches the requested ID."""


def _nonnegative(value: int, field: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_AMOUNT:
        raise ValueError(f'{field} harus integer antara 0 dan 2^63 − 1.')
    return value


def _goal_fields(name: str, target_rupiah: int, due_date: str | None) -> dict[str, Any]:
    day = _day(due_date)
    return dict(name=_text(name, 'Nama target', 100), target_rupiah=_amount(target_rupiah),
                due_date=day.isoformat() if day else None)


def _available(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM main.sqlite_schema WHERE type = 'table' AND name = 'savings_events'",
    ).fetchone() is not None


def _latest(conn: sqlite3.Connection, id: str) -> sqlite3.Row:
    row = (conn.execute('SELECT * FROM savings_events WHERE id = ? ORDER BY revision DESC LIMIT 1',
                        (id,)).fetchone() if _available(conn) else None)
    if row is None:
        raise SavingsNotFound('ID target tabungan tidak ditemukan.')
    return row


def _summary(row: sqlite3.Row | dict[str, Any], contribution: int | None = None) -> dict[str, Any]:
    target, balance = row['target_rupiah'], row['balance_rupiah']
    shortfall = max(0, target - balance) if balance is not None else None
    eta = None
    if shortfall == 0:
        eta = 0
    elif shortfall is not None and contribution:
        eta = (shortfall + contribution - 1) // contribution
    return {**{key: row[key] for key in ('id', 'revision', 'name', 'target_rupiah', 'due_date',
                                         'opening_rupiah', 'balance_rupiah')},
            'progress_percent': balance * 100 / target if balance is not None else None,
            'shortfall_rupiah': shortfall, 'months_to_target': eta,
            'balance_source': 'user_reported_allocation'}


def read_savings_summaries(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Read the latest snapshot of each goal without initializing schema."""
    if not _available(conn):
        return []
    return [_summary(row) for row in conn.execute('''
        SELECT event.* FROM savings_events AS event JOIN (
            SELECT id, MAX(revision) AS revision FROM savings_events GROUP BY id
        ) AS latest USING (id, revision) ORDER BY event.name, event.id
    ''')]


def _event(row: sqlite3.Row) -> dict[str, Any]:
    return {**_summary(row), 'kind': row['kind'], 'recorded_at': row['recorded_at'],
            'idempotency_key': row['idempotency_key'], 'request': loads(row['request_json'])}


def _proposed(before: sqlite3.Row, operation: str, request: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    after = dict(before)
    after['revision'] += 1
    kind = operation
    if operation == 'update':
        fields = ('name', 'target_rupiah', 'due_date')
        if all(before[field] == request[field] for field in fields):
            raise ValueError('Target tidak berubah.')
        after.update({field: request[field] for field in fields})
    elif operation == 'opening':
        opening = before['opening_rupiah']
        amount = request['amount_rupiah']
        if opening == amount:
            raise ValueError('Saldo awal tidak berubah.')
        kind = 'opening' if opening is None else 'opening_adjustment'
        after['opening_rupiah'] = amount
        after['balance_rupiah'] = (before['balance_rupiah'] or 0) + amount - (opening or 0)
    else:
        if before['balance_rupiah'] is None:
            raise ValueError('Catat saldo awal (boleh Rp0) sebelum mencatat mutasi.')
        kind = request['direction']
        amount = request['amount_rupiah']
        after['balance_rupiah'] += amount if kind == 'deposit' else -amount
    if after['balance_rupiah'] is not None:
        if after['balance_rupiah'] < 0:
            raise InsufficientFund('Operasi membuat saldo target negatif.')
        if after['balance_rupiah'] > MAX_AMOUNT:
            raise ValueError('Saldo melebihi kapasitas integer SQLite.')
    return kind, after


class SavingsStore:
    """Append one audited snapshot per operation on an existing fictional ledger."""

    def __init__(self, db_path: str | Path) -> None:
        self._ledger = BudgetStore(db_path)

    def list_goals(self) -> list[dict[str, Any]]:
        with self._ledger._connection() as conn:
            return read_savings_summaries(conn)

    def get(self, *, id: str, monthly_contribution_rupiah: int | None = None) -> dict[str, Any]:
        goal_id = _transaction_id(id)
        if monthly_contribution_rupiah is not None:
            _nonnegative(monthly_contribution_rupiah, 'Setoran rutin')
        with self._ledger._connection() as conn:
            return _summary(_latest(conn, goal_id), monthly_contribution_rupiah)

    def history(self, *, id: str) -> list[dict[str, Any]]:
        goal_id = _transaction_id(id)
        with self._ledger._connection() as conn:
            _latest(conn, goal_id)
            return [_event(row) for row in conn.execute(
                'SELECT * FROM savings_events WHERE id = ? ORDER BY revision', (goal_id,))]

    def preview(self, *, id: str, **fields: Any) -> dict[str, Any]:
        goal_id = _transaction_id(id)
        if fields.keys() == {'amount_rupiah'}:
            operation = 'opening'
            request = dict(amount_rupiah=_nonnegative(fields['amount_rupiah'], 'Saldo awal'))
        elif {'name', 'target_rupiah'} <= fields.keys() <= {'name', 'target_rupiah', 'due_date'}:
            operation = 'update'
            request = _goal_fields(fields['name'], fields['target_rupiah'], fields.get('due_date'))
        else:
            raise ValueError('Pratinjau memerlukan amount_rupiah atau nama dan nominal target lengkap.')
        with self._ledger._connection() as conn:
            before = _latest(conn, goal_id)
            kind, after = _proposed(before, operation, request)
            return {'kind': kind, 'before': _summary(before), 'after': _summary(after),
                    'changes': {'id': goal_id, **request, 'expected_revision': before['revision']}}

    def create(self, *, name: str, target_rupiah: int, idempotency_key: str,
               due_date: str | None = None) -> dict[str, Any]:
        return self._write('create', idempotency_key, **_goal_fields(name, target_rupiah, due_date))

    def update(self, *, id: str, name: str, target_rupiah: int, expected_revision: int, confirmed: bool,
               reason: str, idempotency_key: str, due_date: str | None = None) -> dict[str, Any]:
        return self._write('update', idempotency_key, id=_transaction_id(id),
                           **_goal_fields(name, target_rupiah, due_date),
                           **self._confirmation(expected_revision, confirmed, reason))

    def opening(self, *, id: str, amount_rupiah: int, expected_revision: int, confirmed: bool,
                reason: str, idempotency_key: str) -> dict[str, Any]:
        return self._write('opening', idempotency_key, id=_transaction_id(id),
                           amount_rupiah=_nonnegative(amount_rupiah, 'Saldo awal'),
                           **self._confirmation(expected_revision, confirmed, reason))

    @staticmethod
    def _confirmation(revision: int, confirmed: bool, reason: str) -> dict[str, Any]:
        if confirmed is not True:
            raise ValueError('Tinjau perubahan dan berikan konfirmasi eksplisit.')
        return dict(expected_revision=_nonnegative(revision, 'Revisi'), confirmed=True,
                    reason=_text(reason, 'Alasan', 500))

    def move(self, *, id: str, direction: str, amount_rupiah: int, idempotency_key: str,
             description: str | None = None) -> dict[str, Any]:
        if direction not in ('deposit', 'withdrawal'):
            raise ValueError('Arah mutasi harus deposit atau withdrawal.')
        return self._write('move', idempotency_key, id=_transaction_id(id), direction=direction,
                           amount_rupiah=_amount(amount_rupiah), description=_description(description))

    def _write(self, operation: str, key: str, **request: Any) -> dict[str, Any]:
        key = _text(key, 'Idempotency key', 128, strip=False)
        payload = dumps({'idempotency_key': key, **request}, sort_keys=True)
        with self._ledger._connection(write=True) as conn:
            if operation == 'create' and not _available(conn):
                conn.execute(_SCHEMA)
            if not _available(conn):
                raise SavingsNotFound('ID target tabungan tidak ditemukan.')
            replay = conn.execute('SELECT * FROM savings_events WHERE idempotency_key = ?', (key,)).fetchone()
            if replay is not None:
                replay_operation = {'opening_adjustment': 'opening', 'deposit': 'move', 'withdrawal': 'move'}
                if replay_operation.get(replay['kind'], replay['kind']) != operation or replay['request_json'] != payload:
                    raise IdempotencyConflict('Key sudah digunakan untuk operasi tabungan berbeda.')
                return _event(replay)
            if operation == 'create':
                kind = 'create'
                after = dict(id=str(uuid4()), revision=0, opening_rupiah=None, balance_rupiah=None, **request)
            else:
                before = _latest(conn, request['id'])
                if operation in ('update', 'opening') and before['revision'] != request['expected_revision']:
                    raise StaleVersion('Revisi target berubah; tinjau ulang dan konfirmasi kembali.')
                kind, after = _proposed(before, operation, request)
            row = conn.execute('''
                INSERT INTO savings_events (id, revision, kind, name, target_rupiah, due_date, opening_rupiah,
                                            balance_rupiah, recorded_at, idempotency_key, request_json)
                VALUES (:id, :revision, :kind, :name, :target_rupiah, :due_date, :opening_rupiah,
                        :balance_rupiah, :recorded_at, :idempotency_key, :request_json) RETURNING *
            ''', after | dict(kind=kind, recorded_at=_local_iso(datetime.now(PONTIANAK)),
                              idempotency_key=key, request_json=payload)).fetchone()
            return _event(row)
