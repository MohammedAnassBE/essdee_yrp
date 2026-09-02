from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp import hooks
from essdee_yrp.process_cost import get_pc_attribute_values


class TestProcessCostCustomization(FrappeTestCase):
	def test_lot_attribute_endpoint_enforces_linked_document_permissions(self):
		with (
			patch(
				"essdee_yrp.process_cost.frappe.has_permission",
				side_effect=frappe.PermissionError,
			),
			patch.object(frappe.db, "get_value") as get_value,
			self.assertRaises(frappe.PermissionError),
		):
			get_pc_attribute_values(
				item="_Test Item",
				lot="_Test Lot",
				attribute="Colour",
				process_name="Printing",
			)
		get_value.assert_not_called()

	def test_lot_ipd_attribute_values_fill_the_cost_table(self):
		ipd = frappe._dict(
			stiching_attribute="Panel",
			cutting_process="Cutting",
			emblishment_details_json={},
			item_attributes=[
				frappe._dict(attribute="Colour", mapping="_Test Colour Mapping")
			],
		)
		mapping = frappe._dict(
			values=[
				frappe._dict(attribute_value="Navy"),
				frappe._dict(attribute_value="Black"),
			]
		)
		with (
			patch.object(frappe.db, "get_value", return_value="_Test IPD"),
			patch.object(frappe, "get_cached_doc", side_effect=[ipd, mapping]),
		):
			values = get_pc_attribute_values(
				lot="_Test Lot", attribute="Colour", process_name="Printing"
			)

		self.assertEqual(
			[row["attribute_value"] for row in values],
			["Navy", "Black"],
		)

	def test_generic_base_callback_is_neutralized_and_desk_adapter_is_loaded(self):
		self.assertIsNone(get_pc_attribute_values(item="ITEM", attribute="Colour"))
		self.assertEqual(hooks.doctype_js["Process Cost"], "public/js/process_cost.js")
		self.assertEqual(
			hooks.override_whitelisted_methods[
				"yrp.yrp.doctype.process_cost.process_cost.get_pc_attribute_values"
			],
			"essdee_yrp.process_cost.get_pc_attribute_values",
		)
		source = (
			Path(frappe.get_app_path("essdee_yrp")) / "public/js/process_cost.js"
		).read_text(encoding="utf-8")
		self.assertIn("lot: frm.doc.lot", source)
		self.assertIn("process_name: frm.doc.process_name", source)

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
