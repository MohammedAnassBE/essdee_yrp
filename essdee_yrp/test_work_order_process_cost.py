from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from yrp.yrp.doctype.work_order.work_order import get_variant_attributes

from essdee_yrp.hooks import override_doctype_class
from essdee_yrp.overrides.work_order import EssdeeWorkOrder


class TestEssdeeWorkOrderProcessCost(FrappeTestCase):
	def test_work_order_controller_is_overridden(self):
		self.assertEqual(
			override_doctype_class["Work Order"],
			"essdee_yrp.overrides.work_order.EssdeeWorkOrder",
		)

	def test_garment_rate_is_equal_per_panel_type_and_divided_by_panel_count(self):
		work_order = _work_order()
		process_cost = frappe._dict(
			name="TEST-PROCESS-COST",
			depends_on_attribute=1,
			attribute="Colour",
		)
		ipd = frappe._dict(
			stiching_attribute="Panel",
			packing_attribute="Colour",
			primary_item_attribute="Size",
			dependent_attribute="Stage",
		)
		attributes = {
			"GARMENT-BLACK-M": {"Stage": "Piece", "Colour": "Black", "Size": "M"},
			"FRONT-BLACK-M": {
				"Stage": "Cut",
				"Panel": "Front",
				"Colour": "Black",
				"Size": "M",
			},
			"BACK-BLACK-M": {
				"Stage": "Cut",
				"Panel": "Back",
				"Colour": "Black",
				"Size": "M",
			},
			"SLEEVE-BLACK-M": {
				"Stage": "Cut",
				"Panel": "Sleeve",
				"Colour": "Black",
				"Size": "M",
			},
		}

		with (
			patch(
				"essdee_yrp.overrides.work_order.frappe.get_cached_doc",
				return_value=ipd,
			),
			patch(
				"essdee_yrp.overrides.work_order.get_variant_attributes",
				side_effect=lambda item_variant: attributes[item_variant],
			),
			patch(
				"essdee_yrp.overrides.work_order.get_process_cost_rate",
				return_value=3,
			),
		):
			work_order.apply_receivable_process_costs(process_cost)

		by_item = {row.item_variant: row for row in work_order.receivables}
		self.assertEqual(by_item["FRONT-BLACK-M"].cost, 1)
		self.assertEqual(by_item["BACK-BLACK-M"].cost, 1)
		self.assertEqual(by_item["SLEEVE-BLACK-M"].cost, 0.5)
		self.assertEqual(sum(row.total_cost for row in work_order.receivables), 30)

	def test_size_rate_uses_the_same_panel_type_split_for_each_garment_variant(self):
		work_order = _work_order()
		_add_garment_rows(work_order, colour="Navy", size="M", quantity=20)
		process_cost = frappe._dict(
			name="TEST-SIZE-PROCESS-COST",
			depends_on_attribute=1,
			attribute="Size",
		)
		ipd = _ipd()
		attributes = _variant_attributes("Black", "M") | _variant_attributes("Navy", "M")

		with (
			patch(
				"essdee_yrp.overrides.work_order.frappe.get_cached_doc",
				return_value=ipd,
			),
			patch(
				"essdee_yrp.overrides.work_order.get_variant_attributes",
				side_effect=lambda item_variant: attributes[item_variant],
			),
			patch(
				"essdee_yrp.overrides.work_order.get_process_cost_rate",
				return_value=4,
			),
		):
			work_order.apply_receivable_process_costs(process_cost)

		by_item = {row.item_variant: row for row in work_order.receivables}
		for colour in ("Black", "Navy"):
			self.assertAlmostEqual(by_item[f"FRONT-{colour.upper()}-M"].cost, 4 / 3)
			self.assertAlmostEqual(by_item[f"BACK-{colour.upper()}-M"].cost, 4 / 3)
			self.assertAlmostEqual(by_item[f"SLEEVE-{colour.upper()}-M"].cost, 2 / 3)
		self.assertEqual(sum(row.total_cost for row in work_order.receivables), 120)

	def test_panel_attribute_keeps_its_direct_per_panel_rate(self):
		work_order = _work_order()
		process_cost = frappe._dict(
			name="TEST-PANEL-PROCESS-COST",
			depends_on_attribute=1,
			attribute="Panel",
			process_cost_values=[
				frappe._dict(attribute_value="Front", min_order_qty=0, price=3),
				frappe._dict(attribute_value="Back", min_order_qty=0, price=2),
				frappe._dict(attribute_value="Sleeve", min_order_qty=0, price=1),
			],
		)
		attributes = _variant_attributes("Black", "M")

		with (
			patch(
				"essdee_yrp.overrides.work_order.frappe.get_cached_doc",
				return_value=_ipd(),
			),
			patch(
				"yrp.yrp.doctype.work_order.work_order.get_variant_attributes",
				side_effect=lambda item_variant: attributes[item_variant],
			),
		):
			work_order.apply_receivable_process_costs(process_cost)

		by_item = {row.item_variant: row for row in work_order.receivables}
		self.assertEqual(by_item["FRONT-BLACK-M"].cost, 3)
		self.assertEqual(by_item["BACK-BLACK-M"].cost, 2)
		self.assertEqual(by_item["SLEEVE-BLACK-M"].cost, 1)

	def test_pc_25_oracle_conserves_colour_value_with_panel_type_split(self):
		if not frappe.db.exists("Work Order", "YRP-WO-2026-00058"):
			self.skipTest("YRP-WO-2026-00058 is unavailable")
		if not frappe.db.exists("Process Cost", "YRP-PC-00025"):
			self.skipTest("YRP-PC-00025 is unavailable")

		work_order = frappe.get_doc("Work Order", "YRP-WO-2026-00058")
		process_cost = frappe.get_doc("Process Cost", "YRP-PC-00025")
		self.assertIsInstance(work_order, EssdeeWorkOrder)
		work_order.apply_receivable_process_costs(process_cost)

		colour_totals = {"Black": 0, "Mint": 0, "Navy": 0, "Olive": 0}
		front_rate = None
		sleeve_rate = None
		for row in work_order.receivables:
			attributes = get_variant_attributes(row.item_variant)
			colour_totals[attributes["Colour"]] += row.total_cost
			if attributes["Colour"] == "Black" and attributes["Size"] == "45 cm":
				if attributes["Panel"] == "Top Front":
					front_rate = row.cost
				elif attributes["Panel"] == "Sleeve 1":
					sleeve_rate = row.cost

		self.assertAlmostEqual(front_rate, 5 / 9, places=8)
		self.assertAlmostEqual(sleeve_rate, 5 / 18, places=8)
		self.assertAlmostEqual(colour_totals["Black"], 3000, places=4)
		self.assertAlmostEqual(colour_totals["Mint"], 3000, places=4)
		self.assertAlmostEqual(colour_totals["Navy"], 3000, places=4)
		self.assertAlmostEqual(colour_totals["Olive"], 2400, places=4)


