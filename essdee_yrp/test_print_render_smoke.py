from unittest import TestCase

import frappe

PRINTS = (
	("YRP Work Order", "Essdee Ironing Mistake Print", {"lot": ["is", "set"]}),
	("YRP Production Order", "Essdee Production Order", {}),
)


class TestPrintRenderSmoke(TestCase):
	"""Renders site print formats against existing docs without request params."""

	def test_prints_render_without_attribute_ids(self):
		frappe.form_dict.pop("pieces_per_box", None)
		for doctype, print_format, filters in PRINTS:
			name = frappe.db.get_value(doctype, {"docstatus": ["<", 2], **filters}, "name")
			if not name:
				self.skipTest(f"No {doctype} on this site")
			with self.subTest(print_format=print_format, name=name):
				html = frappe.get_print(doctype, name, print_format=print_format)
				self.assertTrue(html)
				self.assertNotIn("IAV-", html)

	def test_production_order_piece_row_follows_param(self):
		name = frappe.db.get_value("YRP Production Order", {"docstatus": ["<", 2]}, "name")
		if not name:
			self.skipTest("No YRP Production Order on this site")
		frappe.form_dict.pop("pieces_per_box", None)
		self.assertNotIn("Qty (Piece)", frappe.get_print("YRP Production Order", name, print_format="Essdee Production Order"))
		frappe.form_dict["pieces_per_box"] = "6"
		try:
			html = frappe.get_print("YRP Production Order", name, print_format="Essdee Production Order")
		finally:
			frappe.form_dict.pop("pieces_per_box", None)
		self.assertIn("Qty (Piece)", html)
