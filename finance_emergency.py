"""User-reported emergency allocations, separate from transaction cash flow."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from json import dumps, loads
from typing import Any
from pathlib import Path
from uuid import uuid4

from finance_budgets import BudgetStore
from finance_storage import MAX_AMOUNT, PONTIANAK, IdempotencyConflict, StaleVersion, _amount, _description, _local_iso, _text

_CONFIG = """
CREATE TABLE IF NOT EXISTS emergency_configurations (
    version INTEGER PRIMARY KEY CHECK (version >= 0),
    essential_rupiah INTEGER CHECK (essential_rupiah IS NULL OR (typeof(essential_rupiah) = 'integer' AND essential_rupiah > 0)),
    target_months INTEGER CHECK (target_months IS NULL OR (typeof(target_months) = 'integer' AND target_months > 0)),
    recorded_at TEXT NOT NULL,
    reason TEXT,
    idempotency_key TEXT UNIQUE NOT NULL,
    request_json TEXT NOT NULL
)
"""
_MOVEMENTS = """
CREATE TABLE IF NOT EXISTS emergency_movements (
    revision INTEGER PRIMARY KEY CHECK (revision >= 0),
    id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('opening', 'opening_adjustment', 'deposit', 'withdrawal')),
    amount_rupiah INTEGER NOT NULL CHECK (typeof(amount_rupiah) = 'integer' AND amount_rupiah >= 0
        AND (amount_rupiah > 0 OR kind IN ('opening', 'opening_adjustment'))),
    delta_rupiah INTEGER NOT NULL CHECK (typeof(delta_rupiah) = 'integer'),
    balance_after_rupiah INTEGER NOT NULL CHECK (typeof(balance_after_rupiah) = 'integer' AND balance_after_rupiah >= 0),
    description TEXT,
    recorded_at TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    request_json TEXT NOT NULL
)
"""
_TABLES = frozenset({'emergency_configurations', 'emergency_movements'})


class InsufficientFund(ValueError):
    """The operation would result in a negative allocation."""


@dataclass(frozen=True)
class FundConfiguration:
    version: int
    essential_rupiah: int | None
    target_months: int | None
    recorded_at: str
    reason: str | None
    idempotency_key: str
    request: dict[str, Any]


@dataclass(frozen=True)
class FundMovement:
    revision: int
    id: str
    kind: str
    amount_rupiah: int
    delta_rupiah: int
    balance_after_rupiah: int
    description: str | None
    recorded_at: str
    idempotency_key: str
    request: dict[str, Any]


@dataclass(frozen=True)
class FundSummary:
    essential_rupiah: int | None
    target_months: int | None
    config_version: int | None
    opening_rupiah: int | None
    balance_rupiah: int | None
    balance_revision: int | None
    target_rupiah: int | None
    coverage_months: float | None
    progress_percent: float | None
    shortfall_rupiah: int | None
    months_to_target: int | None
    balance_source: str = 'user_reported_allocation'


def calculate_fund(essential: int | None, months: int | None, balance: int | None,
                   contribution: int | None) -> tuple[int | None, float | None, float | None, int | None, int | None]:
    target = essential * months if essential and months else None
    coverage = balance / essential if balance is not None and essential else None
    progress = balance * 100 / target if balance is not None and target else None
    shortfall = max(0, target - balance) if target is not None and balance is not None else None
    eta = None
    if shortfall == 0:
        eta = 0
    elif shortfall is not None and contribution:
        eta = (shortfall + contribution - 1) // contribution
    return target, coverage, progress, shortfall, eta


def _available(conn: sqlite3.Connection) -> bool:
    tables = {row['name'] for row in conn.execute(
        "SELECT name FROM main.sqlite_schema WHERE type = 'table' AND name IN (?, ?)", sorted(_TABLES),
    )}
    if tables and tables != _TABLES:
        raise sqlite3.DatabaseError('Incomplete emergency fund schema')
    return bool(tables)


def _latest(conn: sqlite3.Connection) -> tuple[sqlite3.Row | None, sqlite3.Row | None, sqlite3.Row | None]:
    if not _available(conn):
        return None, None, None
    config = conn.execute('SELECT * FROM emergency_configurations ORDER BY version DESC LIMIT 1').fetchone()
    balance = conn.execute('SELECT * FROM emergency_movements ORDER BY revision DESC LIMIT 1').fetchone()
    opening = conn.execute("SELECT * FROM emergency_movements WHERE kind IN ('opening','opening_adjustment') "
                           'ORDER BY revision DESC LIMIT 1').fetchone()
    return config, balance, opening


def read_fund_summary(conn: sqlite3.Connection, contribution: int | None = None) -> FundSummary:
    """Use the caller's SQLite snapshot; no schema initialization on reads."""
    config, latest, opening = _latest(conn)
    essential, months = (config['essential_rupiah'], config['target_months']) if config else (None, None)
    balance = latest['balance_after_rupiah'] if latest else None
    return FundSummary(essential, months, config['version'] if config else None,
                       opening['amount_rupiah'] if opening else None, balance, latest['revision'] if latest else None,
                       *calculate_fund(essential, months, balance, contribution))