def _work_order():
	work_order = EssdeeWorkOrder({"doctype": "Work Order", "production_detail": "TEST-IPD"})
	_add_garment_rows(work_order, colour="Black", size="M", quantity=10)
	return work_order


def _add_garment_rows(work_order, colour, size, quantity):
	combination = frappe.as_json({"major_colour": colour})
	colour_key = colour.upper()
	work_order.append(
		"work_order_calculated_items",
		{
			"item_variant": f"GARMENT-{colour_key}-{size}",
			"quantity": quantity,
			"set_combination": combination,
		},
	)
	for item_variant, panel_quantity in (
		(f"FRONT-{colour_key}-{size}", quantity),
		(f"BACK-{colour_key}-{size}", quantity),
		(f"SLEEVE-{colour_key}-{size}", quantity * 2),
	):
		work_order.append(
			"receivables",
			{
				"item_variant": item_variant,
				"qty": panel_quantity,
				"set_combination": combination,
			},
		)


def _ipd():
	return frappe._dict(
		stiching_attribute="Panel",
		packing_attribute="Colour",
		primary_item_attribute="Size",
		dependent_attribute="Stage",
	)


def _variant_attributes(colour, size):
	colour_key = colour.upper()
	base = {"Colour": colour, "Size": size}
	return {
		f"GARMENT-{colour_key}-{size}": {**base, "Stage": "Piece"},
		f"FRONT-{colour_key}-{size}": {**base, "Stage": "Cut", "Panel": "Front"},
		f"BACK-{colour_key}-{size}": {**base, "Stage": "Cut", "Panel": "Back"},
		f"SLEEVE-{colour_key}-{size}": {**base, "Stage": "Cut", "Panel": "Sleeve"},
	}
