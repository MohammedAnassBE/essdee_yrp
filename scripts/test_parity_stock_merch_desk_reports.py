"""Check parity failures and partial-run evidence retention."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).with_name("parity_stock_merch_desk_reports.py")


class TestStockMerchParityRunner(unittest.TestCase):
	def saved_cases(self, output, *, rows_equal=True, columns_equal=True, error=False):
		for index in (1, 2):
			for side in ("source", "target"):
				payload = {
					"columns": [{"fieldname": "qty", "label": "Qty"}],
					"normalized": ['{"qty": 1}'],
					"row_count": 1,
				}
				if side == "target":
					if not rows_equal:
						payload["normalized"] = ['{"qty": 2}']
					if not columns_equal:
						payload["columns"][0]["label"] = "Wrong label"
					if error:
						payload = {"error": "ValidationError"}
				(output / f"stock_ledger_{index}_{side}.json").write_text(json.dumps(payload))

	def run_saved(self, output):
		return subprocess.run(
			[
				sys.executable,
				str(RUNNER),
				"--compare-only",
				"--report",
				"stock_ledger",
				"--output",
				str(output),
			],
			capture_output=True,
			text=True,
		)

	def test_mismatched_rows_columns_and_blocked_cases_fail_process(self):
		for options in ({"rows_equal": False}, {"columns_equal": False}, {"error": True}):
			with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
				output = Path(directory)
				self.saved_cases(output, **options)
				self.assertNotEqual(self.run_saved(output).returncode, 0)

	def test_partial_run_replaces_its_cases_and_preserves_other_reports(self):
		with tempfile.TemporaryDirectory() as directory:
			output = Path(directory)
			other = {"report": "reserved_stock", "case": 1, "rows_equal": True}
			previous = [other, {"report": "stock_ledger", "case": 1, "rows_equal": False}]
			(output / "summary.json").write_text(json.dumps(previous))
			self.saved_cases(output)
			process = self.run_saved(output)
			self.assertEqual(process.returncode, 0, process.stderr)
			current = json.loads((output / "summary.json").read_text())
			self.assertIn(other, current)
			self.assertEqual(len(current), 3)
			self.assertTrue(all(row["rows_equal"] for row in current))


if __name__ == "__main__":
	unittest.main()
