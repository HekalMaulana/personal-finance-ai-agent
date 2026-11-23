"""Read exported workbooks independently against isolated fictional fixtures."""

import json
import sqlite3
import subprocess
import sys
import unittest
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from openpyxl import load_workbook

import finance_reporting as reporting
from finance_storage import TransactionStore

ROOT = Path(__file__).resolve().parents[1]
SHEETS = ["Dashboard", "Transaksi", "Bulanan", "Anggaran", "Dana Darurat", "Target Tabungan"]


def add(store, kind, amount, when, key, category="Simulasi", description=None):
    return store.add_transaction(transaction_type=kind, amount_rupiah=amount,
                                 occurred_at=when, idempotency_key=key,
                                 category=category, description=description)


class ReportingUnitTests(unittest.TestCase):
    def test_monthly_aggregation_uses_local_month_and_exact_integers(self):
        with TemporaryDirectory() as sandbox:
            store = TransactionStore(Path(sandbox) / "fixture.db")
            add(store, "income", 5_000_000, "2026-10-31T16:59:59.999999Z", "oct")
            add(store, "expense", 25_000, "2026-10-31T17:00:00Z", "nov")
            rows = store.list_versioned_transactions()
        total, months = reporting.summarize(rows)
        self.assertEqual(total, (5_000_000, 25_000, 4_975_000, 2))
        self.assertEqual(months, [("2026-10", (5_000_000, 0, 5_000_000, 1)),
                                  ("2026-11", (0, 25_000, -25_000, 1))])


