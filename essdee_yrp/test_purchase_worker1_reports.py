"""Purchase C1-C4 regressions without writing any site data.

Run the actual report SQL against small in-memory fixtures. These cases catch
using warehouse codes as names, missing supplier-only receipt locations, and
collapsing Ordered and Partially Delivered into ERP's shared To Receive status.
"""

import importlib
import re
import sqlite3
from unittest import TestCase
from unittest.mock import patch

import frappe


def report(slug):
	return importlib.import_module(f"essdee_yrp.essdee_yrp.report.sd_yrp_{slug}.sd_yrp_{slug}")


class TestPurchaseWorker1Reports(TestCase):
	def setUp(self):
		self.db = sqlite3.connect(":memory:")
		self.db.row_factory = sqlite3.Row
		self.addCleanup(self.db.close)
		self.db.executescript("""
			CREATE TABLE `tabYRP Stock Entry` (
				name TEXT, docstatus INT, purpose TEXT, against TEXT, against_id TEXT,
				from_warehouse TEXT, to_warehouse TEXT, transfer_supplier TEXT,
				posting_date TEXT, posting_time TEXT
			);
			CREATE TABLE `tabYRP Stock Entry Detail` (
				parent TEXT, docstatus INT, lot TEXT, item TEXT, qty REAL, received_type TEXT, remarks TEXT
			);
			CREATE TABLE `tabWarehouse` (name TEXT, warehouse_name TEXT, supplier TEXT);
			CREATE TABLE `tabSupplier` (name TEXT, supplier_name TEXT);
			CREATE TABLE `tabItem` (name TEXT, variant_of TEXT);
			CREATE TABLE `tabYRP Work Order` (name TEXT, process_name TEXT);
			INSERT INTO `tabSupplier` VALUES ('S-1', 'Cutting Unit'), ('S-2', 'Cut Panel Store');
			INSERT INTO `tabWarehouse` VALUES ('WH-1', 'WH-1', 'S-1'), ('WH-2', 'WH-2', 'S-2'),
				('WH-native', 'Native Warehouse', NULL);
			INSERT INTO `tabItem` VALUES ('Shirt-M', 'Shirt');
			INSERT INTO `tabYRP Work Order` VALUES ('WO-1', 'Cutting');
		""")
		self.sql_patch = patch.object(frappe.db, "sql", side_effect=self.sql)
		self.sql_patch.start()
		self.addCleanup(self.sql_patch.stop)
		# Metadata introspection must use the same isolated SQL fixture as report
		# execution, rather than querying MariaDB's information_schema via SQLite.
		columns_patch = patch.object(
			frappe.db,
			"has_column",
			side_effect=lambda dt, field: (
				field in {r[1] for r in self.db.execute(f"PRAGMA table_info(`tab{dt}`)")}
			),
		)
		columns_patch.start()
		self.addCleanup(columns_patch.stop)

	def sql(self, query, values=None, as_dict=False, **kwargs):
		query = re.sub(r"%\((\w+)\)s", r":\1", str(query))
		rows = self.db.execute(query, values or {}).fetchall()
		return [frappe._dict(dict(row)) for row in rows] if as_dict else [tuple(row) for row in rows]

	def stock_entry(self, purpose, source="WH-1", target="WH-2", supplier="S-2", against=""):
		self.db.execute(
			"INSERT INTO `tabYRP Stock Entry` VALUES (?,1,?,?,?,?,?,?,?,?)",
			("STE-1", purpose, against, "WO-1", source, target, supplier, "2026-09-01", "12:00:00"),
		)
		self.db.execute(
			"INSERT INTO `tabYRP Stock Entry Detail` VALUES ('STE-1',1,'L-1','Shirt-M',5,NULL,'Note')"
		)

	def test_jobwork_resolves_supplier_name_through_warehouse(self):
		self.stock_entry("Material Issue", against="YRP Work Order")
		rows = report("jobwork_issued_items").get_stock_entry_rows(frappe._dict(from_location="WH-1"))
		self.assertEqual(len(rows), 1)
		self.assertEqual((rows[0].from_location, rows[0].from_location_name), ("WH-1", "Cutting Unit"))
		self.assertEqual((rows[0].quantity, rows[0].received_type), (5, None))

	def test_non_jobwork_resolves_supplier_name_through_warehouse(self):
		self.stock_entry("Material Issue")
		rows = report("non_jobwork_issued_items").execute({})[1]
		self.assertEqual(len(rows), 1)
		self.assertEqual(
			(rows[0].from_location_name, rows[0].supplier_name), ("Cutting Unit", "Cut Panel Store")
		)

	def test_non_grn_resolves_both_warehouse_names(self):
		self.stock_entry("Send to Warehouse")
		rows = report("non_grn_received_items").execute({"received_location": "WH-2"})[1]
		self.assertEqual(len(rows), 1)
		self.assertEqual(
			(rows[0].from_location_name, rows[0].received_location_name), ("Cutting Unit", "Cut Panel Store")
		)

	def test_non_grn_resolves_transfer_supplier_without_a_source_warehouse(self):
		self.stock_entry("Material Receipt", source="", supplier="S-1")
		row = report("non_grn_received_items").execute({})[1][0]
		self.assertEqual((row.from_location, row.from_location_name), ("S-1", "Cutting Unit"))

	def test_supplier_codes_and_location_names_are_both_visible(self):
		self.stock_entry("Send to Warehouse")
		for slug in ("non_jobwork_issued_items", "non_grn_received_items"):
			with self.subTest(report=slug):
				columns, rows = report(slug).execute({})
				visible = {c["fieldname"] for c in columns}
				self.assertTrue({"from_supplier", "from_location_name"} <= visible)
				self.assertEqual((rows[0].from_supplier, rows[0].from_location_name), ("S-1", "Cutting Unit"))
				if slug == "non_grn_received_items":
					self.assertTrue({"received_supplier", "received_location_name", "supplier"} <= visible)
					self.assertEqual(
						(rows[0].received_supplier, rows[0].received_location_name),
						("S-2", "Cut Panel Store"),
					)
		self.db.execute("UPDATE `tabYRP Stock Entry` SET purpose='Material Issue', against='YRP Work Order'")
		jobwork = report("jobwork_issued_items")
		self.assertIn("from_supplier", {c["fieldname"] for c in jobwork.get_columns()})
		row = jobwork.get_stock_entry_rows(frappe._dict())[0]
		self.assertEqual((row.from_supplier, row.from_location_name), ("S-1", "Cutting Unit"))

	def test_supplier_only_receipt_exposes_supplier_code_and_display_name(self):
		self.stock_entry("Material Receipt", source="", supplier="S-1")
		row = report("non_grn_received_items").execute({})[1][0]
		self.assertEqual((row.from_supplier, row.from_location_name), ("S-1", "Cutting Unit"))

	def test_native_warehouse_keeps_its_display_name(self):
		# A coincidentally named Supplier is not the warehouse's linked owner.
		self.db.execute("INSERT INTO `tabSupplier` VALUES ('WH-native', 'Unrelated Supplier')")
		self.stock_entry("Send to Warehouse", source="WH-native", target="WH-native")
		for slug in ("non_jobwork_issued_items", "non_grn_received_items"):
			with self.subTest(report=slug):
				row = report(slug).execute({})[1][0]
				self.assertEqual(row.from_location_name, "Native Warehouse")
				if slug == "non_grn_received_items":
					self.assertEqual(row.received_location_name, "Native Warehouse")

	def purchase_order_tables(self):
		self.db.executescript("""
			CREATE TABLE `tabPurchase Order` (
				name TEXT, creation TEXT, modified TEXT, modified_by TEXT, supplier TEXT, supplier_name TEXT,
				transaction_date TEXT, comments TEXT, status TEXT, yrp_fulfillment_status TEXT,
				open_status TEXT, is_yrp_managed INT, docstatus INT
			);
			CREATE TABLE `tabPurchase Order Item` (
				parent TEXT, item_code TEXT, qty REAL, pending_quantity REAL, cancelled_quantity REAL,
				uom TEXT, rate REAL, tax TEXT, discount_percentage REAL, delivery_location TEXT,
				schedule_date TEXT, lot TEXT, comments TEXT
			);
		""")
		cases = [
			("PO-ordered", "To Receive", "Ordered", "Open", 1),
			("PO-partial", "To Receive", "Partially Received", "Open", 1),
			("PO-delivered", "Completed", "Received", "Open", 1),
			("PO-closed", "Closed", "Closed", "Close", 1),
			("PO-approval", "Pending Approval", "Draft", "Open", 1),
			("PO-native", "To Receive", "Draft", "Open", 0),
			("PO-native-delivered", "Completed", "Draft", "Open", 0),
			("PO-native-cancelled", "Cancelled", "Draft", "Open", 0),
		]
		for name, status, fulfillment, open_status, managed in cases:
			self.db.execute(
				"INSERT INTO `tabPurchase Order` VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",
				(
					name,
					"2026-09-01",
					"2026-09-02",
					"Administrator",
					"S-1",
					"Cutting Unit",
					"2026-09-01",
					"PO note",
					status,
					fulfillment,
					open_status,
					managed,
				),
			)
			self.db.execute(
				"INSERT INTO `tabPurchase Order Item` VALUES (?,'Shirt-M',10,6,1,'Nos',2,'5',0,'S-2','2026-09-03','L-1','Item note')",
				(name,),
			)

	def test_purchase_status_filters_preserve_distinct_fulfillment_states(self):
		self.purchase_order_tables()
		for status, expected in [
			("Ordered", [("PO-ordered", "Ordered"), ("PO-native", "Ordered")]),
			("Partially Delivered", [("PO-partial", "Partially Delivered")]),
			("Delivered", [("PO-delivered", "Delivered"), ("PO-native-delivered", "Delivered")]),
			("Cancelled", [("PO-native-cancelled", "Cancelled")]),
			("Pending Approval", [("PO-approval", "Pending Approval")]),
		]:
			with self.subTest(status=status):
				rows = report("purchase_order_itemwise").execute({"status": status, "open_status": "Open"})[1]
				self.assertEqual([(row.name, row.status) for row in rows], expected)
				self.assertTrue(
					all((row.qty, row.delivered_qty, row.pending_qty) == (10, 3, 6) for row in rows)
				)

	def test_purchase_closed_filter_accepts_mrp_and_erp_labels(self):
		self.purchase_order_tables()
		for open_status in ("Closed", "Close"):
			with self.subTest(open_status=open_status):
				rows = report("purchase_order_itemwise").execute({"open_status": open_status})[1]
				self.assertEqual([(row.name, row.status) for row in rows], [("PO-closed", "Closed")])

	def test_purchase_uom_keeps_erp_values_even_with_legacy_blank_provenance(self):
		self.purchase_order_tables()
		self.db.execute("ALTER TABLE `tabPurchase Order Item` ADD custom_mrp_report_uom TEXT")
		self.db.execute("ALTER TABLE `tabPurchase Order Item` ADD modified TEXT DEFAULT '2026-09-02'")
		self.db.execute("ALTER TABLE `tabPurchase Order Item` ADD secondary_uom TEXT")
		self.db.execute("UPDATE `tabPurchase Order Item` SET secondary_uom='Boxes'")
		self.db.execute(
			"UPDATE `tabPurchase Order Item` SET custom_mrp_report_uom=? WHERE parent=?",
			('{"source_uom":null,"stored_uom":"Nos","modified":"2026-09-02"}', "PO-ordered"),
		)
		self.db.execute(
			"UPDATE `tabPurchase Order Item` SET custom_mrp_report_uom=? WHERE parent=?",
			('{"source_uom":"","stored_uom":"Nos","modified":"2026-09-02"}', "PO-partial"),
		)
		with patch.object(frappe.db, "has_column", return_value=True):
			columns, rows = report("purchase_order_itemwise").execute({})
		by_name = {row.name: row for row in rows}
		self.assertEqual(by_name["PO-ordered"].uom, "Nos")
		self.assertEqual(by_name["PO-partial"].uom, "Nos")
		self.assertEqual(by_name["PO-native"].uom, "Nos")
		self.assertEqual(by_name["PO-delivered"].uom, "Nos")
		self.assertTrue(all(not any(key.startswith("_mrp_report_uom") for key in row) for row in rows))
		self.assertEqual([c["fieldname"] for c in columns].count("uom"), 1)

	def test_purchase_changed_operational_uom_overrides_migration_provenance(self):
		self.purchase_order_tables()
		self.db.execute("ALTER TABLE `tabPurchase Order Item` ADD custom_mrp_report_uom TEXT")
		self.db.execute("ALTER TABLE `tabPurchase Order Item` ADD modified TEXT DEFAULT '2026-09-02'")
		self.db.execute(
			"UPDATE `tabPurchase Order Item` SET uom=?, custom_mrp_report_uom=? WHERE parent=?",
			("Kg", '{"source_uom":null,"stored_uom":"Nos","modified":"2026-09-02"}', "PO-ordered"),
		)
		with patch.object(frappe.db, "has_column", return_value=True):
			rows = report("purchase_order_itemwise").execute({"purchase_order": "PO-ordered"})[1]
		self.assertEqual(rows[0].uom, "Kg")
		# A saved UOM change retires the marker permanently, even if changed back.
		self.db.execute(
			"UPDATE `tabPurchase Order Item` SET uom='Nos', custom_mrp_report_uom=NULL, modified='2026-10-01'"
		)
		with patch.object(frappe.db, "has_column", return_value=True):
			rows = report("purchase_order_itemwise").execute({"purchase_order": "PO-ordered"})[1]
		self.assertEqual(rows[0].uom, "Nos")

	def test_purchase_parent_only_save_keeps_erp_uom(self):
		self.purchase_order_tables()
		self.db.execute("ALTER TABLE `tabPurchase Order Item` ADD custom_mrp_report_uom TEXT")
		self.db.execute("ALTER TABLE `tabPurchase Order Item` ADD modified TEXT DEFAULT '2026-09-02'")
		self.db.execute(
			"UPDATE `tabPurchase Order Item` SET custom_mrp_report_uom=? WHERE parent='PO-ordered'",
			('{"source_uom":null,"stored_uom":"Nos","modified":"2026-09-02"}',),
		)
		# Frappe stamps all children when a parent-only field changes.
		self.db.execute("UPDATE `tabPurchase Order` SET comments='Unrelated edit', modified='2026-10-20'")
		self.db.execute("UPDATE `tabPurchase Order Item` SET modified='2026-10-20'")
		rows = report("purchase_order_itemwise").execute({"purchase_order": "PO-ordered"})[1]
		self.assertEqual(rows[0].uom, "Nos")
