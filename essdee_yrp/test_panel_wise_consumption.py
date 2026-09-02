# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from types import SimpleNamespace
from unittest.mock import Mock, patch

from essdee_yrp.panel_wise_consumption import (
	_blank_matrix,
	_merge_cutting_rows,
	expand_panel_wise_matrix,
)
from essdee_yrp.ipd_validations import validate_stiching_fields
from essdee_yrp.ipd_ui import (
	DUPLICATE_IPD_SCALAR_FIELDS,
	get_approval_roles,
	revert_ipd_approval,
)


def _context():
	return {
		"primary_attribute": "Size",
		"panel_attribute": "Panel",
		"packing_attribute": "Colour",
		"primary_values": ["75 cm", "80 cm"],
		"panel_values": ["Back", "Front"],
		"packing_values": ["Black", "Maroon"],
		"source_packing_values": ["Black", "Maroon"],
		"panel_packing_values": {
			"Back": ["Black", "Maroon"],
			"Front": ["Black", "Maroon"],
		},
		"panel_colour_map": {
			"Back": {"Black": "Black", "Maroon": "Maroon"},
			"Front": {"Black": "Black", "Maroon": "Maroon"},
		},
	}


def _centre_panel_context():
	return {
		"primary_attribute": "Size",
		"panel_attribute": "Panel",
		"packing_attribute": "Colour",
		"primary_values": ["75 cm"],
		"panel_values": ["Center Panel"],
		"packing_values": ["Red", "A Mel", "G Mel", "Black"],
		"source_packing_values": ["Black", "Maroon", "Navy", "A Mel", "G Mel"],
		"panel_packing_values": {
			"Center Panel": ["Red", "A Mel", "G Mel", "Black"],
		},
		"panel_colour_map": {
			"Center Panel": {
				"Black": "Red",
				"Maroon": "A Mel",
				"Navy": "G Mel",
				"A Mel": "Red",
				"G Mel": "Black",
			},
		},
	}


