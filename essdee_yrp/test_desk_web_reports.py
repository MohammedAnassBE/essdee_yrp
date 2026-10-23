from unittest.mock import patch

import frappe
from frappe.desk.query_report import run as run_desk_report
from frappe.tests import IntegrationTestCase
from yrp.web_reports.jobs import run_web_report
from yrp.web_reports.registry import clear_web_report_cache, get_web_reports

STOCK_REPORTS = (
	("stock-entry-report", "SD YRP Stock Entry Report"),
	("stock-reconciliation-report", "SD YRP Stock Reconciliation Report"),
	("stock-update-report", "SD YRP Stock Update Report"),
	("item-conversion-report", "SD YRP Item Conversion Report"),
)
STOCK_DEPARTMENTS = (
	"cutting", "fabric-store", "cut-panel-store", "accessory-store", "sewing", "finishing", "merch", "purchase",
)
ISSUED_REPORTS = (
	("dc-report", "SD YRP DC Report"),
	("jobwork-issued-items", "SD YRP Jobwork Issued Items"),
)
PLACEMENT_REPORTS = (
	("jobwork-issued-items", "SD YRP Jobwork Issued Items"),
	("non-jobwork-issued-items", "SD YRP Non Jobwork Issued Items"),
	("non-grn-received-items", "SD YRP Non-GRN Received Items"),
	("lot-wise-stock-ageing", "SD YRP Lot Wise Stock Ageing"),
	("stock-ageing", "YRP Stock Ageing"),
)
QUARTER = {"days": 92, "from_field": "from_date", "to_field": "to_date", "when": {}, "missing_bound": "background"}
BACKGROUND = {
	"stock-entry-report": QUARTER,
	"stock-reconciliation-report": {**QUARTER, "days": 366},
	"dc-report": QUARTER,
	"jobwork-issued-items": QUARTER,
	"non-jobwork-issued-items": QUARTER,
	"non-grn-received-items": QUARTER,
	"lot-wise-stock-ageing": "always",
	"stock-ageing": "always",
}
PLACEMENT_DEPARTMENTS = ("purchase", "accessory-store", "fabric-store", "accounts")
CONVERSION_DEPARTMENTS = ("purchase", "accessory-store", "fabric-store", "cutting")


