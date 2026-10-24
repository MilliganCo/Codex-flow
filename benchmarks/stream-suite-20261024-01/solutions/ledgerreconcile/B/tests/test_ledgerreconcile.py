"""Finite, offline acceptance checks, including the real module CLI on disk."""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ledgerreconcile.core import ReconciliationError, parse_amount, write_report


ROOT = Path(__file__).resolve().parents[1]


class LedgerAcceptanceTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".tmp"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="ledger tests ", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.orders = self.directory / "orders input.csv"
        self.payments = self.directory / "payments input.csv"
        self.output = self.directory / "output report.json"
        self.write_orders([["001", "USD", "1.00"]])
        self.write_payments([["p1", "001", "USD", "1.00"]])

    def write_csv(self, path, headers, rows, *, bom=False):
        with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(rows)

    def write_orders(self, rows, **kwargs):
        self.write_csv(self.orders, ["order_id", "currency", "amount"], rows, **kwargs)

    def write_payments(self, rows, **kwargs):
        self.write_csv(self.payments, ["payment_id", "order_id", "currency", "amount"], rows, **kwargs)

    def invoke(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "ledgerreconcile", *map(str, arguments)],
            cwd=ROOT,
            capture_output=True,
            encoding="utf-8",
            timeout=20,
        )

    def reconcile(self, output=None):
        before = (self.orders.read_bytes(), self.payments.read_bytes())
        result = self.invoke(
            "--orders", self.orders, "--payments", self.payments,
            "--output", self.output if output is None else output,
        )
        self.assertEqual(before, (self.orders.read_bytes(), self.payments.read_bytes()))
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(list(self.directory.glob(".ledgerreconcile-*")), [])
        return result

    def successful_report(self, output=None):
        result = self.reconcile(output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        data = (self.output if output is None else output).read_bytes()
        report = json.loads(data)
        self.assertEqual(
            data,
            (json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
        )
        self.assertEqual(data.count(b"\n"), 1)
        return report, data

    def rejected(self):
        result = self.reconcile()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)
        self.assertFalse(self.output.exists())
        return result

    def test_basic_schema_and_exact_canonical_bytes(self):
        report, data = self.successful_report()
        expected = {
            "schema": 1,
            "orders": [{"order_id": "001", "currency": "USD", "expected_cents": 100,
                        "received_cents": 100, "balance_cents": 0, "status": "paid"}],
            "totals": [{"currency": "USD", "expected_cents": 100,
                        "received_cents": 100, "balance_cents": 0}],
        }
        self.assertEqual(report, expected)
        self.assertTrue(data.endswith(b"}\n"))
        self.assertNotIn(b"\r", data)

    def test_exact_cents_and_maximum_bounds(self):
        cases = {"0": 0, "-0.00": 0, "0.01": 1, "0.1": 10, "1.2": 120,
                 "1.23": 123, "1000000": 100000000, "-1000000.00": -100000000}
        for text, cents in cases.items():
            with self.subTest(amount=text):
                self.assertEqual(parse_amount(text), cents)
        self.write_orders([["001", "USD", "0.30"], ["max", "EUR", "1000000.00"]])
        self.write_payments([["a", "001", "USD", "0.10"], ["b", "001", "USD", "0.20"],
                             ["c", "max", "EUR", "1000000.00"], ["d", "max", "EUR", "-1000000.00"]])
        report, _ = self.successful_report()
        self.assertEqual(report["orders"][0]["received_cents"], 30)
        self.assertEqual(report["orders"][0]["status"], "paid")
        self.assertEqual(report["orders"][1]["received_cents"], 0)

    def test_all_statuses_refunds_and_orders_without_payments(self):
        self.write_orders([[str(i), "USD", "1"] for i in range(6)])
        self.write_payments([
            ["a", "0", "USD", "1.50"], ["refund", "0", "USD", "-1.51"],
            ["zero", "1", "USD", "-0.00"], ["b", "2", "USD", "0.01"],
            ["c", "3", "USD", "1"], ["d", "4", "USD", "1.01"],
        ])
        report, _ = self.successful_report()
        self.assertEqual([row["status"] for row in report["orders"]],
                         ["negative_net", "unpaid", "partial", "paid", "overpaid", "unpaid"])
        self.assertEqual([row["balance_cents"] for row in report["orders"]], [101, 100, 99, 0, -1, 100])
        self.assertEqual(report["totals"], [{"currency": "USD", "expected_cents": 600,
                                          "received_cents": 201, "balance_cents": 399}])

    def test_multiple_currency_totals_are_sorted_arrays(self):
        self.write_orders([["z", "USD", "1"], ["b", "EUR", "2"],
                           ["a", "USD", "3"], ["j", "JPY", "4"]])
        self.write_payments([["p", "z", "USD", "0.10"], ["q", "a", "USD", "-0.20"]])
        report, _ = self.successful_report()
        self.assertEqual(report["totals"], [
            {"currency": "EUR", "expected_cents": 200, "received_cents": 0, "balance_cents": 200},
            {"currency": "JPY", "expected_cents": 400, "received_cents": 0, "balance_cents": 400},
            {"currency": "USD", "expected_cents": 400, "received_cents": -10, "balance_cents": 410},
        ])

    def test_original_string_ids_and_sorting(self):
        ids = ["1", "001", " 1", "1 ", "a", "A", " ", "é", "订单"]
        self.write_orders([[identifier, "USD", "1"] for identifier in ids])
        self.write_payments([[str(i), identifier, "USD", "1"] for i, identifier in enumerate(ids)])
        report, _ = self.successful_report()
        self.assertEqual([row["order_id"] for row in report["orders"]], sorted(ids))
        self.assertTrue(all(row["status"] == "paid" for row in report["orders"]))

    def test_row_permutations_and_logical_duplicates_preserve_bytes(self):
        orders = [["z", "USD", "2"], ["001", "EUR", "3"], ["1", "USD", "4"]]
        payments = [["c", "z", "USD", "1.0"], ["a", "001", "EUR", "3"],
                    ["b", "z", "USD", "-0.10"], ["d", "1", "USD", "5"]]
        self.write_orders(orders)
        self.write_payments(payments)
        _, original = self.successful_report()
        self.write_orders(list(reversed(orders)))
        self.write_payments(list(reversed(payments)) + [["c", "z", "USD", "1.00"],
                                                       ["a", "001", "EUR", "3.00"]])
        _, permuted = self.successful_report(self.directory / "permuted.json")
        self.assertEqual(original, permuted)

    def test_payment_idempotence_including_signed_zero(self):
        self.write_payments([["p", "001", "USD", amount] for amount in ["1", "1.0", "1.00"]]
                            + [["z", "001", "USD", amount] for amount in ["0", "-0.0", "0.00"]])
        report, _ = self.successful_report()
        self.assertEqual(report["orders"][0]["received_cents"], 100)

    def test_conflicting_payments_in_each_payload_field_are_rejected(self):
        self.write_orders([["001", "USD", "1"], ["002", "USD", "1"]])
        for changed in [["p", "002", "USD", "1"], ["p", "001", "EUR", "1"],
                        ["p", "001", "USD", "1.01"]]:
            with self.subTest(changed=changed):
                self.write_payments([["p", "001", "USD", "1"], changed])
                self.assertIn("conflicting payment_id", self.rejected().stderr)

    def test_duplicate_orders_identical_or_different_are_rejected(self):
        for second in [["001", "USD", "1.00"], ["001", "EUR", "2"]]:
            with self.subTest(second=second):
                self.write_orders([["001", "USD", "1"], second])
                self.assertIn("duplicate order_id", self.rejected().stderr)

    def test_unknown_orders_are_rejected(self):
        self.write_payments([["p", "unknown", "USD", "1"]])
        self.assertIn("unknown order_id", self.rejected().stderr)

    def test_currency_mismatch_is_rejected(self):
        self.write_payments([["p", "001", "EUR", "1"]])
        self.assertIn("currency mismatch", self.rejected().stderr)

    def test_empty_ids_are_rejected(self):
        cases = [([["", "USD", "1"]], []),
                 ([["001", "USD", "1"]], [["", "001", "USD", "1"]]),
                 ([["001", "USD", "1"]], [["p", "", "USD", "1"]])]
        for orders, payments in cases:
            with self.subTest(orders=orders, payments=payments):
                self.write_orders(orders)
                self.write_payments(payments)
                self.rejected()

    def test_invalid_money_grammar_and_bounds(self):
        invalid = ["", "+1", "01", "-01", ".1", "1.", "1.000", "-0.001", "1e2", "NaN", "Inf",
                   "-Infinity", "1,000", " 1", "1 ", "1\n", "١", "１", "--1", "1000000.01",
                   "-1000000.01", "1000001", "9" * 5000]
        for amount in invalid:
            with self.subTest(amount=amount[:40]):
                with self.assertRaises(ReconciliationError):
                    parse_amount(amount)
        for amount in ["+1", "1e2", "NaN", "1.001", "1000000.01", "9" * 5000]:
            with self.subTest(cli_amount=amount[:40]):
                self.write_payments([["p", "001", "USD", amount]])
                self.rejected()

    def test_nonpositive_orders_are_rejected(self):
        for amount in ["0", "0.00", "-0", "-0.00", "-0.01", "-1000000"]:
            with self.subTest(amount=amount):
                self.write_orders([["001", "USD", amount]])
                self.rejected()

    def test_currency_requires_three_uppercase_ascii_letters(self):
        for currency in ["usd", "US", "USDD", "US1", " USD", "USD ", "ＵＳＤ", "UſD", "US\n"]:
            with self.subTest(currency=currency):
                self.write_orders([["001", currency, "1"]])
                self.rejected()
        self.write_orders([["001", "USD", "1"]])
        self.write_payments([["p", "001", "usd", "1"]])
        self.rejected()

    def test_headers_missing_extra_duplicate_or_misspelled_are_rejected(self):
        for path, variants in [
            (self.orders, [["order_id", "amount"], ["order_id", "currency", "amount", "extra"],
                           ["order_id", "order_id", "amount"], ["order_id", "currency", "Amount"]]),
            (self.payments, [["payment_id", "currency", "amount"],
                             ["payment_id", "order_id", "currency", "amount", "extra"],
                             ["payment_id", "order_id", "currency", "currency"],
                             ["Payment_id", "order_id", "currency", "amount"]]),
        ]:
            for headers in variants:
                with self.subTest(path=path.name, headers=headers):
                    self.write_orders([["001", "USD", "1"]])
                    self.write_payments([])
                    self.write_csv(path, headers, [])
                    self.rejected()

    def test_malformed_csv_and_wrong_widths_are_rejected(self):
        for path, header, invalid_rows in [
            (self.orders, "order_id,currency,amount\n",
             ['"unterminated,USD,1\n', 'ab"c,USD,1\n', '"a"junk,USD,1\n',
              '"a" ,USD,1\n', 'a,USD\n', 'a,USD,1,extra\n', '\n']),
            (self.payments, "payment_id,order_id,currency,amount\n",
             ['"p,001,USD,1\n', 'p,00"1,USD,1\n', 'p,"001"junk,USD,1\n',
              'p,001,USD\n', 'p,001,USD,1,extra\n', '\n']),
        ]:
            for invalid in invalid_rows:
                with self.subTest(path=path.name, invalid=invalid):
                    self.write_orders([["001", "USD", "1"]])
                    self.write_payments([])
                    path.write_bytes((header + invalid).encode("utf-8"))
                    self.rejected()

    def test_bom_reordered_headers_unicode_quotes_commas_and_newlines(self):
        identifier = '订单, "café"\r\nnext\rline\nlast'
        self.write_csv(self.orders, ["amount", "order_id", "currency"], [["1", identifier, "USD"]], bom=True)
        self.write_csv(self.payments, ["currency", "amount", "payment_id", "order_id"],
                       [["USD", "1.00", '付款,"x"\nline', identifier]], bom=True)
        report, data = self.successful_report()
        self.assertEqual(report["orders"][0]["order_id"], identifier)
        self.assertEqual(report["orders"][0]["status"], "paid")
        self.assertIn("订单".encode("utf-8"), data)
        self.assertNotIn(b"\\u8ba2", data)

    def test_all_csv_line_endings_and_no_final_newline(self):
        for index, ending in enumerate(["\n", "\r\n", "\r"]):
            with self.subTest(ending=repr(ending)):
                self.orders.write_bytes(("order_id,currency,amount" + ending + "001,USD,1").encode())
                self.payments.write_bytes(("payment_id,order_id,currency,amount" + ending + "p,001,USD,1").encode())
                self.successful_report(self.directory / f"line-ending-{index}.json")

    def test_invalid_utf8_is_a_controlled_error(self):
        for path in [self.orders, self.payments]:
            with self.subTest(path=path.name):
                self.write_orders([["001", "USD", "1"]])
                self.write_payments([])
                path.write_bytes(path.read_bytes() + b"\xff")
                self.rejected()

    def test_header_only_inputs_produce_exact_empty_report(self):
        self.write_orders([])
        self.write_payments([])
        report, data = self.successful_report()
        self.assertEqual(report, {"schema": 1, "orders": [], "totals": []})
        self.assertEqual(data, b'{"orders":[],"schema":1,"totals":[]}\n')

    def test_zero_byte_or_bom_only_inputs_are_rejected(self):
        for path in [self.orders, self.payments]:
            for empty in [b"", b"\xef\xbb\xbf"]:
                with self.subTest(path=path.name, empty=empty):
                    self.write_orders([])
                    self.write_payments([])
                    path.write_bytes(empty)
                    self.rejected()

    def test_payments_with_no_orders_are_rejected(self):
        self.write_orders([])
        self.rejected()

    def test_shared_row_limit_counts_duplicate_records(self):
        self.write_payments([["p", "001", "USD", "1"]] * 9999)
        report, _ = self.successful_report(self.directory / "at-limit.json")
        self.assertEqual(report["orders"][0]["received_cents"], 100)
        self.write_payments([["p", "001", "USD", "1"]] * 10000)
        self.assertIn("10000", self.rejected().stderr)
        self.write_orders([[str(index), "USD", "1"] for index in range(10001)])
        self.write_payments([])
        self.rejected()

    def test_long_identifier_has_no_default_csv_field_size_limit(self):
        identifier = "x" * 150000
        self.write_orders([[identifier, "USD", "1"]])
        self.write_payments([])
        report, _ = self.successful_report()
        self.assertEqual(report["orders"][0]["order_id"], identifier)

    def test_late_validation_failure_never_publishes_output(self):
        self.write_payments([["p", "001", "USD", "1"], ["bad", "001", "USD", "1.001"]])
        self.rejected()

    def test_existing_file_and_directories_are_unchanged(self):
        sentinel = b"existing output must survive\x00\xff"
        self.output.write_bytes(sentinel)
        result = self.reconcile()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), sentinel)
        for name, populated in [("empty directory", False), ("populated directory", True)]:
            directory = self.directory / name
            directory.mkdir()
            if populated:
                (directory / "sentinel").write_bytes(sentinel)
            result = self.reconcile(directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(directory.is_dir())
            self.assertEqual(list(directory.iterdir()), [directory / "sentinel"] if populated else [])
            if populated:
                self.assertEqual((directory / "sentinel").read_bytes(), sentinel)

    def test_output_equal_to_either_input_preserves_both(self):
        for path in [self.orders, self.payments]:
            with self.subTest(path=path.name):
                self.assertNotEqual(self.reconcile(path).returncode, 0)

    def test_missing_parent_or_input_and_directory_input_are_controlled(self):
        result = self.reconcile(self.directory / "absent" / "report.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.directory / "absent").exists())
        for invalid_input in [self.directory / "missing.csv", self.directory]:
            result = self.invoke("--orders", invalid_input, "--payments", self.payments, "--output", self.output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("error:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(self.output.exists())

    def test_publication_stages_complete_bytes_before_real_atomic_link(self):
        data = b'{"complete":true}\n'
        real_link = os.link

        def observe_link(source, destination):
            self.assertFalse(self.output.exists())
            self.assertEqual(Path(source).read_bytes(), data)
            real_link(source, destination)

        with mock.patch("ledgerreconcile.core.os.link", side_effect=observe_link) as link:
            write_report(self.output, data)
        link.assert_called_once()
        self.assertEqual(self.output.read_bytes(), data)
        self.assertEqual(list(self.directory.glob(".ledgerreconcile-*")), [])

    def test_write_flush_or_link_failures_clean_temporary_and_do_not_publish(self):
        for operation in ["fsync", "link"]:
            with self.subTest(operation=operation):
                with mock.patch(f"ledgerreconcile.core.os.{operation}", side_effect=OSError("injected failure")):
                    with self.assertRaises(OSError):
                        write_report(self.output, b"complete\n")
                self.assertFalse(self.output.exists())
                self.assertEqual(list(self.directory.glob(".ledgerreconcile-*")), [])

    def test_destination_created_during_publication_is_preserved(self):
        real_link = os.link

        def competing_creator(source, destination):
            Path(destination).write_bytes(b"competitor")
            real_link(source, destination)

        with mock.patch("ledgerreconcile.core.os.link", side_effect=competing_creator):
            with self.assertRaises(FileExistsError):
                write_report(self.output, b"our report\n")
        self.assertEqual(self.output.read_bytes(), b"competitor")
        self.assertEqual(list(self.directory.glob(".ledgerreconcile-*")), [])

    def test_two_real_cli_processes_cannot_overwrite_each_other(self):
        command = [sys.executable, "-m", "ledgerreconcile", "--orders", str(self.orders),
                   "--payments", str(self.payments), "--output", str(self.output)]
        before = (self.orders.read_bytes(), self.payments.read_bytes())
        processes = [subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for _ in range(2)]
        for process in processes:
            self.addCleanup(lambda p=process: p.kill() if p.poll() is None else None)
        results = [process.communicate(timeout=20) for process in processes]
        self.assertEqual(sorted(process.returncode for process in processes), [0, 1])
        self.assertTrue(all(b"Traceback" not in stderr for _, stderr in results))
        report = json.loads(self.output.read_bytes())
        self.assertEqual(report["orders"][0]["received_cents"], 100)
        self.assertEqual(before, (self.orders.read_bytes(), self.payments.read_bytes()))
        self.assertEqual(list(self.directory.glob(".ledgerreconcile-*")), [])

    def test_help_missing_flags_and_unknown_flags(self):
        help_result = self.invoke("--help")
        self.assertEqual(help_result.returncode, 0)
        for flag in ["--orders", "--payments", "--output"]:
            self.assertIn(flag, help_result.stdout)
        for arguments in [[], ["--bogus"], ["--orders", self.orders]]:
            result = self.invoke(*arguments)
            self.assertEqual(result.returncode, 2)
            self.assertIn("error:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.output.exists())

    def test_readme_smoke_is_a_real_single_line_command(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('python -m unittest discover -s tests -p "test*.py"', readme)
        match = re.search(r"```console\n(python -m ledgerreconcile --orders [^\n]+)\n```", readme)
        self.assertIsNotNone(match)
        command = shlex.split(match.group(1))
        self.assertEqual(command[:3], ["python", "-m", "ledgerreconcile"])
        self.assertEqual(len(command), 9)
        self.assertTrue((ROOT / command[4]).is_file())
        self.assertTrue((ROOT / command[6]).is_file())
        command[8] = str(self.output)
        result = self.invoke(*command[3:])
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(self.output.read_bytes())
        self.assertEqual([order["status"] for order in report["orders"]], ["paid", "partial"])


if __name__ == "__main__":
    unittest.main()
