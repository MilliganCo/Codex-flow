import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
OH = ["order_id", "currency", "amount"]
PH = ["payment_id", "order_id", "currency", "amount"]
def csv_text(header, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue()
class LedgerCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.serial = 0
    def invoke(self, orders, payments, output=None):
        op, pp = self.folder / "orders.csv", self.folder / "payments.csv"
        op.write_bytes(orders.encode("utf-8"))
        pp.write_bytes(payments.encode("utf-8"))
        originals = (op.read_bytes(), pp.read_bytes())
        self.serial += 1
        output = output or self.folder / f"report {self.serial}.json"
        result = subprocess.run(
            [sys.executable, "-m", "ledgerreconcile", "--orders", str(op),
             "--payments", str(pp), "--output", str(output)], cwd=ROOT,
            capture_output=True, timeout=15)
        self.assertEqual((op.read_bytes(), pp.read_bytes()), originals)
        self.assertNotIn(b"Traceback", result.stdout + result.stderr)
        return result, output
    def success(self, orders, payments):
        result, output = self.invoke(orders, payments)
        self.assertEqual(result.returncode, 0, result.stderr)
        raw = output.read_bytes()
        report = json.loads(raw)
        expected = json.dumps(report, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":")).encode("utf-8") + b"\n"
        self.assertEqual(raw, expected)
        self.assertEqual(set(report), {"schema", "orders", "totals"})
        self.assertEqual(report["schema"], 1)
        for row in report["orders"]:
            self.assertEqual(set(row), {"order_id", "currency", "expected_cents",
                                      "received_cents", "balance_cents", "status"})
        for row in report["totals"]:
            self.assertEqual(set(row), {"currency", "expected_cents",
                                      "received_cents", "balance_cents"})
        return report, raw
    def reject(self, orders, payments):
        result, output = self.invoke(orders, payments)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stdout or result.stderr)
        self.assertFalse(output.exists())
    def test_statuses_totals_and_string_sorting(self):
        ids = ["D", "C", "B", "A", "1", "001"]
        orders = [[i, "EUR" if i == "D" else "USD", "1"] for i in ids]
        values = {"001": "1", "1": "-1", "A": "0", "B": "0.50",
                  "C": "1.00", "D": "2"}
        payments = [[f"p{i}", i, "EUR" if i == "D" else "USD", values[i]]
                    for i in ids]
        report, _ = self.success(csv_text(OH, orders), csv_text(PH, payments))
        self.assertEqual([r["order_id"] for r in report["orders"]], sorted(ids))
        self.assertEqual([r["status"] for r in report["orders"]],
                         ["paid", "negative_net", "unpaid", "partial", "paid", "overpaid"])
        self.assertEqual(report["totals"], [
            dict(currency="EUR", expected_cents=100, received_cents=200, balance_cents=-100),
            dict(currency="USD", expected_cents=500, received_cents=150, balance_cents=350)])
    def test_permutations_and_logical_duplicates(self):
        orders = [["b", "USD", "0.30"], ["a", "USD", "1"]]
        payments = [["p", "b", "USD", "0.1"], ["q", "b", "USD", "0.20"]]
        _, first = self.success(csv_text(OH, orders), csv_text(PH, payments))
        duplicate = ["p", "b", "USD", "0.10"]
        _, second = self.success(csv_text(OH, orders[::-1]),
                                 csv_text(PH, payments[::-1] + [duplicate]))
        self.assertEqual(first, second)
    def test_bom_quotes_unicode_and_reordered_headers(self):
        oid = ' 001,"é\n終 '
        orders = "\ufeff" + csv_text(["amount", "order_id", "currency"], [["1", oid, "USD"]])
        payments = "\ufeff" + csv_text(["currency", "amount", "order_id", "payment_id"],
                                       [["USD", "1.00", oid, 'p,"é\n']])
        report, raw = self.success(orders, payments)
        self.assertEqual(report["orders"][0]["order_id"], oid)
        self.assertEqual(raw.count(b"\n"), 1)
        self.assertIn("終".encode(), raw)
    def test_empty_headers_and_unpaid_order(self):
        report, _ = self.success(csv_text(OH, []), csv_text(PH, []))
        self.assertEqual(report, {"schema": 1, "orders": [], "totals": []})
        report, _ = self.success(csv_text(OH, [["x", "USD", "0.01"]]), csv_text(PH, []))
        self.assertEqual(report["orders"][0]["status"], "unpaid")
        self.assertEqual(report["orders"][0]["balance_cents"], 1)
    def test_exact_bounds_refund_and_negative_zero(self):
        report, _ = self.success(csv_text(OH, [["x", "USD", "1000000.00"]]),
            csv_text(PH, [["a", "x", "USD", "-1000000"], ["b", "x", "USD", "0.01"],
                          ["z", "x", "USD", "-0"], ["z", "x", "USD", "0.00"]]))
        self.assertEqual(report["orders"][0]["received_cents"], -99999999)
        self.assertEqual(report["orders"][0]["balance_cents"], 199999999)
    def test_invalid_money_and_nonpositive_orders(self):
        for amount in ["NaN", "Inf", "1e2", "+1", "01", ".1", "1.", "1.001",
                       "1000000.01", "-1000000.01", " 1", "1,000", ""]:
            with self.subTest(amount=amount):
                self.reject(csv_text(OH, [["x", "USD", "1"]]),
                            csv_text(PH, [["p", "x", "USD", amount]]))
        for amount in ["0", "-0.00", "-0.01"]:
            self.reject(csv_text(OH, [["x", "USD", amount]]), csv_text(PH, []))
    def test_duplicate_relationship_and_field_rejections(self):
        good = csv_text(OH, [["x", "USD", "1"]])
        self.reject(csv_text(OH, [["x", "USD", "1"]] * 2), csv_text(PH, []))
        for rows in [
            [["p", "x", "USD", "1"], ["p", "x", "USD", "2"]],
            [["p", "unknown", "USD", "1"]], [["p", "x", "EUR", "1"]],
            [["", "x", "USD", "1"]], [["p", "", "USD", "1"]],
            [["p", "x", "usd", "1"]], [["p", "x", "ＵＳＤ", "1"]],
        ]:
            self.reject(good, csv_text(PH, rows))
        self.reject(csv_text(OH, [["", "USD", "1"]]), csv_text(PH, []))
    def test_headers_and_malformed_csv(self):
        for orders in ["", "order_id,currency\nx,USD\n",
                       "order_id,currency,amount,extra\nx,USD,1,z\n",
                       "order_id,currency,amount,amount\nx,USD,1,1\n",
                       'order_id,currency,amount\n"x,USD,1',
                       'order_id,currency,amount\n"x"junk,USD,1\n',
                       "order_id,currency,amount\nx,USD,1,extra\n"]:
            self.reject(orders, csv_text(PH, []))
        self.reject(csv_text(OH, []), "")
    def test_combined_row_limit_counts_duplicate_rows(self):
        orders = csv_text(OH, [["x", "USD", "1"]])
        row = ["p", "x", "USD", "0"]
        self.success(orders, csv_text(PH, [row] * 9999))
        self.reject(orders, csv_text(PH, [row] * 10000))
    def test_existing_outputs_preserved_and_help(self):
        for directory in (False, True):
            output = self.folder / ("directory" if directory else "existing.json")
            output.mkdir() if directory else output.write_bytes(b"sentinel")
            result, _ = self.invoke(csv_text(OH, []), csv_text(PH, []), output)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(output.iterdir()) if directory else output.read_bytes(),
                             [] if directory else b"sentinel")
        result = subprocess.run([sys.executable, "-m", "ledgerreconcile", "--help"],
                                cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"--orders", result.stdout)
if __name__ == "__main__":
    unittest.main()
