from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from yrp.yrp.doctype.yrp_item.yrp_item import get_or_create_variant

from essdee_yrp.fabric_store.documents.purchase_order import _capability_candidates
from essdee_yrp.purchase_order_attribute_values import (
	get_purchase_order_attribute_rows,
	update_purchase_order_attribute_values,
)

COLOUR = "_Test PO Attr Colour"
SIZE = "_Test PO Attr Size"
ATTRIBUTE_VALUES = {COLOUR: ("Red", "Blue"), SIZE: ("S", "M")}
MODULE = "essdee_yrp.purchase_order_attribute_values"


def make_attributes():
	for attribute, values in ATTRIBUTE_VALUES.items():
		if not frappe.db.exists("Item Attribute", attribute):
			frappe.get_doc(
				{
					"doctype": "Item Attribute",
					"attribute_name": attribute,
					"item_attribute_values": [{"attribute_value": value, "abbr": value} for value in values],
				}
			).insert(ignore_permissions=True)


def make_template():
	return frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": f"_Test PO Attr {frappe.generate_hash(length=8)}",
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_purchase_item": 1,
			"has_variants": 1,
			"gst_hsn_code": frappe.db.get_value("GST HSN Code", {}, "name"),
			"attributes": [{"attribute": COLOUR}, {"attribute": SIZE}],
		}
	).insert(ignore_permissions=True)


def make_submitted_purchase_order(item_code):
	"""Raw insert so the test owns a submitted YRP order without supplier or pricing setup."""
	doc = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"name": f"_TEST-PO-ATTR-{frappe.generate_hash(length=8)}",
			"docstatus": 1,
			"is_yrp_managed": 1,
			"status": "To Receive",
			"open_status": "Open",
			"supplier": "_Test Supplier",
			"company": frappe.db.get_value("Company", {}, "name"),
			"transaction_date": "2026-11-06",
			"items": [
				{
					"item_code": item_code,
					"item_name": item_code,
					"qty": 12,
					"pending_quantity": 12,
					"uom": "Nos",
					"stock_uom": "Nos",
					"conversion_factor": 1,
					"rate": 10,
					"amount": 120,
					"warehouse": frappe.db.get_value("Warehouse", {"is_group": 0}, "name"),
					"row_index": "0",
				}
			],
		}
	)
	doc.db_insert()
	for row in doc.items:
		row.docstatus = 1
		row.db_insert()
	return doc


