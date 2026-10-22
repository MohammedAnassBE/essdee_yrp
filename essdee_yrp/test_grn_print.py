import re
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import print_helpers


def _sized_row(received_type, quantities, row_index="1"):
	sizes = ("S", "M", "L", "XL", "2XL")
	return {
		"name": "Pyjama",
		"row_index": row_index,
		"dimensions": {"lot": "L1", "received_type": received_type},
		"attributes": {"Stage": "Piece", "Colour": "Black"},
		"set_combination": '{"major_colour":"Black"}',
		"default_uom": "Pieces",
		"values": {
			size: {
				"received": quantities.get(size, 0),
				"ref_docname": f"{size}-{received_type}" if size in quantities else "",
			}
			for size in sizes
		},
	}


MIXED_SIZE_ROWS = (
	("Accepted", {"S": 58, "M": 187, "L": 130, "XL": 70, "2XL": 59}),
	("Adas", {"S": 7, "M": 8, "L": 13}),
	("Fusing Mistake", {"S": 1, "M": 1}),
)


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
		self.assertEqual(item["values"]["S"]["types"], {"Accepted": 0, "Rejected": 0})
		self.assertEqual(result[0]["attributes"], ["Stage", "Colour"])

	def get_mixed_structure(self, rows=MIXED_SIZE_ROWS):
		groups = [
			{
				"attributes": ["Stage", "Colour"],
				"primary_attribute": "Size",
				"primary_attribute_values": ["S", "M", "L", "XL", "2XL"],
				"lot": "L1",
				"items": [_sized_row(received_type, quantities) for received_type, quantities in rows],
			}
		]
		doc = frappe._dict(items=[], lot="L1")
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(print_helpers, "_group_items", return_value=groups),
		):
			return print_helpers.get_grn_structure("GRN-1")

	def test_every_size_holds_every_received_type_so_rows_stay_aligned(self):
		item = self.get_mixed_structure()[0]["items"][0]
		self.assertEqual(item["types"], ["Accepted", "Adas", "Fusing Mistake"])
		for cell in item["values"].values():
			self.assertEqual(list(cell["types"]), item["types"])
		self.assertEqual(item["values"]["XL"]["types"], {"Accepted": 70, "Adas": 0, "Fusing Mistake": 0})
		column_totals = {size: sum(cell["types"].values()) for size, cell in item["values"].items()}
		self.assertEqual(column_totals, {"S": 66, "M": 196, "L": 143, "XL": 70, "2XL": 59})

	def test_repeated_received_type_rows_add_up_instead_of_repeating_the_row(self):
		rows = (("Accepted", {"S": 5}), ("Adas", {"S": 1}), ("Accepted", {"M": 4}))
		item = self.get_mixed_structure(rows)[0]["items"][0]
		self.assertEqual(item["types"], ["Accepted", "Adas"])
		self.assertEqual(item["values"]["S"]["types"], {"Accepted": 5, "Adas": 1})
		self.assertEqual(item["values"]["M"]["types"], {"Accepted": 4, "Adas": 0})

	def test_received_types_follow_the_grn_row_order_like_mrp(self):
		items = [
			_sized_row("Accepted", {"S": 1}),
			_sized_row("Oil Mark", {"S": 1}),
			_sized_row("Adas", {"S": 1}),
		]
		positions = {("1", "Accepted"): 0, ("1", "Adas"): 1, ("1", "Oil Mark"): 2}
		merged = print_helpers.merge_received_types(items, positions)
		self.assertEqual(merged[0]["types"], ["Accepted", "Adas", "Oil Mark"])

	def test_work_order_grid_prints_a_cell_per_size_and_correct_column_totals(self):
		template = Path(
			frappe.get_app_path("essdee_yrp", "templates", "print_formats", "essdee_goods_received_note.html")
		)
		doc = frappe._dict(name="GRN-1", against="YRP Work Order", items=[], lot="L1", comments="")
		groups = self.get_mixed_structure()
		html = (
			frappe.get_jenv()
			.from_string(template.read_text())
			.render(doc=doc, frappe=frappe, get_grn_structure=lambda name: groups)
		)
		rows = []
		for row in re.findall(r"<tr>(.*?)</tr>", html, flags=re.S):
			cells = [
				re.sub(r"<[^>]+>|\s+", " ", cell).strip()
				for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)
			]
			if cells and cells[0] in ("1", "2", "3", "Total"):
				rows.append([re.sub(r"\s+", " ", cell) for cell in cells])
		self.assertEqual({len(row) for row in rows}, {10})
		self.assertEqual(
			rows[1],
			[
				"2",
				"Piece",
				"Black",
				"Adas",
				"7.0 Pieces",
				"8.0 Pieces",
				"13.0 Pieces",
				"0.0 Pieces",
				"0.0 Pieces",
				"28.0",
			],
		)
		self.assertEqual(rows[-1], ["Total", "", "", "", "66.0", "196.0", "143.0", "70.0", "59.0", "534.0"])

	def test_party_name_line_is_not_repeated_in_the_address(self):
		strip = print_helpers.strip_party_name_line
		self.assertEqual(
			strip("Sri Iyyappa Garments<br>\n4/144/36, First Floor", "Sri Iyyappa Garments"),
			"4/144/36, First Floor",
		)
		self.assertEqual(strip("Essdee Store,\nChengapalli", "Essdee Store"), "Chengapalli")
		self.assertEqual(
			strip("Banswara Syntex Limited Unit-BSL<br>Banswara", "Banswara Syntex Limited"),
			"Banswara Syntex Limited Unit-BSL<br>Banswara",
		)
		self.assertEqual(strip(None, "Party"), "")

	def test_grn_print_shows_each_party_name_once(self):
		doc = frappe.get_doc(
			{
				"doctype": "YRP Goods Received Note",
				"supplier_name": "Sri Iyyappa Garments",
				"supplier_address_display": "Sri Iyyappa Garments<br>4/144/36, First Floor",
				"delivery_location_name": "Essdee Ironing Unit - Tirupur",
				"delivery_address_display": "Essdee Ironing Unit - Tirupur<br>No.1/2, Ground Floor",
			}
		)
		with patch.object(print_helpers, "get_dc_grn_letter_head", return_value=""):
			print_helpers.prepare_print_document(doc)
		self.assertEqual(doc.supplier_address_display, "4/144/36, First Floor")
		self.assertEqual(doc.delivery_address_display, "No.1/2, Ground Floor")

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
