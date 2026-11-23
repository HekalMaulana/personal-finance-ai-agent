"""Deterministic scheduled reviews for an existing fictional ledger."""

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from finance_budgets import BudgetStore
from finance_cli import _Parser, _emit, ledger_path
from finance_emergency import read_fund_summary
from finance_storage import CashFlow, PONTIANAK, Transaction, _effective_sql, _local_iso

Kind = Literal['weekly', 'quarterly']
WEEKLY_CATCHUP = 4
_WEEK = timedelta(days=7)
_NINE = time(9)


@dataclass(frozen=True)
class Job:
    kind: Kind
    period: str
    due_at: datetime


def due_jobs(now: datetime) -> list[Job]:
    """Return the last four due weeks and latest due quarter, oldest first."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Waktu analisis harus memiliki offset zona waktu.')
    local = now.astimezone(PONTIANAK)
    monday = local.date() - timedelta(days=local.weekday())
    weekly = datetime.combine(monday, _NINE, PONTIANAK)
    if local < weekly:
        weekly -= _WEEK
    jobs = [Job('weekly', (due - _WEEK).date().isoformat(), due)
            for due in (weekly - _WEEK * i for i in range(WEEKLY_CATCHUP))]

    quarter_day = local.date().replace(month=(local.month - 1) // 3 * 3 + 1, day=1)
    if local < datetime.combine(quarter_day, _NINE, PONTIANAK):
        previous = quarter_day - timedelta(days=1)
        quarter_day = previous.replace(month=previous.month - 2, day=1)
    quarter = datetime.combine(quarter_day, _NINE, PONTIANAK)
    jobs.append(Job('quarterly', f'{quarter.year:04}-Q{(quarter.month - 1) // 3 + 1}', quarter))
    return sorted(jobs, key=lambda job: (job.due_at, job.kind))


MAX_ATTEMPTS = 3
_JOB_KINDS = ('weekly', 'quarterly')
_RUNS = """
CREATE TABLE IF NOT EXISTS analysis_runs (
    kind TEXT NOT NULL CHECK (kind IN ('weekly', 'quarterly')),
    period TEXT NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
    started_at TEXT,
    finished_at TEXT,
    observed_at TEXT,
    result_json TEXT,
    failures_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (kind, period)
)
"""


def _now() -> datetime:
    return datetime.now(PONTIANAK)


def _key(kind: str, period: str) -> tuple[str, str]:
    if kind == 'weekly' and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', period):
        if date.fromisoformat(period).weekday() == 0:
            return kind, period
    if kind == 'quarterly' and re.fullmatch(r'[0-9]{4}-Q[1-4]', period) and period[:4] != '0000':
        return kind, period
    raise ValueError('Identitas periode harus Senin YYYY-MM-DD (weekly) atau YYYY-Q1..Q4 (quarterly).')


def _table_exists(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'analysis_runs'").fetchone() is not None


def _get(conn: sqlite3.Connection, key: tuple[str, str]) -> sqlite3.Row | None:
    return conn.execute('SELECT * FROM analysis_runs WHERE kind = ? AND period = ?', key).fetchone()


def _public(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    payload = result.pop('result_json')
    result['result'] = None if payload is None else json.loads(payload)
    result['failures'] = json.loads(result.pop('failures_json'))
    return result


def _calculate(conn: sqlite3.Connection, kind: str, period: str) -> dict[str, Any]:
    if kind == 'quarterly':
        return {'snapshot_basis': 'current_at_execution_not_historical',
                'fund': asdict(read_fund_summary(conn))}

    start = date.fromisoformat(period)
    end = start + _WEEK
    start_at = datetime.combine(start, time.min, PONTIANAK)
    end_at = datetime.combine(end, time.min, PONTIANAK)
    expenses = []
    income = expense = count = 0
    for row in conn.execute(
        'SELECT * FROM (' + _effective_sql(conn) + ') WHERE occurred_at >= ? AND occurred_at < ?',
        (_local_iso(start_at), _local_iso(end_at)),
    ):
        count += 1
        if row['transaction_type'] == 'income':
            income += row['amount_rupiah']
        else:
            expense += row['amount_rupiah']
            expenses.append(Transaction(**{name: row[name] for name in row.keys() if name != 'version'}))
    months = sorted({str(start)[:7], str(end - timedelta(days=1))[:7]})
    budgets = []
    for month in months:
        for row in BudgetStore._summarize(conn, month, None, False, expenses):
            budgets.append({'period': row.period, 'category': row.category,
                            'monthly_limit_rupiah': row.amount_rupiah, 'weekly_spent_rupiah': row.spent_rupiah,
                            'weekly_usage_percent': row.usage_percent})
    return {'start_at': start_at.isoformat(), 'end_at_exclusive': end_at.isoformat(),
            'cash_flow': asdict(CashFlow(income, expense, income - expense, count)),
            'budget_basis': 'weekly_expenses_against_effective_monthly_limits', 'budgets': budgets}


class AnalysisStore:
    """Use the existing ledger connection protections; write only the run journal."""

    def __init__(self, path: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self._ledger = BudgetStore(path)
        self._clock = _now if clock is None else clock

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        with self._ledger._connection(write=True) as conn:
            # Check under the writer lock so the schema cannot change before commit.
            table = conn.execute("SELECT type FROM pragma_table_list WHERE schema = 'main' "
                                 "AND name = 'analysis_runs' COLLATE NOCASE").fetchone()
            trigger = conn.execute("SELECT 1 FROM main.sqlite_schema WHERE type = 'trigger' "
                                   "AND tbl_name = 'analysis_runs' COLLATE NOCASE").fetchone()
            if (table is not None and table['type'] != 'table') or trigger is not None:
                raise sqlite3.DatabaseError('Unsupported analysis journal schema')
            yield conn

    def status(self, kind: str, period: str) -> dict[str, Any] | None:
        key = _key(kind, period)
        with self._ledger._connection() as conn:
            row = _get(conn, key) if _table_exists(conn) else None
            return _public(row) if row is not None else None

    def history(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Limit riwayat harus integer 1–100.')
        with self._ledger._connection() as conn:
            if not _table_exists(conn):
                return []
            return [_public(row) for row in conn.execute(
                'SELECT * FROM analysis_runs ORDER BY due_at DESC, kind LIMIT ?', (limit,),
            )]

    def check_due(self) -> list[dict[str, Any]]:
        jobs = due_jobs(self._clock())
        with self._ledger._connection() as conn:
            exists = _table_exists(conn)
            due = []
            for job in jobs:
                row = _get(conn, (job.kind, job.period)) if exists else None
                if row is not None and row['status'] == 'completed':
                    continue
                status = row['status'] if row is not None else 'pending'
                attempts = row['attempts'] if row is not None else 0
                action = {'pending': 'run', 'running': 'reconcile',
                          'failed': 'retry_explicitly' if attempts < MAX_ATTEMPTS else 'attempts_exhausted'}[status]
                due.append({'kind': job.kind, 'period': job.period, 'due_at': job.due_at.isoformat(),
                            'status': status, 'attempts': attempts, 'action': action})
            return due

    def run_due(self, *, resume: tuple[str, str] | None = None) -> list[dict[str, Any]]:
        """Catch up on launch, or explicitly resume one already persisted due job."""
        now = self._clock()
        keys: list[tuple[str, str]]
        if resume is None:
            jobs = due_jobs(now)
            keys = [(job.kind, job.period) for job in jobs]
            with self._write_connection() as conn:
                conn.execute(_RUNS)
                conn.executemany('''INSERT INTO analysis_runs (kind, period, due_at) VALUES (?, ?, ?)
                                    ON CONFLICT (kind, period) DO NOTHING''',
                                 [(job.kind, job.period, job.due_at.isoformat()) for job in jobs])
        else:
            keys = [_key(*resume)]
            if self.status(*resume) is None:
                raise LookupError('Periode belum tercatat oleh run-due.')
        outcomes = []
        for key in keys:
            with self._write_connection() as conn:
                row = _get(conn, key)
                if row is None or datetime.fromisoformat(row['due_at']) > now:
                    continue
                status, attempt = row['status'], row['attempts']
                if status == 'completed' or (status == 'failed' and (resume is None or attempt >= MAX_ATTEMPTS)):
                    continue
                if status != 'running':
                    attempt += 1
                    conn.execute("""UPDATE analysis_runs SET status = 'running', attempts = ?,
                                    started_at = ?, finished_at = NULL WHERE kind = ? AND period = ?""",
                                 (attempt, _local_iso(self._clock()), *key))
            # The claim is durable. SQLite's write lock is live ownership during analysis:
            # after a crash the OS releases it; the next runner can reconcile the same attempt.
            result = self._finish(key, attempt)
            if result is not None:
                outcomes.append(result)
        return outcomes

    def _finish(self, key: tuple[str, str], attempt: int) -> dict[str, Any] | None:
        with self._write_connection() as conn:
            row = _get(conn, key)
            if row is None or row['status'] != 'running' or row['attempts'] != attempt:
                return None
            observed = _local_iso(self._clock())
            try:
                result = json.dumps(_calculate(conn, *key), ensure_ascii=True, allow_nan=False)
            except Exception as exc:
                code = 'analysis_storage_error' if isinstance(exc, sqlite3.Error) else 'analysis_error'
                failures = json.loads(row['failures_json'])
                finished = _local_iso(self._clock())
                failures.append({'attempt': attempt, 'failed_at': finished, 'code': code})
                conn.execute("""UPDATE analysis_runs SET status = 'failed', finished_at = ?, failures_json = ?
                                WHERE kind = ? AND period = ?""", (finished, json.dumps(failures), *key))
            else:
                conn.execute("""UPDATE analysis_runs SET status = 'completed', observed_at = ?, finished_at = ?,
                                result_json = ? WHERE kind = ? AND period = ?""",
                             (observed, _local_iso(self._clock()), result, *key))
            updated = _get(conn, key)
            assert updated is not None
            return _public(updated)


class _AnalysisParser(_Parser):
    def error(self, message: str) -> Any:
        raise ValueError('Gunakan --ledger NAMA dan lihat --help untuk argumen operasi.')


def main(argv: list[str] | None = None) -> int:
    parser = _AnalysisParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--ledger', required=True)
    commands = parser.add_subparsers(dest='operation', required=True)
    commands.add_parser('check-due', allow_abbrev=False)
    run = commands.add_parser('run-due', allow_abbrev=False)
    run.add_argument('--resume', nargs=2, metavar=('KIND', 'PERIOD'))
    status = commands.add_parser('status', allow_abbrev=False)
    status.add_argument('kind', choices=_JOB_KINDS)
    status.add_argument('period')
    history = commands.add_parser('history', allow_abbrev=False)
    history.add_argument('--limit', type=int, default=20)
    try:
        args = parser.parse_args(argv)
        path = ledger_path(args.ledger)
        if not path.is_file():
            return _emit(4, code='database_not_found', message='Ledger fiktif belum ada.')
        store = AnalysisStore(path)
        data: Any
        if args.operation == 'check-due':
            data = store.check_due()
        elif args.operation == 'run-due':
            data = store.run_due(resume=tuple(args.resume) if args.resume else None)
        elif args.operation == 'status':
            data = store.status(args.kind, args.period)
            if data is None:
                raise LookupError('Periode belum tercatat oleh run-due.')
        else:
            data = store.history(limit=args.limit)
    except LookupError as exc:
        return _emit(4, code='analysis_not_found', message=str(exc))
    except ValueError as exc:
        return _emit(2, code='invalid_input', message=str(exc))
    except (OSError, sqlite3.Error, RuntimeError):
        return _emit(5, code='storage_error', message='Operasi analisis gagal; periksa status sebelum retry.')
    return _emit(0, operation=args.operation, data=data)


if __name__ == '__main__':
    raise SystemExit(main())