class ReportingIntegrationTests(unittest.TestCase):
    def setUp(self):
        sandbox = TemporaryDirectory()
        self.addCleanup(sandbox.cleanup)
        self.root = Path(sandbox.name)
        self.db = self.root / "fixture.db"
        self.out = self.root / "reports" / "laporan-keuangan.xlsx"
        self.store = TransactionStore(self.db)

    def test_export_matches_independent_sql_and_preserves_database(self):
        add(self.store, "income", 5_000_000, "2026-10-31T16:59:59.999999Z", "oct")
        original = add(self.store, "expense", 250_000, "2026-10-31T16:59:59Z", "corrected")
        self.store.correct_transaction(original.id, expected_version=0,
                                       changes={"amount_rupiah": 25_000, "occurred_at": "2026-10-31T17:00:00Z"},
                                       reason="Koreksi simulasi", idempotency_key="revision")
        self.store.prepare_add(transaction_type="expense", amount_rupiah=9000, category="Belum commit",
                               occurred_at="2026-11-01T12:00:00+07:00", idempotency_key="prepared")
        with closing(sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True)) as conn:
            income, expense, count = conn.execute("""
                WITH latest AS (
                    SELECT *, row_number() OVER (PARTITION BY transaction_id ORDER BY version DESC) AS n
                    FROM transaction_corrections
                )
                SELECT sum(CASE WHEN coalesce(c.transaction_type, t.transaction_type) = 'income'
                                THEN coalesce(c.amount_rupiah, t.amount_rupiah) ELSE 0 END),
                       sum(CASE WHEN coalesce(c.transaction_type, t.transaction_type) = 'expense'
                                THEN coalesce(c.amount_rupiah, t.amount_rupiah) ELSE 0 END), count(*)
                FROM transactions t LEFT JOIN latest c ON c.transaction_id = t.id AND c.n = 1
            """).fetchone()
        before = (sha256(self.db.read_bytes()).hexdigest(), self.db.stat().st_mtime_ns)
        reporting.export_report(self.db, self.out, ledger="fixture")
        self.assertEqual((sha256(self.db.read_bytes()).hexdigest(), self.db.stat().st_mtime_ns), before)
        self.assertEqual(list(self.root.glob("fixture.db*")), [self.db])
        wb = load_workbook(self.out)
        self.addCleanup(wb.close)
        self.assertEqual(wb.sheetnames, SHEETS)
        self.assertEqual(tuple(wb["Dashboard"][f"B{i}"].value for i in range(5, 9)),
                         (income, expense, income - expense, count))
        rows = list(wb["Transaksi"].values)[4:]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1], (original.id, "2026-11-01T00:00:00.000000+07:00", "expense",
                                   "Simulasi", None, 25_000, 1))
        self.assertEqual(list(wb["Bulanan"].values)[4:], [("2026-10", 5_000_000, 0, 5_000_000, 1),
                                                            ("2026-11", 0, 25_000, -25_000, 1)])
        self.assertEqual(wb["Transaksi"].freeze_panes, "A5")
        self.assertEqual(wb["Transaksi"].auto_filter.ref, "A4:G6")
        with ZipFile(self.out) as archive:
            chart = archive.read("xl/charts/chart1.xml")
            self.assertIn(b"Bulanan", chart)
        for name in SHEETS[3:]:
            values = [cell.value for row in wb[name] for cell in row if cell.value is not None]
            self.assertIn("Belum dikonfigurasi", values)
            self.assertTrue(all(isinstance(value, str) for value in values))

    def test_empty_report_has_zero_totals_and_no_chart(self):
        reporting.export_report(self.db, self.out, ledger="fixture")
        with ZipFile(self.out) as archive:
            self.assertFalse(any(path.startswith("xl/charts/") for path in archive.namelist()))
        wb = load_workbook(self.out, read_only=True)
        with closing(wb):
            self.assertEqual(tuple(wb["Dashboard"][f"B{i}"].value for i in range(5, 9)), (0, 0, 0, 0))

    def test_text_remains_literal_on_reopen(self):
        for i, text in enumerate(("=1+2", "+1+2", "-1+2", "@SUM(1)", "#REF!")):
            add(self.store, "expense", 1, "2026-11-01T12:00:00+07:00", str(i), text, text)
        reporting.export_report(self.db, self.out, ledger="fixture")
        with closing(load_workbook(self.out)) as wb:
            rows = list(wb["Transaksi"].iter_rows(min_row=5))
            self.assertEqual({str(r[3].value) for r in rows}, {"=1+2", "+1+2", "-1+2", "@SUM(1)", "#REF!"})
            self.assertTrue(all(r[3].data_type == r[4].data_type == "s" and r[3].value == r[4].value for r in rows))

    def test_invalid_xml_characters_are_replaced_only_in_workbook(self):
        text = "=Simulasi\ufffe\uffff"
        row = add(self.store, "expense", 1, "2026-11-01T12:00:00+07:00", "unicode", text, text)
        reporting.export_report(self.db, self.out, ledger="fixture")
        with closing(load_workbook(self.out)) as wb:
            for cell in (wb["Transaksi"]["D5"], wb["Transaksi"]["E5"]):
                self.assertEqual(cell.value, "=Simulasi\ufffd\ufffd")
                self.assertEqual(cell.data_type, "s")
        self.assertEqual(self.store.get_transaction(row.id), row)

    def test_hard_link_rejected_before_opening_sqlite(self):
        from os import link
        from finance_cli import ledger_path

        alias = self.root / "alias.db"
        link(self.db, alias)
        with patch("finance_cli._LEDGER_DIR", self.root.resolve()):
            with self.assertRaisesRegex(ValueError, "tautan"):
                ledger_path("alias")
        with patch("finance_reporting.BudgetStore") as store:
            with self.assertRaisesRegex(ValueError, "tautan"):
                reporting.export_report(alias, self.out, ledger="alias")
            store.assert_not_called()
        self.assertFalse(self.out.parent.exists())

    def test_replace_and_failure_preserve_other_files_and_existing_report(self):
        reporting.export_report(self.db, self.out, ledger="fixture")
        other = self.out.with_name("keep.txt")
        other.write_bytes(b"keep")
        before = self.out.read_bytes()
        add(self.store, "expense", 25_000, "2026-11-01T12:00:00+07:00", "next")
        with patch("finance_reporting.os.replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                reporting.export_report(self.db, self.out, ledger="fixture")
        self.assertEqual(self.out.read_bytes(), before)
        reporting.export_report(self.db, self.out, ledger="fixture")
        self.assertNotEqual(self.out.read_bytes(), before)
        with closing(load_workbook(self.out, read_only=True)) as wb:
            self.assertEqual(wb["Dashboard"]["B6"].value, 25_000)
        self.assertEqual(other.read_bytes(), b"keep")
        self.assertEqual(set(self.out.parent.iterdir()), {self.out, other})

    def test_amount_outside_excel_precision_fails_without_replacing_report(self):
        reporting.export_report(self.db, self.out, ledger="fixture")
        before = self.out.read_bytes()
        add(self.store, "income", 9_223_372_036_854_775_807, "2026-11-01T12:00:00+07:00", "huge")
        with self.assertRaises(ValueError):
            reporting.export_report(self.db, self.out, ledger="fixture")
        self.assertEqual(self.out.read_bytes(), before)

    def test_cli_only_exports_on_explicit_operation(self):
        from shutil import copyfile

        for name in ("finance_cli.py", "finance_storage.py", "finance_budgets.py", "finance_emergency.py", "finance_savings.py", "finance_reporting.py"):
            copyfile(ROOT / name, self.root / name)

        def cli(script, operation, payload=None, ledger="lesson4-fixture"):
            result = subprocess.run([sys.executable, "-B", script, "--ledger", ledger, operation],
                                    input=json.dumps(payload or {}).encode(), capture_output=True,
                                    cwd=self.root, timeout=15)
            self.assertEqual(result.stderr, b"", result)
            response = json.loads(result.stdout)
            self.assertEqual(response["ok"], result.returncode == 0)
            return response

        self.assertFalse(cli("finance_reporting.py", "export")["ok"])
        self.assertFalse(self.out.parent.exists())
        self.assertFalse(cli("finance_reporting.py", "export", ledger="../finance")["ok"])
        original = cli("finance_cli.py", "add", dict(transaction_type="expense", amount_rupiah=25_000,
                      category="Simulasi", occurred_at="2026-11-01T12:00:00+07:00", idempotency_key="first"))["data"]
        self.assertTrue(cli("finance_cli.py", "correct", dict(id=original["id"], expected_version=0,
                        changes={"amount_rupiah": 30_000}, reason="Simulasi", idempotency_key="revision"))["ok"])
        for operation in ("list", "summary", "history"):
            self.assertTrue(cli("finance_cli.py", operation, {"id": original["id"]} if operation == "history" else {})["ok"])
        self.assertFalse(self.out.parent.exists())
        self.assertFalse(cli("finance_reporting.py", "summary")["ok"])
        result = cli("finance_reporting.py", "export")
        self.assertEqual(result["data"], {"path": "reports/laporan-keuangan.xlsx", "ledger": "lesson4-fixture",
                                          "transaction_count": 1, "verified": True})
        with closing(load_workbook(self.out, read_only=True)) as wb:
            self.assertEqual(wb["Dashboard"]["B6"].value, 30_000)
        before = self.out.read_bytes()
        self.assertTrue(cli("finance_cli.py", "summary")["ok"])
        self.assertEqual(self.out.read_bytes(), before)
