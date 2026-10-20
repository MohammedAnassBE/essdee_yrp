from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.planning.reports import colour_wise_diff as report
from essdee_yrp.planning.reports.test_b3_support import LiveProductionChecks, production_fixture


class TestColourWiseDiff(TestCase):
	def test_legacy_per_row_sewing_difference_and_deduplicates_suppliers(self):
		rows = report.aggregate(production_fixture(), ["Print", "Wash"], ["M", "S"], {"S": "Unit"})
		by_label = {row["process"]: row for row in rows}
		self.assertEqual(by_label["Sewing Sent"]["total"], 70)
		self.assertEqual(by_label["Cut to Sew Diff"]["total"], -110)
		self.assertEqual(by_label["Finishing Inward"]["total"], 50)
		self.assertEqual(by_label["In Sew"]["total"], -20)
		self.assertEqual(by_label["Sewing Sent"]["supplier"], "Unit")
		self.assertIn("Finishing Inward", by_label)
		self.assertEqual(by_label["Print to Cut Diff"]["total"], -30)
		self.assertEqual(by_label["Wash to Sew Diff"]["total"], -15)
		self.assertEqual(by_label["Sewing Sent"]["size_1"], 0)

	def test_ordered_processes_compare_to_base_and_no_orders(self):
		context = production_fixture()
		context["stages"][1]["in_stage"] = "Panels"
		rows = report.aggregate(context, ["Print", "Wash"], ["M"])
		self.assertEqual(next(row for row in rows if row["process"] == "Wash to Cut Diff")["total"], -55)
		context["items"] = []
		rows = report.aggregate(context, ["Print"], ["M"])
		self.assertEqual(next(row for row in rows if row["process"] == "Print Diff")["total"], 0)

	def test_selected_process_comparison_only_exists_for_applicable_part(self):
		context = production_fixture()
		context["details"]["D"].update(is_set_item=1, set_item_attribute="Part", major_attribute_value="Top", packing_attribute="Colour")
		context["attributes"] = {part: {"Part": part, "Size": "M", "Colour": "Red"} for part in ("Top", "Bottom")}
		context["order_rows"] = [{**context["order_rows"][0], "item_variant": part} for part in ("Top", "Bottom")]
		context["items"] = [{**row, "item_variant": "Bottom" if row["parent"] == "P2" else "Top"} for row in context["items"]]
		context["stages"][1]["in_stage"] = "Panels"
		rows = report.aggregate(context, ["Print", "Wash"], ["M"])
		bottom = {row["process"]: row for row in rows if row["colour"] == "Red(Red) @Bottom"}
		self.assertIn("Wash to Cut Diff", bottom)
		self.assertNotIn("Print to Cut Diff", bottom)
		self.assertNotIn("Wash to Print Diff", bottom)
		self.assertEqual(bottom["Wash to Cut Diff"]["total"], -55)

	def test_selected_cut_rows_precede_sewing_and_keep_requested_process_order(self):
		context = production_fixture()
		context["stages"][1]["in_stage"] = "Panels"
		rows = report.aggregate(context, ["Wash", "Print"], ["M"])
		self.assertEqual([row["process"] for row in rows], [
			"Order Qty", "Cut Qty", "Order to Cut Diff",
			"Wash Sent", "Wash Received", "Wash Diff", "Wash to Cut Diff",
			"Print Sent", "Print Received", "Print Diff", "Print to Cut Diff",
			"Sewing Sent", "Cut to Sew Diff", "Finishing Inward", "In Sew",
		])

	def test_cumulative_selected_comparison_uses_child_idx_order(self):
		context = production_fixture()
		template = context["items"][-2]
		context["items"] = [{**template, "idx": idx, "received_qty": received} for idx, received in ((2, 40), (1, 20))]
		rows = report.aggregate(context, ["Print"], ["M"])
		self.assertEqual(next(row for row in rows if row["process"] == "Print to Cut Diff")["total"], -100)


	def test_lot_required(self):
		with patch.object(report, "require_access"):
			with self.assertRaises(frappe.ValidationError):
				report.run({})

	def test_set_parts_do_not_merge(self):
		context = production_fixture()
		context["items"] = []
		context["order_rows"] *= 2
		with patch.object(report.quantities, "matrix_identity", side_effect=[("Red", "Top", "M"), ("Red", "Bottom", "M")]):
			rows = report.aggregate(context, [], ["M"])
		self.assertEqual({row["colour"] for row in rows}, {"Red(Red) @Top", "Red(Red) @Bottom"})
		self.assertEqual([row["total"] for row in rows if row["process"] == "Order Qty"], [100, 100])


class TestColourWiseDiffLive(LiveProductionChecks, IntegrationTestCase):
	report = report