class TestDeskWebReports(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		clear_web_report_cache()

	def tearDown(self):
		clear_web_report_cache()

	def test_stock_report_registry_filters_and_rows_match_desk(self):
		reports = get_web_reports()
		common = {"from_date": "Date", "to_date": "Date", "lot": ("Link", "SD YRP Lot")}
		items = {"item": ("Link", "Item"), "item_variant": ("Link", "Item")}
		schemas = (
			{**common, **items, "from_warehouse": ("Link", "Supplier"), "to_warehouse": ("Link", "Supplier")},
			{**common, **items, "supplier": ("Link", "Supplier")},
			{**common, **items, "warehouse": ("Link", "Supplier")},
			{**common, "from_item": ("Link", "Item"), "to_item": ("Link", "Item")},
		)
		for (key, name), schema in zip(STOCK_REPORTS, schemas):
			with self.subTest(report=name):
				self.assertIn(key, reports)
				entry = reports[key]
				self.assertEqual((entry.kind, entry.report, entry.background), ("frappe_report", name, BACKGROUND.get(key, "never")))
				self.assertEqual(entry.filters, schema)
				filters, voucher_field, voucher = self.make_stock_report_fixture(key)
				desk = run_desk_report(name, filters=filters, ignore_prepared_report=True, are_default_filters=True)
				web = run_web_report(key, filters)
				self.assertEqual(len(desk["result"]), 1)
				self.assertEqual(desk["result"][0][voucher_field], voucher)
				self.assertEqual(web["columns"], desk["columns"])
				self.assertEqual(web["result"], desk["result"])

	def test_stock_report_location_filters_match_only_linked_supplier(self):
		other_supplier = f"_Test Other Report Supplier-{frappe.generate_hash(length=8)}"
		frappe.get_doc({"doctype": "Supplier", "name": other_supplier, "supplier_name": other_supplier}).db_insert()
		for (key, name), location_fields in zip(STOCK_REPORTS, (
			("from_warehouse", "to_warehouse"), ("supplier",), ("warehouse",),
		)):
			filters, voucher_field, voucher = self.make_stock_report_fixture(key)
			base_filters = {field: value for field, value in filters.items() if field not in location_fields}
			for field in location_fields:
				for supplier, expected in ((filters[field], [voucher]), (other_supplier, [])):
					request = {**base_filters, field: supplier}
					with self.subTest(report=name, field=field, supplier=supplier):
						desk = run_desk_report(name, filters=request, ignore_prepared_report=True, are_default_filters=True)
						web = run_web_report(key, request)
						self.assertEqual([row[voucher_field] for row in desk["result"]], expected)
						self.assertEqual(web["result"], desk["result"])

	def make_stock_report_fixture(self, key):
		"""Insert isolated report inputs without transaction or ledger hooks."""
		prefix = f"_Test Web Stock-{frappe.generate_hash(length=8)}"
		item, lot, supplier, warehouse = (f"{prefix}-{suffix}" for suffix in ("Item", "Lot", "Supplier", "Warehouse"))
		for doctype, name, values in (
			("Item", item, {"item_code": item, "item_name": item, "is_stock_item": 1}),
			("SD YRP Lot", lot, {}),
			("Supplier", supplier, {"supplier_name": supplier}),
			("Warehouse", warehouse, {"warehouse_name": warehouse, "supplier": supplier}),
		):
			frappe.get_doc({"doctype": doctype, "name": name, **values}).db_insert()
		self.assertNotEqual(warehouse, supplier)
		self.assertEqual(frappe.db.get_value("Warehouse", warehouse, "supplier"), supplier)
		parent_doctype, child_doctype, parentfield, voucher_field, parent_values, child_values = {
			"stock-entry-report": (
				"YRP Stock Entry", "YRP Stock Entry Detail", "items", "stock_entry",
				{"from_warehouse": warehouse, "to_warehouse": warehouse}, {"item": item, "qty": 5},
			),
			"stock-reconciliation-report": (
				"YRP Stock Reconciliation", "YRP Stock Reconciliation Item", "items", "stock_reconciliation",
				{"default_warehouse": warehouse}, {"item": item, "qty": 5},
			),
			"stock-update-report": (
				"YRP Stock Update", "YRP Stock Update Detail", "stock_update_details", "stock_update",
				{"warehouse": warehouse, "update_type": "Add"}, {"item_variant": item, "available_stock": 2, "update_diff_qty": 5},
			),
			"item-conversion-report": (
				"SD YRP Item Conversion", "SD YRP Item Conversion Detail", "from_items", "item_conversion",
				{"warehouse": supplier, "from_item": item, "to_item": item}, {"item": item, "qty": 5},
			),
		}[key]
		frappe.get_doc({
			"doctype": parent_doctype, "name": prefix, "docstatus": 1,
			"posting_date": "2099-02-15", "posting_time": "12:00:00", **parent_values,
		}).db_insert()
		detail = frappe.get_doc({
			"doctype": child_doctype, "name": f"{prefix}-Detail", "docstatus": 1,
			"parent": prefix, "parenttype": parent_doctype, "parentfield": parentfield,
			"lot": lot, **child_values,
		})
		detail.db_insert()
		if key == "stock-reconciliation-report":
			frappe.get_doc({
				"doctype": "YRP Stock Ledger Entry", "name": f"{prefix}-Ledger", "docstatus": 1,
				"voucher_type": parent_doctype, "voucher_no": prefix, "voucher_detail_no": detail.name,
				"item": item, "warehouse": warehouse, "lot": lot,
				"posting_date": "2099-02-15", "posting_datetime": "2099-02-15 12:00:00",
				"qty_after_transaction": 5, "valuation_rate": 2,
			}).db_insert()
		filters = {"from_date": "2099-02-15", "to_date": "2099-02-15", "lot": lot}
		if key == "item-conversion-report":
			filters.update(from_item=item, to_item=item)
		else:
			filters.update(item=item, item_variant=item)
			for field in ("from_warehouse", "to_warehouse", "warehouse"):
				if field in parent_values:
					filters[field] = supplier
			if key == "stock-reconciliation-report":
				filters["supplier"] = supplier
		return filters, voucher_field, prefix

	def test_stock_report_department_visibility_and_existing_access(self):
		from essdee_yrp.desk_web_reports import department_report_capabilities

		with patch("essdee_yrp.desk_web_reports.can_run_desk_report", return_value=True):
			for department in (*STOCK_DEPARTMENTS, "sales", "pd", "hr", "accounts", "planning"):
				reports = department_report_capabilities(department, True)
				for key, _name in STOCK_REPORTS:
					allowed = CONVERSION_DEPARTMENTS if key == "item-conversion-report" else STOCK_DEPARTMENTS
					with self.subTest(department=department, report=key):
						self.assertEqual(key.replace("-", "_") in reports, department in allowed)
				self.assertEqual(department_report_capabilities(department, False), {})

	def test_stock_reports_enforce_desk_permissions_and_menu_read_access(self):
		from essdee_yrp.desk_web_reports import department_report_capabilities

		original_has_permission = frappe.has_permission
		for key, name in STOCK_REPORTS:
			for denied in ("role", "read", "report"):
				target = "frappe.core.doctype.report.report.Report.is_permitted" if denied == "role" else "frappe.has_permission"
				kwargs = {"return_value": False} if denied == "role" else {
					"side_effect": lambda doctype, ptype="read", **kw: False if ptype == denied else original_has_permission(doctype, ptype=ptype, **kw),
				}
				with self.subTest(report=name, denied=denied), patch(target, **kwargs):
					self.assertNotIn(key.replace("-", "_"), department_report_capabilities("purchase", True))
					# Desk execution checks role and report permission; menus also require read.
					if denied == "read":
						continue
					with self.assertRaises(frappe.PermissionError):
						run_desk_report(name, filters={}, ignore_prepared_report=True)
					with self.assertRaises(frappe.PermissionError):
						run_web_report(key, {})

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
		from essdee_yrp.cut_panel_store.web_workspace import get_capabilities as cut_panel
		from essdee_yrp.cutting.reports import get_report_permissions
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
			for department in ("sales", "pd", "hr", "planning"):
				self.assertEqual(department_report_capabilities(department, True), {})
		with patch("essdee_yrp.desk_web_reports.can_run_desk_report", return_value=False):
			self.assertEqual(department_report_capabilities("purchase", True), {})

	def test_fi_updates_uses_desk_rows_and_planner_role(self):
		from essdee_yrp.desk_web_reports import can_view_fi_updates, run_fi_updates
		from essdee_yrp.sewing.fi_dates import get_fi_updates_data

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
		from essdee_yrp.cut_panel_store.web_workspace import get_capabilities as cut_panel
		from essdee_yrp.cutting.reports import get_report_permissions
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

	def test_issued_reports_registry_filters_and_rows_match_desk(self):
		prefix = f"_Test Web Issued-{frappe.generate_hash(length=8)}"
		item, lot, origin, supplier = (f"{prefix}-{suffix}" for suffix in ("Item", "Lot", "Origin", "Supplier"))
		for doctype, name, values in (
			("Item", item, {"item_code": item, "item_name": item}),
			("SD YRP Lot", lot, {}),
			("Supplier", origin, {"supplier_name": origin}),
			("Supplier", supplier, {"supplier_name": supplier}),
		):
			frappe.get_doc({"doctype": doctype, "name": name, **values}).db_insert()
		frappe.get_doc({
			"doctype": "YRP Delivery Challan", "name": prefix, "docstatus": 1,
			"posting_date": "2099-03-15", "posting_time": "12:00:00", "lot": lot,
			"from_location": origin, "supplier": supplier,
		}).db_insert()
		frappe.get_doc({
			"doctype": "YRP Delivery Challan Item", "name": f"{prefix}-Detail", "docstatus": 1,
			"parent": prefix, "parenttype": "YRP Delivery Challan", "parentfield": "items",
			"lot": lot, "item_variant": item, "delivered_quantity": 7,
		}).db_insert()
		common = {
			"from_date": "Date", "to_date": "Date", "lot": ("Link", "SD YRP Lot"),
			"from_location": ("Link", "Supplier"), "supplier": ("Link", "Supplier"),
		}
		for key, name in ISSUED_REPORTS:
			with self.subTest(report=name):
				entry = get_web_reports().get(key)
				self.assertIsNotNone(entry)
				self.assertEqual((entry.kind, entry.report, entry.background), ("frappe_report", name, BACKGROUND.get(key, "never")))
				schema = {**common, **({"item": ("Link", "Item")} if key == "jobwork-issued-items" else {})}
				self.assertEqual(entry.filters, schema)
				self.assertEqual(entry.link_sources["supplier"], "Supplier")
				self.assertEqual(entry.link_sources["from_location" if key == "dc-report" else "from_supplier"], "Supplier")
				filters = {"from_date": "2099-03-15", "to_date": "2099-03-15", "lot": lot, "from_location": origin, "supplier": supplier}
				if key == "jobwork-issued-items":
					filters["item"] = item
				desk = run_desk_report(name, filters=filters, ignore_prepared_report=True, are_default_filters=True)
				web = run_web_report(key, filters)
				voucher_field = "delivery_challan" if key == "dc-report" else "source_name"
				self.assertEqual([row[voucher_field] for row in desk["result"] if isinstance(row, dict) and row.get(voucher_field)], [prefix])
				self.assertEqual(web["columns"], desk["columns"])
				self.assertEqual(web["result"], desk["result"])

	def test_issued_reports_department_visibility_and_access(self):
		from essdee_yrp.desk_web_reports import department_report_capabilities

		with patch("essdee_yrp.desk_web_reports.can_run_desk_report", return_value=True):
			for department in (*STOCK_DEPARTMENTS, "accounts", "sales", "pd", "hr", "planning"):
				reports = department_report_capabilities(department, True)
				self.assertEqual("dc_report" in reports, department in STOCK_DEPARTMENTS)
				self.assertEqual("jobwork_issued_items" in reports, department in ("purchase", "accessory-store", "fabric-store", "accounts"))
				self.assertEqual(department_report_capabilities(department, False), {})
			self.assertEqual(set(department_report_capabilities("accounts", True)), {key.replace("-", "_") for key, _ in PLACEMENT_REPORTS} | {"purchase_order_itemwise", "lot_consumption_report"})

	def test_accounts_issued_report_keeps_existing_report_area_gate(self):
		from essdee_yrp.accounts.web_capabilities import get_capabilities

		with patch("essdee_yrp.desk_web_reports.can_run_desk_report", return_value=True):
			with patch("essdee_yrp.accounts.web_capabilities.can_view_accounts_reports", return_value=True):
				reports = get_capabilities()["reports"]
				for key, _name in PLACEMENT_REPORTS:
					self.assertTrue(reports.get(key.replace("-", "_"), {}).get("can_read"))
			with patch("essdee_yrp.accounts.web_capabilities.can_view_accounts_reports", return_value=False):
				capabilities = get_capabilities()
				self.assertEqual(capabilities["reports"], {})
				self.assertFalse(capabilities["sections"]["reports"]["can_read"])

	def test_issued_reports_keep_desk_permission_gates(self):
		from essdee_yrp.desk_web_reports import department_report_capabilities

		original_has_permission = frappe.has_permission
		for key, name in ISSUED_REPORTS:
			for denied in ("role", "read", "report"):
				target = "frappe.core.doctype.report.report.Report.is_permitted" if denied == "role" else "frappe.has_permission"
				kwargs = {"return_value": False} if denied == "role" else {
					"side_effect": lambda doctype, ptype="read", **kw: False if ptype == denied else original_has_permission(doctype, ptype=ptype, **kw),
				}
				with self.subTest(report=name, denied=denied), patch(target, **kwargs):
					for department in ("purchase", "accounts"):
						self.assertNotIn(key.replace("-", "_"), department_report_capabilities(department, True))
					if denied == "read":
						continue
					with self.assertRaises(frappe.PermissionError):
						run_desk_report(name, filters={}, ignore_prepared_report=True)
					with self.assertRaises(frappe.PermissionError):
						run_web_report(key, {})


	def test_additional_placements_respect_department_and_desk_gates(self):
		from essdee_yrp.desk_web_reports import department_report_capabilities

		with patch("essdee_yrp.desk_web_reports.can_run_desk_report", return_value=True):
			for department in (*STOCK_DEPARTMENTS, "accounts", "sales", "pd", "hr", "planning", "unknown"):
				for key, name in PLACEMENT_REPORTS:
					with self.subTest(report=name, department=department):
						self.assertEqual(key.replace("-", "_") in department_report_capabilities(department, True), department in PLACEMENT_DEPARTMENTS)
				self.assertEqual(department_report_capabilities(department, False), {})
		for key, name in PLACEMENT_REPORTS:
			for denied in ("role", "read", "report"):
				original = frappe.has_permission
				target = "frappe.core.doctype.report.report.Report.is_permitted" if denied == "role" else "frappe.has_permission"
				kwargs = {"return_value": False} if denied == "role" else {"side_effect": lambda doctype, ptype="read", **kw: False if ptype == denied else original(doctype, ptype=ptype, **kw)}
				with self.subTest(report=name, denied=denied), patch(target, **kwargs):
					for department in PLACEMENT_DEPARTMENTS:
						self.assertNotIn(key.replace("-", "_"), department_report_capabilities(department, True))
					if denied != "read":
						with self.assertRaises(frappe.PermissionError):
							run_web_report(key, {})

	def test_additional_placements_schemas_and_nonempty_desk_equality(self):
		prefix = f"_Test Placement-{frappe.generate_hash(length=8)}"
		item, lot, supplier, warehouse, other = (f"{prefix}-{suffix}" for suffix in ("Item", "Lot", "Supplier", "Warehouse", "Other"))
		for doctype, name, values in (
			("Item", item, {"item_code": item, "item_name": item, "is_stock_item": 1}),
			("SD YRP Lot", lot, {}),
			("Supplier", supplier, {"supplier_name": supplier}),
			("Supplier", other, {"supplier_name": other}),
			("Warehouse", warehouse, {"warehouse_name": warehouse, "supplier": supplier}),
		):
			frappe.get_doc({"doctype": doctype, "name": name, **values}).db_insert()
		self.assertNotEqual(warehouse, supplier)
		for suffix, purpose, against in (("Jobwork", "Material Issue", "YRP Work Order"), ("Issue", "Material Issue", ""), ("Receipt", "Material Receipt", "")):
			frappe.get_doc({
				"doctype": "YRP Stock Entry", "name": f"{prefix}-{suffix}", "docstatus": 1,
				"posting_date": "2099-04-15", "posting_time": "12:00:00", "purpose": purpose,
				"against": against, "from_warehouse": warehouse, "to_warehouse": warehouse, "transfer_supplier": supplier,
			}).db_insert()
			frappe.get_doc({
				"doctype": "YRP Stock Entry Detail", "name": f"{prefix}-{suffix}-Detail", "docstatus": 1,
				"parent": f"{prefix}-{suffix}", "parenttype": "YRP Stock Entry", "parentfield": "items",
				"lot": lot, "item": item, "qty": 7,
			}).db_insert()
		frappe.get_doc({
			"doctype": "YRP Stock Ledger Entry", "name": f"{prefix}-Ledger", "docstatus": 1,
			"item": item, "warehouse": warehouse, "lot": lot, "is_cancelled": 0,
			"posting_date": "2099-04-15", "posting_time": "12:00:00", "posting_datetime": "2099-04-15 12:00:00",
			"qty": 7, "qty_after_transaction": 7, "rate": 2, "valuation_rate": 2,
			"voucher_type": "YRP Stock Entry", "voucher_no": f"{prefix}-Receipt",
		}).db_insert()
		issued = {"from_date": "Date", "to_date": "Date", "lot": ("Link", "SD YRP Lot"), "supplier": ("Link", "Supplier"), "item": ("Link", "Item")}
		ageing = {"to_date": "Date", "warehouse": ("Link", "Supplier"), "item": ("Link", "Item"), "parent_item": ("Link", "Item"), "range1": "Int", "range2": "Int", "range3": "Int", "show_warehouse_wise_stock": "Check"}
		for key, name in PLACEMENT_REPORTS:
			is_ageing = "ageing" in key
			location = "warehouse" if is_ageing else "received_location" if key == "non-grn-received-items" else "from_location"
			if is_ageing:
				schema = {**ageing, **({"lot": ("Link", "SD YRP Lot"), "brand": ("Link", "Brand")} if key == "lot-wise-stock-ageing" else {})}
				filters = {"to_date": "2099-04-15", "item": item, "parent_item": item, "range1": 12, "range2": 24, "range3": 48, "show_warehouse_wise_stock": 1}
				if key == "lot-wise-stock-ageing":
					filters["lot"] = lot
			else:
				schema = {**issued, location: ("Link", "Supplier"), **({"purpose": "Select"} if key != "jobwork-issued-items" else {})}
				filters = {"from_date": "2099-04-15", "to_date": "2099-04-15", "lot": lot, "supplier": supplier, "item": item}
				if key != "jobwork-issued-items":
					filters["purpose"] = "Material Receipt" if key == "non-grn-received-items" else "Material Issue"
			with self.subTest(report=name):
				entry = get_web_reports().get(key)
				self.assertIsNotNone(entry)
				self.assertEqual((entry.kind, entry.report, entry.background), ("frappe_report", name, BACKGROUND.get(key, "never")))
				self.assertEqual(entry.filters, schema)
				for location_value, expect_rows in ((supplier, True), (other, False)):
					request = {**filters, location: location_value}
					desk = run_desk_report(name, filters=request, ignore_prepared_report=True, are_default_filters=True)
					with patch("yrp.web_reports.jobs.needs_background", return_value=False):
						web = run_web_report(key, request)
					rows = [row for row in desk["result"] if isinstance(row, dict) and not row.get("is_total_row")]
					self.assertEqual(bool(rows), expect_rows)
					if expect_rows:
						self.assertEqual(rows[0]["qty" if is_ageing else "quantity"], 7)
					self.assertEqual(web["columns"], desk["columns"])
					self.assertEqual(web["result"], desk["result"])
				legacy = run_desk_report(name, filters={**filters, location: warehouse}, ignore_prepared_report=True, are_default_filters=True)
				selected = run_desk_report(name, filters={**filters, location: supplier}, ignore_prepared_report=True, are_default_filters=True)
				self.assertEqual(legacy["result"], selected["result"])
