"""Regression coverage for the migrated garment Work Order calculator."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.garment_work_order import (
	_validated_demands,
	calculate_garment_work_order,
	get_garment_work_order_context,
	regenerate_ipd_process_matrices,
)
from essdee_yrp.work_order_actions import get_wo_recut_defaults


class TestGarmentWorkOrder(IntegrationTestCase):
	"""Exercise the exact Machine Cutting record that exposed the missing button."""

	work_order = "YRP-WO-2026-00038"
	ipd = "CS-34820 Heavy Tee-1"

	def setUp(self):
		if not frappe.db.exists("YRP Work Order", self.work_order):
			self.skipTest(f"Migration oracle {self.work_order} is unavailable")
		if not frappe.db.exists("YRP Item Production Detail", self.ipd):
			self.skipTest(f"Migration oracle {self.ipd} is unavailable")

	def test_machine_cutting_context_exposes_every_lot_variant_and_missing_matrix(self):
		context = get_garment_work_order_context(self.work_order)

		self.assertEqual(context["process"], "Cutting")
		self.assertEqual(context["quantity_field"], "quantity")
		self.assertEqual(len(context["rows"]), 32)
		self.assertEqual(context["primary_attribute"], "Size")
		self.assertEqual(
			context["primary_values"],
			["45 cm", "50 cm", "55 cm", "60 cm", "65 cm", "70 cm", "75 cm", "80 cm"],
		)
		self.assertEqual(context["display_attributes"], ["Colour"])
		self.assertEqual(len(context["matrix_rows"]), 4)
		self.assertEqual(
			[row["attributes"]["Colour"] for row in context["matrix_rows"]],
			["Mint", "Black", "Olive", "Navy"],
		)
		self.assertTrue(
			all(list(row["values"]) == context["primary_values"] for row in context["matrix_rows"])
		)
		self.assertFalse(context["matrix_ready"])
		self.assertEqual(len(context["missing_matrix_variants"]), 8)
		self.assertTrue(all("-Navy-" in variant for variant in context["missing_matrix_variants"]))

	def test_regeneration_and_calculation_backfill_the_legacy_ipd(self):
		ipd_modified = frappe.db.get_value("YRP Item Production Detail", self.ipd, "modified")
		regenerated = regenerate_ipd_process_matrices(self.ipd)

		self.assertEqual(regenerated["count"], 24)
		self.assertEqual(regenerated["processes"], ["Cutting"])
		self.assertEqual(len(regenerated["skipped"]), 8)
		self.assertEqual(
			frappe.db.get_value("YRP Item Production Detail", self.ipd, "approval_status"),
			"Approved",
		)
		self.assertEqual(
			frappe.db.get_value("YRP Item Production Detail", self.ipd, "modified"),
			ipd_modified,
		)

		context = get_garment_work_order_context(self.work_order)
		missing = set(context["missing_matrix_variants"])
		selected = [
			{"source_row": row["source_row"], "qty": row["qty"]}
			for row in context["rows"]
			if row["item_variant"] not in missing
		]
		result = calculate_garment_work_order(self.work_order, selected)

		self.assertEqual(
			result,
			{"deliverables": 6, "receivables": 216, "calculated_items": 24},
		)
		work_order = frappe.get_doc("YRP Work Order", self.work_order)
		self.assertEqual(len(work_order.deliverables), 6)
		self.assertEqual(len(work_order.receivables), 216)
		self.assertEqual(len(work_order.work_order_calculated_items), 24)
		self.assertGreater(work_order.total_quantity, 0)
		self.assertTrue(work_order.completed_items_json)
		self.assertTrue(work_order.incompleted_items_json)

	def test_calculation_accepts_quantity_above_the_lot_quantity(self):
		work_order = frappe.get_doc("YRP Work Order", self.work_order)
		lot = frappe.get_doc("SD YRP Lot", work_order.lot)
		ipd = frappe.get_cached_doc("YRP Item Production Detail", work_order.production_detail)
		context = get_garment_work_order_context(self.work_order)
		source = context["rows"][0]
		excess_qty = source["available_qty"] + 450

		demands = _validated_demands(
			lot,
			ipd,
			[{"source_row": source["source_row"], "qty": excess_qty}],
		)

		self.assertEqual(len(demands), 1)
		self.assertEqual(demands[0]["qty"], excess_qty)

	def test_main_group_and_extra_process_branches(self):
		oracles = {
			# Main garment stages.
			"WO-2627-00666": ("Stitching", "cut_qty", 65, 16, 16),
			"WO-2627-00644": ("Packing", "cut_qty", 23, 15, 15),
			# IPD extra-process and Process.is_group paths.
			"WO-2627-00735": ("Printing", "cut_qty", 80, 80, 80),
			"WO-2627-00855": ("Ironing and Packing", "cut_qty", 22, 16, 16),
		}
		missing = [name for name in oracles if not frappe.db.exists("YRP Work Order", name)]
		if missing:
			self.skipTest(f"Migration Work Order oracles are unavailable: {', '.join(missing)}")

		for name, expected in oracles.items():
			with self.subTest(work_order=name):
				process, quantity_field, deliverables, receivables, calculated = expected
				context = get_garment_work_order_context(name)
				selected = [
					{"source_row": row["source_row"], "qty": row["qty"]}
					for row in context["rows"]
					if row["qty"] > 0
				]
				result = calculate_garment_work_order(name, selected)

				self.assertEqual(context["process"], process)
				self.assertEqual(context["quantity_field"], quantity_field)
				self.assertEqual(
					result,
					{
						"deliverables": deliverables,
						"receivables": receivables,
						"calculated_items": calculated,
					},
				)

	def test_new_recut_defaults_expose_zero_quantity_source_skus(self):
		name = "WO-2627-00847"
		if not frappe.db.exists(
			"YRP Work Order",
			{"name": name, "docstatus": 1, "open_status": "Open", "is_rework": 0},
		):
			self.skipTest(f"Open Work Order recut oracle {name} is unavailable")

		defaults = get_wo_recut_defaults(name)
		groups = defaults["item_details"]
		self.assertEqual(defaults["lot"], frappe.db.get_value("YRP Work Order", name, "lot"))
		self.assertTrue(groups)
		self.assertTrue(any(group.get("items") for group in groups))
		self.assertTrue(
			all(
				value.get("qty") == 0
				for group in groups
				for item in group.get("items") or []
				for value in (item.get("values") or {}).values()
			)
		)


class TestGarmentWorkOrderPlannedQuantity(TestCase):
	def test_every_calculation_resets_planned_quantity_to_the_selected_demand(self):
		module = "essdee_yrp.garment_work_order"
		work_order = frappe._dict(
			name="WO-1", docstatus=0, modified="m", lot="LOT-1", production_detail="IPD-1",
			process_name="Printing", planned_quantity=137, no_receivables=0, includes_packing=0,
		)
		work_order.check_permission = MagicMock()
		work_order.set = MagicMock()
		work_order.append = MagicMock()
		work_order.save = MagicMock()
		demands = [
			{"item_variant": "V-S", "qty": 300, "table_index": 0, "row_index": 0, "set_combination": {}},
			{"item_variant": "V-M", "qty": 337, "table_index": 0, "row_index": 1, "set_combination": {}},
		]
		rows = [{"qty": 1}]
		with (
			patch(f"{module}.frappe.get_doc", side_effect=[work_order, frappe._dict(name="LOT-1")]),
			patch(f"{module}.frappe.get_cached_doc"),
			patch(f"{module}._validate_garment_work_order"),
			patch(f"{module}._validated_demands", return_value=demands),
			patch(f"{module}.calculate_garment_process_rows", return_value=(rows, rows)),
			patch(f"{module}._processes", return_value=[]),
			patch(f"{module}.normalize_item_matrix_row_indexes", side_effect=lambda value: value),
			patch(f"{module}.frappe.db.get_single_value", return_value="Accepted"),
			patch(f"{module}._filter_child_fields", side_effect=lambda _doctype, value: value),
			patch(f"{module}._colour_summary", return_value=""),
			patch(f"{module}._update_cutting_tracking_json"),
		):
			calculate_garment_work_order("WO-1", [])

		self.assertEqual(work_order.planned_quantity, 637)
		work_order.save.assert_called_once()
