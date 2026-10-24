"""Finite offline acceptance tests; run with standard-library unittest discovery."""

import csv
import io
import json
from pathlib import Path
import random
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ledgerreconcile import LedgerError, reconcile, write_report


ROOT = Path(__file__).resolve().parents[1]
ORDER_HEADERS = ["order_id", "currency", "amount"]
PAYMENT_HEADERS = ["payment_id", "order_id", "currency", "amount"]
EMPTY = {"schema": 1, "orders": [], "totals": []}


def csv_bytes(headers, rows, *, bom=False):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig" if bom else "utf-8")


class LedgerTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".tmp"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="ledger tests ", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.orders = self.folder / "input orders.csv"
        self.payments = self.folder / "input payments.csv"
        self.output = self.folder / "new report.json"

    def inputs(self, orders=(), payments=(), *, bom=False):
        self.orders.write_bytes(csv_bytes(ORDER_HEADERS, orders, bom=bom))
        self.payments.write_bytes(csv_bytes(PAYMENT_HEADERS, payments, bom=bom))

    def report(self):
        return reconcile(self.orders, self.payments)

    def rendered(self):
        # Independent filename on each call so no output is ever replaced.
        output = self.folder / f"rendered-{len(list(self.folder.glob('rendered-*')))}.json"
        write_report(self.report(), output)
        return output.read_bytes()

    def cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "ledgerreconcile", *map(str, arguments)],
            cwd=ROOT, capture_output=True, timeout=10,
        )

    def run_inputs(self):
        return self.cli("--orders", self.orders, "--payments", self.payments, "--output", self.output)

    def assert_cli_error(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"error:", result.stderr.lower())
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertEqual(result.stdout, b"")

    def test_basic_cli_exact_schema_and_bytes(self):
        self.inputs([("001", "USD", "1")], [("p1", "001", "USD", "1.00")])
        result = self.run_inputs()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")
        self.assertEqual(self.output.read_bytes(), (
            b'{"orders":[{"balance_cents":0,"currency":"USD","expected_cents":100,'
            b'"order_id":"001","received_cents":100,"status":"paid"}],"schema":1,'
            b'"totals":[{"balance_cents":0,"currency":"USD","expected_cents":100,'
            b'"received_cents":100}]}\n'
        ))

    def test_decimal_addition_is_exact(self):
        self.inputs([("x", "USD", "0.30")], [
            ("a", "x", "USD", "0.1"), ("b", "x", "USD", "0.20")
        ])
        order = self.report()["orders"][0]
        self.assertEqual((order["expected_cents"], order["received_cents"], order["balance_cents"]), (30, 30, 0))
        self.assertEqual(order["status"], "paid")

    def test_signed_payments_and_all_five_statuses(self):
        self.inputs([(name, "USD", "1.00") for name in ("negative", "zero", "partial", "paid", "over")], [
            ("n1", "negative", "USD", "0.25"), ("n2", "negative", "USD", "-0.50"),
            ("z1", "zero", "USD", "1.00"), ("z2", "zero", "USD", "-1.00"),
            ("z3", "zero", "USD", "-0.00"), ("s", "partial", "USD", "0.01"),
            ("e", "paid", "USD", "1"), ("o", "over", "USD", "1.01"),
        ])
        actual = {row["order_id"]: (row["received_cents"], row["balance_cents"], row["status"]) for row in self.report()["orders"]}
        self.assertEqual(actual, {
            "negative": (-25, 125, "negative_net"), "zero": (0, 100, "unpaid"),
            "partial": (1, 99, "partial"), "paid": (100, 0, "paid"),
            "over": (101, -1, "overpaid"),
        })

    def test_currency_totals_include_unpaid_orders(self):
        self.inputs([("z", "USD", "2"), ("a", "EUR", "1"), ("b", "EUR", "3")], [
            ("a", "a", "EUR", "-0.25"), ("z", "z", "USD", "3")
        ])
        report = self.report()
        self.assertEqual(report["totals"], [
            {"currency": "EUR", "expected_cents": 400, "received_cents": -25, "balance_cents": 425},
            {"currency": "USD", "expected_cents": 200, "received_cents": 300, "balance_cents": -100},
        ])
        self.assertEqual(report["orders"][1]["status"], "unpaid")

    def test_original_string_ids_are_distinct_and_sorted(self):
        ids = ["1", "001", "a", "A", " 1", "é", "中", " "]
        self.inputs([(value, "USD", "1") for value in ids], [
            ("001", "001", "USD", "1"), ("1", "1", "USD", "0.50")
        ])
        orders = self.report()["orders"]
        self.assertEqual([row["order_id"] for row in orders], [" ", " 1", "001", "1", "A", "a", "é", "中"])
        actual = {row["order_id"]: row["received_cents"] for row in orders}
        self.assertEqual((actual["001"], actual["1"], actual[" 1"]), (100, 50, 0))

    def test_row_permutations_and_logical_duplicates_preserve_bytes(self):
        orders = [("b", "USD", "0.3"), ("001", "EUR", "2"), ("1", "USD", "1")]
        payments = [("p", "b", "USD", "0.1"), ("q", "b", "USD", "0.2"), ("r", "001", "EUR", "-0.25")]
        self.inputs(orders, payments)
        baseline = self.rendered()
        payments.extend([("p", "b", "USD", "0.10"), ("r", "001", "EUR", "-0.25")])
        generator = random.Random(20261024)
        for _ in range(4):
            generator.shuffle(orders)
            generator.shuffle(payments)
            self.inputs(orders, payments)
            self.assertEqual(self.rendered(), baseline)

    def test_equivalent_payment_amounts_and_signed_zero_are_idempotent(self):
        self.inputs([("x", "USD", "1")], [
            ("p", "x", "USD", "1"), ("p", "x", "USD", "1.0"), ("p", "x", "USD", "1.00"),
            ("z", "x", "USD", "0"), ("z", "x", "USD", "-0.00"),
        ])
        self.assertEqual(self.report()["orders"][0]["received_cents"], 100)

    def test_conflicting_duplicate_payment_rejected(self):
        for conflicting in [("p", "x", "USD", "1.01"), ("p", "y", "USD", "1"), ("p", "x", "USD", "-1")]:
            with self.subTest(conflicting=conflicting):
                self.inputs([("x", "USD", "1"), ("y", "USD", "1")], [("p", "x", "USD", "1"), conflicting])
                with self.assertRaisesRegex(LedgerError, "conflicting duplicate"):
                    self.report()

    def test_duplicate_order_even_identical_is_rejected(self):
        for second_amount in ("1.00", "2"):
            with self.subTest(second_amount=second_amount):
                self.inputs([("x", "USD", "1.00"), ("x", "USD", second_amount)])
                with self.assertRaisesRegex(LedgerError, "duplicate order_id"):
                    self.report()

    def test_unknown_order_rejected_including_empty_orders(self):
        for orders in ([], [("x", "USD", "1")]):
            with self.subTest(orders=orders):
                self.inputs(orders, [("p", "missing", "USD", "0")])
                with self.assertRaisesRegex(LedgerError, "unknown order_id"):
                    self.report()

    def test_currency_mismatch_rejected(self):
        self.inputs([("x", "USD", "1")], [("p", "x", "EUR", "1")])
        with self.assertRaisesRegex(LedgerError, "currency mismatch"):
            self.report()

    def test_invalid_money_grammar_rejected_in_both_inputs(self):
        invalid = ["", " 1", "1 ", "+1", "01", "00.10", ".1", "1.", "1.001", "-0.001", "1e2", "1E+2", "NaN", "Inf", "-Infinity", "1,000", "１", "1\n", "--1", "1_000"]
        for value in invalid:
            for payment in (False, True):
                with self.subTest(value=value, payment=payment):
                    self.inputs([("x", "USD", "1" if payment else value)], [("p", "x", "USD", value)] if payment else [])
                    with self.assertRaises(LedgerError):
                        self.report()

    def test_money_bounds_inclusive_and_no_integer_conversion_limit_leak(self):
        self.inputs([("x", "USD", "1000000.00")], [("p", "x", "USD", "-1000000.00")])
        order = self.report()["orders"][0]
        self.assertEqual((order["expected_cents"], order["received_cents"], order["balance_cents"]), (100000000, -100000000, 200000000))
        for value in ("1000000.01", "-1000000.01", "1000001", "9" * 5000):
            with self.subTest(value=value[:30]):
                self.inputs([("x", "USD", "1")], [("p", "x", "USD", value)])
                with self.assertRaises(LedgerError):
                    self.report()

    def test_nonpositive_orders_rejected(self):
        for value in ("0", "0.00", "-0", "-0.00", "-0.01", "-1000000"):
            with self.subTest(value=value):
                self.inputs([("x", "USD", value)])
                with self.assertRaisesRegex(LedgerError, "strictly positive"):
                    self.report()

    def test_currency_grammar_rejected_in_both_inputs(self):
        for value in ("", "usd", "Usd", "US", "USDD", " USD", "USD ", "US1", "ÜSD", "USD\n"):
            for payment in (False, True):
                with self.subTest(value=value, payment=payment):
                    self.inputs([("x", "USD" if payment else value, "1")], [("p", "x", value, "1")] if payment else [])
                    with self.assertRaisesRegex(LedgerError, "invalid currency"):
                        self.report()

    def test_empty_ids_rejected(self):
        cases = [([("", "USD", "1")], []), ([("x", "USD", "1")], [("", "x", "USD", "1")]), ([("x", "USD", "1")], [("p", "", "USD", "1")])]
        for orders, payments in cases:
            with self.subTest(orders=orders, payments=payments):
                self.inputs(orders, payments)
                with self.assertRaisesRegex(LedgerError, "empty .*id"):
                    self.report()

    def test_header_order_may_vary(self):
        self.orders.write_bytes(csv_bytes(["amount", "order_id", "currency"], [("1", "x", "USD")]))
        self.payments.write_bytes(csv_bytes(["currency", "amount", "payment_id", "order_id"], [("USD", "1", "p", "x")]))
        self.assertEqual(self.report()["orders"][0]["status"], "paid")

    def test_missing_extra_duplicate_and_inexact_headers_rejected(self):
        for payment in (False, True):
            headers = PAYMENT_HEADERS if payment else ORDER_HEADERS
            bad_headers = [headers[:-1], headers + ["extra"], headers[:-1] + [headers[0]], [" " + headers[0]] + headers[1:], [headers[0].upper()] + headers[1:]]
            for bad in bad_headers:
                with self.subTest(payment=payment, headers=bad):
                    self.inputs()
                    (self.payments if payment else self.orders).write_bytes(csv_bytes(bad, []))
                    with self.assertRaisesRegex(LedgerError, "headers"):
                        self.report()

    def test_malformed_quoting_and_record_width_rejected(self):
        invalid = [b'"x,USD,1\n', b'x"bad,USD,1\n', b'"x"tail,USD,1\n', b'x,USD\n', b'x,USD,1,extra\n', b'\n', b'"x",USD,"1"junk\n']
        for payment in (False, True):
            for row in invalid:
                with self.subTest(payment=payment, row=row):
                    self.inputs([("x", "USD", "1")])
                    path = self.payments if payment else self.orders
                    header = PAYMENT_HEADERS if payment else ORDER_HEADERS
                    path.write_bytes(csv_bytes(header, []) + (b'p,' if payment else b'') + row)
                    with self.assertRaises(LedgerError):
                        self.report()

    def test_bom_quotes_unicode_and_embedded_newlines_preserved(self):
        order_id = '  é, "雪"\r\nsecond\rtail\nend  '
        self.inputs([(order_id, "USD", "1.00")], [('p,"é"\nline', order_id, "USD", "1")], bom=True)
        report = self.report()
        self.assertEqual(report["orders"][0]["order_id"], order_id)
        data = self.rendered()
        self.assertEqual(data.count(b"\n"), 1)
        self.assertNotIn(b"\r", data)
        self.assertIn("雪".encode("utf-8"), data)
        self.assertEqual(json.loads(data), report)

    def test_record_endings_and_final_record_without_newline(self):
        for ending in (b"\n", b"\r\n", b"\r"):
            with self.subTest(ending=ending):
                self.orders.write_bytes(ending.join([b'order_id,currency,amount', b'"x",USD,1']))
                self.payments.write_bytes(ending.join([b'payment_id,order_id,currency,amount', b'p,"x",USD,1']))
                self.assertEqual(self.report()["orders"][0]["status"], "paid")

    def test_invalid_utf8_is_controlled_and_no_output(self):
        self.inputs()
        self.orders.write_bytes(b"order_id,currency,amount\nx,USD,\xff\n")
        result = self.run_inputs()
        self.assert_cli_error(result)
        self.assertFalse(self.output.exists())

    def test_header_only_inputs_are_valid(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                self.inputs(bom=bom)
                self.assertEqual(self.report(), EMPTY)
                self.assertEqual(self.rendered(), b'{"orders":[],"schema":1,"totals":[]}\n')

    def test_zero_byte_bom_only_and_blank_header_rejected(self):
        for payment in (False, True):
            for data in (b"", b"\xef\xbb\xbf", b"\n"):
                with self.subTest(payment=payment, data=data):
                    self.inputs()
                    (self.payments if payment else self.orders).write_bytes(data)
                    with self.assertRaises(LedgerError):
                        self.report()

    def test_exact_combined_row_limit_includes_duplicate_payments(self):
        self.inputs([("x", "USD", "1")], [("p", "x", "USD", "1")] * 9999)
        self.assertEqual(self.report()["orders"][0]["received_cents"], 100)
        with self.payments.open("ab") as stream:
            stream.write(b"p,x,USD,1\n")
        with self.assertRaisesRegex(LedgerError, "10000"):
            self.report()

    def test_large_valid_id_has_no_arbitrary_csv_field_limit(self):
        order_id = "x" * 150000
        self.inputs([(order_id, "USD", "0.01")])
        self.assertEqual(self.report()["orders"][0]["order_id"], order_id)

    def test_failure_after_valid_rows_leaves_no_output_and_preserves_inputs(self):
        self.inputs([("x", "USD", "1")], [("ok", "x", "USD", "1"), ("bad", "missing", "USD", "1")])
        before = [path.read_bytes() for path in (self.orders, self.payments)]
        self.assert_cli_error(self.run_inputs())
        self.assertFalse(self.output.exists())
        self.assertEqual([path.read_bytes() for path in (self.orders, self.payments)], before)
        self.assertEqual(list(self.folder.glob(".ledgerreconcile-*")), [])

    def test_success_preserves_both_input_bytes(self):
        self.inputs([("x", "USD", "1")], [("p", "x", "USD", "0.50")], bom=True)
        before = [path.read_bytes() for path in (self.orders, self.payments)]
        result = self.run_inputs()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([path.read_bytes() for path in (self.orders, self.payments)], before)

    def test_existing_output_file_is_preserved(self):
        self.inputs()
        self.output.write_bytes(b"existing bytes\x00\xff")
        self.assert_cli_error(self.run_inputs())
        self.assertEqual(self.output.read_bytes(), b"existing bytes\x00\xff")

    def test_existing_output_directory_is_preserved(self):
        self.inputs()
        self.output.mkdir()
        sentinel = self.output / "keep"
        sentinel.write_bytes(b"keep")
        self.assert_cli_error(self.run_inputs())
        self.assertTrue(self.output.is_dir())
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_input_cannot_be_used_as_output(self):
        self.inputs([("x", "USD", "1")])
        before = self.orders.read_bytes()
        self.assert_cli_error(self.cli("--orders", self.orders, "--payments", self.payments, "--output", self.orders))
        self.assertEqual(self.orders.read_bytes(), before)

    def test_sync_and_publication_failures_never_create_output(self):
        for operation in ("os.fsync", "os.link"):
            with self.subTest(operation=operation):
                with patch(f"ledgerreconcile.core.{operation}", side_effect=OSError("injected I/O failure")):
                    with self.assertRaises(OSError):
                        write_report(EMPTY, self.output)
                self.assertFalse(self.output.exists())
                self.assertEqual(list(self.folder.glob(".ledgerreconcile-*")), [])

    def test_publication_exposes_only_complete_bytes(self):
        import os
        real_link = os.link

        def inspect_then_link(source, destination):
            self.assertFalse(Path(destination).exists())
            self.assertEqual(Path(source).read_bytes(), b'{"orders":[],"schema":1,"totals":[]}\n')
            real_link(source, destination)

        with patch("ledgerreconcile.core.os.link", side_effect=inspect_then_link):
            write_report(EMPTY, self.output)
        self.assertEqual(self.output.read_bytes(), b'{"orders":[],"schema":1,"totals":[]}\n')
        self.assertEqual(list(self.folder.glob(".ledgerreconcile-*")), [])

    def test_destination_created_during_publication_is_preserved(self):
        import os
        real_link = os.link

        def race(source, destination):
            Path(destination).write_bytes(b"racing writer")
            real_link(source, destination)

        with patch("ledgerreconcile.core.os.link", side_effect=race):
            with self.assertRaises(FileExistsError):
                write_report(EMPTY, self.output)
        self.assertEqual(self.output.read_bytes(), b"racing writer")
        self.assertEqual(list(self.folder.glob(".ledgerreconcile-*")), [])

    def test_help_argument_errors_and_paths_with_spaces(self):
        result = self.cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for flag in (b"--orders", b"--payments", b"--output"):
            self.assertIn(flag, result.stdout)
        self.assert_cli_error(self.cli())
        self.assert_cli_error(self.cli("--unknown"))
        self.inputs()
        result = self.run_inputs()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.output.read_bytes()), EMPTY)

    def test_missing_input_and_missing_output_parent_are_controlled(self):
        self.inputs()
        self.orders.unlink()
        self.assert_cli_error(self.run_inputs())
        self.assertFalse(self.output.exists())
        self.inputs()
        self.output = self.folder / "missing parent" / "report.json"
        self.assert_cli_error(self.run_inputs())
        self.assertFalse(self.output.exists())

    def test_actual_readme_smoke_command(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('python -m unittest discover -s tests -p "test*.py"', readme)
        commands = re.findall(r"```sh\n([^\n]+)\n```", readme)
        smoke = next(command for command in commands if "--orders" in command)
        argv = shlex.split(smoke)
        self.assertEqual(argv[:3], ["python", "-m", "ledgerreconcile"])
        self.assertEqual(len(argv), 9)
        argv[0] = sys.executable
        argv[argv.index("--output") + 1] = str(self.output)
        input_paths = [ROOT / argv[argv.index(flag) + 1] for flag in ("--orders", "--payments")]
        before = [path.read_bytes() for path in input_paths]
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(self.output.read_bytes())
        self.assertEqual([(row["order_id"], row["status"]) for row in report["orders"]], [("001", "paid"), ("002", "negative_net")])
        self.assertEqual([path.read_bytes() for path in input_paths], before)


if __name__ == "__main__":
    unittest.main()
