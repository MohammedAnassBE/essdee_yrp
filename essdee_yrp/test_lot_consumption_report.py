"""Voucher selection and strict parity regressions for Lot Consumption."""

import copy
import importlib.util
from pathlib import Path
from unittest import TestCase


def parity_module():
	path = Path(__file__).resolve().parents[1] / "scripts" / "lot_consumption_report_parity.py"
	spec = importlib.util.spec_from_file_location("lot_consumption_report_parity", path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


class TestLotConsumptionParity(TestCase):
	def setUp(self):
		self.module = parity_module()
		self.source = dict(
			filters={"lot": "L-1"},
			columns=[dict(fieldname="voucher_no", fieldtype="Dynamic Link", options="voucher_type")],
			rows=[
				dict(item_variant="Fabric-M", valuation_rate=3.5, quantity=-8, voucher_type="Stock Entry", voucher_no="STE-1", stock_ledger_entry="SLE-1", from_warehouse="S-1", to_warehouse="S-2"),
				dict(item_variant="Fabric-L", valuation_rate=4, quantity=-2, voucher_type="Stock Entry", voucher_no="STE-2", stock_ledger_entry="SLE-2", from_warehouse="S-1", to_warehouse="S-3"),
			],
			extras=[],
		)

	def test_doctype_renames_do_not_hide_reference_differences(self):
		target = copy.deepcopy(self.source)
		for row in target["rows"]:
			row["voucher_type"] = "YRP Stock Entry"
		result = self.module.compare_case("test", self.source, target)
		self.assertTrue(result["rows_equal"])
		target["rows"][0]["voucher_no"] = "STE-3"
		result = self.module.compare_case("test", self.source, target)
		self.assertFalse(result["rows_equal"])
		self.assertEqual(result["different_voucher_rows"], 1)

	def test_row_sorting_and_quantities_are_compared_exactly(self):
		target = copy.deepcopy(self.source)
		target["rows"].reverse()
		self.assertFalse(self.module.compare_case("test", self.source, target)["rows_equal"])
		target = copy.deepcopy(self.source)
		target["rows"][0]["quantity"] = -8.0000001
		self.assertFalse(self.module.compare_case("test", self.source, target)["rows_equal"])

	def test_missing_rows_fail_even_when_remaining_rows_match(self):
		target = copy.deepcopy(self.source)
		target["rows"].pop()
		result = self.module.compare_case("test", self.source, target)
		self.assertFalse(result["rows_equal"])
		self.assertEqual(result["different_voucher_rows"], 1)
