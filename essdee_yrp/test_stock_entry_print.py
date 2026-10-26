import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from essdee_yrp import print_helpers


def _group(attributes, names, primary_attribute="Size", dependent_attribute=None, row_indexes=None):
	return {
		"attributes": attributes,
		"primary_attribute": primary_attribute,
		"dependent_attribute": dependent_attribute,
		"primary_attribute_values": ["S", "M"] if primary_attribute else [],
		"items": [
			{"name": name, "row_index": row_index}
			for name, row_index in zip(names, row_indexes or [""] * len(names), strict=True)
		],
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

	def test_items_with_a_dependent_attribute_get_one_table_per_row_like_mrp(self):
		source = [_group(["Stage", "Colour"], ["Vest", "Vest", "Vest"], dependent_attribute="Stage")]
		with patch.object(print_helpers, "_group_items", return_value=source):
			groups = print_helpers.fetch_stock_entry_items([])
		self.assertEqual([len(group["items"]) for group in groups], [1, 1, 1])
		self.assertTrue(all(group["attributes"] == ["Colour", "Stage"] for group in groups))

	def test_rows_follow_row_index_text_order_like_mrp(self):
		source = [
			_group(["Colour"], ["Box", "Tape", "Cone"], primary_attribute=None, row_indexes=["2", "10", "1"])
		]
		with patch.object(print_helpers, "_group_items", return_value=source):
			groups = print_helpers.fetch_stock_entry_items([])
		self.assertEqual([item["row_index"] for item in groups[0]["items"]], ["1", "10", "2"])

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


def render_stock_transfer(groups):
	from essdee_yrp.test_delivery_challan_print import print_format_data

	html = next(
		field["options"]
		for field in json.loads(print_format_data("essdee_stock_transfer"))
		if field.get("fieldname") == "_custom_html"
	)
	doc = frappe.new_doc("YRP Stock Entry", purpose="Send to Warehouse", posting_date="2026-10-26")
	doc.docstatus = 1
	return (
		frappe.get_jenv()
		.from_string(html)
		.render(doc=doc, frappe=frappe, fetch_stock_entry_items=lambda items: groups)
	)


class TestStockEntryRowRemarksPrint(IntegrationTestCase):
	def test_each_item_row_prints_its_remarks_once(self):
		sized = {
			"name": "Shirt",
			"lot": "L1",
			"attributes": {"Colour": "Red"},
			"values": {"S": {"qty": 2}, "M": {"qty": 3}},
			"remarks": "Wash &amp; press\nfirst",
		}
		plain = {
			"name": "Tape",
			"lot": "L1",
			"attributes": {"Colour": "White"},
			"values": {"default": {"qty": 4, "rate": 0}},
			"remarks": "Loose roll",
		}
		groups = [
			{
				"attributes": ["Colour"],
				"primary_attribute": "Size",
				"primary_attribute_values": ["S", "M"],
				"items": [sized],
			},
			{"attributes": ["Colour"], "primary_attribute": "", "items": [plain]},
		]
		html = render_stock_transfer(groups)
		self.assertEqual(html.count(">Remarks</th>"), 2)
		self.assertEqual(html.count("Wash &amp; press\nfirst"), 1)
		self.assertNotIn("&amp;amp;", html)
		self.assertEqual(html.count("Loose roll"), 1)


class TestStockEntryPrintAddresses(IntegrationTestCase):
	def test_to_supplier_with_only_a_non_primary_address_prints_that_address(self):
		group = frappe.get_all("Supplier Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
		supplier = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"STE Print {frappe.generate_hash(length=8)}",
				"supplier_group": group,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": supplier.supplier_name,
				"address_type": "Billing",
				"address_line1": "12 Mill Road",
				"city": "Tiruppur",
				"state": "Tamil Nadu",
				"country": "India",
				"is_primary_address": 0,
				"links": [{"link_doctype": "Supplier", "link_name": supplier.name}],
			}
		).insert(ignore_permissions=True)
		doc = frappe.new_doc("YRP Stock Entry", purpose="Send to Warehouse", to_supplier=supplier.name)
		print_helpers.prepare_stock_entry_print(doc)
		self.assertEqual(doc.to_location_name, supplier.supplier_name)
		self.assertIn("12 Mill Road", doc.to_address_details)
		self.assertIn("Tiruppur", doc.to_address_details)
