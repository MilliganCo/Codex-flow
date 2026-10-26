"""Acceptance and boundary tests; no third-party test runner is needed."""

import csv
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ledgerreconcile import LedgerError, build_report, write_report

ROOT = Path(__file__).resolve().parents[1]
ORDER_HEADER = ("order_id", "currency", "amount")
PAYMENT_HEADER = ("payment_id", "order_id", "currency", "amount")


def csv_bytes(header, rows, *, bom=False, newline="\r\n"):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator=newline)
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig" if bom else "utf-8")


def report_bytes(report):
    return (json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class LedgerTests(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / ".tmp"
        temporary_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="ledger tests ", dir=temporary_root)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.orders = self.directory / "orders input.csv"
        self.payments = self.directory / "payments input.csv"
        self.output = self.directory / "report output.json"
        self.inputs([("001", "USD", "1.00")], [])

    def inputs(self, orders, payments, *, bom=False):
        self.orders.write_bytes(csv_bytes(ORDER_HEADER, orders, bom=bom))
        self.payments.write_bytes(csv_bytes(PAYMENT_HEADER, payments, bom=bom))

    def report(self):
        return build_report(self.orders, self.payments)

    def cli(self, *extra, output=None):
        return subprocess.run(
            [sys.executable, "-m", "ledgerreconcile", "--orders", str(self.orders),
             "--payments", str(self.payments), "--output", str(output or self.output), *extra],
            cwd=ROOT, capture_output=True, timeout=15,
        )

    def assert_rejected(self):
        before = (self.orders.read_bytes(), self.payments.read_bytes())
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(before, (self.orders.read_bytes(), self.payments.read_bytes()))
        self.assertEqual(list(self.directory.glob(".ledgerreconcile-*.tmp")), [])

    def test_cli_exact_schema_and_bytes(self):
        self.inputs([("001", "USD", "1.00")], [("p", "001", "USD", "1.0")])
        expected = {
            "schema": 1,
            "orders": [{"order_id": "001", "currency": "USD", "expected_cents": 100,
                        "received_cents": 100, "balance_cents": 0, "status": "paid"}],
            "totals": [{"currency": "USD", "expected_cents": 100,
                        "received_cents": 100, "balance_cents": 0}],
        }
        before = (self.orders.read_bytes(), self.payments.read_bytes())
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")
        self.assertEqual(self.output.read_bytes(), report_bytes(expected))
        self.assertEqual(before, (self.orders.read_bytes(), self.payments.read_bytes()))

    def test_exact_cents_small_values_and_upper_bound(self):
        self.inputs(
            [("tiny", "USD", "0.30"), ("max", "EUR", "1000000.00")],
            [("a", "tiny", "USD", "0.10"), ("b", "tiny", "USD", "0.2"),
             ("c", "max", "EUR", "1000000")],
        )
        entries = {row["order_id"]: row for row in self.report()["orders"]}
        self.assertEqual(entries["tiny"]["received_cents"], 30)
        self.assertEqual(entries["max"]["received_cents"], 100_000_000)
        self.assertTrue(all(row["status"] == "paid" for row in entries.values()))

    def test_all_statuses_refunds_and_unpaid_orders(self):
        ids = ("negative", "zero", "partial", "paid", "overpaid", "untouched")
        payments = [("n", "negative", "USD", "-0.01"),
                    ("z", "zero", "USD", "1"), ("zr", "zero", "USD", "-1.00"),
                    ("p", "partial", "USD", "0.99"), ("f", "paid", "USD", "1"),
                    ("o", "overpaid", "USD", "1.01")]
        self.inputs([(i, "USD", "1") for i in ids], payments)
        entries = {row["order_id"]: row for row in self.report()["orders"]}
        statuses = ("negative_net", "unpaid", "partial", "paid", "overpaid", "unpaid")
        for order_id, status in zip(ids, statuses):
            self.assertEqual(entries[order_id]["status"], status)
            self.assertEqual(entries[order_id]["balance_cents"], 100 - entries[order_id]["received_cents"])

    def test_negative_maximum_and_signed_zero_payments(self):
        self.inputs([("001", "USD", "0.01")],
                    [("p", "001", "USD", "-1000000.00"), ("z", "001", "USD", "-0.00"),
                     ("z", "001", "USD", "0")])
        entry = self.report()["orders"][0]
        self.assertEqual(entry["received_cents"], -100_000_000)
        self.assertEqual(entry["balance_cents"], 100_000_001)
        self.assertEqual(entry["status"], "negative_net")

    def test_currency_totals_include_unpaid_and_large_sums(self):
        self.inputs(
            [("a", "USD", "1000000"), ("b", "USD", "1000000"), ("c", "EUR", "0.01")],
            [("x", "a", "USD", "1000000"), ("y", "a", "USD", "1000000"),
             ("z", "c", "EUR", "-0.01")],
        )
        self.assertEqual(self.report()["totals"], [
            {"currency": "EUR", "expected_cents": 1, "received_cents": -1, "balance_cents": 2},
            {"currency": "USD", "expected_cents": 200_000_000,
             "received_cents": 200_000_000, "balance_cents": 0},
        ])

    def test_ids_preserve_spaces_case_unicode_and_leading_zeros(self):
        ids = ["1", "001", " 001", "001 ", "A", "a", " ", "é", "订单"]
        self.inputs([(i, "USD", "1") for i in ids], [])
        self.assertEqual([row["order_id"] for row in self.report()["orders"]], sorted(ids))

    def test_all_small_row_permutations_and_duplicate_payments(self):
        orders = [("1", "USD", "2"), ("001", "EUR", "1")]
        payments = [("p", "1", "USD", "1.00"), ("r", "1", "USD", "-0.01"),
                    ("e", "001", "EUR", "1")]
        baseline = None
        for order_rows in itertools.permutations(orders):
            for payment_rows in itertools.permutations(payments):
                self.inputs(order_rows, [*payment_rows, ("p", "1", "USD", "1.0")])
                actual = report_bytes(self.report())
                if baseline is None:
                    baseline = actual
                self.assertEqual(actual, baseline)
        self.inputs(orders, payments)
        self.assertEqual(report_bytes(self.report()), baseline)

    def test_payment_identity_is_the_entire_logical_payload(self):
        self.inputs([("001", "USD", "10")],
                    [("p", "001", "USD", "1"), ("p", "001", "USD", "1.0"),
                     ("p", "001", "USD", "1.00"), ("P", "001", "USD", "1.00")])
        self.assertEqual(self.report()["orders"][0]["received_cents"], 200)

    def test_conflicting_payment_duplicates_are_rejected(self):
        orders = [("001", "USD", "1"), ("other", "USD", "1"), ("eur", "EUR", "1")]
        for changed in [("p", "001", "USD", "0.99"), ("p", "other", "USD", "1"),
                        ("p", "eur", "EUR", "1")]:
            with self.subTest(changed=changed):
                self.inputs(orders, [("p", "001", "USD", "1"), changed])
                self.assert_rejected()

    def test_identical_and_changed_duplicate_orders_rejected(self):
        for amount in ("1", "1.00", "2"):
            with self.subTest(amount=amount):
                self.inputs([("001", "USD", "1"), ("001", "USD", amount)], [])
                self.assert_rejected()

    def test_unknown_order_and_currency_mismatch_rejected(self):
        for payment in [("p", "missing", "USD", "1"), ("p", "001", "EUR", "1")]:
            with self.subTest(payment=payment):
                self.inputs([("001", "USD", "1")], [payment])
                self.assert_rejected()

    def test_invalid_amount_syntax_and_bounds_in_both_inputs(self):
        invalid = ["", "NaN", "Inf", "-Inf", "+1", "1e0", "01", "00.1", ".5", "1.",
                   "1.001", "1,000", " 1", "1 ", "1\n", "١", "１.00", "1000000.01",
                   "-1000000.01", "1000001", "9" * 5000]
        for amount in invalid:
            for payment in (False, True):
                with self.subTest(amount=amount[:25], payment=payment):
                    orders = [("001", "USD", "1" if payment else amount)]
                    payments = [("p", "001", "USD", amount)] if payment else []
                    self.inputs(orders, payments)
                    with self.assertRaises(LedgerError):
                        self.report()
        self.inputs([("001", "USD", "1")], [("p", "001", "USD", "9" * 5000)])
        self.assert_rejected()

    def test_orders_reject_zero_and_negative_forms(self):
        for amount in ("0", "0.0", "0.00", "-0", "-0.00", "-0.01", "-1000000"):
            with self.subTest(amount=amount):
                self.inputs([("001", "USD", amount)], [])
                with self.assertRaises(LedgerError):
                    self.report()

    def test_empty_ids_and_invalid_currencies_rejected(self):
        invalid_orders = [("", "USD", "1")]
        invalid_orders += [("001", c, "1") for c in ("", "usd", "US", "USDD", " USD", "USD ", "ÜSD", "UＳD")]
        for row in invalid_orders:
            with self.subTest(order=row):
                self.inputs([row], [])
                with self.assertRaises(LedgerError):
                    self.report()
        for row in [("", "001", "USD", "1"), ("p", "", "USD", "1"), ("p", "001", "usd", "1")]:
            with self.subTest(payment=row):
                self.inputs([("001", "USD", "1")], [row])
                with self.assertRaises(LedgerError):
                    self.report()

    def test_header_permutations(self):
        for order_header in itertools.permutations(ORDER_HEADER):
            for payment_header in itertools.permutations(PAYMENT_HEADER):
                order = {"order_id": "001", "currency": "USD", "amount": "1"}
                payment = {"payment_id": "p", **order}
                self.orders.write_bytes(csv_bytes(order_header, [[order[h] for h in order_header]]))
                self.payments.write_bytes(csv_bytes(payment_header, [[payment[h] for h in payment_header]]))
                self.assertEqual(self.report()["orders"][0]["status"], "paid")

    def test_missing_extra_duplicate_and_spaced_headers(self):
        for path, headers in [(self.orders, ORDER_HEADER), (self.payments, PAYMENT_HEADER)]:
            variants = [headers[:-1], (*headers, "extra"), (*headers, headers[0]),
                        (headers[0],) * len(headers), (" " + headers[0], *headers[1:])]
            for header in variants:
                with self.subTest(path=path.name, header=header):
                    self.inputs([("001", "USD", "1")], [])
                    path.write_bytes(csv_bytes(header, []))
                    with self.assertRaises(LedgerError):
                        self.report()

    def test_malformed_csv_rejected_in_either_file(self):
        malformed = [b'"unfinished', b'abc"def,USD,1\n', b'"abc"x,USD,1\n',
                     b'"abc" ,USD,1\n', b'few,USD\n', b'too,many,USD,1,fields\n', b'\n']
        for path, header in [(self.orders, ORDER_HEADER), (self.payments, PAYMENT_HEADER)]:
            for bad in malformed:
                with self.subTest(path=path.name, bad=bad):
                    self.inputs([("001", "USD", "1")], [])
                    path.write_bytes(csv_bytes(header, []) + bad)
                    with self.assertRaises(LedgerError):
                        self.report()
        self.orders.write_bytes(b'order_id,currency,amount\na,USD,"1\n')
        self.assert_rejected()

    def test_bom_quotes_unicode_and_embedded_newlines(self):
        order_id = '订单, "001"\r\nline\nlast\rpart'
        payment_id = 'réfund, "p"\nsecond'
        self.inputs([(order_id, "USD", "0.01")], [(payment_id, order_id, "USD", "0.01")], bom=True)
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self.output.read_bytes()
        self.assertIn("订单".encode("utf-8"), data)
        self.assertEqual(data.count(b"\n"), 1)
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(json.loads(data)["orders"][0]["order_id"], order_id)
        self.assertEqual(data, report_bytes(self.report()))

    def test_lf_crlf_and_cr_record_separators(self):
        for newline in ("\n", "\r\n", "\r"):
            with self.subTest(newline=newline):
                self.orders.write_bytes(csv_bytes(ORDER_HEADER, [("001", "USD", "1")], newline=newline))
                self.payments.write_bytes(csv_bytes(PAYMENT_HEADER, [], newline=newline))
                self.assertEqual(self.report()["orders"][0]["status"], "unpaid")

    def test_invalid_utf8_and_missing_headers(self):
        for path, header in [(self.orders, ORDER_HEADER), (self.payments, PAYMENT_HEADER)]:
            for invalid in (b"", b"\xef\xbb\xbf", b"\n", csv_bytes(header, []) + b"\xff\n"):
                with self.subTest(path=path.name, invalid=invalid):
                    self.inputs([("001", "USD", "1")], [])
                    path.write_bytes(invalid)
                    self.assert_rejected()

    def test_header_only_inputs_and_unpaid_orders(self):
        self.inputs([], [], bom=True)
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_bytes(), b'{"orders":[],"schema":1,"totals":[]}\n')
        self.inputs([("001", "USD", "1")], [])
        self.assertEqual(self.report()["orders"][0]["status"], "unpaid")
        self.inputs([], [("p", "001", "USD", "0")])
        with self.assertRaises(LedgerError):
            self.report()

    def test_row_limit_includes_logical_duplicates(self):
        payment = ("p", "001", "USD", "1")
        self.inputs([("001", "USD", "1")], [payment] * 9999)
        self.assertEqual(self.report()["orders"][0]["received_cents"], 100)
        self.inputs([("001", "USD", "1")], [payment] * 10_000)
        self.assert_rejected()

    def test_row_limit_at_boundary_with_only_orders(self):
        self.inputs([(str(i), "USD", "0.01") for i in range(10_000)], [])
        self.assertEqual(len(self.report()["orders"]), 10_000)
        self.inputs([(str(i), "USD", "0.01") for i in range(10_001)], [])
        with self.assertRaises(LedgerError):
            self.report()

    def test_long_ids_are_valid_and_csv_setting_is_restored(self):
        order_id = "x" * 150_000
        old_limit = csv.field_size_limit()
        self.inputs([(order_id, "USD", "1")], [("p", order_id, "USD", "1")])
        self.assertEqual(self.report()["orders"][0]["order_id"], order_id)
        self.assertEqual(csv.field_size_limit(), old_limit)
        self.orders.write_bytes(b"bad\n")
        with self.assertRaises(LedgerError):
            self.report()
        self.assertEqual(csv.field_size_limit(), old_limit)

    def test_existing_file_directory_and_input_aliases_preserved(self):
        self.output.write_bytes(b"DO NOT REPLACE\x00\xff")
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertEqual(self.output.read_bytes(), b"DO NOT REPLACE\x00\xff")
        directory = self.directory / "existing directory"
        directory.mkdir()
        marker = directory / "marker"
        marker.write_bytes(b"keep")
        self.assertNotEqual(self.cli(output=directory).returncode, 0)
        self.assertEqual(marker.read_bytes(), b"keep")
        for path in (self.orders, self.payments):
            before = path.read_bytes()
            self.assertNotEqual(self.cli(output=path).returncode, 0)
            self.assertEqual(path.read_bytes(), before)
        alias = self.directory / "input hard link"
        os.link(self.orders, alias)
        before = alias.read_bytes()
        self.assertNotEqual(self.cli(output=alias).returncode, 0)
        self.assertEqual(alias.read_bytes(), before)
        self.assertEqual(self.orders.read_bytes(), before)

    def test_invalid_input_preserves_existing_output(self):
        self.output.write_bytes(b"original report")
        self.payments.write_bytes(b"invalid header\n")
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), b"original report")

    def test_missing_input_or_output_parent_is_controlled(self):
        self.orders.unlink()
        self.assert_rejected_missing_file()
        self.inputs([("001", "USD", "1")], [])
        result = self.cli(output=self.directory / "missing parent" / "report.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertFalse((self.directory / "missing parent").exists())

    def assert_rejected_missing_file(self):
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertFalse(self.output.exists())

    def test_atomic_publication_exposes_only_complete_bytes(self):
        report = self.report()
        expected = report_bytes(report)
        real_link = os.link

        def inspect_link(source, destination):
            self.assertFalse(self.output.exists())
            self.assertEqual(Path(source).read_bytes(), expected)
            real_link(source, destination)
            self.assertEqual(self.output.read_bytes(), expected)

        with mock.patch("ledgerreconcile.core.os.link", side_effect=inspect_link) as linked:
            write_report(report, self.output)
        linked.assert_called_once()
        self.assertEqual(list(self.directory.glob(".ledgerreconcile-*.tmp")), [])

    def test_destination_race_does_not_clobber_competing_file(self):
        real_link = os.link

        def compete(source, destination):
            Path(destination).write_bytes(b"concurrent owner")
            return real_link(source, destination)

        with mock.patch("ledgerreconcile.core.os.link", side_effect=compete):
            with self.assertRaises(LedgerError):
                write_report(self.report(), self.output)
        self.assertEqual(self.output.read_bytes(), b"concurrent owner")
        self.assertEqual(list(self.directory.glob(".ledgerreconcile-*.tmp")), [])

    def test_flush_and_link_failure_leave_no_output_or_temp(self):
        for target in ("ledgerreconcile.core.os.fsync", "ledgerreconcile.core.os.link"):
            with self.subTest(target=target):
                with mock.patch(target, side_effect=OSError("simulated disk failure")):
                    with self.assertRaises(OSError):
                        write_report(self.report(), self.output)
                self.assertFalse(self.output.exists())
                self.assertEqual(list(self.directory.glob(".ledgerreconcile-*.tmp")), [])

    def test_two_simultaneous_cli_writers_have_exactly_one_winner(self):
        command = [sys.executable, "-m", "ledgerreconcile", "--orders", str(self.orders),
                   "--payments", str(self.payments), "--output", str(self.output)]
        processes = [subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for _ in range(2)]
        try:
            results = [p.communicate(timeout=15) for p in processes]
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        self.assertEqual(sorted(p.returncode for p in processes), [0, 1])
        self.assertEqual(self.output.read_bytes(), report_bytes(self.report()))
        self.assertTrue(all(b"Traceback" not in stderr for _, stderr in results))
        self.assertEqual(list(self.directory.glob(".ledgerreconcile-*.tmp")), [])

    def test_help_and_usage_errors(self):
        help_result = subprocess.run([sys.executable, "-m", "ledgerreconcile", "--help"],
                                     cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(help_result.returncode, 0)
        for flag in (b"--orders", b"--payments", b"--output"):
            self.assertIn(flag, help_result.stdout)
        for args in ([], ["--unknown"], ["--orders"]):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, "-m", "ledgerreconcile", *args],
                                        cwd=ROOT, capture_output=True, timeout=15)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(b"Traceback", result.stderr)

    def test_readme_actual_smoke_command_and_source_preservation(self):
        import shlex

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('python -m unittest discover -s tests -p "test*.py"', readme)
        commands = [line for line in readme.splitlines()
                    if line.startswith("python -m ledgerreconcile --orders ")]
        self.assertEqual(len(commands), 1)
        command = shlex.split(commands[0])
        self.assertEqual(command[:3], ["python", "-m", "ledgerreconcile"])
        sources = list((ROOT / "ledgerreconcile").glob("*.py")) + list((ROOT / "examples").glob("*.csv"))
        hashes = {path: hashlib.sha256(path.read_bytes()).digest() for path in sources}
        command[0] = sys.executable
        command[command.index("--output") + 1] = str(self.output)
        result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(self.output.read_bytes())
        self.assertEqual([row["status"] for row in report["orders"]], ["paid", "paid"])
        self.assertEqual(self.output.read_bytes(), report_bytes(report))
        self.assertEqual(hashes, {path: hashlib.sha256(path.read_bytes()).digest() for path in sources})


if __name__ == "__main__":
    unittest.main()
