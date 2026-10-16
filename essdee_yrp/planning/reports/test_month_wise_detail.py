from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.planning.reports import inhouse_quantity, inward_quantity, process_pending
from essdee_yrp.planning.reports import month_wise_detail as report
from essdee_yrp.planning.reports.test_b2_support import LiveReportChecks


class TestMonthWiseDetail(TestCase):
	def test_read_permissions_gate_every_report(self):
		for module in (report, process_pending, inward_quantity, inhouse_quantity):
			for denied in ("YRP Work Order", "SD YRP Lot"):
				with self.subTest(module=module.__name__, denied=denied), patch.dict(frappe.session, {"user": "restricted@example.com"}), patch.object(frappe, "has_permission", side_effect=lambda doctype, permission: doctype != denied):
					self.assertFalse(module.can_view())
					with self.assertRaises(frappe.PermissionError):
						module.run({})

	def test_year_month_order_and_item_totals(self):
		rows = report.aggregate([{"item": "A", "date": "2026-03-02", "cut_qty": 10}, {"item": "A", "date": "2025-03-01", "dispatch": 4}, {"item": "B", "date": "2026-03-01", "sewing_sent": 5}, {"item": "A", "date": "2026-03-15", "finishing_inward": 7}])
		self.assertEqual([row["month"] for row in rows[:3]], ["2025-03", "2026-03", "Total"])
		self.assertEqual(rows[2]["cut_qty"], 10)
		self.assertEqual(rows[2]["finishing_inward"], 7)
		self.assertEqual(rows[2]["dispatch"], 4)
		self.assertEqual(rows[-1]["sewing_sent"], 5)

	def test_dispatch_dates_bound_on_stock_entry_and_conversion(self):
		def read(doctype, **kwargs):
			if doctype == "SD YRP Finishing Plan":
				return [{"name": "P", "lot": "L"}]
			if doctype == "SD YRP Finishing Plan Dispatch":
				return ["D"]
			if doctype == "YRP Stock Entry":
				self.assertEqual(kwargs["filters"]["posting_date"], ["between", ["2026-03-01", "2026-03-31"]])
				self.assertEqual(kwargs["filters"]["docstatus"], 1)
				return [{"name": "S", "against": "SD YRP Finishing Plan Dispatch", "against_id": "D", "posting_date": "2026-03-02"}]
			self.fail(doctype)
		with patch.object(report.quantities, "can_read", return_value=True), patch.object(frappe, "get_list", side_effect=read), patch.object(report.quantities, "child_rows", return_value=[{"parent": "S", "lot": "L", "item": "V", "qty": 2, "conversion_factor": 12}]), patch.object(frappe, "get_all", return_value=[{"name": "V", "variant_of": "A"}]):
			self.assertEqual(report.dispatch_events({"L": {"item": "A"}}, "2026-03-01", "2026-03-31"), [{"item": "A", "date": "2026-03-02", "dispatch": 24}])

	def test_required_selection_and_paired_dates(self):
		with patch.object(report, "require_access"):
			with self.assertRaises(frappe.ValidationError):
				report.run({})
		for filters in ({"from_date": "2026-01-01"}, {"to_date": "2026-01-01"}, {"from_date": "2026-02-01", "to_date": "2026-01-01"}):
			with self.assertRaises(frappe.ValidationError):
				report.quantities.validate_dates(filters)

	def test_every_json_filter_rejects_invisible_values_before_queries(self):
		for module in (report, process_pending):
			for field in ("lot", "item"):
				with self.subTest(module=module.__name__, field=field), patch.object(module, "require_access"), patch.object(frappe, "get_list", return_value=[]) as read, patch.object(frappe, "get_all") as children:
					with self.assertRaises(frappe.PermissionError):
						module.run({field: '["DENIED"]'})
					self.assertEqual(read.call_count, 1)
					self.assertEqual(read.call_args.args[0], "Item" if field == "item" else "SD YRP Lot")
					children.assert_not_called()


class TestMonthWiseDetailLive(LiveReportChecks, IntegrationTestCase):
	report = report
