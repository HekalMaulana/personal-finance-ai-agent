"""Explicit XLSX exports from read-only, named fictional ledgers."""

import os
import re
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime
from math import isclose
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Iterable, Never
from zipfile import BadZipFile

from finance_budgets import BudgetStore, BudgetSummary
from finance_cli import _Parser, _emit, ledger_path, reject_hardlinked_ledger
from finance_storage import DEFAULT_DB_PATH, PONTIANAK, Transaction

if TYPE_CHECKING:
    from openpyxl import Workbook
    from openpyxl.worksheet.worksheet import Worksheet

ROOT = Path(__file__).resolve().parent
REPORT = Path("reports/laporan-keuangan.xlsx")
SHEETS = ("Dashboard", "Transaksi", "Bulanan", "Anggaran", "Dana Darurat", "Target Tabungan")
RUPIAH = '"Rp" #,##0;[Red]-"Rp" #,##0;"Rp" 0'
# Excel retains only 15 significant decimal digits for numeric values.
MAX_EXCEL_INTEGER = 10**15 - 1
Totals = tuple[int, int, int, int]
BUDGET_HEADER = ("Periode", "Kategori", "Anggaran (Rp)", "Realisasi (Rp)", "Sisa (Rp)", "Penggunaan", "Status")
BudgetCells = tuple[str, str, int, int, int, float, str]


def _excel_text(value: str) -> str:
    return re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]", "\ufffd", value)


def summarize(rows: list[tuple[Transaction, int]]) -> tuple[Totals, list[tuple[str, Totals]]]:
    """Calculate exact Rupiah totals, grouped by the effective local month."""
    months: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for row, _ in rows:
        month = datetime.fromisoformat(row.occurred_at).astimezone(PONTIANAK).isoformat()[:7]
        group = months[month]
        group[0 if row.transaction_type == "income" else 1] += row.amount_rupiah
        group[2] += 1
    income = sum(group[0] for group in months.values())
    expense = sum(group[1] for group in months.values())
    totals = income, expense, income - expense, len(rows)
    return totals, [(month, (inc, exp, inc - exp, count)) for month, (inc, exp, count) in sorted(months.items())]


def _sheet_header(ws: "Worksheet", title: str, subtitle: str, widths: tuple[int, ...]) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    ws.sheet_view.showGridLines = False
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(widths))
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(widths))
    ws["A1"] = title
    ws["A1"].font = Font(color="FFFFFF", bold=True, size=17)
    ws["A1"].fill = PatternFill("solid", fgColor="173650")
    ws["A1"].alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[1].height = 32
    ws["A2"] = subtitle
    ws["A2"].font = Font(color="315665", italic=True)
    ws.row_dimensions[2].height = 20
    for col, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width


def _tabular_rows(ws: "Worksheet", header: tuple[str, ...],
                  rows: Iterable[tuple[str | int | float | None, ...]], currency: tuple[int, ...],
                  *, wrap_column: int | None = None, filter_rows: bool = True) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    heading = PatternFill("solid", fgColor="216A70")
    alternate = PatternFill("solid", fgColor="EDF6F6")
    white_bold = Font(color="FFFFFF", bold=True)
    wrapped = Alignment(wrap_text=True, vertical="top")
    for col, label in enumerate(header, 1):
        cell = ws.cell(4, col, label)
        cell.fill, cell.font = heading, white_bold
    ws.row_dimensions[4].height = 22
    for i, values in enumerate(rows, 5):
        for col, value in enumerate(values, 1):
            if isinstance(value, str):
                value = _excel_text(value)
            cell = ws.cell(i, col, value)
            if isinstance(value, str):
                # Always serialize text as text, even if openpyxl inferred formula/error.
                cell.data_type = "s"
            if col in currency:
                cell.number_format = RUPIAH
            if col == wrap_column:
                cell.alignment = wrapped
            if i % 2 == 1:
                cell.fill = alternate
    ws.freeze_panes = "A5"
    if filter_rows:
        ws.auto_filter.ref = f"A4:{get_column_letter(len(header))}{ws.max_row}"


