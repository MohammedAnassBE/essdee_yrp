"""Hand-checked sales matrices and sewing balances."""

import importlib
import importlib.util
import json
import unittest
from pathlib import Path

import frappe


class TestRemainingDeskReports(unittest.TestCase):
	def sales(self):
		name = "essdee_yrp.sales.desk_page_reports"
		self.assertIsNotNone(importlib.util.find_spec(name), "Sales Desk report service is missing")
		return importlib.import_module(name)

	def test_size_matrix_keeps_secondary_groups_and_adds_quantities(self):
		service = self.sales()
		catalog = [
			{"name": "V1", "item": "Tee", "primary_attribute": "Size"},
			{"name": "V2", "item": "Tee", "primary_attribute": "Size"},
			{"name": "V3", "item": "Tee", "primary_attribute": "Size"},
		]
		attrs = {
			"V1": {"Size": "S", "Colour": "Red"},
			"V2": {"Size": "M", "Colour": "Red"},
			"V3": {"Size": "S", "Colour": "Blue"},
		}
		columns, rows = service.matrix(
			catalog, attrs, {"Tee": ["M", "S"]}, {"V1": 2, "V2": 3}, {"V1": 4}, show_stock=True
		)
		self.assertEqual(
			[c["label"] for c in columns], ["S.No", "Item Name", "Colour", "Type", "M", "S", "Total Boxes"]
		)
		self.assertEqual(
			[(r["secondary_0"], r["type"], r["size_0"], r["size_1"], r["total_boxes"]) for r in rows],
			[
				("Red", "Order", 3, 2, 5),
				("Red", "Stock", 0, 4, 4),
				("Blue", "Order", 0, 0, 0),
				("Blue", "Stock", 0, 0, 0),
			],
		)

	def test_no_primary_attribute_uses_quantity_and_hides_stock(self):
		columns, rows = self.sales().matrix([{"name": "Plain", "item": "Plain"}], {}, {}, {"Plain": 7})
		self.assertEqual(
			[c["label"] for c in columns], ["S.No", "Item Name", "Type", "Quantity", "Total Boxes"]
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual((rows[0]["quantity"], rows[0]["total_boxes"]), (7, 7))

	def test_box_conversion_preserves_fractional_demand_and_rounds_stock_up(self):
		convert = self.sales().boxes
		item = {"name": "V1", "item": "Tee", "stock_uom": "Nos", "pcs_per_box": 6}
		self.assertEqual(convert(7, item, {}, ceiling=True), 2)
		self.assertAlmostEqual(convert(9, item, {}), 1.5)
		with self.assertRaises(frappe.ValidationError):
			convert(1, {"name": "V2", "item": "Other", "stock_uom": "Kg"}, {})

	def test_date_bounds_are_required_and_inclusive(self):
		validate = self.sales().date_bounds
		with self.assertRaises(frappe.ValidationError):
			validate({})
		with self.assertRaises(frappe.ValidationError):
			validate({"start_date": "2026-09-02", "end_date": "2026-09-01"})
		start, end = validate({"start_date": "2026-09-01", "end_date": "2026-09-01"})
		self.assertEqual(start, end)
		with self.assertRaises(frappe.ValidationError):
			validate({"start_date": "2026-09-01", "end_date": frappe.utils.add_days(frappe.utils.today(), 1)})

	def test_io_pending_filters_before_numbering_and_keeps_negative_balance(self):
		name = "essdee_yrp.essdee_yrp.report.sd_yrp_io_input_pending.sd_yrp_io_input_pending"
		self.assertIsNotNone(importlib.util.find_spec(name.rsplit(".", 1)[0]), "IO Desk report is missing")
		module = importlib.import_module(name)
		rows = module.finish_rows(
			[
				{
					"sewing_line": "Line 1",
					"lot": "LOT-1",
					"item": "Tee",
					"input_qty": 80,
					"line_output_qty": 60,
				},
				{
					"sewing_line": "Line 2",
					"lot": "LOT-2",
					"item": "Vest",
					"input_qty": 5,
					"line_output_qty": 8,
				},
			],
			{"work_station": "Line 2", "search": "vest"},
		)
		self.assertEqual(
			rows,
			[
				{
					"serial_no": 1,
					"sewing_line": "Line 2",
					"lot": "LOT-2",
					"item": "Vest",
					"input_qty": 5.0,
					"line_output_qty": 8.0,
					"input_pending": -3.0,
				}
			],
		)

	def test_guest_cannot_run_sales_reports(self):
		service = self.sales()
		user = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				service.pending({})
			with self.assertRaises(frappe.PermissionError):
				service.packed({})
		finally:
			frappe.set_user(user)

	def insert(self, doctype, **values):
		name = values.pop("name", None) or "W5-" + frappe.generate_hash(length=10)
		doc = frappe.get_doc(dict(doctype=doctype, name=name, **values))
		doc.db_insert()
		return doc.name

	def fixture_item(self, disabled=0):
		name = "W5-" + frappe.generate_hash(length=10)
		item = self.insert(
			"Item",
			name=name,
			item_code=name,
			item_name="W5 test",
			stock_uom="Nos",
			has_variants=0,
			disabled=disabled,
		)
		self.insert("SD YRP FG Item Master", item=item, pcs_per_box=6, disabled=disabled)
		return item

	def test_item_user_permissions_limit_the_catalog_even_without_readable_orders(self):
		point = "worker5_item_scope"
		frappe.db.savepoint(point)
		previous_user = frappe.session.user
		user = "w5-" + frappe.generate_hash(length=10) + "@example.com"
		try:
			allowed, hidden = self.fixture_item(), self.fixture_item()
			self.insert("User", name=user, email=user, enabled=1, first_name="W5", user_type="System User")
			self.insert("Has Role", parent=user, parenttype="User", parentfield="roles", role="Sales User")
			self.insert(
				"User Permission", user=user, allow="Item", for_value=allowed, apply_to_all_doctypes=1
			)
			frappe.clear_cache(user=user)
			frappe.set_user(user)
			self.assertEqual(frappe.get_list("Item", pluck="name", limit_page_length=0), [allowed])
			rows = self.sales().pending({})[1]
			self.assertEqual({r["item"] for r in rows}, {allowed})
			self.assertNotIn(hidden, {r["item"] for r in rows})
		finally:
			frappe.set_user(previous_user)
			frappe.db.rollback(save_point=point)
			frappe.clear_cache(user=user)

	def test_native_pending_subtracts_delivery_and_cancellation_and_excludes_closed_orders(self):
		point = "worker5_pending"
		frappe.db.savepoint(point)
		try:
			item = self.fixture_item()
			for status, docstatus, qty, delivered, cancelled in [
				("Partially Delivered", 1, 12, 2, 1),
				("To Deliver", 1, 3, 0, 0),
				("Closed", 1, 99, 0, 0),
				("Draft", 0, 99, 0, 0),
			]:
				parent = self.insert("YRP Sales Order", status=status, docstatus=docstatus)
				self.insert(
					"YRP Sales Order Item",
					parent=parent,
					parenttype="YRP Sales Order",
					parentfield="items",
					item_code=item,
					qty=qty,
					delivered_qty=delivered,
					cancelled_qty=cancelled,
					conversion_factor=6,
					uom="Box",
				)
			rows = self.sales().pending({"search": item})[1]
			order = [r for r in rows if r["type"] == "Order"]
			self.assertEqual([(r["item"], r["total_boxes"]) for r in order], [(item, 12)])
		finally:
			frappe.db.rollback(save_point=point)

	def test_pending_stock_uses_only_positive_default_fg_lot_balances(self):
		point = "worker5_pending_stock"
		frappe.db.savepoint(point)
		try:
			item = self.fixture_item()
			fg_lot = frappe.db.get_single_value("YRP Stock Settings", "default_fg_lot")
			accepted = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
			rejected = frappe.db.get_single_value("YRP Stock Settings", "default_rejected_received_type")
			self.assertTrue(fg_lot and accepted and rejected)
			for warehouse, lot, received_type, actual, reserved in [
				("W5-A", fg_lot, accepted, 14, 2),
				("W5-A", "W5-WIP-LOT", accepted, 60, 0),
				("W5-A", fg_lot, rejected, 60, 0),
				("W5-B", fg_lot, accepted, 6, 36),
			]:
				self.insert(
					"YRP Bin",
					item_code=item,
					warehouse=warehouse,
					lot=lot,
					received_type=received_type,
					actual_qty=actual,
					reserved_qty=reserved,
				)
			rows = self.sales().pending({"search": item})[1]
			stock = [r for r in rows if r["type"] == "Stock"]
			self.assertEqual([(r["item"], r["total_boxes"]) for r in stock], [(item, 2)])
		finally:
			frappe.db.rollback(save_point=point)

	def packing_slip(self, item, posting_date, creation, qty, *, is_return=0, docstatus=1, uom="Box"):
		note = self.insert("YRP Delivery Note", docstatus=1, is_return=is_return)
		parent = self.insert(
			"YRP Packing Slip",
			delivery_note=note,
			docstatus=docstatus,
			posting_date=posting_date,
			creation=creation,
		)
		self.insert(
			"YRP Packing Slip Item",
			parent=parent,
			parenttype="YRP Packing Slip",
			parentfield="items",
			item_code=item,
			qty=qty,
			uom=uom,
		)

	def test_native_packed_filters_posting_date_and_excludes_return_cancelled_and_non_box(self):
		point = "worker5_packed"
		frappe.db.savepoint(point)
		try:
			item = self.fixture_item()
			self.packing_slip(item, "2026-09-01", "2026-09-05 10:20:00", 4)
			self.packing_slip(item, "2026-09-01", "2026-09-01 23:59:00", 3)
			self.packing_slip(item, "2026-09-02", "2026-09-01 10:20:00", 90)
			self.packing_slip(item, "2026-09-01", "2026-09-01 10:20:00", 80, is_return=1)
			self.packing_slip(item, "2026-09-01", "2026-09-01 10:20:00", 70, docstatus=2)
			self.packing_slip(item, "2026-09-01", "2026-09-01 10:20:00", 60, uom="Nos")
			rows = self.sales().packed(
				{"start_date": "2026-09-01", "end_date": "2026-09-01", "search": item}
			)[1]
			self.assertEqual([(r["item"], r["total_boxes"]) for r in rows], [(item, 7)])
		finally:
			frappe.db.rollback(save_point=point)

	def test_native_packed_keeps_items_disabled_after_packing(self):
		point = "worker5_packed_disabled"
		frappe.db.savepoint(point)
		try:
			item = self.fixture_item(disabled=1)
			self.packing_slip(item, "2026-09-01", "2026-09-01 10:20:00", 5)
			rows = self.sales().packed(
				{"start_date": "2026-09-01", "end_date": "2026-09-01", "search": item}
			)[1]
			self.assertEqual([(r["item"], r["total_boxes"]) for r in rows], [(item, 5)])
		finally:
			frappe.db.rollback(save_point=point)

	def test_owned_workspace_names_do_not_replace_other_apps_workspaces(self):
		def names(app):
			return {
				json.loads(path.read_text())["name"]
				for path in Path(frappe.get_app_path(app)).glob("**/workspace/*/*.json")
			}

		owned = {"Accounts", "Merch", "Purchase Reports", "Sewing", "Stock Reports"}
		self.assertLessEqual(owned, names("essdee_yrp"))
		for app in frappe.get_all_apps():
			if app != "essdee_yrp":
				with self.subTest(app=app):
					self.assertFalse(owned & names(app))