class TestPanelWiseConsumption(IntegrationTestCase):
	def test_ipd_child_grids_expose_synced_values(self):
		expected_columns = {
			'SD YRP Stiching Item Detail': (
				"stiching_attribute_value",
				"set_item_attribute_value",
				"quantity",
				"category",
				"is_default",
			),
			'SD YRP Item Production Detail Packing Attribute Detail': (
				"attribute_value",
				"quantity",
			),
			'SD YRP Item Production Detail Packing Size Detail': (
				"attribute_value",
				"quantity",
			),
			'SD YRP Item Production Detail Packing Assortment Attribute': ("attribute",),
			'SD YRP Item Production Detail Cloth Detail': (
				"name1",
				"cloth",
				"required_gsm",
				"is_bom_item",
			),
			'SD YRP Item Production Detail Set Item Combination': (
				"index",
				"major_attribute_value",
				"set_item_attribute_value",
				"attribute_value",
			),
			'SD YRP Cutting Attribute Detail': ("attribute",),
		}
		for doctype, fieldnames in expected_columns.items():
			meta = frappe.get_meta(doctype)
			for fieldname in fieldnames:
				self.assertTrue(
					meta.get_field(fieldname).in_list_view,
					f"{doctype}.{fieldname} must be visible in the grid",
				)

	def test_system_manager_can_approve_ipd(self):
		self.assertIn("System Manager", get_approval_roles())

	def test_configured_approver_can_revert_ipd(self):
		doc = SimpleNamespace(
			name="TEST-IPD",
			approval_status="Approved",
			approved_by="approver@example.com",
			check_permission=Mock(),
		)
		with patch(
			"essdee_yrp.ipd_ui.get_approval_roles",
			return_value=["Merchandising Manager", "System Manager"],
		), patch.object(
			frappe,
			"get_roles",
			return_value=["Merchandising Manager"],
		), patch.object(
			frappe,
			"get_doc",
			return_value=doc,
		), patch.object(
			frappe.db,
			"set_value",
		) as set_value, patch.object(
			frappe,
			"clear_document_cache",
		):
			result = revert_ipd_approval("TEST-IPD")

		self.assertEqual(result, {"status": "success"})
		doc.check_permission.assert_called_once_with("write")
		set_value.assert_called_once_with(
			'YRP Item Production Detail',
			"TEST-IPD",
			{"approval_status": "Not Approved", "approved_by": None},
			update_modified=True,
		)

	def test_duplicate_keeps_panel_matrix_fields(self):
		self.assertIn(
			"enable_panel_wise_consumption_matrix",
			DUPLICATE_IPD_SCALAR_FIELDS,
		)
		self.assertIn(
			"panel_wise_consumption_matrix_json",
			DUPLICATE_IPD_SCALAR_FIELDS,
		)
		self.assertIn("cutting_items_json", DUPLICATE_IPD_SCALAR_FIELDS)

	def test_initial_garment_draft_can_save_before_stitching_tab_is_visible(self):
		doc = frappe._dict(
			stiching_process="Stitching",
			stiching_item_details=[],
			is_new=lambda: True,
		)
		validate_stiching_fields(doc)

		doc.is_new = lambda: False
		with self.assertRaises(frappe.ValidationError):
			validate_stiching_fields(doc)

	def test_legacy_rows_are_expanded_across_packing_values(self):
		context = _context()
		matrix = _blank_matrix(context)
		_merge_cutting_rows(
			matrix,
			{
				"items": [
					{
						"Panel": "Back",
						"Size": "75 cm",
						"Dia": "26 Dia",
						"Weight": 0.03,
					}
				]
			},
			context,
		)
		row = matrix["panels"][0]["rows"][0]
		self.assertEqual(row["values"]["Black"], {"dia": "26 Dia", "weight": 0.03})
		self.assertEqual(row["values"]["Maroon"], {"dia": "26 Dia", "weight": 0.03})

	def test_matrix_expands_to_existing_cutting_contract(self):
		context = _context()
		matrix = _blank_matrix(context)
		for panel_index, panel in enumerate(matrix["panels"]):
			for size_index, row in enumerate(panel["rows"]):
				base_dia = 26 + panel_index * 2 + size_index * 2
				row["values"] = {
					"Black": {
						"dia": f"{base_dia} Dia",
						"weight": 0.03 + panel_index * 0.01 + size_index * 0.001,
					},
					"Maroon": {
						"dia": f"{base_dia + 1} Dia",
						"weight": 0.031 + panel_index * 0.01 + size_index * 0.001,
					},
				}

		expanded = expand_panel_wise_matrix(matrix, context)
		self.assertEqual(
			expanded["attributes"], ["Size", "Panel", "Colour", "Dia", "Weight"]
		)
		self.assertEqual(len(expanded["items"]), 8)
		self.assertEqual(
			expanded["items"][0],
			{
				"Size": "75 cm",
				"Panel": "Back",
				"Colour": "Black",
				"Dia": "26 Dia",
				"Weight": 0.03,
			},
		)
		self.assertEqual(expanded["items"][1]["Dia"], "27 Dia")

	def test_panel_uses_only_actual_stitching_colours(self):
		context = _centre_panel_context()
		matrix = _blank_matrix(context)
		self.assertEqual(
			matrix["panels"][0]["packing_values"],
			["Red", "A Mel", "G Mel", "Black"],
		)
		self.assertEqual(
			list(matrix["panels"][0]["rows"][0]["values"]),
			["Red", "A Mel", "G Mel", "Black"],
		)

	def test_legacy_garment_colours_collapse_to_one_panel_colour(self):
		context = _centre_panel_context()
		matrix = _blank_matrix(context)
		_merge_cutting_rows(
			matrix,
			{
				"items": [
					{
						"Panel": "Center Panel",
						"Size": "75 cm",
						"Colour": "Black",
						"Dia": "15 Dia",
						"Weight": 0.01,
					},
					{
						"Panel": "Center Panel",
						"Size": "75 cm",
						"Colour": "A Mel",
						"Dia": "15 Dia",
						"Weight": 0.01,
					},
				]
			},
			context,
			source_schema=1,
		)
		self.assertEqual(
			matrix["panels"][0]["rows"][0]["values"]["Red"]["weight"],
			0.01,
		)

	def test_conflicting_legacy_rows_for_same_panel_colour_are_rejected(self):
		context = _centre_panel_context()
		matrix = _blank_matrix(context)
		with self.assertRaises(frappe.ValidationError):
			_merge_cutting_rows(
				matrix,
				{
					"items": [
						{
							"Panel": "Center Panel",
							"Size": "75 cm",
							"Colour": "Black",
							"Dia": "15 Dia",
							"Weight": 0.01,
						},
						{
							"Panel": "Center Panel",
							"Size": "75 cm",
							"Colour": "A Mel",
							"Dia": "15 Dia",
							"Weight": 0.02,
						},
					]
				},
				context,
				source_schema=1,
			)

	def test_incomplete_matrix_is_rejected(self):
		context = _context()
		matrix = _blank_matrix(context)
		with self.assertRaises(frappe.ValidationError):
			expand_panel_wise_matrix(matrix, context)
