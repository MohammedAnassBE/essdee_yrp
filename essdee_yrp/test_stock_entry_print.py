from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp import print_helpers


def _group(attributes, names, primary_attribute="Size"):
	return {
		"attributes": attributes,
		"primary_attribute": primary_attribute,
		"primary_attribute_values": ["S", "M"] if primary_attribute else [],
		"items": [{"name": name} for name in names],
	}


class TestStockEntryPrint(UnitTestCase):
	def test_sized_items_get_one_table_each_with_sorted_attributes(self):
		source = [_group(["Stage", "Colour"], ["Shirt", "Vest", "Shirt"])]
		with patch.object(print_helpers, "_group_items", return_value=source):
			groups = print_helpers.fetch_stock_entry_items([])
		self.assertEqual(
			[[item["name"] for item in group["items"]] for group in groups], [["Shirt", "Shirt"], ["Vest"]]
		)
		self.assertEqual(groups[0]["attributes"], ["Colour", "Stage"])

	def test_items_without_sizes_share_a_table_per_attribute_set(self):
		source = [_group(["Colour"], ["Box", "Tape"], primary_attribute=None)]
		with patch.object(print_helpers, "_group_items", return_value=source):
			groups = print_helpers.fetch_stock_entry_items([])
		self.assertEqual(len(groups), 1)
		self.assertEqual([item["name"] for item in groups[0]["items"]], ["Box", "Tape"])

	def test_single_row_keeps_item_attribute_order(self):
		source = [_group(["Stage", "Colour"], ["Shirt"])]
		with patch.object(print_helpers, "_group_items", return_value=source):
			groups = print_helpers.fetch_stock_entry_items([])
		self.assertEqual(groups[0]["attributes"], ["Stage", "Colour"])

	def test_locations_use_warehouse_supplier_on_own_side_and_transfer_supplier_otherwise(self):
		suppliers = {"WH-A": "SUP-A", "WH-B": "SUP-B"}
		with patch.object(frappe.db, "get_value", side_effect=lambda doctype, name, field: suppliers[name]):
			send = frappe._dict(purpose="Send to Warehouse", from_warehouse="WH-A", to_warehouse="WH-B")
			self.assertEqual(print_helpers.get_stock_entry_locations(send), ("SUP-A", "SUP-B"))
			issue = frappe._dict(purpose="Material Issue", from_warehouse="WH-A", transfer_supplier="JOB")
			self.assertEqual(print_helpers.get_stock_entry_locations(issue), ("SUP-A", "JOB"))
			receipt = frappe._dict(purpose="Material Receipt", to_warehouse="WH-B", transfer_supplier="JOB")
			self.assertEqual(print_helpers.get_stock_entry_locations(receipt), ("JOB", "SUP-B"))
			explicit = frappe._dict(purpose="Send to Warehouse", from_supplier="X", to_supplier="Y")
			self.assertEqual(print_helpers.get_stock_entry_locations(explicit), ("X", "Y"))

	def test_size_grid_prints_zero_for_sizes_without_quantity(self):
		from essdee_yrp.test_delivery_challan_print import print_format_data

		format_data = print_format_data("essdee_stock_transfer")
		self.assertIn('text-center\\">\\n' + " " * 48 + "0\\n", format_data)
		self.assertNotIn("---", format_data)
