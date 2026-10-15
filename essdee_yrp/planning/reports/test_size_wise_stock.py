from unittest import TestCase

from frappe.tests import IntegrationTestCase

from essdee_yrp.planning.reports import size_wise_stock as report
from essdee_yrp.planning.reports.test_b3_support import (
	LiveProductionChecks,
	finishing_fixture,
	production_fixture,
)


class TestSizeWiseStock(TestCase):
	def test_set_dispatch_transfers_and_matrices(self):
		context = production_fixture()
		values = report.aggregate(context, finishing_fixture(), ["Print", "Wash"])
		self.assertEqual(values["L"]["dispatch"]["M"], 30)
		self.assertEqual(values["L"]["transferred"]["M"], 7)
		self.assertEqual(values["L"]["cut_to_dispatch_diff"]["M"], -53)
		self.assertEqual(values["L"]["work_in_progress"]["M"], 53)
		self.assertEqual(values["L"]["process_0_against_cut"]["M"], -30)
		rows, sizes = report.matrices(context, values, ["Print", "Wash"], {"D": ["M", "S"]})
		self.assertEqual(sizes, ["M", "S"])
		self.assertEqual(len(rows), 40)
		for matrix in ("Lot", "Style"):
			self.assertEqual(next(row for row in rows if row["matrix"] == matrix and row["type"] == "Transferred")["total"], 7)
			self.assertEqual(next(row for row in rows if row["matrix"] == matrix and row["type"] == "Print against cut")["total"], -30)
			self.assertEqual(next(row for row in rows if row["matrix"] == matrix and row["type"] == "Wash against piece")["total"], -15)
		self.assertEqual({row["type"] for row in rows if row["matrix"] == "Lot"}, {label for _field, label in report.METRICS} | {process + " " + suffix for process in ("Print", "Wash") for suffix in ("Sent", "Received", "Diff")} | {"Print against cut", "Wash against piece"})

	def test_comparisons_advance_independently_for_each_stage(self):
		for stage, comparison, initial in (("Panels", "cut", -30), ("Pieces", "piece", 10)):
			context = production_fixture()
			for process in context["stages"]:
				process["in_stage"] = stage
			values = report.aggregate(context, finishing_fixture(), ["Print", "Wash"])
			self.assertEqual(values["L"][f"process_0_against_{comparison}"]["M"], initial)
			self.assertEqual(values["L"][f"process_1_against_{comparison}"]["M"], -25)
			rows, _sizes = report.matrices(context, values, ["Print", "Wash"], {"D": ["M"]})
			for matrix in ("Lot", "Style"):
				self.assertEqual(next(row for row in rows if row["matrix"] == matrix and row["type"] == f"Wash against {comparison}")["total"], -25)

	def test_each_matrix_preserves_its_ipd_size_order(self):
		context = production_fixture()
		values = report.aggregate(context, finishing_fixture(), [])
		context["lots"].append({"name": "L2", "item": "Style2", "production_detail": "D2"})
		values["L2"] = values["L"]
		rows, sizes = report.matrices(context, values, [], {"D": ["M", "S"], "D2": ["S", "M"]})
		self.assertEqual(sizes, ["M", "S"])
		for row in rows:
			self.assertEqual(row["matrix_sizes"], ["M", "S"] if row["item"] == "Style" else ["S", "M"])
			if row["type"] == "Order Qty":
				self.assertEqual((row["size_0"], row["size_1"]), (100, 0))

	def test_style_sums_lots_and_uncut_fallback(self):
		context = production_fixture()
		values = report.aggregate(context, finishing_fixture(), [])
		context["lots"].append({"name": "L2", "item": "Style", "production_detail": "D"})
		values["L2"] = values["L"]
		rows, _sizes = report.matrices(context, values, [], {"D": ["M"]})
		self.assertEqual(next(row for row in rows if row["matrix"] == "Style" and row["type"] == "Transferred")["total"], 14)
		context = production_fixture()
		context["order_rows"][0]["cut_qty"] = 0
		values = report.aggregate(context, finishing_fixture(), [])
		self.assertEqual(values["L"]["work_in_progress"]["M"], 63)


class TestSizeWiseStockLive(LiveProductionChecks, IntegrationTestCase):
	report = report
