from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.planning.reports import colour_wise_diff as report
from essdee_yrp.planning.reports.test_b3_support import LiveProductionChecks, production_fixture


class TestColourWiseDiff(TestCase):
	def test_aggregates_before_subtracting_and_deduplicates_suppliers(self):
		rows = report.aggregate(production_fixture(), ["Print", "Wash"], ["M", "S"], {"S": "Unit"})
		by_label = {row["process"]: row for row in rows}
		self.assertEqual(by_label["Sewing Sent"]["total"], 70)
		self.assertEqual(by_label["Cut-to-Sew Diff"]["total"], -20)
		self.assertEqual(by_label["Sewing Received"]["total"], 50)
		self.assertEqual(by_label["In Sew"]["total"], -20)
		self.assertEqual(by_label["Sewing Sent"]["supplier"], "Unit")
		self.assertNotIn("Finishing Inward", by_label)
		self.assertEqual(by_label["Print to Cut Diff"]["total"], -30)
		self.assertEqual(by_label["Wash to Sewing Diff"]["total"], -15)
		self.assertEqual(by_label["Sewing Sent"]["size_1"], 0)

	def test_ordered_process_chain_and_no_orders(self):
		context = production_fixture()
		context["stages"][1]["in_stage"] = "Panels"
		rows = report.aggregate(context, ["Print", "Wash"], ["M"])
		self.assertEqual(next(row for row in rows if row["process"] == "Wash to Print Diff")["total"], -25)
		context["items"] = []
		rows = report.aggregate(context, ["Print"], ["M"])
		self.assertEqual(next(row for row in rows if row["process"] == "Print Diff")["total"], 0)

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
		self.assertEqual({row["colour"] for row in rows}, {"Red @Top", "Red @Bottom"})
		self.assertEqual([row["total"] for row in rows if row["process"] == "Order Qty"], [100, 100])


class TestColourWiseDiffLive(LiveProductionChecks, IntegrationTestCase):
	report = report
