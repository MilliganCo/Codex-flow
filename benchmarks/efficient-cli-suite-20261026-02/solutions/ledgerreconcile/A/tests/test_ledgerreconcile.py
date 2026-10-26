"""Finite standard-library tests for the CLI, validation, and safe publication."""

import csv
import itertools
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ledgerreconcile import ReconcileError, reconcile, write_report


ROOT = Path(__file__).resolve().parents[1]
ORDER_HEADER = ["order_id", "currency", "amount"]
PAYMENT_HEADER = ["payment_id", "order_id", "currency", "amount"]


class LedgerTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".tmp"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="ledger-tests-", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.orders = self.directory / "orders input.csv"
        self.payments = self.directory / "payments input.csv"
        self.output = self.directory / "new report.json"
        self.inputs([], [])

    def inputs(self, orders, payments, *, bom=False, order_header=None, payment_header=None):
        for path, header, rows in (
            (self.orders, ORDER_HEADER if order_header is None else order_header, orders),
            (self.payments, PAYMENT_HEADER if payment_header is None else payment_header, payments),
        ):
            with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(header)
                writer.writerows(rows)

    def report(self):
        return reconcile(self.orders, self.payments)

    def cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "ledgerreconcile", *map(str, arguments)],
            cwd=ROOT, capture_output=True, encoding="utf-8", timeout=15,
        )

    def run_cli(self, output=None):
        return self.cli(
            "--orders", self.orders, "--payments", self.payments,
            "--output", self.output if output is None else output,
        )

    def assert_rejected(self):
        with self.assertRaises(ReconcileError):
            self.report()

    def test_cli_exact_schema_bytes_and_space_paths(self):
        self.inputs([["001", "USD", "1.00"]], [["p", "001", "USD", "1"]])
        before = (self.orders.read_bytes(), self.payments.read_bytes())
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        expected = {
            "schema": 1,
            "orders": [{"order_id": "001", "currency": "USD", "expected_cents": 100,
                        "received_cents": 100, "balance_cents": 0, "status": "paid"}],
            "totals": [{"currency": "USD", "expected_cents": 100,
                        "received_cents": 100, "balance_cents": 0}],
        }
        self.assertEqual(json.loads(self.output.read_bytes()), expected)
        self.assertEqual(self.output.read_bytes(), (
            json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8"))
        self.assertEqual((self.orders.read_bytes(), self.payments.read_bytes()), before)

    def test_exact_cents_and_amount_boundaries(self):
        self.inputs(
            [["tiny", "USD", "0.30"], ["max", "USD", "1000000.00"]],
            [["a", "tiny", "USD", "0.1"], ["b", "tiny", "USD", "0.20"],
             ["c", "max", "USD", "1000000"], ["d", "max", "USD", "-1000000.00"]],
        )
        orders = {row["order_id"]: row for row in self.report()["orders"]}
        self.assertEqual(orders["tiny"]["received_cents"], 30)
        self.assertEqual(orders["tiny"]["balance_cents"], 0)
        self.assertEqual(orders["max"]["expected_cents"], 100_000_000)
        self.assertEqual(orders["max"]["received_cents"], 0)

    def test_all_statuses_and_refund_net(self):
        identifiers = ["negative", "unpaid", "partial", "paid", "overpaid", "no payments"]
        self.inputs(
            [[identifier, "USD", "1"] for identifier in identifiers],
            [["neg", "negative", "USD", "-0.01"], ["zero", "unpaid", "USD", "-0.00"],
             ["half", "partial", "USD", "0.50"], ["full", "paid", "USD", "2"],
             ["refund", "paid", "USD", "-1"], ["extra", "overpaid", "USD", "1.01"]],
        )
        orders = {row["order_id"]: row for row in self.report()["orders"]}
        for identifier, status, received in (
            ("negative", "negative_net", -1), ("unpaid", "unpaid", 0),
            ("partial", "partial", 50), ("paid", "paid", 100),
            ("overpaid", "overpaid", 101), ("no payments", "unpaid", 0),
        ):
            with self.subTest(status=identifier):
                self.assertEqual(orders[identifier]["status"], status)
                self.assertEqual(orders[identifier]["received_cents"], received)
                self.assertEqual(orders[identifier]["balance_cents"], 100 - received)

    def test_currency_totals_are_sorted_arrays(self):
        self.inputs(
            [["z", "USD", "2"], ["a", "EUR", "1"], ["b", "USD", "0.50"]],
            [["p1", "z", "USD", "3"], ["p2", "a", "EUR", "-0.50"]],
        )
        self.assertEqual(self.report()["totals"], [
            {"currency": "EUR", "expected_cents": 100, "received_cents": -50, "balance_cents": 150},
            {"currency": "USD", "expected_cents": 250, "received_cents": 300, "balance_cents": -50},
        ])

    def test_string_ids_preserve_whitespace_case_and_leading_zeroes(self):
        identifiers = ["1", "001", "A", "a", " 1", "1 ", " ", "é"]
        self.inputs([[identifier, "USD", "1"] for identifier in identifiers], [])
        self.assertEqual([row["order_id"] for row in self.report()["orders"]], sorted(identifiers))

    def test_input_permutations_and_logical_duplicates_have_identical_bytes(self):
        orders = [["z", "USD", "1"], ["001", "EUR", "2"]]
        payments = [["p1", "z", "USD", "1.0"], ["p2", "001", "EUR", "-0.10"]]
        canonical = None
        index = 0
        for order_rows in itertools.permutations(orders):
            for payment_rows in itertools.permutations(payments + [["p1", "z", "USD", "1.00"]]):
                self.inputs(order_rows, payment_rows)
                destination = self.directory / f"permutation-{index}.json"
                write_report(self.report(), destination)
                raw = destination.read_bytes()
                if canonical is None:
                    canonical = raw
                self.assertEqual(raw, canonical)
                index += 1
        self.inputs(orders, payments)
        destination = self.directory / "without-duplicate.json"
        write_report(self.report(), destination)
        self.assertEqual(destination.read_bytes(), canonical)

    def test_payment_idempotence_including_negative_zero(self):
        self.inputs([["o", "USD", "2"]], [
            ["p", "o", "USD", "1"], ["p", "o", "USD", "1.0"], ["p", "o", "USD", "1.00"],
            ["z", "o", "USD", "-0"], ["z", "o", "USD", "0.00"],
            ["refund", "o", "USD", "-0.1"], ["refund", "o", "USD", "-0.10"],
        ])
        self.assertEqual(self.report()["orders"][0]["received_cents"], 90)

    def test_conflicting_payment_amount_order_or_currency_rejected(self):
        for conflicting in (
            ["p", "one", "USD", "1.01"], ["p", "two", "USD", "1"],
            ["p", "three", "EUR", "1"],
        ):
            with self.subTest(payload=conflicting):
                self.inputs(
                    [["one", "USD", "2"], ["two", "USD", "2"], ["three", "EUR", "2"]],
                    [["p", "one", "USD", "1"], conflicting],
                )
                self.assert_rejected()

    def test_duplicate_order_even_identical_rejected(self):
        for amount in ("1", "1.00", "2"):
            with self.subTest(amount=amount):
                self.inputs([["o", "USD", "1"], ["o", "USD", amount]], [])
                self.assert_rejected()

    def test_unknown_order_rejected_even_with_empty_orders(self):
        for orders in ([], [["known", "USD", "1"]]):
            with self.subTest(orders=orders):
                self.inputs(orders, [["p", "unknown", "USD", "1"]])
                self.assert_rejected()

    def test_payment_currency_mismatch_rejected(self):
        self.inputs([["o", "USD", "1"]], [["p", "o", "EUR", "1"]])
        self.assert_rejected()

    def test_invalid_money_grammar_and_bounds_in_both_files(self):
        invalid = ["", "+1", "01", "00.10", "-01", ".1", "1.", "1.001", "-0.001",
                   "1e2", "NaN", "Inf", "-Infinity", "1,000.00", " 1", "1 ", "1\n",
                   "١", "1.２", "--1", "1000000.01", "-1000000.01", "1000001", "9" * 5000]
        for value in invalid:
            for payment in (False, True):
                with self.subTest(value=value[:24], payment=payment):
                    self.inputs(
                        [["o", "USD", "1" if payment else value]],
                        [["p", "o", "USD", value]] if payment else [],
                    )
                    self.assert_rejected()

    def test_orders_must_be_strictly_positive(self):
        for value in ("0", "0.0", "-0", "-0.00", "-0.01", "-1000000.00"):
            with self.subTest(value=value):
                self.inputs([["o", "USD", value]], [])
                self.assert_rejected()

    def test_invalid_currencies_in_both_files(self):
        for value in ("", "usd", "US", "USDD", "Usd", " USD", "USD ", "ÜSD", "US1", "ＵＳＤ"):
            for payment in (False, True):
                with self.subTest(currency=value, payment=payment):
                    self.inputs(
                        [["o", "USD" if payment else value, "1"]],
                        [["p", "o", value, "1"]] if payment else [],
                    )
                    self.assert_rejected()

    def test_empty_ids_rejected(self):
        cases = [([["", "USD", "1"]], []),
                 ([["o", "USD", "1"]], [["", "o", "USD", "1"]]),
                 ([["o", "USD", "1"]], [["p", "", "USD", "1"]])]
        for orders, payments in cases:
            with self.subTest(orders=orders, payments=payments):
                self.inputs(orders, payments)
                self.assert_rejected()

    def test_reordered_headers(self):
        self.inputs([["1.00", "USD", "001"]], [["USD", "1", "p", "001"]],
                    order_header=["amount", "currency", "order_id"],
                    payment_header=["currency", "amount", "payment_id", "order_id"])
        self.assertEqual(self.report()["orders"][0]["status"], "paid")

    def test_missing_extra_duplicate_and_inexact_headers_rejected(self):
        for payment in (False, True):
            header = PAYMENT_HEADER if payment else ORDER_HEADER
            variants = [header[:-1], header + ["extra"], header[:-1] + [header[0]],
                        [" " + header[0]] + header[1:], [header[0].upper()] + header[1:], []]
            for bad_header in variants:
                with self.subTest(payment=payment, header=bad_header):
                    self.inputs([], [], **{"payment_header" if payment else "order_header": bad_header})
                    self.assert_rejected()

    def test_malformed_csv_and_wrong_width_in_both_files(self):
        cases = [
            '"unterminated,USD,1', 'bad"quote,USD,1\n', '"closed"junk,USD,1\n',
            '\n', 'one,USD\n', 'one,USD,1,extra\n',
        ]
        for payment in (False, True):
            for bad in cases:
                with self.subTest(payment=payment, bad=bad):
                    self.inputs([["o", "USD", "1"]], [])
                    path = self.payments if payment else self.orders
                    header = PAYMENT_HEADER if payment else ORDER_HEADER
                    # Prefix a payment ID so the three-field malformed cases have
                    # the correct expected width whenever the syntax is valid.
                    content = ("p," if payment and bad != "\n" else "") + bad
                    path.write_bytes((",".join(header) + "\n" + content).encode("utf-8"))
                    self.assert_rejected()

    def test_bom_unicode_commas_quotes_and_embedded_newlines(self):
        order_id = '001, "café"\n雪\r\nend'
        payment_id = 'payment, "réglé"\n行'
        self.inputs([[order_id, "USD", "1"]], [[payment_id, order_id, "USD", "1.00"]], bom=True)
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        raw = self.output.read_bytes()
        self.assertEqual(json.loads(raw)["orders"][0]["order_id"], order_id)
        self.assertEqual(raw.count(b"\n"), 1)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn("雪".encode("utf-8"), raw)
        self.assertNotIn(b"\r", raw)

    def test_lf_crlf_cr_and_missing_final_input_newline(self):
        for newline in ("\n", "\r\n", "\r"):
            with self.subTest(newline=repr(newline)):
                self.orders.write_bytes(("order_id,currency,amount" + newline + "o,USD,1").encode())
                self.payments.write_bytes(("payment_id,order_id,currency,amount" + newline + "p,o,USD,1").encode())
                self.assertEqual(self.report()["orders"][0]["status"], "paid")

    def test_ids_larger_than_default_csv_field_limit(self):
        identifier = "x" * 150_000
        self.inputs([[identifier, "USD", "1"]], [["p", identifier, "USD", "1"]])
        previous_limit = csv.field_size_limit()
        self.assertEqual(self.report()["orders"][0]["order_id"], identifier)
        self.assertEqual(csv.field_size_limit(), previous_limit)

    def test_invalid_utf8_and_zero_byte_files_rejected(self):
        for payment in (False, True):
            for content in (b"", b"\xef\xbb\xbf", b"\xff"):
                with self.subTest(payment=payment, content=content):
                    self.inputs([], [])
                    (self.payments if payment else self.orders).write_bytes(content)
                    self.assert_rejected()

    def test_header_only_inputs_and_no_payments(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                self.inputs([], [], bom=bom)
                self.assertEqual(self.report(), {"schema": 1, "orders": [], "totals": []})
        self.inputs([["o", "USD", "0.01"]], [])
        self.assertEqual(self.report()["orders"][0]["status"], "unpaid")

    def test_combined_row_limit_including_idempotent_rows(self):
        self.inputs([["o", "USD", "1"]], [["p", "o", "USD", "1"]] * 9999)
        self.assertEqual(self.report()["orders"][0]["received_cents"], 100)
        with self.payments.open("a", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerow(["p", "o", "USD", "1.00"])
        self.assert_rejected()
        self.inputs([[str(index), "USD", "1"] for index in range(10000)], [])
        self.assertEqual(len(self.report()["orders"]), 10000)
        with self.orders.open("a", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerow(["last", "USD", "1"])
        self.assert_rejected()

    def test_late_validation_error_never_publishes_or_changes_inputs(self):
        self.inputs([["o", "USD", "1"]], [["p", "o", "USD", "1"], ["bad", "missing", "USD", "1"]])
        before = (self.orders.read_bytes(), self.payments.read_bytes())
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown order", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual((self.orders.read_bytes(), self.payments.read_bytes()), before)
        self.assertEqual(list(self.directory.glob(".ledgerreconcile-*")), [])

    def test_existing_file_directory_and_input_output_preserved(self):
        self.inputs([["o", "USD", "1"]], [])
        self.output.write_bytes(b"existing\x00bytes\r\n")
        directory = self.directory / "existing directory"
        directory.mkdir()
        sentinel = directory / "keep.txt"
        sentinel.write_bytes(b"keep")
        for output in (self.output, directory, self.orders, self.payments):
            before = output.read_bytes() if output.is_file() else None
            with self.subTest(output=output.name):
                result = self.run_cli(output)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                if before is not None:
                    self.assertEqual(output.read_bytes(), before)
                else:
                    self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_destination_created_during_publication_is_preserved(self):
        self.inputs([["o", "USD", "1"]], [])

        def concurrent_creation(source, destination):
            self.assertEqual(json.loads(Path(source).read_bytes())["schema"], 1)
            Path(destination).write_bytes(b"concurrent owner")
            raise FileExistsError("another writer created the output")

        with patch("ledgerreconcile.core.os.link", side_effect=concurrent_creation):
            with self.assertRaises(FileExistsError):
                write_report(self.report(), self.output)
        self.assertEqual(self.output.read_bytes(), b"concurrent owner")
        self.assertEqual(list(self.directory.glob(".ledgerreconcile-*")), [])

    def test_flush_failure_never_publishes_partial_report(self):
        with patch("ledgerreconcile.core.os.fsync", side_effect=OSError("simulated flush failure")):
            with self.assertRaises(OSError):
                write_report(self.report(), self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.directory.glob(".ledgerreconcile-*")), [])

    def test_publication_failure_never_publishes_partial_report(self):
        with patch("ledgerreconcile.core.os.link", side_effect=OSError("hard links unavailable")):
            with self.assertRaises(OSError):
                write_report(self.report(), self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.directory.glob(".ledgerreconcile-*")), [])

    def test_help_and_controlled_argument_and_filesystem_errors(self):
        result = self.cli("--help")
        self.assertEqual(result.returncode, 0)
        for flag in ("--orders", "--payments", "--output"):
            self.assertIn(flag, result.stdout)
        for arguments in ([], ["--unknown"], ["--orders", "missing.csv", "--payments", self.payments,
                                             "--output", self.output]):
            with self.subTest(arguments=arguments):
                result = self.cli(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
        self.inputs([["o", "USD", "1"]], [])
        result = self.run_cli(self.directory / "missing directory" / "report.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.output.exists())

    def test_readme_contains_actual_test_command_and_runnable_smoke(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('python -m unittest discover -s tests -p "test*.py"', readme)
        smoke = re.search(r"^python -m ledgerreconcile --orders .+ --payments .+ --output .+$", readme, re.MULTILINE)
        self.assertIsNotNone(smoke)
        arguments = shlex.split(smoke.group())
        self.assertEqual(arguments[:3], ["python", "-m", "ledgerreconcile"])
        arguments[arguments.index("--output") + 1] = str(self.output)
        result = subprocess.run([sys.executable, *arguments[1:]], cwd=ROOT,
                                capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(self.output.read_bytes())
        self.assertEqual([row["status"] for row in report["orders"]], ["paid", "unpaid"])


if __name__ == "__main__":
    unittest.main()
