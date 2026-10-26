"""Additional chief-owned checks of parsing and publication boundaries."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import unittest

import test_cli as cli


class BoundaryTests(unittest.TestCase):
    # Reuse the reviewed black-box harness, without inheriting its test methods.
    invoke = cli.LedgerCLITests.invoke
    success = cli.LedgerCLITests.success
    reject = cli.LedgerCLITests.reject

    def setUp(self):
        cli.LedgerCLITests.setUp(self)
        self.folder = self.folder / "paths with spaces"
        self.folder.mkdir()

    def run_cli(self, op, pp, output):
        result = subprocess.run(
            [sys.executable, "-m", "ledgerreconcile", "--orders", str(op),
             "--payments", str(pp), "--output", str(output)],
            cwd=cli.ROOT, capture_output=True, timeout=15)
        self.assertNotIn(b"Traceback", result.stdout + result.stderr)
        return result

    def test_strict_quote_placement_blank_records_and_payment_headers(self):
        for body in ['x"y,USD,1\n', '"x" ,USD,1\n', 'x,USD\n', '\n']:
            with self.subTest(body=body):
                self.reject('order_id,currency,amount\n' + body, cli.csv_text(cli.PH, []))
        good = cli.csv_text(cli.OH, [["x", "USD", "1"]])
        for header in [[], ["payment_id", "order_id", "amount"],
                       cli.PH + ["extra"], ["payment_id", "order_id", "amount", "amount"]]:
            self.reject(good, cli.csv_text(header, []))
        self.reject(good, cli.csv_text(cli.PH, [["p", "x", "USD"]]))
        self.reject(good, 'payment_id,order_id,currency,amount\np"q,x,USD,1\n')

    def test_money_grammar_on_orders_and_currency_ascii(self):
        invalid = ["NaN", "-Inf", "+1", "01", "-01", "1.", ".1", "1e0", "0.001",
                   "1\n", "1\t", "١", "１", "1_000", "1000000.01", "9" * 5000]
        for value in invalid:
            with self.subTest(value=value[:30]):
                self.reject(cli.csv_text(cli.OH, [["x", "USD", value]]), cli.csv_text(cli.PH, []))
        for currency in ["usd", "US", "USDD", " USD", "USD ", "ÜSD", "U\nD", ""]:
            with self.subTest(currency=currency):
                self.reject(cli.csv_text(cli.OH, [["x", currency, "1"]]), cli.csv_text(cli.PH, []))

    def test_zero_spellings_cent_precision_and_net_refund(self):
        rows = [["a", "x", "USD", "0.01"], ["b", "x", "USD", "-0.01"],
                ["z", "x", "USD", "-0.0"], ["z", "x", "USD", "0"],
                ["z", "x", "USD", "0.00"]]
        report, _ = self.success(cli.csv_text(cli.OH, [["x", "USD", "0.01"]]),
                                 cli.csv_text(cli.PH, rows))
        self.assertEqual(report["orders"][0]["received_cents"], 0)
        self.assertEqual(report["orders"][0]["status"], "unpaid")
        rows.append(["refund", "x", "USD", "-0.01"])
        report, _ = self.success(cli.csv_text(cli.OH, [["x", "USD", "0.01"]]),
                                 cli.csv_text(cli.PH, rows))
        self.assertEqual(report["orders"][0]["balance_cents"], 2)
        self.assertEqual(report["orders"][0]["status"], "negative_net")

    def test_payment_conflicts_on_each_payload_component(self):
        orders = cli.csv_text(cli.OH, [["x", "USD", "1"], ["y", "USD", "1"],
                                       ["z", "EUR", "1"]])
        first = ["same", "x", "USD", "1"]
        for second in [["same", "y", "USD", "1"], ["same", "z", "EUR", "1"],
                       ["same", "x", "USD", "-1"]]:
            self.reject(orders, cli.csv_text(cli.PH, [first, second]))
        self.reject(cli.csv_text(cli.OH, [["x", "USD", "1"], ["x", "USD", "1.00"]]),
                    cli.csv_text(cli.PH, []))

    def test_unrestricted_string_ids_and_all_line_endings(self):
        ids = [" ", "A", "a", "a\r\nb", "é", "😀", "001", "1", "\x00", "z" * 140000]
        orders = cli.csv_text(cli.OH, [[i, "USD", "1"] for i in reversed(ids)])
        payments = cli.csv_text(cli.PH, [["p" + i, i, "USD", "1"] for i in ids])
        report, raw = self.success(orders, payments)
        self.assertEqual([r["order_id"] for r in report["orders"]], sorted(ids))
        self.assertTrue(all(r["status"] == "paid" for r in report["orders"]))
        self.assertEqual(raw.count(b"\n"), 1)
        for ending in ["\n", "\r", "\r\n", ""]:
            self.success("order_id,currency,amount" + ending,
                         "payment_id,order_id,currency,amount" + ending)

    def test_maximum_unique_orders_and_large_currency_total(self):
        orders = cli.csv_text(cli.OH, [[str(i), "USD", "1000000"] for i in range(10000)])
        report, _ = self.success(orders, cli.csv_text(cli.PH, []))
        self.assertEqual(len(report["orders"]), 10000)
        self.assertEqual(report["totals"], [dict(currency="USD", expected_cents=10**12,
                                               received_cents=0, balance_cents=10**12)])
        self.reject(orders, cli.csv_text(cli.PH, [["p", "0", "USD", "0"]]))

    def test_invalid_utf8_missing_inputs_and_missing_parent(self):
        op, pp = self.folder / "orders.csv", self.folder / "payments.csv"
        op.write_bytes(b"order_id,currency,amount\nx,USD,1\n")
        pp.write_bytes(b"payment_id,order_id,currency,amount\n\xff,x,USD,1\n")
        original = (op.read_bytes(), pp.read_bytes())
        out = self.folder / "new.json"
        result = self.run_cli(op, pp, out)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(out.exists())
        self.assertEqual((op.read_bytes(), pp.read_bytes()), original)
        for source in [self.folder / "missing.csv", self.folder]:
            self.assertNotEqual(self.run_cli(source, op, out).returncode, 0)
            self.assertFalse(out.exists())
        pp.write_bytes(cli.csv_text(cli.PH, []).encode("utf-8"))
        out = self.folder / "missing parent" / "new.json"
        self.assertNotEqual(self.run_cli(op, pp, out).returncode, 0)
        self.assertFalse(out.parent.exists())
        self.assertFalse(list(self.folder.glob(".ledgerreconcile-*")))

    def test_late_failure_and_input_output_aliases(self):
        orders = cli.csv_text(cli.OH, [["x", "USD", "1"]])
        payments = cli.csv_text(cli.PH, [["p", "x", "USD", "1"], ["q", "unknown", "USD", "1"]])
        self.reject(orders, payments)
        for filename in ["orders.csv", "payments.csv"]:
            output = self.folder / filename
            result, _ = self.invoke(orders, cli.csv_text(cli.PH, []), output)
            self.assertNotEqual(result.returncode, 0)
        directory = self.folder / "existing dir"
        directory.mkdir()
        sentinel = directory / "keep"
        sentinel.write_bytes(b"preserved")
        result, _ = self.invoke(orders, cli.csv_text(cli.PH, []), directory)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_bytes(), b"preserved")
        self.assertFalse(list(self.folder.glob(".ledgerreconcile-*")))

    def test_concurrent_publish_never_replaces_or_leaves_partial_file(self):
        op, pp, output = [self.folder / name for name in ["orders.csv", "payments.csv", "race.json"]]
        op.write_bytes(cli.csv_text(cli.OH, []).encode("utf-8"))
        pp.write_bytes(cli.csv_text(cli.PH, []).encode("utf-8"))
        command = [sys.executable, "-m", "ledgerreconcile", "--orders", str(op),
                   "--payments", str(pp), "--output", str(output)]
        processes = [subprocess.Popen(command, cwd=cli.ROOT, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE) for _ in range(2)]
        for process in processes:
            try:
                stdout, stderr = process.communicate(timeout=15)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
            self.assertNotIn(b"Traceback", stdout + stderr)
        self.assertEqual(sorted(p.returncode for p in processes), [0, 1])
        self.assertEqual(output.read_bytes(), b'{"orders":[],"schema":1,"totals":[]}\n')
        self.assertFalse(list(self.folder.glob(".ledgerreconcile-*")))

    def test_cli_argument_errors_and_actual_readme_smoke(self):
        for args in [[], ["--unknown"], ["--orders"], ["--ord", "x"]]:
            result = subprocess.run([sys.executable, "-m", "ledgerreconcile", *args],
                                    cwd=cli.ROOT, capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(b"Traceback", result.stdout + result.stderr)
        readme = (cli.ROOT / "README.md").read_text(encoding="utf-8")
        blocks = re.findall(r"```[^\n]*\n(.*?)\n```", readme, re.S)
        smoke = next(block for block in blocks if block.startswith("python -m ledgerreconcile --orders"))
        self.assertNotIn("\n", smoke)
        args = shlex.split(smoke)
        self.assertEqual(args[:3], ["python", "-m", "ledgerreconcile"])
        output = self.folder / "README smoke.json"
        args[args.index("--output") + 1] = str(output)
        result = subprocess.run([sys.executable, *args[1:]], cwd=cli.ROOT,
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(output.read_bytes())
        self.assertEqual([r["received_cents"] for r in report["orders"]], [700, 250])
        self.assertIn('python -m unittest discover -s tests -p "test*.py"', readme)


if __name__ == "__main__":
    unittest.main()
