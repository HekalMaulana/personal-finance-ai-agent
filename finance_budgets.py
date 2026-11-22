"""Append-only monthly budgets in an existing local fictional SQLite ledger."""

import re
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterator
from unicodedata import normalize

from finance_storage import (
    DEFAULT_DB_PATH, MAX_AMOUNT, PONTIANAK, IdempotencyConflict, StaleVersion,
    Transaction, TransactionStore, _amount, _effective_sql, _local_iso, _text, reject_hardlinked_ledger,
)

WARNING_PERCENT = 90
_BUDGETS = """
CREATE TABLE IF NOT EXISTS budgets (
    period TEXT NOT NULL CHECK (period GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'
                                AND substr(period, 1, 4) <> '0000'
                                AND substr(period, 6, 2) BETWEEN '01' AND '12'),
    category_key TEXT NOT NULL,
    category TEXT NOT NULL CHECK (length(category) BETWEEN 1 AND 100),
    PRIMARY KEY (period, category_key)
)
"""
_REVISIONS = """
CREATE TABLE IF NOT EXISTS budget_revisions (
    period TEXT NOT NULL,
    category_key TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (typeof(version) = 'integer' AND version >= 0),
    amount_rupiah INTEGER NOT NULL CHECK (typeof(amount_rupiah) = 'integer' AND amount_rupiah > 0),
    previous_amount_rupiah INTEGER,
    reason TEXT,
    recorded_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    PRIMARY KEY (period, category_key, version),
    FOREIGN KEY (period, category_key) REFERENCES budgets (period, category_key),
    CHECK ((version = 0 AND previous_amount_rupiah IS NULL AND reason IS NULL)
           OR (version > 0 AND previous_amount_rupiah IS NOT NULL AND reason IS NOT NULL))
)
"""
_JOIN = """
SELECT r.*, b.category FROM budget_revisions AS r
JOIN budgets AS b USING (period, category_key)
"""
_CURRENT = _JOIN + """
WHERE (:period IS NULL OR r.period = :period)
  AND (:category IS NULL OR r.category_key = :category)
  AND r.version = (SELECT max(v.version) FROM budget_revisions AS v
                   WHERE v.period = r.period AND v.category_key = r.category_key)
ORDER BY r.period, r.category_key
"""


class BudgetExists(ValueError):
    """A create cannot implicitly replace a budget."""


class BudgetNotFound(LookupError):
    """No configured budget for this period and category."""


@dataclass(frozen=True)
class BudgetRevision:
    period: str
    category_key: str
    category: str
    version: int
    amount_rupiah: int
    previous_amount_rupiah: int | None
    reason: str | None
    recorded_at: str
    idempotency_key: str


@dataclass(frozen=True)
class BudgetSummary:
    period: str
    category: str
    amount_rupiah: int
    spent_rupiah: int
    remaining_rupiah: int
    usage_percent: float
    status: str


def _period(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}', value):
        raise ValueError("Periode harus YYYY-MM.")
    date.fromisoformat(value + '-01')
    return value


def _category_key(category: str) -> str:
    # Collapse Unicode whitespace; NFC and casefold also match ledger categories.
    return normalize('NFC', normalize('NFC', ' '.join(category.split())).casefold())


def _category(category: str) -> tuple[str, str]:
    label = normalize('NFC', ' '.join(_text(category, 'Kategori', 100).split()))
    return _text(label, "Kategori ternormalisasi", 100), _category_key(label)


