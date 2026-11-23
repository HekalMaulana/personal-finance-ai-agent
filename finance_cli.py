"""JSON CLI for named fictional ledgers. Requests arrive on UTF-8 stdin."""

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Never

from finance_budgets import BudgetExists, BudgetNotFound, BudgetStore
from finance_emergency import EmergencyFundStore, InsufficientFund
from finance_savings import SavingsNotFound, SavingsStore
from finance_storage import (
    IdempotencyConflict, StaleVersion, TransactionNotFound, TransactionStore, reject_hardlinked_ledger,
)

_ROOT = Path(__file__).resolve().parent
_LEDGER_DIR = _ROOT / "data" / "finance-cli"
_LEDGER = re.compile(r"[a-z][a-z0-9-]{0,47}")
# A compact ASCII JSON correction can use 12 bytes per Unicode character.
# The 1,228 allowed characters across free-text fields fit within 16 KiB.
_MAX_REQUEST = 16 * 1024
_DATES = {"start_date", "end_date"}
_BUDGET_KEY = {"period", "category"}
_BUDGET_WRITE = _BUDGET_KEY | {"amount_rupiah", "idempotency_key"}
_BUDGET_FIELDS = {
    "budget-create": (_BUDGET_WRITE, set()),
    "budget-update": (_BUDGET_WRITE | {"expected_version", "confirmed", "reason"}, set()),
    "budget-get": (_BUDGET_KEY, set()),
    "budget-history": (_BUDGET_KEY, set()),
    "budget-summary": ({"period"}, {"category", "above_warning"}),
}
_EMERGENCY_FIELDS = {
    "emergency-configure": ({"idempotency_key"}, {"essential_rupiah", "target_months", "expected_version", "confirmed", "reason"}),
    "emergency-opening": ({"amount_rupiah", "idempotency_key"}, {"expected_revision", "confirmed", "reason"}),
    "emergency-move": ({"direction", "amount_rupiah", "idempotency_key"}, {"description"}),
    "emergency-summary": (set(), {"monthly_contribution_rupiah"}),
    "emergency-history": (set(), set()),
}
_SAVINGS_ID = {"id"}
_SAVINGS_GOAL = {"name", "target_rupiah"}
_SAVINGS_CONFIRM = {"expected_revision", "confirmed", "reason", "idempotency_key"}
_SAVINGS_FIELDS = {
    "savings-create": (_SAVINGS_GOAL | {"idempotency_key"}, {"due_date"}),
    "savings-list": (set(), set()),
    "savings-get": (_SAVINGS_ID, {"monthly_contribution_rupiah"}),
    "savings-history": (_SAVINGS_ID, set()),
    "savings-preview": (_SAVINGS_ID, _SAVINGS_GOAL | {"due_date", "amount_rupiah"}),
    "savings-update": (_SAVINGS_ID | _SAVINGS_GOAL | _SAVINGS_CONFIRM | {"due_date"}, set()),
    "savings-opening": (_SAVINGS_ID | _SAVINGS_CONFIRM | {"amount_rupiah"}, set()),
    "savings-move": (_SAVINGS_ID | {"direction", "amount_rupiah", "idempotency_key"}, {"description"}),
}
_FIELDS = {
    **_SAVINGS_FIELDS,
    **_BUDGET_FIELDS,
    **_EMERGENCY_FIELDS,
    "add": ({"transaction_type", "amount_rupiah", "category", "occurred_at", "idempotency_key"}, {"description"}),
    "prepare-add": ({"transaction_type", "amount_rupiah", "category", "occurred_at", "idempotency_key"}, {"description"}),
    "commit-add": ({"operation_id"}, set()),
    "operation-status": (set(), {"operation_id", "idempotency_key"}),
    "find-add": ({"amount_rupiah"}, _DATES | {"category", "transaction_type"}),
    "get": ({"id"}, {"include_version"}),
    "correct": ({"id", "expected_version", "changes", "reason", "idempotency_key"}, set()),
    "history": ({"id"}, set()),
    "list": (set(), _DATES | {"transaction_type"}),
    "summary": (set(), _DATES),
}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError("Gunakan --ledger NAMA dan operasi yang tersedia di --help.")


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
        raise ValueError(f"Payload JSON melebihi {_MAX_REQUEST} byte.")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                             parse_constant=_invalid_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Masukan harus satu objek JSON UTF-8 yang valid.") from exc
    required, optional = _FIELDS[operation]
    if not isinstance(payload, dict) or not required <= payload.keys() <= required | optional:
        raise ValueError("Field JSON wajib kurang atau ada field yang tidak dikenali.")
    return payload


def ledger_path(name: str) -> Path:
    if not _LEDGER.fullmatch(name):
        raise ValueError("Nama ledger: 1–48 karakter ASCII huruf kecil, angka, atau tanda hubung; awali dengan huruf.")
    # Avoid Windows device names, including when followed by a suffix.
    if re.fullmatch(r"con|prn|aux|nul|com[0-9]|lpt[0-9]", name):
        raise ValueError("Nama ledger dicadangkan.")
    path = _LEDGER_DIR / (name + ".db")
    if path.resolve() != path:
        raise ValueError("Lokasi ledger berupa tautan atau berada di luar lokasi yang diizinkan.")
    reject_hardlinked_ledger(path)
    return path