class TestPurchaseOrderAttributeValues(IntegrationTestCase):
	def setUp(self):
		make_attributes()
		self.template = make_template()
		self.red_small = get_or_create_variant(self.template.name, {COLOUR: "Red", SIZE: "S"})
		self.order = make_submitted_purchase_order(self.red_small)
		self.row = self.order.items[0]

	def change(self, attributes, **payload):
		row = {"name": self.row.name, "item_code": self.row.item_code, "qty": 12, "attributes": attributes}
		row.update(payload)
		return update_purchase_order_attribute_values(self.order.name, [row])

	def saved_row(self):
		return frappe.db.get_value(
			"Purchase Order Item",
			self.row.name,
			["item_code", "item_name", "qty", "pending_quantity", "rate", "amount"],
			as_dict=True,
		)

	def test_rows_list_current_and_allowed_values(self):
		rows = get_purchase_order_attribute_rows(self.order.name)["rows"]

		self.assertEqual(rows[0]["template"], self.template.name)
		self.assertEqual(rows[0]["qty"], 12)
		attributes = {entry["attribute"]: entry for entry in rows[0]["attributes"]}
		self.assertEqual(attributes[COLOUR]["value"], "Red")
		self.assertEqual(attributes[COLOUR]["options"], ["Red", "Blue"])
		self.assertTrue(attributes[SIZE]["editable"])

	def test_attribute_change_resolves_variant_and_keeps_quantity_and_price(self):
		result = self.change({COLOUR: "Blue"})

		blue_small = get_or_create_variant(self.template.name, {COLOUR: "Blue", SIZE: "S"})
		saved = self.saved_row()
		self.assertEqual(saved.item_code, blue_small)
		self.assertEqual(saved.item_name, frappe.db.get_value("Item", blue_small, "item_name"))
		self.assertEqual((saved.qty, saved.pending_quantity, saved.rate, saved.amount), (12, 12, 10, 120))
		self.assertEqual(result["changes"][0]["old_item_code"], self.red_small)
		comment = frappe.get_all(
			"Comment",
			filters={"reference_doctype": "Purchase Order", "reference_name": self.order.name},
			pluck="content",
		)
		self.assertTrue(any(self.red_small in text and blue_small in text for text in comment))

	def test_existing_variant_is_reused(self):
		blue_medium = get_or_create_variant(self.template.name, {COLOUR: "Blue", SIZE: "M"})

		self.change({COLOUR: "Blue", SIZE: "M"})

		self.assertEqual(self.saved_row().item_code, blue_medium)

	def test_yrp_order_leaves_erpnext_bins_untouched(self):
		warehouse = self.row.warehouse
		self.change({COLOUR: "Blue"})

		new_item = self.saved_row().item_code
		for item_code in (self.red_small, new_item):
			self.assertFalse(frappe.db.exists("Bin", {"item_code": item_code, "warehouse": warehouse}))

	def test_unchanged_values_record_nothing(self):
		result = self.change({COLOUR: "Red"})

		self.assertEqual(result["changes"], [])
		self.assertEqual(self.saved_row().item_code, self.red_small)

	def test_rejects_value_outside_allowed_list(self):
		with self.assertRaises(frappe.ValidationError):
			self.change({COLOUR: "Purple"})
		self.assertEqual(self.saved_row().item_code, self.red_small)

	def test_rejects_quantity_or_rate_change(self):
		with self.assertRaises(frappe.ValidationError):
			self.change({COLOUR: "Blue"}, qty=13)
		with self.assertRaises(frappe.ValidationError):
			self.change({COLOUR: "Blue"}, rate=11)
		self.assertEqual(self.saved_row().item_code, self.red_small)

	def test_rejects_stale_item_code(self):
		with self.assertRaises(frappe.ValidationError):
			self.change({COLOUR: "Blue"}, item_code="other-item")

	def test_requires_system_manager(self):
		with patch(f"{MODULE}.frappe.get_roles", return_value=["Purchase Manager"]):
			with self.assertRaises(frappe.PermissionError):
				get_purchase_order_attribute_rows(self.order.name)
			with self.assertRaises(frappe.PermissionError):
				self.change({COLOUR: "Blue"})

	def test_blocked_by_open_goods_received_note(self):
		grn = frappe.get_doc(
			{
				"doctype": "YRP Goods Received Note",
				"name": f"_TEST-GRN-{frappe.generate_hash(length=8)}",
				"against": "Purchase Order",
				"against_id": self.order.name,
				"docstatus": 0,
			}
		)
		grn.db_insert()

		with self.assertRaises(frappe.ValidationError):
			self.change({COLOUR: "Blue"})

		frappe.db.set_value("YRP Goods Received Note", grn.name, "docstatus", 2)
		self.change({COLOUR: "Blue"})
		self.assertNotEqual(self.saved_row().item_code, self.red_small)

	def test_rejects_draft_order(self):
		frappe.db.set_value("Purchase Order", self.order.name, "docstatus", 0)

		with self.assertRaises(frappe.ValidationError):
			self.change({COLOUR: "Blue"})

	def test_web_capability_follows_role_and_receipts(self):
		doc = frappe.get_doc("Purchase Order", self.order.name)
		approval = {"pending_approval": False, "live_request": None}
		grn = {"can_create": False}

		with patch(
			"essdee_yrp.fabric_store.documents.purchase_order.frappe.get_roles",
			return_value=["System Manager"],
		):
			self.assertTrue(_capability_candidates(doc, approval, grn)["update_attribute_values"]["eligible"])
		with patch(
			"essdee_yrp.fabric_store.documents.purchase_order.frappe.get_roles",
			return_value=["Purchase Manager"],
		):
			self.assertFalse(
				_capability_candidates(doc, approval, grn)["update_attribute_values"]["eligible"]
			)
