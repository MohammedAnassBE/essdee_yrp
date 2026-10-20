"""2026-10-20 report decisions: source scan dates, stable vouchers and web placement."""

from unittest.mock import patch

import frappe
from frappe.desk.query_report import run as run_desk_report
from frappe.tests import IntegrationTestCase
from yrp.web_reports.jobs import run_web_report
from yrp.web_reports.registry import clear_web_report_cache, get_web_reports

from essdee_yrp.desk_web_reports import department_report_capabilities
from essdee_yrp.time_and_action.reports import execute_time_and_action_summary

REPORTS = (
	("purchase-order-itemwise", "SD YRP Purchase Order Itemwise", ("purchase", "accounts")),
	("lot-consumption-report", "SD YRP Lot Consumption Report", ("purchase", "fabric-store", "accessory-store", "accounts")),
)
DEPARTMENTS = ("purchase", "accounts", "fabric-store", "accessory-store", "cutting", "cut-panel-store", "sewing", "finishing", "merch", "planning", "sales", "pd", "hr")


class TestUserDecisionsReports(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		clear_web_report_cache()

	def tearDown(self):
		clear_web_report_cache()

	def test_summary_uses_mrp_first_scanned_date_instead_of_latest_or_earliest(self):
		# Read-only source exports, including two lots with different completion dates.
		for lot, date, count in (("C0425-01", "2025-06-25", 5), ("34178", "2024-12-18", 6), ("36224", "2024-12-16", 6)):
			with self.subTest(lot=lot):
				rows = execute_time_and_action_summary({"lot": lot})[1]
				self.assertEqual(len(rows), count)
				sewing = next(row for row in rows if row.action == "SEWING")
				self.assertEqual(str(sewing.actual_date), date)
				self.assertEqual(sewing.no_of_completed, 1)

	def test_summary_explicit_representative_with_strict_grouping_and_insertion_orders(self):
		prefix = "_Test Summary Scan-" + frappe.generate_hash(length=8)
		action = prefix + "-Action"
		frappe.get_doc({"doctype": "SD YRP Action", "name": action, "default": 1, "default_order": 99}).db_insert()
		parents = [(prefix + suffix, prefix + lot) for suffix, lot in (("-Z", "-Lot1"), ("-A", "-Lot1"), ("-B", "-Lot2"))]
		# Parent/name scan picks A's A detail, regardless of idx or date order.
		candidates = [
			("-Z", "-Z", 1, "2099-12-31", 1),
			("-A", "-Z", 1, "2099-01-01", 0),
			("-A", "-A", 9, "2099-06-15", 1),
			("-B", "-B", 1, "2099-04-10", 1),
		]
		mode = frappe.db.sql("SELECT @@SESSION.sql_mode")[0][0]
		try:
			frappe.db.sql("SET SESSION sql_mode=%s", (mode + ",ONLY_FULL_GROUP_BY",))
			for reverse in (False, True):
				for parent, lot in reversed(parents) if reverse else parents:
					frappe.get_doc({"doctype": "SD YRP Time and Action", "name": parent, "lot": lot}).db_insert()
				for parent, detail, idx, date, completed in reversed(candidates) if reverse else candidates:
					frappe.get_doc({"doctype": "SD YRP Time and Action Detail", "name": prefix + parent + detail,
						"parent": prefix + parent, "parenttype": "SD YRP Time and Action", "parentfield": "details",
						"action": action, "idx": idx, "actual_date": date, "completed": completed}).db_insert()
				for lot in (prefix + "-Lot1", None):
					names = [parent for parent, parent_lot in parents if not lot or lot == parent_lot]
					with self.subTest(reverse=reverse, lot=lot), patch("essdee_yrp.time_and_action.reports._allowed_names", return_value=names):
						rows = execute_time_and_action_summary({"lot": lot})[1]
						self.assertEqual(len(rows), 1)
						self.assertEqual((rows[0].no_of_completed, str(rows[0].actual_date)), (0 if lot else 1, "2099-06-15"))
				with patch("essdee_yrp.time_and_action.reports._allowed_names", return_value=[prefix + "-Z"]):
					row = execute_time_and_action_summary({"lot": prefix + "-Lot1"})[1][0]
					self.assertEqual(str(row.actual_date), "2099-12-31")
				frappe.db.set_value("SD YRP Time and Action Detail", prefix + "-A-A", "actual_date", None)
				with patch("essdee_yrp.time_and_action.reports._allowed_names", return_value=[prefix + "-A", prefix + "-Z"]):
					self.assertIsNone(execute_time_and_action_summary({"lot": prefix + "-Lot1"})[1][0].actual_date)
				frappe.db.delete("SD YRP Time and Action Detail", {"action": action})
				frappe.db.delete("SD YRP Time and Action", {"name": ["in", [name for name, _ in parents]]})
		finally:
			frappe.db.sql("SET SESSION sql_mode=%s", (mode,))

	def test_summary_keeps_parent_record_permission_scope(self):
		with patch("essdee_yrp.time_and_action.reports._allowed_names", return_value=[]):
			self.assertEqual(execute_time_and_action_summary({"lot": "C0425-01"})[1], [])

	def test_department_visibility_and_denied_permissions(self):
		with patch("essdee_yrp.desk_web_reports.can_run_desk_report", return_value=True):
			for department in DEPARTMENTS:
				capabilities = department_report_capabilities(department, True)
				for key, _, allowed in REPORTS:
					self.assertEqual(key.replace("-", "_") in capabilities, department in allowed)
				self.assertEqual(department_report_capabilities(department, False), {})
		original = frappe.has_permission
		for key, name, departments in REPORTS:
			for denied in ("role", "read", "report"):
				target = "frappe.core.doctype.report.report.Report.is_permitted" if denied == "role" else "frappe.has_permission"
				kwargs = {"return_value": False} if denied == "role" else {"side_effect": lambda doctype, ptype="read", **kw: False if ptype == denied else original(doctype, ptype=ptype, **kw)}
				with self.subTest(report=name, denied=denied), patch(target, **kwargs):
					for department in departments:
						self.assertNotIn(key.replace("-", "_"), department_report_capabilities(department, True))
					if denied != "read":
						with self.assertRaises(frappe.PermissionError):
							run_web_report(key, {})

	def test_registry_filters_and_nonempty_rows_equal_desk(self):
		cases = (
			(REPORTS[0], {"item": ("Link", "Item"), "supplier": ("Link", "Supplier"), "purchase_order": ("Link", "Purchase Order"), "delivery_location": ("Link", "Supplier"), "lot": ("Link", "SD YRP Lot"), "status": "Select", "open_status": "Select", "docstatus": "Select", "date_based_on": "Select", "from_date": "Date", "to_date": "Date"}, [
				{"open_status": "Open", "status": "Ordered"}, {"open_status": "Open", "status": "Partially Delivered"},
			]),
			(REPORTS[1], {"lot": ("Link", "SD YRP Lot"), "start_date": "Date", "end_date": "Date", "item_group": ("Link", "Item Group")}, [
				{"lot": "C0925-57/1", "start_date": "2026-08-01", "end_date": "2026-09-30", "item_group": "Purchase"},
				{"lot": "JB2627-015", "start_date": "2026-08-01", "end_date": "2026-09-30", "item_group": "Products"},
			]),
		)
		for (key, name, _), schema, filters_list in cases:
			entry = get_web_reports().get(key)
			self.assertIsNotNone(entry)
			self.assertEqual((entry.kind, entry.report, entry.background), ("frappe_report", name, "never"))
			self.assertEqual(entry.filters, schema)
			for filters in filters_list:
				with self.subTest(report=name, filters=filters):
					desk = run_desk_report(name, filters=filters, ignore_prepared_report=True, are_default_filters=True)
					web = run_web_report(key, filters)
					self.assertTrue(desk["result"])
					self.assertEqual(web["columns"], desk["columns"])
					self.assertEqual(web["result"], desk["result"])
					if key == "purchase-order-itemwise":
						for row in desk["result"]:
							self.assertEqual(row["uom"], frappe.db.get_value("Purchase Order Item", {"parent": row["name"], "item_code": row["item_variant"], "lot": row["lot"]}, "uom"))

	def test_consumption_earliest_voucher_ties_and_bucket_totals(self):
		from essdee_yrp.essdee_yrp.report.sd_yrp_lot_consumption_report.sd_yrp_lot_consumption_report import (
			execute,
		)

		prefix = "_Test Earliest Consumption-" + frappe.generate_hash(length=8)
		group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		item, lot = prefix + "-Item", prefix + "-Lot"
		frappe.get_doc({"doctype": "Item", "name": item, "item_code": item, "item_name": item, "item_group": group}).db_insert()
		frappe.get_doc({"doctype": "SD YRP Lot", "name": lot}).db_insert()
		# Each prefix of this list catches one ordering key. Ledger names and
		# warehouses deliberately sort opposite to the accepted voucher rule.
		entries = [
			("A", "2099-01-02", "01:00:00", "A-Later-Day", -1),
			("B", "2099-01-01", "12:00:00", "A-Later-Time", -2),
			("C", "2099-01-01", "09:00:00", "Z-Same-Time", -3),
			("Z", "2099-01-01", "09:00:00", "A-First-Voucher", -4),
		]
		for ledger, date, time, voucher, qty in entries:
			frappe.get_doc({"doctype": "YRP Stock Ledger Entry", "name": prefix + ledger, "item": item, "lot": lot, "warehouse": ledger, "qty": qty, "valuation_rate": 2, "posting_date": date, "posting_time": time, "voucher_type": "SD YRP Lot Transfer", "voucher_no": voucher, "is_cancelled": 0}).db_insert()
			with self.subTest(latest_insert=ledger):
				rows = execute({"lot": lot, "start_date": "2099-01-01", "end_date": "2099-01-02", "item_group": group})[1]
				self.assertEqual(rows[0].voucher_no, voucher)
		rows = execute({"lot": lot, "start_date": "2099-01-01", "end_date": "2099-01-02", "item_group": group})[1]
		self.assertEqual(len(rows), 1)
		self.assertEqual((rows[0].quantity, rows[0].voucher_no, rows[0].stock_ledger_entry, rows[0].from_warehouse), (-10, "A-First-Voucher", prefix + "Z", "Z"))