def _emit(status: int, *, operation: str | None = None, data: Any = None,
          code: str = "", message: str = "") -> int:
    response = {"ok": True, "operation": operation, "data": data} if status == 0 else {
        "ok": False, "error": {"code": code, "message": message},
    }
    print(json.dumps(response, ensure_ascii=True, allow_nan=False))
    return status


def _budget_request(path: Path, operation: str, payload: dict[str, Any]) -> Any:
    store = BudgetStore(path)
    if operation == "budget-create":
        return asdict(store.create_budget(**payload))
    if operation == "budget-update":
        return asdict(store.update_budget(**payload))
    if operation == "budget-get":
        result = store.get_budget(**payload)
        if result is None:
            raise BudgetNotFound("Anggaran belum dikonfigurasi.")
        return asdict(result)
    if operation == "budget-history":
        return [asdict(row) for row in store.budget_history(**payload)]
    return [asdict(row) for row in store.budget_summary(**payload)]


def _emergency_request(path: Path, operation: str, payload: dict[str, Any]) -> Any:
    store = EmergencyFundStore(path)
    if operation == "emergency-configure":
        return asdict(store.configure(**payload))
    if operation == "emergency-opening":
        return asdict(store.set_opening(**payload))
    if operation == "emergency-move":
        return asdict(store.move(**payload))
    if operation == "emergency-summary":
        return asdict(store.summary(**payload))
    configurations, movements = store.history()
    return {"configurations": [asdict(row) for row in configurations],
            "movements": [asdict(row) for row in movements]}


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--ledger", required=True, help="nama ledger fiktif di data/finance-cli/")
    parser.add_argument("operation", choices=_FIELDS)
    try:
        args = parser.parse_args(argv)
        payload = _request(args.operation)
        path = ledger_path(args.ledger)
        if args.operation == "operation-status" and (len(payload) != 1 or None in payload.values()):
            raise ValueError("Pilih tepat satu: operation_id atau idempotency_key.")
        creates = args.operation in ("add", "prepare-add")
        writing = creates or args.operation in ("correct", "commit-add")
        if not creates and not path.exists():
            return _emit(4, code="database_not_found", message="Ledger belum ada.")
        if args.operation in _BUDGET_FIELDS:
            return _emit(0, operation=args.operation, data=_budget_request(path, args.operation, payload))
        if args.operation in _EMERGENCY_FIELDS:
            return _emit(0, operation=args.operation, data=_emergency_request(path, args.operation, payload))
        if args.operation in _SAVINGS_FIELDS:
            store_savings = SavingsStore(path)
            handlers: dict[str, Callable[..., Any]] = {
                "savings-create": store_savings.create, "savings-list": store_savings.list_goals,
                "savings-get": store_savings.get, "savings-history": store_savings.history,
                "savings-preview": store_savings.preview, "savings-update": store_savings.update,
                "savings-opening": store_savings.opening, "savings-move": store_savings.move,
            }
            return _emit(0, operation=args.operation, data=handlers[args.operation](**payload))
        store = TransactionStore(path, read_only=not writing, defer_init=writing)
        if args.operation == "add":
            data: Any = asdict(store.add_transaction(**payload))
        elif args.operation == "prepare-add":
            data = store.prepare_add(**payload)
        elif args.operation in ("commit-add", "operation-status"):
            data = (store.commit_add(**payload) if args.operation == "commit-add"
                    else store.operation_status(**payload))
            if data is None:
                return _emit(4, code="operation_not_found", message="Identitas operasi tidak ditemukan; jangan menebak hasilnya.")
        elif args.operation == "find-add":
            data = store.find_add(**payload)
        elif args.operation == "correct":
            target = payload.pop("id")
            data = asdict(store.correct_transaction(target, **payload))
        elif args.operation == "history":
            original, revisions = store.transaction_history(payload["id"])
            data = {"original": asdict(original), "corrections": [asdict(r) for r in revisions]}
        elif args.operation == "get":
            include_version = payload.get("include_version", False)
            if type(include_version) is not bool:
                raise ValueError("include_version harus boolean.")
            found = store.get_versioned_transaction(payload["id"])
            if found is None:
                raise TransactionNotFound("Transaction ID tidak ditemukan.")
            row, version = found
            data = asdict(row)
            if include_version:
                data["version"] = version
        elif args.operation == "list":
            data = [asdict(row) for row in store.list_transactions(**payload)]
        else:
            data = asdict(store.cash_flow(**payload))
    except IdempotencyConflict as exc:
        return _emit(3, code="idempotency_conflict", message=str(exc))
    except StaleVersion as exc:
        return _emit(6, code="stale_version", message=str(exc))
    except InsufficientFund as exc:
        return _emit(9, code="insufficient_fund", message=str(exc))
    except BudgetExists as exc:
        return _emit(8, code="budget_exists", message=str(exc))
    except BudgetNotFound as exc:
        return _emit(4, code="budget_not_found", message=str(exc))
    except SavingsNotFound as exc:
        return _emit(4, code="savings_not_found", message=str(exc))
    except TransactionNotFound as exc:
        return _emit(4, code="transaction_not_found", message=str(exc))
    except ValueError as exc:
        return _emit(2, code="invalid_input", message=str(exc))
    except (sqlite3.Error, OSError, RuntimeError):
        return _emit(5, code="storage_error", message="Operasi penyimpanan gagal; jangan anggap transaksi tersimpan.")
    return _emit(0, operation=args.operation, data=data)


if __name__ == "__main__":
    raise SystemExit(main())
