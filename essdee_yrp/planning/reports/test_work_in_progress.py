from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.planning.reports import work_in_progress as report
from essdee_yrp.planning.reports.test_b3_support import (
	LiveProductionChecks,
	finishing_fixture,
	production_fixture,
)


def receipt_fixture():
	return {"packing": {}, "reworked": {"L": 5}, "accepted": {"L": 40}}


class TestWorkInProgress(TestCase):
	def test_columns_differences_dates_totals_and_summary(self):
		result = report.aggregate(production_fixture(), finishing_fixture(), receipt_fixture(), ["Print", "Wash"])
		row, total = result["result"]
		self.assertEqual(row["ready_for_packing"], 15)
		self.assertEqual(row["sewing_received"], 50)
		self.assertEqual(row["finishing_inward"], 45)
		self.assertEqual(row["in_sew"], -20)
		self.assertEqual(row["in_packing"], -15)
		self.assertEqual(row["cut_to_dispatch_diff"], -53)
		self.assertEqual(row["last_cut_date"], "2026-10-01")
		self.assertEqual(row["sew_sent_date"], "2026-10-02")
		self.assertEqual(row["finishing_inward_date"], "2026-10-03")
		self.assertEqual(row["process_0_against_cut"], -30)
		self.assertEqual(row["process_1_against_piece"], -10)
		self.assertTrue({"process_0_against_cut", "process_1_against_piece"} <= {column["fieldname"] for column in result["columns"]})
		self.assertEqual(row["process_links"]["process_1_against_piece"], "Wash")
		self.assertEqual(row["process_links"]["process_0_received"], "Print")
		self.assertTrue(total["is_total_row"])
		self.assertEqual(total["transferred"], 7)
		self.assertEqual(result["summary"]["Lots"], 1)
		self.assertTrue({field for field, _label in (*report.METRICS, *report.DATES)} <= {column["fieldname"] for column in result["columns"]})

	def test_selected_process_without_ipd_row_still_has_comparison_column(self):
		context = production_fixture()
		result = report.aggregate(context, finishing_fixture(), receipt_fixture(), ["Sew"])
		self.assertIn("process_0_against_piece", {column["fieldname"] for column in result["columns"]})
		self.assertEqual(result["result"][0]["process_0_against_piece"], 5)
		self.assertEqual(result["result"][0]["process_links"]["process_0_against_piece"], "Sew")

	def test_ready_for_packing_uses_accepted_permitted_grn_items(self):
		context = production_fixture()
		def children(doctype, parents, fields, parenttype):
			if doctype == "YRP Goods Received Note Item":
				self.assertEqual(set(parents), {"VisibleSew", "VisibleCut"})
				return [{"parent": "VisibleSew", "quantity": 73, "received_type": "Accepted"}, {"parent": "VisibleSew", "quantity": 99, "received_type": "Rejected"}, {"parent": "VisibleCut", "quantity": 888, "received_type": "Accepted"}]
			return []
		with patch.object(report.frappe, "get_list", side_effect=[[{"name": "VisibleSew", "against_id": "S1"}, {"name": "VisibleCut", "against_id": "C"}], []]) as read, patch.object(report.frappe.db, "get_single_value", return_value="Accepted"), patch.object(report.quantities, "child_rows", side_effect=children):
			receipts = report.receipt_context(context)
		self.assertEqual(read.call_args_list[0].kwargs["filters"], {"docstatus": 1, "against": "YRP Work Order", "against_id": ["in", [order["name"] for order in context["orders"]]], "is_return": 0})
		self.assertEqual(receipts["accepted"]["L"], 73)
		self.assertEqual(report.aggregate(context, finishing_fixture(), receipts, [])["result"][0]["ready_for_packing"], 43)

	def test_packing_fallback_zero_clamp_and_cut_from_work_orders(self):
		context = production_fixture()
		context["order_rows"][0]["cut_qty"] = 999
		context["details"]["D"]["packing_combo"] = 5
		finishing = {"plans": {}, "parts": {"D": 2}, "dispatches": [], "inwards": []}
		receipts = receipt_fixture()
		receipts["packing"] = {"L": {"quantity": 10, "stock_qty": 70}}
		row = report.aggregate(context, finishing, receipts, ["Wash"])["result"][0]
		self.assertEqual(row["cut_qty"], 90)
		self.assertEqual(row["dispatch"], 100)
		self.assertEqual(row["finishing_inward"], 70)
		self.assertEqual(row["ready_for_packing"], 0)
		self.assertEqual(row["process_0_against_piece"], -35)

	def test_background_progress_and_empty_result(self):
		context = production_fixture()
		updates = []
		with patch.object(report, "require_access"), patch.object(report.quantities, "authorize_filter_values", return_value=[]), patch.object(report.quantities, "production_lots", return_value=context["lots"]), patch.object(report.quantities, "production_context", return_value=context), patch.object(report.quantities, "finishing_context", return_value=finishing_fixture()), patch.object(report.quantities, "variant_attributes", return_value={}), patch.object(report, "receipt_context", return_value=receipt_fixture()):
			self.assertTrue(report.run({"lot": ["L"]}, progress=lambda current, total: updates.append((current, total)))["columns"])
		self.assertEqual(updates, [(0, 4), (1, 4), (2, 4), (3, 4), (4, 4)])
		context["lots"] = []
		context["order_rows"] = []
		context["items"] = []
		finishing = {"plans": {}, "parts": {}, "dispatches": [], "inwards": []}
		self.assertEqual(report.aggregate(context, finishing, receipt_fixture(), [])["result"], [])


class TestWorkInProgressDateParity(TestCase):
	def test_both_runners_include_only_midnight_at_end_date(self):
		from essdee_yrp.merch import reports as merch
		from essdee_yrp.planning.reports import production_quantities as quantities
		filters = {"lot": ["L"], "item": [], "lot_status": "Open", "from_date": "2026-10-09", "to_date": "2026-10-09"}
		def read(doctype, **kwargs):
			if kwargs.get("pluck"):
				return ["L"]
			conditions = kwargs["filters"]
			upper = next(row for row in conditions if row[-3] == "creation" and row[-2] in ("<", "<="))
			self.assertEqual(upper[-2:], ["<=", "2026-10-09"])
			return []
		with patch.object(frappe, "get_list", side_effect=read):
			quantities.production_lots(filters, creation_end_midnight=True)
			merch.resolve_lots(filters)


class TestWorkInProgressLive(LiveProductionChecks, IntegrationTestCase):
	report = report
