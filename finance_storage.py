"""Local SQLite ledger for fictional transactions; no Hermes integration."""

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from unicodedata import category as character_category
from uuid import UUID, uuid4

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "finance.db"
PONTIANAK = timezone(timedelta(hours=7), "Asia/Pontianak")
MAX_AMOUNT = 2**63 - 1
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('income', 'expense')),
    amount_rupiah INTEGER NOT NULL CHECK (typeof(amount_rupiah) = 'integer' AND amount_rupiah > 0),
    category TEXT NOT NULL CHECK (length(trim(category)) BETWEEN 1 AND 100),
    description TEXT CHECK (length(description) <= 500),
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE CHECK (length(idempotency_key) BETWEEN 1 AND 128)
)
"""
_CORRECTIONS = """
CREATE TABLE IF NOT EXISTS transaction_corrections (
    operation_id TEXT PRIMARY KEY NOT NULL,
    transaction_id TEXT NOT NULL REFERENCES transactions(id),
    version INTEGER NOT NULL CHECK (version > 0),
    idempotency_key TEXT NOT NULL UNIQUE,
    request_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    corrected_at TEXT NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('income', 'expense')),
    amount_rupiah INTEGER NOT NULL CHECK (typeof(amount_rupiah) = 'integer' AND amount_rupiah > 0),
    category TEXT NOT NULL,
    description TEXT,
    occurred_at TEXT NOT NULL,
    UNIQUE (transaction_id, version)
)
"""
_EFFECTIVE = """
SELECT t.id,
       coalesce(c.transaction_type, t.transaction_type) AS transaction_type,
       coalesce(c.amount_rupiah, t.amount_rupiah) AS amount_rupiah,
       coalesce(c.category, t.category) AS category,
       CASE WHEN c.version IS NULL THEN t.description ELSE c.description END AS description,
       coalesce(c.occurred_at, t.occurred_at) AS occurred_at,
       t.recorded_at, t.idempotency_key, coalesce(c.version, 0) AS version
FROM transactions AS t
LEFT JOIN transaction_corrections AS c ON c.transaction_id = t.id
    AND c.version = (SELECT max(r.version) FROM transaction_corrections AS r WHERE r.transaction_id = t.id)
"""
_LEGACY = "SELECT transactions.*, 0 AS version FROM transactions"
_FILTER = """
WHERE (:start IS NULL OR occurred_at >= :start)
  AND (:end IS NULL OR occurred_at <= :end)
