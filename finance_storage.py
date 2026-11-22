"""Local SQLite ledger for fictional transactions; no Hermes integration."""

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterator
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_time ON transactions (occurred_at, id)")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        # Explicit BEGIN/COMMIT for writes; reads use SQLite autocommit.
        target = self._path.as_uri() + "?mode=ro" if self._read_only else str(self._path)
        conn = sqlite3.connect(target, uri=self._read_only, timeout=5, autocommit=True)
        try:
            conn.row_factory = sqlite3.Row
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
        kind = _type(transaction_type)
        if type(amount_rupiah) is not int or not 1 <= amount_rupiah <= MAX_AMOUNT:
            raise ValueError("Nominal harus integer Rupiah positif (maksimum 2^63 − 1).")
        category = _text(category, "Kategori", 100)
        description = _text(description, "Deskripsi", 500) if description is not None else None
        timestamp = _transaction_time(occurred_at)
        key = _text(idempotency_key, "Idempotency key", 128, strip=False)
        payload = (kind, amount_rupiah, category, description, timestamp)
        if self._defer_init and not self._read_only:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            # Reserve the writer lock before checking for an existing key.
            conn.execute("BEGIN IMMEDIATE")
            if self._defer_init and not self._read_only:
                self._initialize(conn)
            row = conn.execute(
                "SELECT * FROM transactions WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if row is not None:
                existing = Transaction(**dict(row))
                if payload != (existing.transaction_type, existing.amount_rupiah,
                               existing.category, existing.description, existing.occurred_at):
                    raise IdempotencyConflict("Konflik idempotency key: payload transaksi berbeda.")
                return existing
            entry = Transaction(str(uuid4()), *payload, _local_iso(datetime.now(PONTIANAK)), key)
            conn.execute(
                """INSERT INTO transactions
                   (id, transaction_type, amount_rupiah, category, description,
                    occurred_at, recorded_at, idempotency_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry.id, *payload, entry.recorded_at, entry.idempotency_key),
            )
            return entry

    def get_transaction(self, transaction_id: str) -> Transaction | None:
        if not isinstance(transaction_id, str):
            raise ValueError("Transaction ID harus berupa UUID.")
        try:
            canonical_id = str(UUID(transaction_id))
        except ValueError as exc:
            raise ValueError("Transaction ID harus berupa UUID.") from exc
        if transaction_id != canonical_id:
            raise ValueError("Transaction ID harus berupa UUID kanonik huruf kecil.")
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
            return Transaction(**dict(row)) if row is not None else None

    def list_transactions(
        self, *, start_date: str | None = None, end_date: str | None = None,
        transaction_type: str | None = None,
    ) -> list[Transaction]:
        """Return in time/ID order; both local calendar dates are inclusive."""
        params = _bounds(start_date, end_date)
        params["kind"] = _type(transaction_type) if transaction_type is not None else None
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM transactions" + _FILTER
                + "AND (:kind IS NULL OR transaction_type = :kind) ORDER BY occurred_at, id",
                params,
            )
            return [Transaction(**dict(row)) for row in rows]

    def cash_flow(self, *, start_date: str | None = None, end_date: str | None = None) -> CashFlow:
        """Sum exact integers without SQLite SUM's signed-64-bit overflow."""
        income = expense = count = 0
        with self._connection() as conn:
            rows = conn.execute("SELECT transaction_type, amount_rupiah FROM transactions" + _FILTER,
                                _bounds(start_date, end_date))
            for kind, amount in rows:
                if kind == "income":
                    income += amount
                else:
                    expense += amount
                count += 1
        return CashFlow(income, expense, income - expense, count)
