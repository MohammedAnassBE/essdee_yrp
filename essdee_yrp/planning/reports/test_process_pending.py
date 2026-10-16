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
		self.assertEqual(named["result"], result["result"])
		orders[1]["supplier_name"] = "Old copied name"
		unnamed = report.aggregate(lots, orders, items, {"L": ["Cut"]}, ["Sew"], {})
		self.assertEqual(next(column["label"] for column in unnamed["columns"] if column["fieldname"] == "supplier_0"), "Unit")
		self.assertEqual(report.aggregate(lots, [], [], {"L": ["Cut"]}, ["Sew"])["result"], [])

	def test_default_open_and_settings_fallback_are_batched(self):
		for count in (1, 30):
			lots = [{"name": f"L{index}", "item": "A", "production_detail": "D"} for index in range(count)]
			with patch.object(report, "require_access"), patch.object(frappe.db, "get_single_value", return_value="Sew"), patch.object(frappe, "get_list", side_effect=[lots, ["Sew"]]) as read, patch.object(frappe, "get_all", side_effect=[[{"name": "D", "cutting_process": "Cut"}], []]) as children, patch.object(report.quantities, "work_orders", return_value=[]) as orders:
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