def _workbook(rows: list[tuple[Transaction, int]], ledger: str, totals: Totals,
              months: list[tuple[str, Totals]], budgets: list[BudgetCells]) -> "Workbook":
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.chart.data_source import AxDataSource, StrData, StrRef, StrVal

    wb = Workbook()
    dashboard = wb.active
    assert dashboard is not None
    dashboard.title = SHEETS[0]
    data, monthly, budget_sheet, *unconfigured = [wb.create_sheet(name) for name in SHEETS[1:]]
    subtitle = f"Simulasi — data fiktif | Ledger: {ledger} | Asia/Pontianak (UTC+07:00)"
    _sheet_header(dashboard, "Laporan Keuangan", subtitle, (26, 26, 24, 24, 20))
    _tabular_rows(dashboard, ("Metrik", "Nilai"), zip(
        ("Total pemasukan", "Total pengeluaran", "Arus kas bersih", "Jumlah transaksi"), totals,
    ), (), filter_rows=False)
    for row in range(5, 8):
        dashboard.cell(row, 2).number_format = RUPIAH
    dashboard.merge_cells("A10:E10")
    dashboard["A10"] = "Arus kas bersih = pemasukan − pengeluaran; bukan saldo rekening aktual."
    _sheet_header(data, "Transaksi — versi efektif", subtitle, (39, 37, 15, 27, 48, 24, 17))
    _tabular_rows(data, ("ID transaksi", "Tanggal transaksi", "Jenis transaksi", "Kategori", "Deskripsi",
                         "Nominal (Rp)", "Versi efektif"), (
        (row.id, row.occurred_at, row.transaction_type, row.category, row.description, row.amount_rupiah, version)
        for row, version in rows
    ), (6,), wrap_column=5)
    _sheet_header(monthly, "Rekap Bulanan", subtitle, (19, 23, 23, 23, 20))
    _tabular_rows(monthly, ("Bulan", "Total pemasukan", "Total pengeluaran", "Arus kas bersih", "Jumlah transaksi"),
                  ((month, *group) for month, group in months), (2, 3, 4))
    if months:
        chart = BarChart()
        chart.type = "col"
        chart.title = "Pemasukan dan Pengeluaran Bulanan"
        chart.y_axis.title = "Rupiah"
        chart.x_axis.title = "Bulan (Asia/Pontianak)"
        chart.width, chart.height = 23, 12
        chart.add_data(Reference(monthly, min_col=2, max_col=3, min_row=4, max_row=monthly.max_row),
                       titles_from_data=True)
        categories = Reference(monthly, min_col=1, min_row=5, max_row=monthly.max_row)
        labels = StrData(ptCount=len(months), pt=[StrVal(idx=i, v=month) for i, (month, _) in enumerate(months)])
        for series, color in zip(chart.series, ("216A70", "C16A3B")):
            series.cat = AxDataSource(strRef=StrRef(f=str(categories), strCache=labels))
            series.graphicalProperties.solidFill = color
        dashboard.add_chart(chart, "A12")
    _sheet_header(budget_sheet, "Anggaran Bulanan", subtitle, (15, 30, 22, 22, 22, 17, 22))
    if budgets:
        _tabular_rows(budget_sheet, BUDGET_HEADER, budgets, (3, 4, 5))
        for index in range(5, len(budgets) + 5):
            budget_sheet.cell(index, 6).number_format = "0.00%"
    else:
        budget_sheet["A4"] = "Belum dikonfigurasi"
        budget_sheet.freeze_panes = "A4"
    for ws in unconfigured:
        _sheet_header(ws, ws.title, subtitle, (27, 26, 24, 24))
        ws["A4"] = "Belum dikonfigurasi"
        ws.freeze_panes = "A4"
    return wb


def _budget_cells(row: BudgetSummary) -> BudgetCells:
    return (row.period, _excel_text(row.category), row.amount_rupiah, row.spent_rupiah,
            row.remaining_rupiah, row.spent_rupiah / row.amount_rupiah, row.status)


