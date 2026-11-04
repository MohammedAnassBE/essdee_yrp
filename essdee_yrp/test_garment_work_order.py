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


class TestStitchingClothAccessoryDeliverables(IntegrationTestCase):
	def test_stitching_delivers_cloth_accessories_like_production_api(self):
		name = "WO-2526-00720"
		if not frappe.db.exists(
			"YRP Work Order", {"name": name, "docstatus": 0, "process_name": "Stitching"}
		):
			self.skipTest(f"Draft Stitching Work Order oracle {name} is unavailable")
		legacy = {
			row.item_variant: row.qty
			for row in frappe.get_all(
				"YRP Work Order Deliverables",
				filters={"parent": name, "uom": "Kg"},
				fields=["item_variant", "qty"],
			)
		}
		self.assertTrue(legacy)
		context = get_garment_work_order_context(name)
		calculate_garment_work_order(
			name,
			[
				{"source_row": row["source_row"], "qty": row["qty"]}
				for row in context["rows"]
				if row["qty"] > 0
			],
		)

		calculated = {
			row.item_variant: row.qty
			for row in frappe.get_doc("YRP Work Order", name).deliverables
			if row.uom == "Kg"
		}
		self.assertLessEqual(legacy.keys(), calculated.keys())
		for variant, qty in legacy.items():
			self.assertAlmostEqual(calculated[variant], qty, places=3)


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


class TestGarmentCalculateQuantity(TestCase):
	def test_entered_quantity_above_the_lot_cut_quantity_is_used_as_entered(self):
		module = "essdee_yrp.garment_work_order"
		source = frappe._dict(
			name="ROW-1", item_variant="V-S", cut_qty=100, table_index=0, row_index=0, set_combination="{}"
		)
		lot = frappe._dict(lot_order_details=[source])
		lot.get = lambda key, default=None: lot[key] if key in lot else default
		ipd = frappe._dict(name="IPD-1", item="TEE")
		with (
			patch(f"{module}.get_variant_attr_details", return_value={"Size": "S"}),
			patch(f"{module}.get_parent_item", return_value="TEE"),
		):
			demands = _validated_demands(lot, ipd, [{"source_row": "ROW-1", "qty": 1234.5}])

		self.assertEqual([demand["qty"] for demand in demands], [1234.5])


class TestStitchingClothAccessoryRounding(TestCase):
	def test_cloth_accessory_quantities_are_summed_before_rounding(self):
		from essdee_yrp.garment_work_order import _stitching_cloth_accessory_deliverables

		rows = [{"item_variant": "FOLD-Red", "qty": 0.0006}, {"item_variant": "FOLD-Red", "qty": 0.0006}]
		with patch("essdee_yrp.garment_work_order._cutting_accessory_outputs", return_value=rows) as outputs:
			result = _stitching_cloth_accessory_deliverables("IPD", [])

		self.assertEqual(outputs.call_args.kwargs, {"precision": None})
		self.assertEqual([(row["item_variant"], row["qty"]) for row in result], [("FOLD-Red", 0.001)])


def _set_item_ipd():
	row = frappe._dict
	combination = [
		row(
			index=0,
			major_attribute_value="Denim",
			set_item_attribute_value="Top Front",
			attribute_value="Denim",
		),
		row(
			index=0, major_attribute_value="Black", set_item_attribute_value="Pocket", attribute_value="Denim"
		),
		row(
			index=0,
			major_attribute_value="Black",
			set_item_attribute_value="Bottom Front",
			attribute_value="Black",
		),
		row(
			index=1,
			major_attribute_value="Peach",
			set_item_attribute_value="Top Front",
			attribute_value="Peach",
		),
		row(
			index=1, major_attribute_value="Black", set_item_attribute_value="Pocket", attribute_value="Peach"
		),
		row(
			index=1,
			major_attribute_value="Black",
			set_item_attribute_value="Bottom Front",
			attribute_value="Black",
		),
	]
	panels = [
		row(stiching_attribute_value="Top Front", set_item_attribute_value="Top", quantity=1),
		row(stiching_attribute_value="Pocket", set_item_attribute_value="Bottom", quantity=1),
		row(stiching_attribute_value="Bottom Front", set_item_attribute_value="Bottom", quantity=1),
	]
	return frappe._dict(
		name="IPD-SET",
		item="SET",
		is_set_item=1,
		packing_attribute="Colour",
		set_item_attribute="Part",
		stiching_attribute="Panel",
		dependent_attribute_mapping=None,
		emblishment_details_json=None,
		is_same_packing_attribute=0,
		stiching_item_details=panels,
		stiching_item_combination_details=combination,
	)


def _panel_colours(ipd, demands):
	from essdee_yrp.garment_work_order import _panel_rows

	module = "essdee_yrp.garment_work_order"
	with (
		patch(f"{module}.build_variant_attributes", side_effect=lambda attrs, _stage, _ipd: attrs),
		patch(
			f"{module}.get_or_create_variant",
			side_effect=lambda _item, attrs, **_: (attrs["Panel"], attrs["Colour"]),
		),
	):
		rows = _panel_rows(ipd, demands, "Cut")
	return {(row["set_combination"], row["item_variant"][0]): row["item_variant"][1] for row in rows}


def _demand(colour, part, major_colour):
	return {
		"attrs": {"Colour": colour, "Part": part, "Size": "S"},
		"qty": 1,
		"table_index": 0,
		"row_index": 0,
		"set_combination": frappe.as_json({"major_colour": major_colour, "major_part": "Top"}),
	}


class TestCuttingPanelColours(TestCase):
	def test_set_item_panel_colour_follows_the_colour_set_like_production_api(self):
		denim = frappe.as_json({"major_colour": "Denim", "major_part": "Top"})
		peach = frappe.as_json({"major_colour": "Peach", "major_part": "Top"})
		colours = _panel_colours(
			_set_item_ipd(), [_demand("Black", "Bottom", "Denim"), _demand("Black", "Bottom", "Peach")]
		)

		self.assertEqual(colours[(denim, "Pocket")], "Denim")
		self.assertEqual(colours[(peach, "Pocket")], "Peach")
		self.assertEqual(colours[(denim, "Bottom Front")], "Black")

	def test_non_set_item_panel_colour_uses_the_garment_colour_mapping(self):
		row = frappe._dict
		ipd = frappe._dict(
			name="IPD-TEE",
			item="TEE",
			is_set_item=0,
			packing_attribute="Colour",
			stiching_attribute="Panel",
			dependent_attribute_mapping=None,
			emblishment_details_json=None,
			is_same_packing_attribute=0,
			stiching_item_details=[
				row(stiching_attribute_value="Front", quantity=1),
				row(stiching_attribute_value="Pocket", quantity=1),
			],
			stiching_item_combination_details=[
				row(
					index=0,
					major_attribute_value="Navy",
					set_item_attribute_value="Front",
					attribute_value="Navy",
				),
				row(
					index=0,
					major_attribute_value="Navy",
					set_item_attribute_value="Pocket",
					attribute_value="Grey",
				),
			],
		)
		colours = _panel_colours(ipd, [_demand("Navy", None, "Navy")])

		self.assertEqual(
			{panel: colour for (_set, panel), colour in colours.items()}, {"Front": "Navy", "Pocket": "Grey"}
		)
