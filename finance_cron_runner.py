"""Report new fictional analysis results without a model or an Excel export."""

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

# The installer replaces this single literal in its profile-local copy.
_INSTALLED: tuple[str, str] | None = None


def engine(root: Path, ledger: str, operation: str) -> list[dict[str, Any]]:
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', ledger):
        raise ValueError
    # Keep OS essentials only; inherited provider credentials and Python overrides are not needed.
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'TMPDIR'}}
    result = subprocess.run(
        [sys.executable, '-E', '-s', '-B', str(root / 'finance_analysis.py'), '--ledger', ledger, operation],
        cwd=root, env=env, capture_output=True, timeout=45, check=True,
    )
    reply = json.loads(result.stdout)
    if (not isinstance(reply, dict) or reply.get('ok') is not True or reply.get('operation') != operation
            or not isinstance(reply.get('data'), list) or len(reply['data']) > 5
            or not all(isinstance(row, dict) for row in reply['data'])):
        raise ValueError
    return reply['data']


def _number(value: Any, *, optional: bool = False, ratio: bool = False) -> str:
    if optional and value is None:
        return 'belum tersedia'
    if type(value) is int:
        return str(value)
    if ratio and type(value) is float and math.isfinite(value):
        return f'{value:.2f}'
    raise ValueError


def _report(row: dict[str, Any]) -> str:
    period = row['period']
    result = row['result']
    if row['kind'] == 'weekly' and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', period):
        cash = result['cash_flow']
        income, expense, net = (_number(cash[k]) for k in ('total_income', 'total_expense', 'net_cash_flow'))
        return f'Minggu {period}: pemasukan Rp{income}; pengeluaran Rp{expense}; arus kas Rp{net} (bukan saldo bank).'
    if row['kind'] == 'quarterly' and re.fullmatch(r'[0-9]{4}-Q[1-4]', period):
        fund = result['fund']
        metrics = [f'{label}: {_number(fund[key], optional=True, ratio=ratio)}'
                   for label, key, ratio in [('saldo (Rp)', 'balance_rupiah', False),
                                             ('target (Rp)', 'target_rupiah', False),
                                             ('cakupan (bulan)', 'coverage_months', True),
                                             ('progres (%)', 'progress_percent', True),
                                             ('kekurangan (Rp)', 'shortfall_rupiah', False)]]
        return f'Dana darurat {period} (alokasi saat analisis, bukan historis): ' + '; '.join(metrics) + '.'
    raise ValueError


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError


def main(argv: list[str] | None = None) -> int:
    try:
        if _INSTALLED is not None:
            root, ledger = Path(_INSTALLED[0]), _INSTALLED[1]
            operation = 'run'
        else:
            parser = _Parser(description=__doc__, allow_abbrev=False)
            parser.add_argument('--ledger', required=True)
            parser.add_argument('operation', choices=('dry-run', 'run'))
            args = parser.parse_args(argv)
            root, ledger, operation = Path(__file__).resolve().parent, args.ledger, args.operation

        due = engine(root, ledger, 'check-due')
        runnable = sum(row['action'] in ('run', 'reconcile') for row in due)
        if operation == 'dry-run':
            print(json.dumps({'runnable': runnable, 'requires_review': len(due) - runnable}))
        elif runnable:
            results = engine(root, ledger, 'run-due')
            if any(row['status'] not in ('completed', 'failed') for row in results):
                raise ValueError
            lines = [_report(row) for row in results if row['status'] == 'completed']
            if lines:
                print('Simulasi - data fiktif\n' + '\n'.join(lines))
            if any(row['status'] == 'failed' for row in results):
                print('Analisis gagal; periksa riwayat SQLite dan gunakan retry eksplisit jika perlu.', file=sys.stderr)
                return 1
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        print('Pemeriksaan analisis gagal; periksa instalasi dan ledger fiktif secara lokal.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