def _verify_budgets(ws: "Worksheet", expected: list[BudgetCells]) -> None:
    if ws.max_row != len(expected) + 4:
        raise OSError("Jumlah baris anggaran gagal diverifikasi.")
    rows = ws.iter_rows(min_row=4, max_col=7, values_only=True)
    header = next(rows)
    if not expected:
        if header[0] != "Belum dikonfigurasi":
            raise OSError("Status anggaran kosong gagal diverifikasi.")
        return
    if header != BUDGET_HEADER:
        raise OSError("Kolom anggaran gagal diverifikasi.")
    for actual, budget in zip(rows, expected, strict=True):
        if (actual[:5] != budget[:5] or actual[6] != budget[6]
                or not isinstance(actual[5], (int, float)) or isinstance(actual[5], bool) or not isclose(actual[5], budget[5], rel_tol=1e-14)):
            raise OSError("Nilai anggaran gagal diverifikasi.")


def export_report(db_path: Path, output: Path, *, ledger: str) -> int:
    """Export from an explicitly supplied, trusted fictional DB, never the default."""
    from openpyxl import load_workbook

    if db_path.resolve() == DEFAULT_DB_PATH or output.suffix.lower() != ".xlsx":
        raise ValueError("Gunakan ledger fiktif, dengan file keluaran .xlsx terpisah.")
    if output.resolve() == db_path.resolve():
        raise ValueError("Workbook tidak boleh menggantikan ledger.")
    reject_hardlinked_ledger(db_path)
    rows, budget_rows = BudgetStore(db_path).reporting_snapshot()
    budgets = [_budget_cells(row) for row in budget_rows]
    totals, months = summarize(rows)
    if (totals[0] > MAX_EXCEL_INTEGER or totals[1] > MAX_EXCEL_INTEGER
            or any(version > MAX_EXCEL_INTEGER for _, version in rows)
            or any(row.amount_rupiah > MAX_EXCEL_INTEGER for row in budget_rows)):
        raise ValueError("Nilai Rupiah atau versi melebihi batas presisi 15 digit Excel.")
    if max(len(rows), len(budgets)) > 1_048_572:  # Four rows precede the details.
        raise ValueError("Jumlah transaksi atau anggaran melebihi kapasitas worksheet Excel.")

    output.parent.mkdir(parents=True, exist_ok=True)
    with closing(_workbook(rows, ledger, totals, months, budgets)) as wb:
        with NamedTemporaryFile(prefix=".laporan-", suffix=".xlsx", dir=output.parent, delete=False) as handle:
            temp = Path(handle.name)
        try:
            with temp.open("wb") as stream:
                wb.save(stream)
            with closing(load_workbook(temp, read_only=True)) as saved:
                if tuple(saved.sheetnames) != SHEETS or saved["Transaksi"].max_row != len(rows) + 4:
                    raise OSError("Struktur workbook gagal diverifikasi.")
                actual = tuple(row[0] for row in saved["Dashboard"].iter_rows(
                    min_row=5, max_row=8, min_col=2, max_col=2, values_only=True,
                ))
                if actual != totals:
                    raise OSError("Total workbook gagal diverifikasi.")
                _verify_budgets(saved["Anggaran"], budgets)
            os.replace(temp, output)
        finally:
            temp.unlink(missing_ok=True)
    return len(rows)


class _ReportParser(_Parser):
    def error(self, message: str) -> Never:
        raise ValueError("Gunakan --ledger NAMA export; lihat --help.")


def main(argv: list[str] | None = None) -> int:
    parser = _ReportParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--ledger", required=True, help="nama ledger fiktif yang sudah ada")
    parser.add_argument("operation", choices=("export",))
    try:
        args = parser.parse_args(argv)
        db = ledger_path(args.ledger)
        if not db.is_file():
            return _emit(4, code="database_not_found", message="Ledger fiktif belum ada.")
        output = ROOT / REPORT
        if output.resolve() != output:
            raise ValueError("Lokasi laporan tidak boleh berupa tautan.")
        count = export_report(db, output, ledger=args.ledger)
    except ImportError:
        return _emit(7, code="dependency_missing", message="Gunakan Python dengan openpyxl (requirements-reporting.txt).")
    except ValueError as exc:
        return _emit(2, code="invalid_input", message=str(exc))
    except (sqlite3.Error, OSError, BadZipFile, RuntimeError):
        return _emit(5, code="export_error", message="Ekspor gagal; laporan sebelumnya tidak diganti.")
    return _emit(0, operation="export", data={"path": REPORT.as_posix(), "ledger": args.ledger,
                                             "transaction_count": count, "verified": True})


if __name__ == "__main__":
    raise SystemExit(main())
