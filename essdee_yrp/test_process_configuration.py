from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.fabric_ipd import get_process_transform
from essdee_yrp.ipd_ui import regenerate_ipd_matrix


class TestProcessConversionConfiguration(IntegrationTestCase):
	def make_process(self, name, is_item_conversion=1, is_cloth_process=1):
		if frappe.db.exists("Process", name):
			frappe.delete_doc("Process", name, force=True)
		return frappe.get_doc({
			"doctype": "Process",
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

	def test_regenerate_matrix_saves_an_approved_cloth_ipd(self):
		doc = MagicMock()
		doc.name = "_Test Approved Cloth IPD"
		doc.modified = "2026-09-05 10:00:00"
		doc.approval_status = "Approved"
		doc.get.side_effect = lambda field: {"is_cloth_item": 1}.get(field)
		matrices = [
			frappe._dict(process_name="Knitting"),
			frappe._dict(process_name="Dyeing"),
		]
		with (
			patch("frappe.get_doc", return_value=doc),
			patch("frappe.get_all", return_value=matrices),
		):
			result = regenerate_ipd_matrix(doc.name, doc.modified)

		doc.check_permission.assert_called_once_with("write")
		doc.save.assert_called_once_with()
		self.assertEqual(result["matrix_count"], 2)
		self.assertEqual(result["process_counts"], {"Knitting": 1, "Dyeing": 1})
