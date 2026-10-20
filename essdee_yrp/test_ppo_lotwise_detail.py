import json

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import (
	add_ppo_lot_qty,
	check_enabled_po,
	delete_ppo_lot_qty,
)
from essdee_yrp.merch.lot_workspace import get_merch_lot_editor, save_merch_lot
from essdee_yrp.purchase.lot_editor import get_lot_production_detail_context


class TestProductionOrderLotQuantity(IntegrationTestCase):
	"""Lot rows on the Production Order's Lotwise Ordered Detail."""

	def setUp(self):
		suffix = frappe.generate_hash(length=8)
		self.production_order = f"_Test PPO Lotwise {suffix}"
		self.lot = (
			frappe.get_doc(
				{
					"doctype": "SD YRP Lot",
					"lot_name": f"_Test Lotwise {suffix}",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.variant = frappe.db.get_value("Item", {"variant_of": ["is", "set"]}, "name")

	def get_rows(self):
		return frappe.get_all(
			"YRP Production Ordered Detail",
			filters={"parent": self.production_order},
			fields=["lot", "reference_doctype", "reference_name", "quantity"],
		)

	def insert_row(self, **values):
		row = frappe.new_doc("YRP Production Ordered Detail")
		row.update(
			{
				"parent": self.production_order,
				"parenttype": "YRP Production Order",
				"parentfield": "production_ordered_details",
				"item_variant": self.variant,
				"quantity": 5,
				**values,
			}
		)
		row.db_insert()

	def test_lot_rows_carry_direct_and_dynamic_lot_links(self):
		add_ppo_lot_qty(self.production_order, self.lot, [frappe._dict(item_variant=self.variant, qty=7)])

		self.assertEqual(
			self.get_rows(),
			[
				{
					"lot": self.lot,
					"reference_doctype": "SD YRP Lot",
					"reference_name": self.lot,
					"quantity": 7,
				}
			],
		)

	def test_delete_removes_migrated_rows_with_only_the_direct_lot_link(self):
		self.insert_row(lot=self.lot)
		self.insert_row(reference_doctype="SD YRP Lot", reference_name=self.lot)

		delete_ppo_lot_qty(self.production_order, self.lot)

		self.assertEqual(self.get_rows(), [])


class TestLotQuantityIsNotBoundByProductionOrder(IntegrationTestCase):
	"""A Lot may order more or less than its Production Order; the PPO keeps its own quantity."""

	def setUp(self):
		frappe.set_user("Administrator")
		# One piece per cell must stay below every PPO size, so pick a PPO with room.
		source = frappe.db.sql(
			"""
			SELECT lot.production_order, lot.production_detail, lot.item
			FROM `tabSD YRP Lot` lot
			WHERE lot.docstatus = 0 AND IFNULL(lot.production_detail, '') != ''
			AND (
				SELECT MIN(detail.quantity) FROM `tabYRP Production Order Detail` detail
				WHERE detail.parent = lot.production_order
			) >= 10
			ORDER BY lot.modified DESC
			LIMIT 1
			""",
			as_dict=True,
		)
		if not source or not check_enabled_po():
			self.skipTest("Needs a migrated Lot linked to a Production Order with PPO mode enabled")
		self.source = source[0]
		self.ppo_quantities = self.get_ppo_quantities()

	def get_ppo_quantities(self):
		return {
			row.item_variant: row.quantity
			for row in frappe.get_doc(
				"YRP Production Order", self.source.production_order
			).production_order_details
		}

	def get_lot_rows(self, lot):
		return {
			row.item_variant: row.quantity
			for row in frappe.get_all(
				"YRP Production Ordered Detail",
				filters={"parent": self.source.production_order, "reference_name": lot},
				fields=["item_variant", "quantity"],
			)
		}

	def get_values(self, item_details, order_item_details, name=None):
		return {
			"lot_name": name or f"_Test Lot Qty {frappe.generate_hash(length=8)}",
			"production_order": self.source.production_order,
			"item": self.source.item,
			"production_detail": self.source.production_detail,
			"item_details": item_details,
			"order_item_details": order_item_details,
			"lot_fabric_details": [],
		}

	def insert_lot(self, box_quantity):
		details = get_lot_production_detail_context(
			self.source.production_detail, self.source.item, self.source.production_order
		)["item_details"]
		for cell in details["items"][0]["values"].values():
			cell["qty"] = box_quantity
		return save_merch_lot(json.dumps(self.get_values([details], [])))["name"]

	def test_box_quantity_above_production_order_saves_and_syncs(self):
		box_quantity = max(self.ppo_quantities.values()) + 10
		lot = frappe.get_doc("SD YRP Lot", self.insert_lot(box_quantity))

		self.assertEqual({row.qty for row in lot.items}, {box_quantity})
		self.assertEqual(self.get_lot_rows(lot.name), {row.item_variant: box_quantity for row in lot.items})
		self.assertEqual(self.get_ppo_quantities(), self.ppo_quantities)

	def test_piece_quantity_below_production_order_saves_and_syncs(self):
		name = self.insert_lot(max(self.ppo_quantities.values()) + 10)
		form = get_merch_lot_editor(name)
		for group in form["order_item_details"]:
			for item in group["items"]:
				for cell in item["values"].values():
					cell["qty"] = 1
		values = self.get_values([form["item_details"]], form["order_item_details"], name)
		save_merch_lot(json.dumps(values), name=name, expected_modified=form["record"]["modified"])
		lot = frappe.get_doc("SD YRP Lot", name)

		self.assertEqual({row.quantity for row in lot.lot_order_details}, {1})
		self.assertEqual(self.get_lot_rows(name), {row.item_variant: row.qty for row in lot.items})
		for row in lot.items:
			self.assertLess(row.qty, self.ppo_quantities[row.item_variant])
		self.assertEqual(self.get_ppo_quantities(), self.ppo_quantities)

	def test_over_ordered_production_order_suggests_zero_not_negative(self):
		self.insert_lot(max(self.ppo_quantities.values()) + 10)
		details = get_lot_production_detail_context(
			self.source.production_detail, self.source.item, self.source.production_order
		)["item_details"]

		self.assertEqual({cell["qty"] for cell in details["items"][0]["values"].values()}, {0})