def _nonnegative(value: int, field: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_AMOUNT:
        raise ValueError(f'{field} harus integer 0 sampai 2^63 − 1.')
    return value


def _confirmed(confirmed: bool, reason: str | None) -> str:
    if confirmed is not True or reason is None:
        raise ValueError('Perubahan nilai yang sudah ada memerlukan konfirmasi eksplisit dan alasan.')
    return reason


def _canonical_request(key: str, **values: Any) -> str:
    # Missing/null optional fields and the default false confirmation normalize the same way.
    return dumps({'idempotency_key': key, **{k: v for k, v in values.items() if v is not None and v is not False}},
                 sort_keys=True)


def _fields(row: sqlite3.Row) -> dict[str, Any]:
    fields = dict(row)
    fields['request'] = loads(fields.pop('request_json'))
    return fields


def _retry(conn: sqlite3.Connection, key: str, request: str, *, config: bool) -> sqlite3.Row | None:
    c = conn.execute('SELECT * FROM emergency_configurations WHERE idempotency_key = ?', (key,)).fetchone()
    m = conn.execute('SELECT * FROM emergency_movements WHERE idempotency_key = ?', (key,)).fetchone()
    if c is None and m is None:
        return None
    row = c if config else m
    if row is None or row['request_json'] != request or (c is not None and m is not None):
        raise IdempotencyConflict('Key sudah digunakan untuk operasi dana darurat berbeda.')
    return row


def _initialize(conn: sqlite3.Connection) -> None:
    if not _available(conn):
        conn.execute(_CONFIG)
        conn.execute(_MOVEMENTS)


class EmergencyFundStore:
    """One allocation per existing fictional ledger; never accesses a bank."""

    def __init__(self, db_path: str | Path) -> None:
        # Reuse the same existing-ledger checks and SQLite snapshot/lock as budgets.
        self._ledger = BudgetStore(db_path)

    def summary(self, *, monthly_contribution_rupiah: int | None = None) -> FundSummary:
        if monthly_contribution_rupiah is not None:
            _nonnegative(monthly_contribution_rupiah, 'Setoran rutin')
        with self._ledger._connection() as conn:
            return read_fund_summary(conn, monthly_contribution_rupiah)

    def history(self) -> tuple[list[FundConfiguration], list[FundMovement]]:
        with self._ledger._connection() as conn:
            if not _available(conn):
                return [], []
            configs = [FundConfiguration(**_fields(row)) for row in conn.execute(
                'SELECT * FROM emergency_configurations ORDER BY version',
            )]
            moves = [FundMovement(**_fields(row)) for row in conn.execute(
                'SELECT * FROM emergency_movements ORDER BY revision',
            )]
            return configs, moves

    def configure(self, *, idempotency_key: str, essential_rupiah: int | None = None, target_months: int | None = None,
                  expected_version: int | None = None, confirmed: bool = False,
                  reason: str | None = None) -> FundConfiguration:
        if essential_rupiah is None and target_months is None:
            raise ValueError('Berikan pengeluaran esensial atau target bulan.')
        if essential_rupiah is not None:
            _amount(essential_rupiah)
        if target_months is not None:
            _amount(target_months)
        if expected_version is not None:
            _nonnegative(expected_version, 'Versi konfigurasi')
        if type(confirmed) is not bool:
            raise ValueError('confirmed harus boolean.')
        reason = _description(reason)
        key = _text(idempotency_key, 'Idempotency key', 128, strip=False)
        request = _canonical_request(key, essential_rupiah=essential_rupiah, target_months=target_months,
                                     expected_version=expected_version, confirmed=confirmed, reason=reason)
        with self._ledger._connection(write=True) as conn:
            _initialize(conn)
            replay = _retry(conn, key, request, config=True)
            if replay is not None:
                return FundConfiguration(**_fields(replay))
            config, _, _ = _latest(conn)
            if expected_version != (config['version'] if config else None):
                raise StaleVersion('Versi konfigurasi berubah; baca ulang sebelum menulis.')
            essential_before = config['essential_rupiah'] if config else None
            months_before = config['target_months'] if config else None
            essential = essential_rupiah if essential_rupiah is not None else essential_before
            months = target_months if target_months is not None else months_before
            if (essential, months) == (essential_before, months_before):
                raise ValueError('Konfigurasi tidak berubah.')
            if ((essential_before is not None and essential != essential_before)
                    or (months_before is not None and months != months_before)):
                _confirmed(confirmed, reason)
            if essential and months and essential * months > MAX_AMOUNT:
                raise ValueError('Target nominal melebihi kapasitas integer SQLite.')
            version = config['version'] + 1 if config else 0
            row = conn.execute(
                'INSERT INTO emergency_configurations (version, essential_rupiah, target_months, recorded_at, reason, '
                'idempotency_key, request_json) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING *',
                (version, essential, months, _local_iso(datetime.now(PONTIANAK)), reason, key, request),
            ).fetchone()
            return FundConfiguration(**_fields(row))

    def set_opening(self, *, amount_rupiah: int, idempotency_key: str, expected_revision: int | None = None,
                    confirmed: bool = False, reason: str | None = None) -> FundMovement:
        _nonnegative(amount_rupiah, 'Saldo awal')
        if type(confirmed) is not bool:
            raise ValueError('confirmed harus boolean.')
        reason = _description(reason)
        if expected_revision is not None:
            _nonnegative(expected_revision, 'Revisi saldo')
            _confirmed(confirmed, reason)
        return self._append('opening', amount_rupiah, idempotency_key, reason, expected_revision, confirmed=confirmed)

    def move(self, *, direction: str, amount_rupiah: int, idempotency_key: str,
             description: str | None = None) -> FundMovement:
        if direction not in ('deposit', 'withdrawal'):
            raise ValueError('Arah mutasi harus deposit atau withdrawal.')
        return self._append(direction, _amount(amount_rupiah), idempotency_key, _description(description), None)

    def _append(self, kind: str, amount: int, key: str, description: str | None,
                expected_revision: int | None, *, confirmed: bool = False) -> FundMovement:
        key = _text(key, 'Idempotency key', 128, strip=False)
        if kind == 'opening':
            request = _canonical_request(key, amount_rupiah=amount, reason=description,
                                         expected_revision=expected_revision, confirmed=confirmed)
        else:
            request = _canonical_request(key, direction=kind, amount_rupiah=amount, description=description)
        with self._ledger._connection(write=True) as conn:
            _initialize(conn)
            replay = _retry(conn, key, request, config=False)
            if replay is not None:
                return FundMovement(**_fields(replay))
            _, current, opening = _latest(conn)
            revision = current['revision'] if current else None
            previous = current['balance_after_rupiah'] if current else 0
            delta = amount if kind != 'withdrawal' else -amount
            if kind == 'opening':
                if revision != expected_revision:
                    raise StaleVersion('Revisi saldo berubah; baca ulang sebelum menetapkan saldo awal.')
                if opening is not None:
                    kind = 'opening_adjustment'
                    delta = amount - opening['amount_rupiah']
                    if delta == 0:
                        raise ValueError('Saldo awal tidak berubah.')
            elif opening is None:
                raise StaleVersion('Tetapkan saldo awal secara eksplisit, boleh Rp0, sebelum mencatat mutasi.')
            balance = previous + delta
            if balance < 0:
                raise InsufficientFund('Operasi ditolak karena saldo dana darurat akan negatif.')
            if balance > MAX_AMOUNT:
                raise ValueError('Saldo melebihi kapasitas integer SQLite.')
            row = conn.execute(
                'INSERT INTO emergency_movements (revision, id, kind, amount_rupiah, delta_rupiah, balance_after_rupiah, '
                'description, recorded_at, idempotency_key, request_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *',
                (0 if revision is None else revision + 1, str(uuid4()), kind, amount, delta, balance,
                 description, _local_iso(datetime.now(PONTIANAK)), key, request),
            ).fetchone()
            return FundMovement(**_fields(row))
