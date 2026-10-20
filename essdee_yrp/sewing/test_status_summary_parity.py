"""Exercise the Status Summary parity gate with saved, database-free exports."""

import contextlib
import copy
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

RUNNER = Path(__file__).resolve().parents[2] / "scripts" / "sewing_status_summary_parity.py"
SPEC = importlib.util.spec_from_file_location("sewing_status_summary_parity", RUNNER)
parity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parity)


class TestStatusSummaryParity(TestCase):
	def setUp(self):
		self.directory = tempfile.TemporaryDirectory()
		self.addCleanup(self.directory.cleanup)
		self.output = Path(self.directory.name) / "current"
		self.output.mkdir()
		self.baseline = Path(self.directory.name) / "baseline"
		self.baseline.mkdir()
		self.erp = {
			"header1": ["Item", "SD YRP Lot", "Colour", "Part"],
			"header2": ["Checking"],
			"header3": ["Ready for Checking"],
			"data": [{}, *[
				{
					"item": item, "lot": "C0426-34/1", "colour": "Blue", "part": "",
					"Checking": 10, "Ready for Checking": "Completed",
					"ready_for_checking": "Completed", "work_order_status": "Open",
				}
				for item in ("Shirt", "Trouser")
			]],
		}
		self.mrp = copy.deepcopy(self.erp)
		self.mrp["header1"][1] = "Lot"
		for row in self.mrp["data"][1:]:
			row["display_colour"] = row.pop("colour")

	def compare(self, *, baseline=None):
		for side, payload in (("mrp", self.mrp), ("erp", self.erp)):
			(self.output / f"{side}.json").write_text(json.dumps(payload))
		with contextlib.redirect_stdout(io.StringIO()):
			passed = parity.compare(self.output, baseline)
		return passed, json.loads((self.output / "summary.json").read_text())

	def save_baseline(self, payload):
		(self.baseline / "erp.json").write_text(json.dumps(payload))

	def test_matching_rows_pass_without_optional_baseline(self):
		passed, summary = self.compare()
		self.assertTrue(passed)
		self.assertEqual(len(summary), 2)
		self.assertTrue(all(row["equal"] for row in summary))

	def test_reordered_rows_fail_even_when_grouped_values_match(self):
		self.erp["data"][1:] = reversed(self.erp["data"][1:])
		passed, summary = self.compare()
		self.assertTrue(all(row["grouped_rows_equal"] for row in summary))
		self.assertTrue(all(not row["row_order_equal"] for row in summary))
		self.assertFalse(passed)
		self.assertTrue(all(not row["equal"] for row in summary))

	def test_extra_work_order_status_column_fails_visible_contract(self):
		self.erp["header3"].append("Work Order Status")
		passed, summary = self.compare()
		self.assertFalse(passed)
		self.assertTrue(all(not row["columns_equal"] for row in summary))

	def test_duplicate_colour_wrappers_are_visible_differences(self):
		self.erp["data"][1]["colour"] = "Blue (Blue)"
		passed, _ = self.compare()
		self.assertFalse(passed)

	def test_stock_column_rename_fails_exact_column_contract(self):
		self.mrp["header2"] = ["Stock"]
		self.erp["header2"] = ["Checking Stock"]
		passed, summary = self.compare()
		self.assertFalse(passed)
		self.assertTrue(all(not row["columns_equal"] for row in summary))

	def test_incorrect_grand_total_fails_despite_matching_rows(self):
		self.mrp["data"][0]["Checking"] = 20
		self.erp["data"][0]["Checking"] = 21
		passed, summary = self.compare()
		self.assertFalse(passed)
		self.assertFalse(summary[0]["grand_totals_equal"])

	def test_non_readiness_baseline_regressions_fail_despite_mrp_equality(self):
		for change in ("quantity", "order", "metadata"):
			with self.subTest(change=change):
				previous = copy.deepcopy(self.erp)
				if change == "quantity":
					previous["data"][1]["Checking"] = 11
				elif change == "order":
					previous["data"][1:] = reversed(previous["data"][1:])
				else:
					previous["header2"] = ["Previous stage"]
				self.save_baseline(previous)
				passed, summary = self.compare(baseline=self.baseline)
				self.assertTrue(all(row["equal"] for row in summary))
				self.assertTrue(all(not row["erp_non_readiness_output_unchanged"] for row in summary))
				self.assertFalse(passed)

	def test_unchanged_baseline_and_readiness_only_changes_pass(self):
		for change_readiness in (False, True):
			with self.subTest(change_readiness=change_readiness):
				previous = copy.deepcopy(self.erp)
				if change_readiness:
					previous["data"][1]["Ready for Checking"] = ""
					previous["data"][1]["ready_for_checking"] = ""
				self.save_baseline(previous)
				passed, summary = self.compare(baseline=self.baseline)
				self.assertTrue(passed)
				self.assertTrue(all(row["erp_non_readiness_output_unchanged"] for row in summary))

	def test_compare_only_cli_rejects_order_and_baseline_regressions(self):
		original = copy.deepcopy(self.erp)
		for failure in ("order", "baseline"):
			with self.subTest(failure=failure):
				self.erp = copy.deepcopy(original)
				self.save_baseline(self.erp)
				if failure == "order":
					self.erp["data"][1:] = reversed(self.erp["data"][1:])
				else:
					previous = copy.deepcopy(self.erp)
					previous["data"][1]["Checking"] = 11
					self.save_baseline(previous)
				self.compare()
				command = [sys.executable, str(RUNNER), "--compare-only", "--output", str(self.output)]
				if failure == "baseline":
					command.extend(["--baseline", str(self.baseline)])
				process = subprocess.run(
					command,
					capture_output=True, text=True,
				)
				self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
