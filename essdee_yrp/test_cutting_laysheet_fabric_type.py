from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet import sd_yrp_cutting_laysheet as module


def cloth_row(fabric_type, no_of_bits):
	return {
		"cloth_type": "Body",
		"colour": "Black",
		"dia": "30",
		"actual_dia": "30",
		"shade": "A",
		"weight": 10,
		"no_of_bits": no_of_bits,
		"fabric_type": fabric_type,
	}


def generate_bundles(fabric_type, no_of_bits, ratio=2, max_plys=72, maximum_allow=10):
	"""Run MRP's lay-to-bundle algorithm on one cloth row of a one-panel, one-size marker."""
	with patch.object(module, "get_detail_doc", return_value=SimpleNamespace(packing_attribute="Colour")):
		with patch.object(module, "get_dia_attribute", return_value="Dia"):
			details = module.save_item_details(
				{"cloth_items": [cloth_row(fabric_type, no_of_bits)]}, None, "Front", 0, cutting_order="CO-1"
			)
	laysheet = MagicMock(
		status="Completed",
		cutting_marker="CM-1",
		cutting_plan=None,
		cutting_order="CO-1",
		cutting_bulk_lay_sheet=None,
	)
	laysheet.cutting_laysheet_details = [
		SimpleNamespace(as_dict=lambda row=row: frappe._dict(row)) for row in details
	]
	laysheet.cutting_laysheet_manual_items = []
	marker = SimpleNamespace(
		version=None,
		is_manual_entry=0,
		cutting_marker_ratios=[SimpleNamespace(size="M", panel="Front", ratio=ratio)],
	)
	with (
		patch.object(
			frappe,
			"get_doc",
			side_effect=lambda doctype, name: marker if doctype == "SD YRP Cutting Marker" else laysheet,
		),
		patch.object(module, "get_parent_ref", return_value=("SD YRP Cutting Order", "CO-1")),
		patch.object(module, "has_cloth_tracking", return_value=False),
		patch.object(module, "update_cutting_plan"),
		patch.object(module, "update_cutting_order_dates"),
	):
		module.get_cut_sheet_data(
			"CLS-1",
			"CM-1",
			None,
			None,
			[{"part": "Front", "value": 1}],
			max_plys,
			maximum_allow,
			"2026-01-01",
		)
	return details[0], [row["quantity"] for row in laysheet.set.call_args.args[1]]


class TestCuttingLaySheetFabricType(TestCase):
	def test_tubler_doubles_effective_bits_and_bundle_quantities(self):
		detail, quantities = generate_bundles("Tubler", 36)
		self.assertEqual((detail["fabric_type"], detail["effective_bits"]), ("Tubler", 72))
		self.assertEqual(quantities, [72, 72])

	def test_open_width_keeps_bits_as_plies(self):
		detail, quantities = generate_bundles("Open Width", 36)
		self.assertEqual((detail["fabric_type"], detail["effective_bits"]), ("Open Width", 36))
		self.assertEqual(quantities, [72])