def _budget_schema_exists(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'budgets'").fetchone() is not None


_TRANSACTION_COLUMNS = {
    'id': 'TEXT', 'transaction_type': 'TEXT', 'amount_rupiah': 'INTEGER', 'category': 'TEXT',
    'description': 'TEXT', 'occurred_at': 'TEXT', 'recorded_at': 'TEXT', 'idempotency_key': 'TEXT',
}


_CORRECTION_COLUMNS = {
    'operation_id': 'TEXT', 'transaction_id': 'TEXT', 'version': 'INTEGER', 'idempotency_key': 'TEXT',
    'request_json': 'TEXT', 'reason': 'TEXT', 'corrected_at': 'TEXT', 'transaction_type': 'TEXT',
    'amount_rupiah': 'INTEGER', 'category': 'TEXT', 'description': 'TEXT', 'occurred_at': 'TEXT',
}


def _require_table(conn: sqlite3.Connection, name: str, required: dict[str, str], *, optional: bool = False) -> None:
    table = conn.execute("SELECT type FROM pragma_table_list WHERE schema = 'main' AND name = ?", (name,)).fetchone()
    if table is None and optional:
        return
    columns = {row['name']: row['type'].upper() for row in conn.execute(
        "SELECT name, type FROM pragma_table_info(?, 'main')", (name,),
    )}
    if table is None or table['type'] != 'table' or not required.items() <= columns.items():
        raise ValueError("Skema database bukan ledger transaksi yang didukung.")


def _require_ledger(conn: sqlite3.Connection) -> None:
    # Legacy ledgers need not have a corrections table; if present it must be usable.
    _require_table(conn, 'transactions', _TRANSACTION_COLUMNS)
    _require_table(conn, 'transaction_corrections', _CORRECTION_COLUMNS, optional=True)


def _check_budget_path(path: Path) -> None:
    if path == DEFAULT_DB_PATH.resolve():
        raise ValueError("Gunakan ledger fiktif terpisah dari database utama.")
    reject_hardlinked_ledger(path)


class BudgetStore:
    """Use an existing trusted fictional ledger; all query methods use mode=ro."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path).resolve()
        _check_budget_path(self._path)

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        store = TransactionStore(self._path, read_only=not write, defer_init=True)
        # Check the exact resolved path the store will use, before opening SQLite.
        _check_budget_path(store._path)
        with store._connection(snapshot=not write, existing=True) as conn:
            if write:
                conn.execute('BEGIN IMMEDIATE')
            _require_ledger(conn)
            yield conn

    def create_budget(self, *, period: str, category: str, amount_rupiah: int,
                      idempotency_key: str) -> BudgetRevision:
        return self._write(period, category, amount_rupiah, idempotency_key, None, None)

    def update_budget(self, *, period: str, category: str, amount_rupiah: int,
                      expected_version: int, confirmed: bool, reason: str,
                      idempotency_key: str) -> BudgetRevision:
        if confirmed is not True:
            raise ValueError("Perubahan anggaran memerlukan confirmed: true setelah konfirmasi pengguna.")
        if type(expected_version) is not int or not 0 <= expected_version < MAX_AMOUNT:
            raise ValueError("expected_version harus integer dalam rentang versi yang valid.")
        return self._write(period, category, amount_rupiah, idempotency_key, expected_version,
                           _text(reason, 'Alasan', 500))

    def _write(self, period: str, category: str, amount: int, key: str,
               expected_version: int | None, reason: str | None) -> BudgetRevision:
        period = _period(period)
        label, category_key = _category(category)
        amount = _amount(amount)
        key = _text(key, 'Idempotency key', 128, strip=False)
        version = 0 if expected_version is None else expected_version + 1
        with self._connection(write=True) as conn:
            conn.execute(_BUDGETS)
            conn.execute(_REVISIONS)
            previous = conn.execute(_JOIN + ' WHERE r.idempotency_key = ?', (key,)).fetchone()
            if previous is not None:
                saved = BudgetRevision(**dict(previous))
                if (saved.period, saved.category_key, saved.version, saved.amount_rupiah, saved.reason) != (
                        period, category_key, version, amount, reason):
                    raise IdempotencyConflict("Key sudah digunakan untuk operasi anggaran berbeda.")
                return saved
            current = self._get_current(conn, period, category_key)
            if expected_version is None:
                if current is not None:
                    raise BudgetExists("Anggaran sudah ada; tinjau sebelum mengubahnya.")
                conn.execute('INSERT INTO budgets (period, category_key, category) VALUES (?, ?, ?)',
                             (period, category_key, label))
            else:
                if current is None:
                    raise BudgetNotFound("Anggaran belum dikonfigurasi.")
                if current.version != expected_version:
                    raise StaleVersion("Versi anggaran telah berubah; tinjau dan konfirmasi ulang.")
                if current.amount_rupiah == amount:
                    raise ValueError("Nominal anggaran tidak berubah.")
            conn.execute(
                """INSERT INTO budget_revisions
                   (period, category_key, version, amount_rupiah, previous_amount_rupiah,
                    reason, recorded_at, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (period, category_key, version, amount, current.amount_rupiah if current else None,
                 reason, _local_iso(datetime.now(PONTIANAK)), key),
            )
            return BudgetRevision(**dict(conn.execute(_JOIN + ' WHERE r.idempotency_key = ?', (key,)).fetchone()))

    @staticmethod
    def _get_current(conn: sqlite3.Connection, period: str, key: str) -> BudgetRevision | None:
        if not _budget_schema_exists(conn):
            return None
        row = conn.execute(_CURRENT, {'period': period, 'category': key}).fetchone()
        return None if row is None else BudgetRevision(**dict(row))

    def get_budget(self, *, period: str, category: str) -> BudgetRevision | None:
        period, (_, key) = _period(period), _category(category)
        with self._connection() as conn:
            return self._get_current(conn, period, key)

    def budget_history(self, *, period: str, category: str) -> list[BudgetRevision]:
        period, (_, key) = _period(period), _category(category)
        with self._connection() as conn:
            if not _budget_schema_exists(conn):
                return []
            return [BudgetRevision(**dict(row)) for row in conn.execute(
                _JOIN + ' WHERE r.period = ? AND r.category_key = ? ORDER BY r.version', (period, key),
            )]

    def budget_summary(self, *, period: str, category: str | None = None,
                       above_warning: bool = False) -> list[BudgetSummary]:
        """Return configured budgets; optionally select strictly over 90%."""
        period = _period(period)
        key = _category(category)[1] if category is not None else None
        if type(above_warning) is not bool:
            raise ValueError("above_warning harus boolean.")
        with self._connection() as conn:
            return self._summarize(conn, period, key, above_warning)

    def reporting_snapshot(self) -> tuple[list[tuple[Transaction, int]], list[BudgetSummary]]:
        """Fetch effective detail and budgets from the same read-only SQLite snapshot."""
        with self._connection() as conn:
            rows = [(Transaction(**{key: row[key] for key in row.keys() if key != 'version'}), row['version'])
                    for row in conn.execute('SELECT * FROM (' + _effective_sql(conn) + ') ORDER BY occurred_at, id')]
            return rows, self._summarize(conn, None, None, False, [row for row, _ in rows])

    @staticmethod
    def _summarize(conn: sqlite3.Connection, period: str | None, key: str | None,
                   above_warning: bool, rows: list[Transaction] | None = None) -> list[BudgetSummary]:
        if not _budget_schema_exists(conn):
            return []
        budgets = list(conn.execute(_CURRENT, {'period': period, 'category': key}))
        if not budgets:
            return []
        configured = {(row['period'], row['category_key']) for row in budgets}
        spent: dict[tuple[str, str], int] = defaultdict(int)
        expenses = ((row.occurred_at, row.category, row.amount_rupiah)
                    for row in rows if row.transaction_type == 'expense') if rows is not None else conn.execute(
            "SELECT occurred_at, category, amount_rupiah FROM (" + _effective_sql(conn) + ") WHERE transaction_type = ?",
            ('expense',),
        )
        for occurred_at, category, amount in expenses:
            month = datetime.fromisoformat(occurred_at).astimezone(PONTIANAK).isoformat()[:7]
            pair = month, _category_key(category)
            if pair in configured:
                spent[pair] += amount
        result = []
        for row in budgets:
            amount = row['amount_rupiah']
            actual = spent[row['period'], row['category_key']]
            threshold = amount * WARNING_PERCENT
            if above_warning and actual * 100 <= threshold:
                continue
            status = ('melebihi batas' if actual > amount else
                      'mendekati batas' if actual * 100 >= threshold else 'normal')
            result.append(BudgetSummary(row['period'], row['category'], amount, actual,
                                        amount - actual, actual * 100 / amount, status))
        return result
