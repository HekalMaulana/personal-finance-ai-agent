"""JSON CLI for named fictional ledgers. Requests arrive on UTF-8 stdin."""

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Never

from finance_storage import IdempotencyConflict, TransactionStore

_ROOT = Path(__file__).resolve().parent
_LEDGER_DIR = _ROOT / "data" / "finance-cli"
_LEDGER = re.compile(r"[a-z][a-z0-9-]{0,47}")
_MAX_REQUEST = 8192
_DATES = {"start_date", "end_date"}
_FIELDS = {
    "add": ({"transaction_type", "amount_rupiah", "category", "occurred_at", "idempotency_key"}, {"description"}),
    "get": ({"id"}, set()),
    "list": (set(), _DATES | {"transaction_type"}),
    "summary": (set(), _DATES),
}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError("Gunakan --ledger NAMA dan operasi add, get, list, atau summary.")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Field JSON tidak boleh muncul dua kali.")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("Konstanta numerik non-JSON tidak diizinkan.")


def _request(operation: str) -> dict[str, Any]:
    raw = sys.stdin.buffer.read(_MAX_REQUEST + 1)
    if len(raw) > _MAX_REQUEST:
        raise ValueError("Payload JSON melebihi 8192 byte.")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                             parse_constant=_invalid_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Masukan harus satu objek JSON UTF-8 yang valid.") from exc
    required, optional = _FIELDS[operation]
    if not isinstance(payload, dict) or not required <= payload.keys() <= required | optional:
        raise ValueError("Field JSON wajib kurang atau ada field yang tidak dikenali.")
    return payload


def _db_path(name: str) -> Path:
    if not _LEDGER.fullmatch(name):
        raise ValueError("Nama ledger: 1–48 karakter ASCII huruf kecil, angka, atau tanda hubung; awali dengan huruf.")
    # Avoid Windows device names, including when followed by a suffix.
    if re.fullmatch(r"con|prn|aux|nul|com[0-9]|lpt[0-9]", name):
        raise ValueError("Nama ledger dicadangkan.")
    path = _LEDGER_DIR / (name + ".db")
    if path.resolve() != path:
        raise ValueError("Lokasi ledger berupa tautan atau berada di luar lokasi yang diizinkan.")
    return path


def _emit(status: int, *, operation: str | None = None, data: Any = None,
          code: str = "", message: str = "") -> int:
    response = {"ok": True, "operation": operation, "data": data} if status == 0 else {
        "ok": False, "error": {"code": code, "message": message},
    }
    print(json.dumps(response, ensure_ascii=True, allow_nan=False))
    return status


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--ledger", required=True, help="nama ledger fiktif di data/finance-cli/")
    parser.add_argument("operation", choices=_FIELDS)
    try:
        args = parser.parse_args(argv)
        payload = _request(args.operation)
        path = _db_path(args.ledger)
        writing = args.operation == "add"
        if not writing and not path.exists():
            return _emit(4, code="database_not_found", message="Ledger belum ada; pembacaan tidak membuat database.")
        store = TransactionStore(path, read_only=not writing, defer_init=writing)
        if writing:
            data: Any = asdict(store.add_transaction(**payload))
        elif args.operation == "get":
            row = store.get_transaction(payload["id"])
            if row is None:
                return _emit(4, code="transaction_not_found", message="Transaction ID tidak ditemukan.")
            data = asdict(row)
        elif args.operation == "list":
            data = [asdict(row) for row in store.list_transactions(**payload)]
        else:
            data = asdict(store.cash_flow(**payload))
    except IdempotencyConflict as exc:
        return _emit(3, code="idempotency_conflict", message=str(exc))
    except ValueError as exc:
        return _emit(2, code="invalid_input", message=str(exc))
    except (sqlite3.Error, OSError, RuntimeError):
        return _emit(5, code="storage_error", message="Operasi penyimpanan gagal; jangan anggap transaksi tersimpan.")
    return _emit(0, operation=args.operation, data=data)


if __name__ == "__main__":
    raise SystemExit(main())
