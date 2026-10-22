from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import print_helpers


def _grouped_row(received_type, quantity):
	return {
		"name": "Shirt",
		"dimensions": {"lot": "L1", "received_type": received_type},
		"attributes": {"Stage": "Cut", "Colour": "Black"},
		"set_combination": '{"major_colour":"Black"}',
		"values": {
			"S": {"received": 0, "ref_docname": ""},
			"M": {"received": quantity, "ref_docname": f"row-{received_type}"},
		},
	}


class TestGoodsReceivedNotePrint(IntegrationTestCase):
	def test_grn_structure_merges_received_types_like_mrp(self):
		groups = [
			{
				"attributes": ["Stage", "Colour"],
				"items": [_grouped_row("Accepted", 10), _grouped_row("Rejected", 2)],
			}
		]
		doc = frappe._dict(items=[], lot="L1")
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(print_helpers, "_group_items", return_value=groups),
		):
			result = print_helpers.get_grn_structure("GRN-1")

		item = result[0]["items"][0]
		self.assertEqual(len(result[0]["items"]), 1)
		self.assertEqual(item["types"], ["Accepted", "Rejected"])
		self.assertEqual(item["values"]["M"]["types"], {"Accepted": 10, "Rejected": 2})
		self.assertEqual(item["values"]["S"]["types"], {})
		self.assertEqual(result[0]["attributes"], ["Stage", "Colour"])

	def test_attribute_columns_sort_once_a_second_row_is_grouped(self):
		single = [{"attributes": ["Stage", "Colour"], "items": [{}]}]
		double = [{"attributes": ["Stage", "Panel", "Colour"], "items": [{}, {}]}]
		self.assertEqual(print_helpers.sort_grouped_attributes(single)[0]["attributes"], ["Stage", "Colour"])
		self.assertEqual(
			print_helpers.sort_grouped_attributes(double)[0]["attributes"], ["Colour", "Panel", "Stage"]
		)

	def test_print_keeps_stored_addresses_and_fills_missing_ones(self):
		doc = frappe.get_doc(
			{
				"doctype": "YRP Goods Received Note",
				"supplier": "SUP-1",
				"supplier_name": "Stored Supplier",
				"supplier_address_display": "Stored address",
				"delivery_location": "SUP-2",
				"delivery_address": "ADDR-2",
				"posting_date": "2026-09-21",
			}
		)
		with (
			patch.object(print_helpers, "get_supplier_address_display", return_value="Primary address"),
			patch.object(
				print_helpers, "_address_display", side_effect=lambda name: f"Linked {name}" if name else ""
			),
			patch.object(print_helpers, "_supplier_name", return_value="Delivery Unit"),
			patch.object(print_helpers, "get_dc_grn_letter_head", return_value="MRP Head"),
		):
			print_helpers.prepare_print_document(doc)

		self.assertEqual(doc.letter_head, "MRP Head")
		self.assertEqual(doc.supplier_name, "Stored Supplier")
		self.assertEqual(doc.supplier_address_display, "Stored address")
		self.assertEqual(doc.delivery_location_name, "Delivery Unit")
		self.assertEqual(doc.delivery_address_display, "Linked ADDR-2")
		self.assertEqual(str(doc.grn_date), "2026-09-21")

	def test_web_print_defaults_to_the_essdee_format_and_dc_grn_letter_head(self):
		from essdee_yrp.api import print as print_api

		name = frappe.db.get_value("YRP Goods Received Note", {"docstatus": 1}, "name")
		letter_head = frappe.db.get_value("Letter Head", {"disabled": 0}, "name")
		if not name or not letter_head:
			self.skipTest("Needs a submitted GRN and an enabled Letter Head")
		with patch.object(print_api, "get_dc_grn_letter_head", return_value=letter_head):
			options = print_api.get_print_options("YRP Goods Received Note", name)

		self.assertEqual(options["default_format"], "Essdee Goods Received Note")
		self.assertEqual(options["default_letter_head"], letter_head)
