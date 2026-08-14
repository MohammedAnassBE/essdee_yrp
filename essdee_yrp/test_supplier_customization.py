import frappe
from frappe.tests.utils import FrappeTestCase


class TestSupplierCustomization(FrappeTestCase):
	def test_production_api_fields_and_sections_are_installed(self):
		meta = frappe.get_meta("Supplier", cached=False)
		expected = {
			"user_mapping_section": ("Section Break", None),
			"supplier_users": ("Table", "Supplier User"),
			"section_break_10": ("Section Break", None),
			"price_html": ("HTML Editor", None),
		}

		for fieldname, definition in expected.items():
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertEqual((field.fieldtype, field.options), definition)

		terms = meta.get_field("terms_and_condition")
		self.assertEqual((terms.fieldtype, terms.options), ("Link", "Terms and Condition"))
		self.assertFalse(
			frappe.db.exists(
				"Custom Field",
				{"dt": "Supplier", "fieldname": "terms_and_condition"},
			)
		)

		field_order = [field.fieldname for field in meta.fields]
		self.assertLess(field_order.index("user_mapping_section"), field_order.index("supplier_users"))
		self.assertLess(field_order.index("supplier_users"), field_order.index("section_break_10"))
		self.assertLess(field_order.index("section_break_10"), field_order.index("price_html"))
