import json

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import hooks


PROPERTY_SETTER = "Stock Reservation Entry-voucher_type-options"
ESSDEE_VOUCHER_TYPES = "\nWork Order\nStock Update\nPacking Slip"


class TestStockReservationEntryVoucherOptions(IntegrationTestCase):
	def test_base_yrp_uses_an_unopinionated_select(self):
		path = frappe.get_app_path(
			"yrp",
			"yrp_stock",
			"doctype",
			"stock_reservation_entry",
			"stock_reservation_entry.json",
		)
		with open(path) as source:
			meta = json.load(source)

		field = next(row for row in meta["fields"] if row.get("fieldname") == "voucher_type")
		self.assertEqual(field["fieldtype"], "Select")
		self.assertNotIn("options", field)

		voucher_no = next(row for row in meta["fields"] if row.get("fieldname") == "voucher_no")
		self.assertEqual(voucher_no["fieldtype"], "Data")
		self.assertNotIn("options", voucher_no)

	def test_essdee_supplies_packing_slip_through_a_scoped_fixture(self):
		path = frappe.get_app_path("essdee_yrp", "fixtures", "property_setter.json")
		with open(path) as source:
			fixture = json.load(source)

		setter = next(row for row in fixture if row.get("name") == PROPERTY_SETTER)
		self.assertEqual(setter["doc_type"], "Stock Reservation Entry")
		self.assertEqual(setter["field_name"], "voucher_type")
		self.assertEqual(setter["property"], "options")
		self.assertEqual(setter["value"], ESSDEE_VOUCHER_TYPES)

		property_setter_fixture = next(row for row in hooks.fixtures if row["dt"] == "Property Setter")
		allowed_names = property_setter_fixture["filters"][0][2]
		self.assertIn(PROPERTY_SETTER, allowed_names)

	def test_live_meta_combines_base_field_and_essdee_options(self):
		meta = frappe.get_meta("Stock Reservation Entry", cached=False)
		field = meta.get_field("voucher_type")
		self.assertEqual(field.fieldtype, "Select")
		self.assertEqual(field.options, ESSDEE_VOUCHER_TYPES)
		self.assertEqual(meta.get_field("voucher_no").fieldtype, "Data")
		self.assertFalse(meta.get_field("voucher_no").options)

		for voucher_type in ("Work Order", "Stock Update", "Packing Slip"):
			doc = frappe.new_doc("Stock Reservation Entry")
			doc.voucher_type = voucher_type
			doc._validate_selects()
