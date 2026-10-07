from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import fabric_ipd, garment_bom_matrix, item_validations, panel_wise_consumption

SETTINGS = "SD YRP IPD Settings"


class TestIPDAttributeUsage(IntegrationTestCase):
	"""Colour and Dia attribute names come from SD YRP IPD Settings, not literals."""

	def setUp(self):
		frappe.db.set_single_value(SETTINGS, "default_packing_attribute", "Shade")
		frappe.db.set_single_value(SETTINGS, "default_dia_attribute", "Width")

	def test_compacting_and_dyeing_shapes_use_configured_attributes(self):
		doc = frappe._dict(knitting_process=None, dyeing_process="DYE", compacting_process="COMPACT")
		shapes = {"DYE": ("swap", "Shade"), "COMPACT": ("swap", "Width")}
		with (
			patch.object(fabric_ipd, "get_process_shape", side_effect=shapes.get),
			patch.object(frappe, "msgprint") as msgprint,
		):
			fabric_ipd.validate_fabric_process_shapes(doc)

		msgprint.assert_not_called()

	def test_yarn_may_vary_by_the_configured_colour_attribute(self):
		with (
			patch.object(item_validations.frappe, "get_all", return_value=["Shade"]),
			patch.object(
				item_validations.frappe, "get_meta", return_value=MagicMock(has_field=lambda _field: False)
			),
		):
			item_validations._validate_yarn_rows([{"yarn_item": "_Test Yarn", "ratio": 100}])

	def test_yarn_varying_by_the_literal_colour_name_is_rejected(self):
		with (
			patch.object(item_validations.frappe, "get_all", return_value=["Colour"]),
			patch.object(
				item_validations.frappe, "get_meta", return_value=MagicMock(has_field=lambda _field: False)
			),
			self.assertRaises(frappe.ValidationError),
		):
			item_validations._validate_yarn_rows([{"yarn_item": "_Test Yarn", "ratio": 100}])

	def test_garment_cloth_rows_key_dia_by_the_configured_attribute(self):
		ipd = frappe._dict(
			item="SHIRT",
			packing_attribute="Shade",
			dependent_attribute=None,
			cloth_detail=[frappe._dict(name1="Body", cloth="CLOTH", is_bom_item=1)],
		)
		variant = frappe._dict(name="SHIRT-RED", variant_of="SHIRT", attributes=[])
		requirement = {"cloth_type": "Body", "colour": "Red", "dia": "20", "quantity": 1}
		with (
			patch.object(garment_bom_matrix.frappe, "get_cached_doc", return_value=variant),
			patch.object(garment_bom_matrix, "get_cloth_combination", return_value={}),
			patch.object(garment_bom_matrix, "get_stitching_combination", return_value={}),
			patch.object(garment_bom_matrix, "calculate_cloth", return_value=[requirement]),
			patch.object(garment_bom_matrix.frappe.db, "get_value", return_value="Kg"),
		):
			rows, _output = garment_bom_matrix._get_variant_cloth_rows(ipd, "SHIRT-RED")

		self.assertEqual(rows[0]["attrs"], {"Shade": "Red", "Width": "20"})

	def test_panel_wise_dia_values_come_from_the_configured_attribute(self):
		get_values = MagicMock(return_value=[])
		context = {"primary_attribute": "Size", "panel_attribute": "Panel", "packing_attribute": "Shade"}
		with (
			patch.object(
				panel_wise_consumption, "make_panel_wise_matrix", return_value=({"panels": []}, context)
			),
			patch.object(panel_wise_consumption, "expand_panel_wise_matrix", return_value={}),
			patch("yrp.yrp.doctype.yrp_item.yrp_item.get_global_attribute_values", get_values),
		):
			panel_wise_consumption.sync_panel_wise_consumption_matrix(
				MagicMock(get=lambda field: field == "enable_panel_wise_consumption_matrix")
			)

		get_values.assert_called_once_with("Width")
