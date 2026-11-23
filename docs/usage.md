# Fictional ledger CLI walkthrough

Run from a disposable clone with the project venv and `requirements-reporting.txt` installed. No Hermes account is needed. These commands create the named demo ledger and replace the clone's single report file. Never use real data or run this demo where you want to keep an existing workbook.

## Windows PowerShell

```powershell
'{"transaction_type":"expense","amount_rupiah":25000,"category":"Food","occurred_at":"2026-11-01T12:00:00+07:00","idempotency_key":"smoke-expense-01"}' | .\.venv\Scripts\python.exe -B finance_cli.py --ledger lesson5d-demo add
'{}' | .\.venv\Scripts\python.exe -B finance_cli.py --ledger lesson5d-demo summary
.\.venv\Scripts\python.exe -B finance_reporting.py --ledger lesson5d-demo export
```

## Linux Bash

```bash
./.venv/bin/python -B finance_cli.py --ledger lesson5d-demo add <<'FINANCE_JSON'
{"transaction_type":"expense","amount_rupiah":25000,"category":"Food","occurred_at":"2026-11-01T12:00:00+07:00","idempotency_key":"smoke-expense-01"}
FINANCE_JSON
printf '%s\n' '{}' | ./.venv/bin/python -B finance_cli.py --ledger lesson5d-demo summary
./.venv/bin/python -B finance_reporting.py --ledger lesson5d-demo export
```

On a clean clone, expect `total_expense: 25000`, `net_cash_flow: -25000`, and `transaction_count: 1`. The export should return `ok: true`, `verified: true` under `data`, and `reports/laporan-keuangan.xlsx`. Repeat the exact add request and key to see idempotency; it should still report one transaction in the next summary. The CLI's `add` is a compatibility command; Hermes uses `prepare-add` then `commit-add` for new conversations.

See each skill for JSON request fields and confirmation rules: [transactions and recovery](../.hermes/skills/finance-transactions/SKILL.md), [budgets](../.hermes/skills/finance-budgets/SKILL.md), [emergency fund](../.hermes/skills/finance-emergency/SKILL.md), [savings goals](../.hermes/skills/finance-savings/SKILL.md), and [reporting](../.hermes/skills/finance-reporting/SKILL.md).
