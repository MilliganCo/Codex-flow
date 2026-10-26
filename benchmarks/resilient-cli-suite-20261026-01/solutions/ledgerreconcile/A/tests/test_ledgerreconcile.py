"""Finite, offline tests, including real module invocations and I/O failures."""

import csv
import itertools
import json
import os
from pathlib import Path
import random
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ledgerreconcile.core import (
    ORDER_HEADERS,
    PAYMENT_HEADERS,
    ReconciliationError,
    parse_cents,
    reconcile,
    write_report,
)


ROOT = Path(__file__).resolve().parents[1]


def canonical(report):
    return (json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class LedgerTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".tmp"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="ledger-tests-", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.orders = self.work / "orders.csv"
        self.payments = self.work / "payments.csv"
        self.output = self.work / "report.json"

    def table(self, path, headers, rows, encoding="utf-8"):
        with path.open("w", encoding=encoding, newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(rows)

    def inputs(self, orders=(), payments=()):
        self.table(self.orders, ORDER_HEADERS, orders)
        self.table(self.payments, PAYMENT_HEADERS, payments)

    def cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "ledgerreconcile", *map(str, arguments)],
            cwd=ROOT,
            capture_output=True,
            timeout=20,
        )

    def run_report(self, output=None):
        return self.cli(
            "--orders", self.orders, "--payments", self.payments,
            "--output", output if output is not None else self.output,
        )

    def assert_rejected(self):
        originals = (self.orders.read_bytes(), self.payments.read_bytes())
        before = set(self.work.iterdir())
        result = self.run_report()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(b"error:", result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(set(self.work.iterdir()), before)
        self.assertEqual((self.orders.read_bytes(), self.payments.read_bytes()), originals)
        return result

    def test_cli_exact_schema_and_canonical_bytes(self):
        self.inputs([("001", "USD", "1.00")], [("p1", "001", "USD", "1")])
        expected = {
            "schema": 1,
            "orders": [{"order_id": "001", "currency": "USD", "expected_cents": 100,
                        "received_cents": 100, "balance_cents": 0, "status": "paid"}],
            "totals": [{"currency": "USD", "expected_cents": 100,
                        "received_cents": 100, "balance_cents": 0}],
        }
        originals = self.orders.read_bytes(), self.payments.read_bytes()
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")
        self.assertEqual(self.output.read_bytes(), canonical(expected))
        self.assertEqual((self.orders.read_bytes(), self.payments.read_bytes()), originals)
        self.assertEqual(set(self.work.iterdir()), {self.orders, self.payments, self.output})

    def test_money_exact_integer_cents_and_boundaries(self):
        valid = {"0": 0, "-0": 0, "-0.00": 0, "0.01": 1, "0.29": 29,
                 "1": 100, "1.0": 100, "1.00": 100, "-1.2": -120,
                 "999999.99": 99999999, "1000000": 100000000,
                 "1000000.00": 100000000, "-1000000.00": -100000000}
        for text, expected in valid.items():
            with self.subTest(text=text):
                cents = parse_cents(text)
                self.assertIs(type(cents), int)
                self.assertEqual(cents, expected)
        self.inputs([("a", "USD", "0.30")],
                    [("p1", "a", "USD", "0.10"), ("p2", "a", "USD", "0.20")])
        row = reconcile(self.orders, self.payments)["orders"][0]
        self.assertEqual((row["received_cents"], row["balance_cents"], row["status"]), (30, 0, "paid"))

    def test_invalid_money_grammar_and_bounds(self):
        invalid = ["", " ", "+1", "01", "00", "-01", ".1", "1.", "1.001",
                   "1e2", "NaN", "Inf", "-Infinity", "1,000", " 1", "1 ", "1\n",
                   "--1", "1_000", "١", "１", "1.２", "1000000.01", "-1000000.01",
                   "1000001", "9" * 5000]
        for value in invalid:
            with self.subTest(value=value[:40]):
                with self.assertRaises(ReconciliationError):
                    parse_cents(value)

    def test_orders_must_be_strictly_positive(self):
        for value in ["0", "0.00", "-0", "-0.00", "-0.01", "-1000000"]:
            with self.subTest(value=value):
                self.inputs([("a", "USD", value)])
                self.assert_rejected()

    def test_invalid_payment_amount_fails_whole_operation(self):
        for value in ["1.001", "1000000.01", "NaN", "+1"]:
            with self.subTest(value=value):
                self.inputs([("a", "USD", "1")], [("p", "a", "USD", value)])
                self.assert_rejected()

    def test_signed_payments_and_every_status(self):
        ids = ["negative", "unpaid", "partial", "paid", "overpaid", "netzero"]
        self.inputs([(key, "USD", "1") for key in ids], [
            ("refund", "negative", "USD", "-0.01"),
            ("zero", "unpaid", "USD", "-0.00"),
            ("part", "partial", "USD", "0.99"),
            ("full", "paid", "USD", "1"),
            ("extra", "overpaid", "USD", "1.01"),
            ("charge", "netzero", "USD", "1"),
            ("reversal", "netzero", "USD", "-1"),
        ])
        report = reconcile(self.orders, self.payments)
        actual = {row["order_id"]: (row["received_cents"], row["status"], row["balance_cents"])
                  for row in report["orders"]}
        self.assertEqual(actual, {
            "negative": (-1, "negative_net", 101), "unpaid": (0, "unpaid", 100),
            "partial": (99, "partial", 1), "paid": (100, "paid", 0),
            "overpaid": (101, "overpaid", -1), "netzero": (0, "unpaid", 100),
        })
        self.assertEqual(report["totals"], [{"currency": "USD", "expected_cents": 600,
                                           "received_cents": 299, "balance_cents": 301}])

    def test_totals_are_sorted_currency_arrays_including_unpaid_orders(self):
        self.inputs([("z", "USD", "1"), ("a", "EUR", "2"), ("b", "USD", "3"),
                     ("c", "JPY", "4")],
                    [("p", "z", "USD", "-1"), ("q", "a", "EUR", "5")])
        report = reconcile(self.orders, self.payments)
        self.assertEqual(report["totals"], [
            {"currency": "EUR", "expected_cents": 200, "received_cents": 500, "balance_cents": -300},
            {"currency": "JPY", "expected_cents": 400, "received_cents": 0, "balance_cents": 400},
            {"currency": "USD", "expected_cents": 400, "received_cents": -100, "balance_cents": 500},
        ])
        self.assertEqual([row["order_id"] for row in report["orders"]], ["a", "b", "c", "z"])
        self.assertEqual(report["orders"][1]["status"], "unpaid")

    def test_ids_preserve_zeros_case_and_whitespace(self):
        ids = ["1", "001", "a", "A", " a ", " "]
        self.inputs([(key, "USD", "1") for key in ids],
                    [("001", "001", "USD", "0.10"), ("1", "1", "USD", "0.20"),
                     ("p", "a", "USD", "0.30"), (" p ", "a", "USD", "0.40")])
        report = reconcile(self.orders, self.payments)
        self.assertEqual([row["order_id"] for row in report["orders"]], sorted(ids))
        actual = {row["order_id"]: row["received_cents"] for row in report["orders"]}
        self.assertEqual(actual, {"001": 10, "1": 20, "a": 70, "A": 0, " a ": 0, " ": 0})

    def test_aggregates_can_exceed_the_per_row_money_limit(self):
        self.inputs([("a", "USD", "1000000.00"), ("b", "USD", "1000000")],
                    [("p1", "a", "USD", "1000000"), ("p2", "a", "USD", "1000000.00"),
                     ("p3", "b", "USD", "-1000000.00")])
        report = reconcile(self.orders, self.payments)
        self.assertEqual(report["orders"][0]["received_cents"], 200_000_000)
        self.assertEqual(report["orders"][0]["status"], "overpaid")
        self.assertEqual(report["orders"][1]["status"], "negative_net")
        self.assertEqual(report["totals"], [{"currency": "USD", "expected_cents": 200_000_000,
                                           "received_cents": 100_000_000, "balance_cents": 100_000_000}])

    def test_row_permutations_and_logical_duplicates_preserve_bytes(self):
        orders = [("z", "USD", "10"), ("001", "EUR", "1"), ("1", "USD", "0.29")]
        payments = [("a", "z", "USD", "1"), ("b", "z", "USD", "-0.1"),
                    ("c", "001", "EUR", "1.00"), ("zero", "1", "USD", "0")]
        generator = random.Random(42)
        baseline = None
        for index in range(8):
            variant = payments + ([] if index == 0 else [
                ("a", "z", "USD", "1.00"), ("b", "z", "USD", "-0.10"),
                ("zero", "1", "USD", "-0.00"),
            ])
            generator.shuffle(orders)
            generator.shuffle(variant)
            self.inputs(orders, variant)
            target = self.work / f"permutation-{index}.json"
            result = self.run_report(target)
            self.assertEqual(result.returncode, 0, result.stderr)
            if baseline is None:
                baseline = target.read_bytes()
            self.assertEqual(target.read_bytes(), baseline)

    def test_conflicting_duplicate_payment_payloads(self):
        for conflict in [("p", "a", "USD", "1.01"), ("p", "b", "USD", "1"),
                         ("p", "c", "EUR", "1")]:
            with self.subTest(conflict=conflict):
                self.inputs([("a", "USD", "1"), ("b", "USD", "1"), ("c", "EUR", "1")],
                            [("p", "a", "USD", "1"), conflict])
                result = self.assert_rejected()
                self.assertIn(b"conflicting payment ID", result.stderr)

    def test_duplicate_order_rows_are_always_rejected(self):
        for second in [("a", "USD", "1"), ("a", "USD", "1.0"), ("a", "EUR", "2")]:
            with self.subTest(second=second):
                self.inputs([("a", "USD", "1"), second])
                self.assertIn(b"duplicate order ID", self.assert_rejected().stderr)

    def test_unknown_order_is_rejected(self):
        self.inputs([("001", "USD", "1")], [("p", "1", "USD", "1")])
        self.assertIn(b"unknown order ID", self.assert_rejected().stderr)

    def test_currency_mismatch_is_rejected(self):
        self.inputs([("a", "USD", "1")], [("p", "a", "EUR", "1")])
        self.assertIn(b"currency mismatch", self.assert_rejected().stderr)

    def test_currency_validation_for_both_inputs(self):
        for currency in ["usd", "US", "USDD", "Usd", " USD", "USD ", "ÜSD", "ＵＳＤ", "USD\n"]:
            for source in ["orders", "payments"]:
                with self.subTest(currency=currency, source=source):
                    self.inputs([("a", currency if source == "orders" else "USD", "1")],
                                [("p", "a", currency if source == "payments" else "USD", "1")])
                    with self.assertRaises(ReconciliationError):
                        reconcile(self.orders, self.payments)

    def test_empty_ids_in_each_position_are_rejected(self):
        for orders, payments in [([("", "USD", "1")], []),
                                 ([("a", "USD", "1")], [("", "a", "USD", "1")]),
                                 ([("a", "USD", "1")], [("p", "", "USD", "1")])]:
            with self.subTest(orders=orders, payments=payments):
                self.inputs(orders, payments)
                self.assert_rejected()

    def test_header_order_can_vary(self):
        for headers in itertools.permutations(ORDER_HEADERS):
            self.table(self.orders, headers, [[{"order_id": "a", "currency": "USD", "amount": "1"}[h]
                                              for h in headers]])
            self.table(self.payments, ("amount", "currency", "order_id", "payment_id"),
                       [("1", "USD", "a", "p")])
            self.assertEqual(reconcile(self.orders, self.payments)["orders"][0]["status"], "paid")

    def test_missing_extra_duplicate_and_inexact_headers(self):
        for source, headers in [(self.orders, ORDER_HEADERS), (self.payments, PAYMENT_HEADERS)]:
            invalid = [headers[:-1], headers + ("extra",), headers[:-1] + (headers[0],),
                       (" " + headers[0],) + headers[1:], (headers[0].upper(),) + headers[1:]]
            for bad in invalid:
                with self.subTest(source=source.name, headers=bad):
                    self.inputs()
                    self.table(source, bad, [])
                    self.assert_rejected()

    def test_malformed_csv_and_wrong_field_counts(self):
        cases = ['"unfinished,USD,1\n', 'a"b,USD,1\n', '"a"x,USD,1\n',
                 '"a" ,USD,1\n', 'a,USD\n', 'a,USD,1,extra\n', '\n']
        for body in cases:
            with self.subTest(body=body):
                self.inputs()
                self.orders.write_bytes(("order_id,currency,amount\n" + body).encode())
                self.assert_rejected()
        self.inputs([("a", "USD", "1")])
        self.payments.write_bytes(b'payment_id,order_id,currency,amount\np,a,USD,"1"oops\n')
        self.assert_rejected()

    def test_bom_unicode_quotes_commas_and_embedded_newlines(self):
        order_id = '001, "snow"\r\n雪\nΩ'
        payment_id = '付款, "yes"\r\nline'
        self.table(self.orders, ORDER_HEADERS, [(order_id, "USD", "1.00")], encoding="utf-8-sig")
        self.table(self.payments, PAYMENT_HEADERS, [(payment_id, order_id, "USD", "1.0")],
                   encoding="utf-8-sig")
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        raw = self.output.read_bytes()
        self.assertEqual(raw.count(b"\n"), 1)
        self.assertNotIn(b"\r", raw)
        self.assertIn("雪".encode(), raw)
        report = json.loads(raw)
        self.assertEqual(report["orders"][0]["order_id"], order_id)
        self.assertEqual(raw, canonical(report))

    def test_lf_crlf_cr_and_missing_final_newline(self):
        for separator in [b"\n", b"\r\n", b"\r"]:
            for final in [b"", separator]:
                with self.subTest(separator=separator, final=final):
                    self.inputs()
                    self.orders.write_bytes(b"order_id,currency,amount" + separator + b"a,USD,1" + final)
                    self.assertEqual(reconcile(self.orders, self.payments)["orders"][0]["order_id"], "a")

    def test_long_ids_are_not_limited_by_csv_default_field_size(self):
        order_id = "x" * 200_000
        self.inputs([(order_id, "USD", "1")], [("p", order_id, "USD", "1")])
        self.assertEqual(reconcile(self.orders, self.payments)["orders"][0]["order_id"], order_id)

    def test_invalid_utf8_is_controlled_and_atomic(self):
        for source in [self.orders, self.payments]:
            with self.subTest(source=source.name):
                self.inputs()
                source.write_bytes(source.read_bytes() + b"\xff")
                self.assert_rejected()

    def test_header_only_inputs_produce_empty_arrays(self):
        self.inputs()
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_bytes(), b'{"orders":[],"schema":1,"totals":[]}\n')

    def test_zero_byte_bom_only_and_blank_files_have_no_valid_header(self):
        for body in [b"", b"\xef\xbb\xbf", b"\n", b"\r\n"]:
            for source in [self.orders, self.payments]:
                with self.subTest(body=body, source=source.name):
                    self.inputs()
                    source.write_bytes(body)
                    self.assert_rejected()

    def test_payments_without_orders_are_invalid(self):
        self.inputs([], [("p", "missing", "USD", "0")])
        self.assert_rejected()

    def test_exactly_ten_thousand_order_rows_allowed(self):
        self.inputs([(str(index), "USD", "0.01") for index in range(10_000)])
        report = reconcile(self.orders, self.payments)
        self.assertEqual(len(report["orders"]), 10_000)
        self.assertEqual(report["totals"][0]["expected_cents"], 10_000)
        self.inputs([(str(index), "USD", "0.01") for index in range(10_001)])
        self.assert_rejected()

    def test_combined_row_limit_counts_duplicate_payments(self):
        payment = ("p", "a", "USD", "1")
        self.inputs([("a", "USD", "1")], [payment] * 9_999)
        self.assertEqual(reconcile(self.orders, self.payments)["orders"][0]["received_cents"], 100)
        self.inputs([("a", "USD", "1")], [payment] * 10_000)
        self.assert_rejected()

    def test_late_failure_never_publishes_partial_report(self):
        self.inputs([("a", "USD", "1")], [("good", "a", "USD", "1"),
                                           ("bad", "missing", "USD", "1")])
        self.assert_rejected()

    def test_existing_file_and_empty_file_are_preserved(self):
        self.inputs([("a", "USD", "1")])
        for original in [b"precious existing output\x00\xff", b""]:
            with self.subTest(original=original):
                self.output.write_bytes(original)
                result = self.run_report()
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(b"Traceback", result.stderr)
                self.assertEqual(self.output.read_bytes(), original)
                self.assertFalse(list(self.work.glob(".ledgerreconcile-*")))

    def test_existing_output_directory_is_preserved(self):
        self.inputs()
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_bytes(b"keep")
        result = self.run_report()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertEqual(marker.read_bytes(), b"keep")

    def test_output_cannot_replace_either_input(self):
        self.inputs([("a", "USD", "1")], [("p", "a", "USD", "1")])
        originals = self.orders.read_bytes(), self.payments.read_bytes()
        for target in [self.orders, self.payments]:
            with self.subTest(target=target.name):
                result = self.run_report(target)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(b"Traceback", result.stderr)
                self.assertEqual((self.orders.read_bytes(), self.payments.read_bytes()), originals)

    def test_output_race_does_not_clobber_concurrently_created_file(self):
        real_link = os.link

        def race(source, destination):
            Path(destination).write_bytes(b"other writer wins")
            return real_link(source, destination)

        with patch("ledgerreconcile.core.os.link", side_effect=race):
            with self.assertRaises((OSError, ReconciliationError)):
                write_report({"schema": 1, "orders": [], "totals": []}, self.output)
        self.assertEqual(self.output.read_bytes(), b"other writer wins")
        self.assertEqual(set(self.work.iterdir()), {self.output})

    def test_flush_and_publish_failures_leave_no_output_or_temp(self):
        for target in ["os.fsync", "os.link"]:
            with self.subTest(target=target):
                with patch("ledgerreconcile.core." + target, side_effect=OSError("injected I/O failure")):
                    with self.assertRaises(OSError):
                        write_report({"schema": 1, "orders": [], "totals": []}, self.output)
                self.assertEqual(list(self.work.iterdir()), [])

    def test_output_race_preserves_concurrently_created_directory(self):
        real_link = os.link

        def race(source, destination):
            Path(destination).mkdir()
            (Path(destination) / "keep.txt").write_bytes(b"other writer")
            return real_link(source, destination)

        with patch("ledgerreconcile.core.os.link", side_effect=race):
            with self.assertRaises((OSError, ReconciliationError)):
                write_report({"schema": 1, "orders": [], "totals": []}, self.output)
        self.assertTrue(self.output.is_dir())
        self.assertEqual((self.output / "keep.txt").read_bytes(), b"other writer")
        self.assertEqual(set(self.work.iterdir()), {self.output})

    def test_publication_source_is_complete_before_destination_appears(self):
        report = {"schema": 1, "orders": [], "totals": []}
        real_link = os.link

        def inspect(source, destination):
            self.assertFalse(Path(destination).exists())
            self.assertEqual(Path(source).read_bytes(), canonical(report))
            real_link(source, destination)
            self.assertEqual(Path(destination).read_bytes(), canonical(report))

        with patch("ledgerreconcile.core.os.link", side_effect=inspect) as publish:
            write_report(report, self.output)
        publish.assert_called_once()
        self.assertEqual(set(self.work.iterdir()), {self.output})

    def test_missing_paths_directories_and_output_parent_are_controlled(self):
        self.inputs()
        for orders, payments, output in [
            (self.work / "missing.csv", self.payments, self.output),
            (self.orders, self.work / "missing.csv", self.output),
            (self.work, self.payments, self.output),
            (self.orders, self.payments, self.work / "missing" / "report.json"),
        ]:
            with self.subTest(orders=orders, payments=payments, output=output):
                result = self.cli("--orders", orders, "--payments", payments, "--output", output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"error:", result.stderr)
                self.assertNotIn(b"Traceback", result.stderr)
                self.assertFalse(output.exists())

    def test_help_and_argument_errors(self):
        result = self.cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for flag in [b"--orders", b"--payments", b"--output"]:
            self.assertIn(flag, result.stdout)
        for arguments in [(), ("--unknown",), ("--orders", "one.csv")]:
            with self.subTest(arguments=arguments):
                result = self.cli(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertIn(b"error:", result.stderr)
                self.assertNotIn(b"Traceback", result.stderr)

    def test_space_and_unicode_paths(self):
        directory = self.work / "space path 雪"
        directory.mkdir()
        self.orders = directory / "orders input.csv"
        self.payments = directory / "payments input.csv"
        self.output = directory / "new report.json"
        self.inputs([("a", "USD", "1")], [("p", "a", "USD", "1")])
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.output.read_bytes())["orders"][0]["status"], "paid")

    def test_readme_smoke_command_uses_real_included_inputs(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('python -m unittest discover -s tests -p "test*.py"', readme)
        matches = re.findall(r"```[^\n]*\n(python -m ledgerreconcile --orders [^\n]+)\n```", readme)
        self.assertTrue(matches, "README needs a fenced, single-line module smoke command")
        command = shlex.split(matches[0])
        self.assertEqual(command[:3], ["python", "-m", "ledgerreconcile"])
        self.assertEqual(len(command), 9)
        for flag in ["--orders", "--payments"]:
            relative = Path(command[command.index(flag) + 1])
            self.assertFalse(relative.is_absolute())
            self.assertTrue((ROOT / relative).is_file())
        command[command.index("--output") + 1] = str(self.output)
        result = self.cli(*command[3:])
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(self.output.read_bytes())["orders"]
        self.assertEqual([(row["order_id"], row["status"]) for row in rows],
                         [("001", "paid"), ("002", "partial")])


if __name__ == "__main__":
    unittest.main()
