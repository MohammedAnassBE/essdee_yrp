from unittest.mock import patch

import frappe
from frappe.desk.query_report import run as run_desk_report
from frappe.tests import IntegrationTestCase
from yrp.web_reports.jobs import run_web_report
from yrp.web_reports.registry import clear_web_report_cache, get_web_reports


class TestDeskWebReports(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		clear_web_report_cache()

	def tearDown(self):
		clear_web_report_cache()

	def test_desk_reports_are_registered_with_matching_results(self):
		reports = get_web_reports()
		grn_date = str(frappe.db.get_value("YRP Goods Received Note", {"docstatus": 1}, "posting_date") or "2026-10-20")
		for key, name, filters in (
			("grn-report", "SD YRP GRN Report", {"from_date": grn_date, "to_date": grn_date}),
			("grn-summary", "SD YRP GRN Summary", {"from_date": grn_date, "to_date": grn_date, "status": "1", "only_show_stock_item": 0}),
			("purchase-order-log", "SD YRP Purchase Order Log", {}),
		):
			with self.subTest(key=key):
				self.assertIn(key, reports)
				self.assertEqual(reports[key].report, name)
				desk = run_desk_report(name, filters=filters, ignore_prepared_report=True, are_default_filters=True)
				web = run_web_report(key, filters)
				self.assertEqual(web["columns"], desk["columns"])
				self.assertEqual(web["result"], desk["result"])

	def test_grn_summary_status_restricts_mixed_document_states(self):
		from essdee_yrp.essdee_yrp.report.sd_yrp_grn_summary.sd_yrp_grn_summary import get_data

		names = {}
		for status in (0, 1, 2):
			name = f"_Test GRN Summary {status}-{frappe.generate_hash(length=8)}"
			# Isolate report rows without invoking stock transactions or submit/cancel hooks.
			frappe.get_doc({
				"doctype": "YRP Goods Received Note", "name": name, "docstatus": status,
				"against": "Purchase Order", "grn_date": "2099-01-15",
			}).db_insert()
			frappe.get_doc({
				"doctype": "YRP Goods Received Note Item", "name": frappe.generate_hash(),
				"parent": name, "parenttype": "YRP Goods Received Note", "parentfield": "items",
				"docstatus": status, "quantity": 10,
			}).db_insert()
			names[status] = name
		filters = {"from_date": "2099-01-15", "to_date": "2099-01-15"}
		fixture_names = set(names.values())
		for selection in (None, "", "0", "1", "2", 0):
			request = {**filters, "status": selection}
			expected = fixture_names if selection in (None, "") else {names[int(selection)]}
			for client, rows in (
				("backend", get_data(request)),
				("desk", run_desk_report("SD YRP GRN Summary", filters=request, ignore_prepared_report=True, are_default_filters=True)["result"]),
				("web", run_web_report("grn-summary", request)["result"]),
			):
				with self.subTest(client=client, status=selection):
					actual = {row["name"] for row in rows if row.get("name") in fixture_names}
					self.assertEqual(actual, expected)
					if selection not in (None, ""):
						self.assertTrue(all(int(row["status"]) == int(selection) for row in rows if row.get("name")))

	def test_finishing_inward_updates_is_registered(self):
		self.assertIn("finishing-inward-updates", get_web_reports())

	def test_lot_purchase_summary_registry_and_lot_results_match_desk(self):
		entry = get_web_reports().get("lot-purchase-summary")
		self.assertIsNotNone(entry)
		self.assertEqual(entry.kind, "frappe_report")
		self.assertEqual(entry.report, "SD YRP Lot Purchase Summary")
		self.assertEqual(entry.filters, {
			"lot": ("Link", "SD YRP Lot"), "item": ("Link", "Item"), "parent_item": ("Link", "Item"),
		})
		self.assertEqual(entry.link_sources, {"lot": "SD YRP Lot", "item": "Item", "parent_item": "Item"})
		lot = f"_Test Lot Purchase Summary-{frappe.generate_hash(length=8)}"
		item = f"{lot}-Item"
		# Isolate report inputs without invoking lot planning or stock transaction hooks.
		frappe.get_doc({"doctype": "Item", "name": item, "item_code": item, "item_name": item}).db_insert()
		frappe.get_doc({"doctype": "SD YRP Lot", "name": lot}).db_insert()
		frappe.get_doc({
			"doctype": "SD YRP Lot BOM", "name": frappe.generate_hash(),
			"parent": lot, "parenttype": "SD YRP Lot", "parentfield": "bom_summary",
			"item_name": item, "required_qty": 10,
		}).db_insert()
		filters = {"lot": lot}
		desk = run_desk_report(entry.report, filters=filters, ignore_prepared_report=True, are_default_filters=True)
		web = run_web_report(entry.key, filters)
		self.assertEqual(desk["result"], [{
			"lot": lot, "item": item, "parent_item": item,
			"required_qty": 10, "stock_qty": 0.0, "po_pending_qty": 0.0,
		}])
		self.assertEqual(web["columns"], desk["columns"])
		self.assertEqual(web["result"], desk["result"])
		self.assertTrue(all(row["lot"] == lot for row in web["result"]))

	def test_lot_purchase_summary_is_purchase_only_and_respects_department_access(self):
		from essdee_yrp.desk_web_reports import department_report_capabilities
		from essdee_yrp.fabric_store.web_workspace import get_capabilities

		self.assertTrue(get_capabilities()["sections"]["reports"]["reports"]["lot_purchase_summary"]["can_read"])
		with patch("essdee_yrp.desk_web_reports.can_run_desk_report", return_value=True):
			for department in ("cutting", "fabric-store", "cut-panel-store", "accessory-store", "sewing", "finishing", "merch", "sales", "pd", "hr", "accounts", "planning", "purchase"):
				with self.subTest(department=department):
					reports = department_report_capabilities(department, True)
					self.assertEqual("lot_purchase_summary" in reports, department == "purchase")
			self.assertEqual(department_report_capabilities("purchase", False), {})

	def test_lot_purchase_summary_enforces_desk_report_permissions(self):
		from essdee_yrp.desk_web_reports import department_report_capabilities

		for target in ("frappe.core.doctype.report.report.Report.is_permitted", "frappe.has_permission"):
			with self.subTest(permission=target), patch(target, return_value=False):
				self.assertNotIn("lot_purchase_summary", department_report_capabilities("purchase", True))
				with self.assertRaises(frappe.PermissionError):
					run_desk_report("SD YRP Lot Purchase Summary", filters={}, ignore_prepared_report=True)
				with self.assertRaises(frappe.PermissionError):
					run_web_report("lot-purchase-summary", {})

	def test_department_capabilities_follow_existing_report_access(self):
		from essdee_yrp.cutting.reports import get_report_permissions
		from essdee_yrp.cut_panel_store.web_workspace import get_capabilities as cut_panel
		from essdee_yrp.fabric_store.web_workspace import get_capabilities as fabric
		from essdee_yrp.finishing.web_workspace import get_capabilities as finishing
		from essdee_yrp.merch.web_workspace import get_capabilities as merch
		from essdee_yrp.sewing.web_workspace import get_capabilities as sewing

		self.assertTrue(get_report_permissions().get("grn-report"))
		for capabilities in (cut_panel(), fabric(), finishing()):
			self.assertTrue(capabilities["sections"]["reports"]["reports"].get("grn_report", {}).get("can_read"))
		for capabilities in (merch(), sewing()):
			self.assertTrue(capabilities["reports"].get("grn_report", {}).get("can_read"))

	def test_additions_cannot_grant_department_report_access(self):
		from essdee_yrp.desk_web_reports import department_report_capabilities

		with patch("essdee_yrp.desk_web_reports.can_run_desk_report", return_value=True):
			for department in ("cutting", "fabric-store", "cut-panel-store", "accessory-store", "sewing", "finishing", "merch", "purchase"):
				self.assertEqual(department_report_capabilities(department, False), {})
			for department in ("sales", "pd", "hr", "accounts", "planning"):
				self.assertEqual(department_report_capabilities(department, True), {})
		with patch("essdee_yrp.desk_web_reports.can_run_desk_report", return_value=False):
			self.assertEqual(department_report_capabilities("purchase", True), {})

	def test_fi_updates_uses_desk_rows_and_planner_role(self):
		from essdee_yrp.desk_web_reports import can_view_fi_updates, run_fi_updates
		from essdee_yrp.sewing.read_models import get_fi_updates_data

		supplier = frappe.db.get_value("SD YRP Sewing Plan", {}, "supplier") or frappe.db.get_value("Supplier", {}, "name")
		self.assertTrue(can_view_fi_updates())
		if supplier:
			self.assertEqual(run_web_report("finishing-inward-updates", {"supplier": supplier})["result"], get_fi_updates_data(supplier)["data"])
		with patch("essdee_yrp.desk_web_reports.frappe.get_roles", return_value=["Sewing User"]):
			self.assertFalse(can_view_fi_updates())
			with self.assertRaises(frappe.PermissionError):
				run_fi_updates({"supplier": supplier})
		with self.assertRaises(frappe.ValidationError):
			run_fi_updates({})

	def test_existing_department_endpoints_still_deny_report_sections(self):
		from essdee_yrp.cutting.reports import get_report_permissions
		from essdee_yrp.cut_panel_store.web_workspace import get_capabilities as cut_panel
		from essdee_yrp.fabric_store.web_workspace import get_capabilities as fabric
		from essdee_yrp.finishing.web_workspace import get_capabilities as finishing
		from essdee_yrp.merch.web_workspace import get_capabilities as merch
		from essdee_yrp.sewing.web_workspace import get_capabilities as sewing

		with (
			patch("essdee_yrp.desk_web_reports.frappe.has_permission", return_value=False),
			patch("essdee_yrp.desk_web_reports.can_run_desk_report", return_value=True),
		):
			self.assertNotIn("grn-report", get_report_permissions())
			for builder in (cut_panel, fabric, finishing, merch, sewing):
				with self.subTest(builder=builder.__module__):
					capabilities = builder()
					self.assertFalse(capabilities["sections"].get("reports", {}).get("can_read"))
					self.assertFalse(capabilities.get("reports", {}).get("grn_report", {}).get("can_read"))