"""


class IdempotencyConflict(ValueError):
    """The same idempotency key already has a different payload."""


@dataclass(frozen=True)
class Transaction:
    id: str
    transaction_type: str
    amount_rupiah: int
    category: str
    description: str | None
    occurred_at: str
    recorded_at: str
    idempotency_key: str


class StaleVersion(ValueError):
    """The effective version changed after the caller read it."""


class TransactionNotFound(LookupError):
    """The requested transaction ID does not exist."""


@dataclass(frozen=True)
class Correction:
    operation_id: str
    transaction_id: str
    version: int
    reason: str
    corrected_at: str
    idempotency_key: str
    before: Transaction
    after: Transaction


@dataclass(frozen=True)
class CashFlow:
    total_income: int
    total_expense: int
    net_cash_flow: int
    transaction_count: int


def _type(value: str) -> str:
    if not isinstance(value, str) or value not in ("income", "expense"):
        raise ValueError("Tipe transaksi harus income atau expense.")
    return value


def _text(value: str, field: str, limit: int, *, strip: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} harus berupa teks.")
    if any(character_category(char) in ("Cc", "Cs") for char in value):
        raise ValueError(f"{field} mengandung karakter kontrol atau Unicode tidak valid.")
    normalized = value.strip()
    if not 1 <= len(normalized) <= limit:
        raise ValueError(f"{field} harus berisi 1–{limit} karakter.")
    if not strip and normalized != value:
        raise ValueError(f"{field} tidak boleh memiliki spasi tepi.")
    return normalized


def _local_iso(value: datetime) -> str:
    return value.astimezone(PONTIANAK).isoformat(timespec="microseconds")


def _transaction_time(value: str) -> str:
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise ValueError("Waktu transaksi harus ISO 8601 dengan detik dan offset atau Z.")
    try:
        return _local_iso(datetime.fromisoformat(value))
    except (ValueError, OverflowError) as exc:
        raise ValueError("Waktu transaksi di luar rentang tanggal/waktu yang valid.") from exc


def _day(value: str | None) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise ValueError("Tanggal filter harus YYYY-MM-DD.")
    return date.fromisoformat(value)


def _bounds(start_date: str | None, end_date: str | None) -> dict[str, str | None]:
    start, end = _day(start_date), _day(end_date)
    if start is not None and end is not None and start > end:
        raise ValueError("Tanggal awal tidak boleh setelah tanggal akhir.")
    return {
        "start": _local_iso(datetime.combine(start, time.min, PONTIANAK)) if start else None,
        "end": _local_iso(datetime.combine(end, time.max, PONTIANAK)) if end else None,
    }


def _amount(value: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_AMOUNT:
        raise ValueError("Nominal harus integer Rupiah positif (maksimum 2^63 − 1).")
    return value


def _description(value: str | None) -> str | None:
    return None if value is None else _text(value, "Deskripsi", 500)


def _transaction_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Transaction ID harus berupa UUID.")
    try:
        canonical = str(UUID(value))
    except ValueError as exc:
        raise ValueError("Transaction ID harus berupa UUID.") from exc
    if value != canonical:
        raise ValueError("Transaction ID harus berupa UUID kanonik huruf kecil.")
    return value


_CHANGE_VALIDATORS: dict[str, Callable[[Any], Any]] = {
    "transaction_type": _type,
    "amount_rupiah": _amount,
    "category": lambda value: _text(value, "Kategori", 100),
    "description": _description,
    "occurred_at": _transaction_time,
}


def _has_corrections(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'transaction_corrections'"
    ).fetchone() is not None


def _effective_sql(conn: sqlite3.Connection) -> str:
    return _EFFECTIVE if _has_corrections(conn) else _LEGACY


def _snapshot(original: Transaction, row: sqlite3.Row) -> Transaction:
    return replace(original, transaction_type=row["transaction_type"], amount_rupiah=row["amount_rupiah"],
                   category=row["category"], description=row["description"], occurred_at=row["occurred_at"])


def _correction(original: Transaction, before: Transaction, row: sqlite3.Row) -> Correction:
    return Correction(row["operation_id"], original.id, row["version"], row["reason"],
                      row["corrected_at"], row["idempotency_key"], before, _snapshot(original, row))


_ADD_JOURNAL = """
CREATE TABLE IF NOT EXISTS add_operations (
    operation_id TEXT PRIMARY KEY NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    prepared_at TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    amount_rupiah INTEGER NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    occurred_at TEXT NOT NULL
)
"""
_ADD_FIELDS = ("transaction_type", "amount_rupiah", "category", "description", "occurred_at")


def _add_payload(transaction_type: str, amount_rupiah: int, category: str,
                 description: str | None, occurred_at: str) -> tuple[str, int, str, str | None, str]:
    return (_type(transaction_type), _amount(amount_rupiah), _text(category, "Kategori", 100),
            _description(description), _transaction_time(occurred_at))


def _operation_id(value: str) -> str:
    try:
        return _transaction_id(value)
    except ValueError as exc:
        raise ValueError("operation_id harus UUID kanonik huruf kecil.") from exc


def _journal_exists(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'add_operations'").fetchone() is not None


def _add_result(conn: sqlite3.Connection, key: str, operation: sqlite3.Row | None) -> dict[str, Any] | None:
    transaction = conn.execute("SELECT * FROM transactions WHERE idempotency_key = ?", (key,)).fetchone()
    if operation is None and transaction is None:
        return None
    source = operation if operation is not None else transaction
    return {
        "operation_id": operation["operation_id"] if operation is not None else None,
        "idempotency_key": key,
        "prepared_at": operation["prepared_at"] if operation is not None else None,
        "status": "committed" if transaction is not None else "prepared",
        "payload": {field: source[field] for field in _ADD_FIELDS},
        "transaction": dict(transaction) if transaction is not None else None,
    }


class TransactionStore:
    """Initialize a local ledger; use only a trusted application or test path."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH, *,
                 read_only: bool = False, defer_init: bool = False) -> None:
        self._path = Path(db_path).resolve()
        self._read_only = read_only
        self._defer_init = defer_init
        if not read_only and not defer_init:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._initialize(conn)

    @staticmethod
    def _initialize(conn: sqlite3.Connection) -> None:
        conn.execute(_SCHEMA)
        conn.execute(_CORRECTIONS)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_time ON transactions (occurred_at, id)")

    @contextmanager
    def _connection(self, *, snapshot: bool = False, existing: bool = False) -> Iterator[sqlite3.Connection]:
        mode = "ro" if self._read_only else "rw" if existing else None
        target = self._path.as_uri() + "?mode=" + mode if mode else str(self._path)
        conn = sqlite3.connect(target, uri=mode is not None, timeout=5, autocommit=True)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            if snapshot:
                conn.execute("BEGIN")
            yield conn
            if conn.in_transaction:
                conn.execute("COMMIT")
        finally:
            # SQLite rolls back an uncommitted write when the connection closes.
            conn.close()

    def add_transaction(
        self, *, transaction_type: str, amount_rupiah: int, category: str,
        occurred_at: str, idempotency_key: str, description: str | None = None,
    ) -> Transaction:
        """Save once. A retry returns the original ID and recording timestamp."""
        payload = _add_payload(transaction_type, amount_rupiah, category, description, occurred_at)
        key = _text(idempotency_key, "Idempotency key", 128, strip=False)
        if self._defer_init and not self._read_only:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            # Reserve the writer lock before checking for an existing key.
            conn.execute("BEGIN IMMEDIATE")
            if self._defer_init and not self._read_only:
                self._initialize(conn)
            return self._save_add(conn, key, payload)

    @staticmethod
    def _save_add(conn: sqlite3.Connection, key: str, payload: tuple[str, int, str, str | None, str]) -> Transaction:
        operation = conn.execute("SELECT * FROM add_operations WHERE idempotency_key = ?", (key,)).fetchone() if _journal_exists(conn) else None
        result = _add_result(conn, key, operation)
        if result is not None:
            if payload != tuple(result["payload"][field] for field in _ADD_FIELDS):
                raise IdempotencyConflict("Konflik idempotency key: payload transaksi berbeda.")
            if result["transaction"] is not None:
                return Transaction(**result["transaction"])
        entry = Transaction(str(uuid4()), *payload, _local_iso(datetime.now(PONTIANAK)), key)
        conn.execute(
            """INSERT INTO transactions
               (id, transaction_type, amount_rupiah, category, description,
                occurred_at, recorded_at, idempotency_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (entry.id, *payload, entry.recorded_at, entry.idempotency_key),
        )
        return entry

    def prepare_add(self, *, transaction_type: str, amount_rupiah: int, category: str,
                    occurred_at: str, idempotency_key: str, description: str | None = None) -> dict[str, Any]:
        payload = _add_payload(transaction_type, amount_rupiah, category, description, occurred_at)
        key = _text(idempotency_key, "Idempotency key", 128, strip=False)
        if not self._read_only:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._initialize(conn)
            conn.execute(_ADD_JOURNAL)
            result = self._lookup_add(conn, None, key)
            if result is not None:
                if payload != tuple(result["payload"][field] for field in _ADD_FIELDS):
                    raise IdempotencyConflict("Konflik idempotency key: payload transaksi berbeda.")
                if result["operation_id"] is not None:
                    return result
            operation_id = str(uuid4())
            conn.execute("""INSERT INTO add_operations
                            (operation_id, idempotency_key, prepared_at, transaction_type,
                             amount_rupiah, category, description, occurred_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                         (operation_id, key, _local_iso(datetime.now(PONTIANAK)), *payload))
            prepared = self._lookup_add(conn, operation_id, None)
            assert prepared is not None
            return prepared

    @staticmethod
    def _lookup_add(conn: sqlite3.Connection, operation_id: str | None,
                    idempotency_key: str | None) -> dict[str, Any] | None:
        operation = None
        if _journal_exists(conn):
            operation = conn.execute("""SELECT * FROM add_operations
                                        WHERE operation_id = ? OR idempotency_key = ?""",
                                     (operation_id, idempotency_key)).fetchone()
        if operation is not None:
            idempotency_key = operation["idempotency_key"]
        return _add_result(conn, idempotency_key, operation) if idempotency_key is not None else None

    def operation_status(self, *, operation_id: str | None = None,
                         idempotency_key: str | None = None) -> dict[str, Any] | None:
        if (operation_id is None) == (idempotency_key is None):
            raise ValueError("Pilih tepat satu: operation_id atau idempotency_key.")
        operation_id = _operation_id(operation_id) if operation_id is not None else None
        key = _text(idempotency_key, "Idempotency key", 128, strip=False) if idempotency_key is not None else None
        with self._connection(snapshot=True, existing=True) as conn:
            return self._lookup_add(conn, operation_id, key)

    def commit_add(self, *, operation_id: str) -> dict[str, Any] | None:
        operation_id = _operation_id(operation_id)
        with self._connection(existing=True) as conn:
            conn.execute("BEGIN IMMEDIATE")
            operation = self._lookup_add(conn, operation_id, None)
            if operation is None or operation["status"] == "committed":
                return operation
            key = operation["idempotency_key"]
            self._save_add(conn, key, _add_payload(**operation["payload"]))
            return self._lookup_add(conn, operation_id, None)

    def find_add(self, *, amount_rupiah: int, category: str | None = None,
                 transaction_type: str | None = None, start_date: str | None = None,
                 end_date: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = _bounds(start_date, end_date)
        params.update(amount=_amount(amount_rupiah), category=_text(category, "Kategori", 100) if category is not None else None,
                      kind=_type(transaction_type) if transaction_type is not None else None)
        with self._connection(snapshot=True, existing=True) as conn:
            # Search original intent, including preparations and pre-journal rows.
            source = "SELECT idempotency_key, amount_rupiah, category, transaction_type, occurred_at FROM transactions"
            if _journal_exists(conn):
                source += """ UNION ALL SELECT j.idempotency_key, j.amount_rupiah, j.category, j.transaction_type, j.occurred_at
                              FROM add_operations AS j WHERE NOT EXISTS
                              (SELECT 1 FROM transactions AS t WHERE t.idempotency_key = j.idempotency_key)"""
            rows = conn.execute("SELECT idempotency_key FROM (" + source + ")" + _FILTER + """
                                AND amount_rupiah = :amount AND (:category IS NULL OR category = :category)
                                AND (:kind IS NULL OR transaction_type = :kind)
                                ORDER BY occurred_at DESC, idempotency_key LIMIT 11""", params).fetchall()
            candidates = [self._lookup_add(conn, None, row[0]) for row in rows[:10]]
        return {"match": "multiple" if len(rows) > 1 else "single" if rows else "none",
                "truncated": len(rows) > 10, "candidates": candidates}

    def get_transaction(self, transaction_id: str) -> Transaction | None:
        result = self.get_versioned_transaction(transaction_id)
        return result[0] if result is not None else None

    def get_versioned_transaction(self, transaction_id: str) -> tuple[Transaction, int] | None:
        transaction_id = _transaction_id(transaction_id)
        with self._connection(snapshot=True) as conn:
            row = conn.execute("SELECT * FROM (" + _effective_sql(conn) + ") WHERE id = ?",
                               (transaction_id,)).fetchone()
            if row is None:
                return None
            values = dict(row)
            version = values.pop("version")
            return Transaction(**values), version

    def transaction_history(self, transaction_id: str) -> tuple[Transaction, list[Correction]]:
        transaction_id = _transaction_id(transaction_id)
        with self._connection(snapshot=True) as conn:
            original = self._original(conn, transaction_id)
            revisions = []
            previous = original
            if _has_corrections(conn):
                rows = conn.execute("SELECT * FROM transaction_corrections WHERE transaction_id = ? ORDER BY version",
                                    (transaction_id,))
                for row in rows:
                    revision = _correction(original, previous, row)
                    revisions.append(revision)
                    previous = revision.after
            return original, revisions

    @staticmethod
    def _original(conn: sqlite3.Connection, transaction_id: str) -> Transaction:
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
        if row is None:
            raise TransactionNotFound("Transaction ID tidak ditemukan.")
        return Transaction(**dict(row))

    def correct_transaction(self, transaction_id: str, *, expected_version: int,
                            changes: dict, reason: str, idempotency_key: str) -> Correction:
        """Append one complete effective snapshot without modifying the original."""
        transaction_id = _transaction_id(transaction_id)
        if type(expected_version) is not int or not 0 <= expected_version < MAX_AMOUNT:
            raise ValueError("expected_version harus integer nonnegatif dalam rentang yang didukung.")
        if not isinstance(changes, dict) or not changes or not changes.keys() <= _CHANGE_VALIDATORS.keys():
            raise ValueError("changes harus objek tidak kosong berisi field transaksi yang dapat dikoreksi.")
        normalized = {field: _CHANGE_VALIDATORS[field](value) for field, value in changes.items()}
        reason = _text(reason, "Alasan koreksi", 500)
        key = _text(idempotency_key, "Idempotency key", 128, strip=False)
        request = json.dumps([transaction_id, expected_version, normalized, reason], sort_keys=True)
        with self._connection(existing=True) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(_CORRECTIONS)
            prior = conn.execute("SELECT * FROM transaction_corrections WHERE idempotency_key = ?", (key,)).fetchone()
            if prior is not None and prior["request_json"] != request:
                raise IdempotencyConflict("Konflik idempotency key: payload koreksi berbeda.")
            original = self._original(conn, transaction_id)
            if prior is not None:
                predecessor = conn.execute(
                    "SELECT * FROM transaction_corrections WHERE transaction_id = ? AND version = ?",
                    (transaction_id, expected_version),
                ).fetchone()
                before = original if predecessor is None else _snapshot(original, predecessor)
                return _correction(original, before, prior)
            latest = conn.execute(
                "SELECT * FROM transaction_corrections WHERE transaction_id = ? ORDER BY version DESC LIMIT 1",
                (transaction_id,),
            ).fetchone()
            version = 0 if latest is None else latest["version"]
            if expected_version != version:
                raise StaleVersion("Versi transaksi telah berubah; baca ulang sebelum mengoreksi.")
            before = original if latest is None else _snapshot(original, latest)
            after = replace(before, **normalized)
            if before == after:
                raise ValueError("Koreksi tidak mengubah nilai efektif transaksi.")
            operation_id = str(uuid4())
            timestamp = _local_iso(datetime.now(PONTIANAK))
            conn.execute(
                """INSERT INTO transaction_corrections
                   (operation_id, transaction_id, version, idempotency_key, request_json, reason,
                    corrected_at, transaction_type, amount_rupiah, category, description, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (operation_id, transaction_id, version + 1, key, request, reason, timestamp,
                 after.transaction_type, after.amount_rupiah, after.category, after.description, after.occurred_at),
            )
            return Correction(operation_id, transaction_id, version + 1, reason, timestamp, key, before, after)

    def list_transactions(
        self, *, start_date: str | None = None, end_date: str | None = None,
        transaction_type: str | None = None,
    ) -> list[Transaction]:
        """Return in time/ID order; both local calendar dates are inclusive."""
        params = _bounds(start_date, end_date)
        params["kind"] = _type(transaction_type) if transaction_type is not None else None
        with self._connection(snapshot=True) as conn:
            rows = conn.execute(
                "SELECT * FROM (" + _effective_sql(conn) + ")" + _FILTER
                + "AND (:kind IS NULL OR transaction_type = :kind) ORDER BY occurred_at, id",
                params,
            )
            return [Transaction(**{key: row[key] for key in row.keys() if key != "version"}) for row in rows]

    def cash_flow(self, *, start_date: str | None = None, end_date: str | None = None) -> CashFlow:
        """Sum exact integers without SQLite SUM's signed-64-bit overflow."""
        income = expense = count = 0
        with self._connection(snapshot=True) as conn:
            rows = conn.execute("SELECT transaction_type, amount_rupiah FROM (" + _effective_sql(conn) + ")" + _FILTER,
                                _bounds(start_date, end_date))
            for kind, amount in rows:
                if kind == "income":
                    income += amount
                else:
                    expense += amount
                count += 1
        return CashFlow(income, expense, income - expense, count)
