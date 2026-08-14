import frappe
from frappe.tests.utils import FrappeTestCase


class TestProcessCostCustomization(FrappeTestCase):
	def test_field_attributes_match_production_api(self):
		meta = frappe.get_meta("Process Cost", cached=False)
		expected = {
			"approved_by": {"read_only": 0},
			"attribute": {"mandatory_depends_on": ""},
			"depends_on_attribute": {"read_only": 1, "default": "1"},
			"is_expired": {"read_only": 0},
			"item": {"fetch_from": "lot.item"},
		}

		for fieldname, attributes in expected.items():
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				for attribute, value in attributes.items():
					self.assertEqual(field.get(attribute), value)

	def test_essdee_property_setters_are_installed(self):
		expected = {
			("approved_by", "read_only"): "0",
			("attribute", "mandatory_depends_on"): "",
			("depends_on_attribute", "read_only"): "1",
			("depends_on_attribute", "default"): "1",
			("is_expired", "read_only"): "0",
			("item", "fetch_from"): "lot.item",
		}

		for (fieldname, property_name), value in expected.items():
			with self.subTest(fieldname=fieldname, property_name=property_name):
				self.assertEqual(
					frappe.db.get_value(
						"Property Setter",
						{
							"doc_type": "Process Cost",
							"field_name": fieldname,
							"property": property_name,
						},
						"value",
					),
					value,
				)
