from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.planning.reports import process_pending as report
from essdee_yrp.planning.reports.test_b2_support import LiveReportChecks


class TestProcessPending(TestCase):
	def test_internal_external_columns_totals_and_five_metrics(self):
		lots = [{"name": "L", "item": "A"}]
		orders = [{"name": name, "lot": "L", "process_name": process, "supplier": supplier, "is_internal_unit": internal, "last_grn_date": "2026-03-02"} for name, process, supplier, internal in (("C", "Cut", "Cutter", 0), ("I", "Sew", "Unit", 1), ("E", "Sew", "External", 0))]
		items = [{"parent": name, "received_qty": received, "delivered_quantity": delivered} for name, received, delivered in (("C", 100, 100), ("I", 40, 60), ("E", 10, 30))]
		result = report.aggregate(lots, orders, items, {"L": ["Cut"]}, ["Sew"])
		self.assertEqual(result["result"][0]["supplier_0"], 20)
		self.assertEqual(result["result"][0]["others"], 20)
		self.assertEqual(result["result"][0]["cutting_completion"], "2026-03-02")
		self.assertTrue(result["result"][-1]["is_total_row"])
		self.assertEqual(result["summary"], {"Total Lots": 1, "Cutting Received": 100, "Received": 50, "Overall Pending": 50, "Not Delivered": 10})
		self.assertEqual(len(result["report_summary"]), 5)
		labels = {"Unit": "Essdee Sewing Unit - Tirupur"}
		named = report.aggregate(lots, orders, items, {"L": ["Cut"]}, ["Sew"], labels)
		self.assertEqual(next(column["label"] for column in named["columns"] if column["fieldname"] == "supplier_0"), labels["Unit"])
		self.assertEqual(named["result"][0]["supplier_0"], result["result"][0]["supplier_0"])
		self.assertEqual(named["result"][0]["supplier_pending_days"], {labels["Unit"]: None, "Others": None})
		self.assertEqual(named["result"][-1], result["result"][-1])
		orders[1]["supplier_name"] = "Old copied name"
		unnamed = report.aggregate(lots, orders, items, {"L": ["Cut"]}, ["Sew"], {})
		self.assertEqual(next(column["label"] for column in unnamed["columns"] if column["fieldname"] == "supplier_0"), "Unit")
		self.assertEqual(report.aggregate(lots, [], [], {"L": ["Cut"]}, ["Sew"])["result"], [])

	def test_pending_annotations_use_latest_submitted_dc_per_supplier_bucket(self):
		lots = [{"name": "L", "item": "Style"}]
		orders = [{"name": name, "lot": "L", "process_name": process, "supplier": supplier, "is_internal_unit": internal} for name, process, supplier, internal in (("C", "Cut", "Cutter", 0), ("S", "Sew", "Unit", 1), ("E", "Sew", "External", 0))]
		items = [{"parent": name, "delivered_quantity": 10, "received_qty": 0} for name in ("C", "S", "E")]
		dcs = [{"work_order": "S", "lot": "L", "posting_date": "2026-10-12"}, {"work_order": "S", "lot": "L", "posting_date": "2026-10-14"}]
		with patch.object(report, "nowdate", return_value="2026-10-20"):
			row = report.aggregate(lots, orders, items, {"L": ["Cut"]}, ["Sew"], {"Unit": "Sewing Unit"}, dcs)["result"][0]
		self.assertEqual(row["supplier_last_dc_dates"], {"Sewing Unit": "2026-10-14", "Others": None})
		self.assertEqual(row["supplier_pending_days"], {"Sewing Unit": 6, "Others": None})


	def test_submitted_dc_lookup_includes_rework_work_orders(self):
		orders = [{"name": "Rework", "supplier": "Unit", "is_internal_unit": 1}]
		dcs = [{"work_order": "Rework", "lot": "L", "posting_date": "2026-10-19"}]
		with patch.object(frappe, "get_list", side_effect=[orders, dcs]) as read:
			result = report.submitted_delivery_challans([{"name": "L"}], ["Sew"])
		self.assertEqual(result[0]["supplier_bucket"], "Unit")
		self.assertEqual(result[0]["posting_date"], "2026-10-19")
		self.assertNotIn("docstatus", read.call_args_list[0].kwargs["filters"])
		self.assertNotIn("is_rework", read.call_args_list[0].kwargs["filters"])
		self.assertEqual(read.call_args_list[1].kwargs["filters"]["docstatus"], 1)

	def test_shared_supplier_display_name_keeps_latest_date(self):
		lots = [{"name": "L", "item": "Style"}]
		orders = [{"name": name, "lot": "L", "process_name": process, "supplier": name, "is_internal_unit": 1} for name, process in (("C", "Cut"), ("S1", "Sew"), ("S2", "Sew"))]
		items = [{"parent": name, "delivered_quantity": 10, "received_qty": 0} for name in ("C", "S1", "S2")]
		dcs = [{"work_order": name, "lot": "L", "posting_date": date} for name, date in (("S1", "2026-10-19"), ("S2", "2026-10-01"))]
		row = report.aggregate(lots, orders, items, {"L": ["Cut"]}, ["Sew"], {"S1": "Unit", "S2": "Unit"}, dcs)["result"][0]
		self.assertEqual(row["supplier_last_dc_dates"], {"Unit": "2026-10-19"})


	def test_default_open_and_settings_fallback_are_batched(self):
		for count in (1, 30):
			lots = [{"name": f"L{index}", "item": "A", "production_detail": "D"} for index in range(count)]
			with patch.object(report, "require_access"), patch.object(frappe.db, "get_single_value", return_value="Sew"), patch.object(frappe, "get_list", side_effect=[lots, ["Sew"]]) as read, patch.object(frappe, "get_all", side_effect=[[{"name": "D", "cutting_process": "Cut"}], []]) as children, patch.object(report.quantities, "work_orders", return_value=[]) as orders, patch.object(report, "submitted_delivery_challans", return_value=[]):
				result = report.run({})
				self.assertTrue(result["columns"])
				self.assertEqual(read.call_args_list[0].kwargs["filters"], {"status": "Open"})
				self.assertEqual(children.call_count, 2)
				orders.assert_called_once()
				self.assertEqual(len(orders.call_args.args[0]["lot"][1]), count)

	def test_status_validation(self):
		with patch.object(report, "require_access"):
			for status in ("", "Close", "invalid"):
				with self.assertRaises(frappe.ValidationError):
					report.run({"lot_status": status})


class TestProcessPendingLive(LiveReportChecks, IntegrationTestCase):
	report = report
