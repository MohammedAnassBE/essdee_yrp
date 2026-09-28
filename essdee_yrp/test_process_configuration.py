import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.fabric_ipd import get_process_transform


class TestProcessConversionConfiguration(IntegrationTestCase):
	def setUp(self):
		for attribute in ("Colour", "Dia"):
			if not frappe.db.exists("Item Attribute", attribute):
				frappe.get_doc({
					"doctype": "Item Attribute",
					"attribute_name": attribute,
				}).insert(ignore_permissions=True)

	def make_process(self, name, is_item_conversion=1, is_cloth_process=1):
		if frappe.db.exists("YRP Process", name):
			frappe.delete_doc("YRP Process", name, force=True)
		return frappe.get_doc({
			"doctype": "YRP Process",
			"process_name": name,
			"is_item_conversion": is_item_conversion,
			"is_cloth_process": is_cloth_process,
		})

	def test_conversion_transform_comes_from_process_attribute_contract(self):
		process = self.make_process("_Test Configured Conversion")
		process.append("conversion_input_attributes", {"attribute": "Colour"})
		process.append("conversion_output_attributes", {"attribute": "Colour"})
		process.append("conversion_output_attributes", {"attribute": "Dia"})
		process.insert()

		self.assertEqual(
			get_process_transform(process.name),
			{
				"shape": "conversion",
				"label": "Item Conversion",
				"is_item_conversion": True,
				"change_attributes": [],
				"input_attributes": ["Colour"],
				"output_attributes": ["Colour", "Dia"],
			},
		)

	def test_duplicate_conversion_attribute_is_rejected(self):
		process = self.make_process("_Test Duplicate Conversion Attribute")
		process.append("conversion_output_attributes", {"attribute": "Dia"})
		process.append("conversion_output_attributes", {"attribute": "Dia"})
		with self.assertRaisesRegex(frappe.ValidationError, "listed more than once"):
			process.insert()

	def test_non_conversion_process_cannot_keep_conversion_contract(self):
		process = self.make_process("_Test Invalid Conversion Contract", is_item_conversion=0)
		process.append("conversion_output_attributes", {"attribute": "Dia"})
		with self.assertRaisesRegex(frappe.ValidationError, "can only be configured"):
			process.insert()

	def test_non_cloth_item_conversion_keeps_base_process_behaviour(self):
		process = self.make_process(
			"_Test Base Non Cloth Conversion",
			is_item_conversion=1,
			is_cloth_process=0,
		)
		process.append("value_change_attributes", {"attribute": "Colour"})
		process.insert()

		self.assertEqual(process.value_change_attributes[0].attribute, "Colour")

	def test_non_cloth_process_cannot_use_cloth_conversion_contract(self):
		process = self.make_process(
			"_Test Non Cloth Conversion Contract",
			is_item_conversion=1,
			is_cloth_process=0,
		)
		process.append("conversion_output_attributes", {"attribute": "Dia"})
		with self.assertRaisesRegex(frappe.ValidationError, "Cloth Conversion Attributes"):
			process.insert()
