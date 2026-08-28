from unittest.mock import patch

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from essdee_yrp.finishing.alternative import (
	create_alternative_fp,
	update_alternative_lot_quantity,
)
from essdee_yrp.finishing.work_order_packing import build_packing_work_order_rows
from essdee_yrp.finishing.work_order import (
	create_or_refresh_finishing_plan,
	on_cancel as on_packing_work_order_cancel,
	on_submit as on_packing_work_order_submit,
)


class TestFinishingWorkOrderPacking(FrappeTestCase):
	@patch("essdee_yrp.finishing.work_order.create_or_refresh_finishing_plan")
	@patch("essdee_yrp.finishing.work_order._transfer_alternative_stock")
	def test_external_packing_work_order_does_not_create_finishing_plan(
		self, transfer_alternative_stock, create_finishing_plan
	):
		doc = frappe._dict(
			name="TEST-EXTERNAL-PACKING-WO",
			includes_packing=1,
			is_rework=0,
			is_internal_unit=0,
		)

		on_packing_work_order_submit(doc)

		transfer_alternative_stock.assert_not_called()
		create_finishing_plan.assert_not_called()

	@patch("essdee_yrp.finishing.work_order._reverse_alternative_stock")
	@patch("essdee_yrp.finishing.work_order.frappe.delete_doc")
	@patch("essdee_yrp.finishing.work_order.frappe.db.get_value", return_value=None)
	def test_external_packing_work_order_cancel_has_no_internal_side_effects(
		self, get_value, delete_doc, reverse_alternative_stock
	):
		doc = frappe._dict(
			name="TEST-EXTERNAL-PACKING-WO",
			includes_packing=1,
			is_internal_unit=0,
		)

		on_packing_work_order_cancel(doc)

		get_value.assert_called_once_with(
			"Finishing Plan", {"work_order": doc.name}, "name"
		)
		delete_doc.assert_not_called()
		reverse_alternative_stock.assert_not_called()

	def test_rebuild_matches_a_migrated_packing_work_order(self):
		# This migrated F15 record is a stable 40-size/colour + four-accessory
		# packing fixture.  Its stored rows are the legacy-calculation oracle.
		work_order_name = "WO-2627-00839"
		if not frappe.db.exists("Work Order", work_order_name):
			work_order_name = None
		if not work_order_name:
			self.skipTest("No migrated packing Work Order is available")

		work_order = frappe.get_doc("Work Order", work_order_name)
		rows = build_packing_work_order_rows(work_order.lot, work_order.process_name)
		self.assertEqual(
			_rows_by_identity(rows["deliverables"]),
			_rows_by_identity(work_order.deliverables),
		)
		self.assertEqual(
			_rows_by_identity(rows["receivables"]),
			_rows_by_identity(work_order.receivables),
		)
		self.assertEqual(
			_calculated_by_identity(rows["calculated_items"]),
			_calculated_by_identity(work_order.work_order_calculated_items),
		)

	def test_refresh_preserves_finishing_operational_quantities(self):
		work_order_name = "WO-2627-00839"
		finishing_plan_name = frappe.db.get_value(
			"Finishing Plan", {"work_order": work_order_name}, "name"
		)
		if not finishing_plan_name:
			self.skipTest("Migrated Finishing Plan oracle is not available")
		before = frappe.get_doc("Finishing Plan", finishing_plan_name)
		operational = {
			(row.item_variant, row.set_combination): (
				row.dc_qty,
				row.return_qty,
				row.pack_return_qty,
				row.transferred_qty,
				row.ironing_excess,
			)
			for row in before.finishing_plan_details
		}

		self.assertEqual(
			create_or_refresh_finishing_plan(work_order_name), finishing_plan_name
		)
		after = frappe.get_doc("Finishing Plan", finishing_plan_name)
		for row in after.finishing_plan_details:
			key = (row.item_variant, row.set_combination)
			if key in operational:
				self.assertEqual(
					(
						row.dc_qty,
						row.return_qty,
						row.pack_return_qty,
						row.transferred_qty,
						row.ironing_excess,
					),
					operational[key],
				)

	def test_alternative_plan_creates_linked_ppo_lot_and_packing_work_order(self):
		"""Exercise the migrated F15 alternative-plan orchestration transactionally."""
		finishing_plan = "FP-2627-00057"
		production_detail = "AISHWARYA PRINT (S/Box)-4"
		if not frappe.db.exists("Finishing Plan", finishing_plan) or not frappe.db.exists(
			"Item Production Detail", production_detail
		):
			self.skipTest("Migrated alternative-plan oracle is unavailable")
		blank_lot = frappe.db.get_value(
			"Lot",
			{
				"production_detail": ["in", [None, ""]],
				"production_order": ["in", [None, ""]],
				"item": ["in", [None, ""]],
				"status": ["!=", "Closed"],
			},
			"name",
		)
		if not blank_lot:
			self.skipTest("No blank Lot is available for the transactional test")
		result = create_alternative_fp(
			doc_name=finishing_plan,
			alternative_item="AISHWARYA PRINT (S/Box)",
			production_detail=production_detail,
			lot_name=None,
			lot_source="existing",
			existing_lot=blank_lot,
			qty_details={
				"data": {
					"data": {
						"Military Green": {
							"check_value": 1,
							"values": {"110 cm": {"conversion_qty": 1}},
						}
					}
				}
			},
		)
		lot = frappe.get_doc("Lot", result["lot"])
		production_order = frappe.get_doc(
			"Production Order", result["production_order"]
		)
		work_order = frappe.get_doc("Work Order", result["work_order"])
		self.assertEqual(lot.production_order, production_order.name)
		self.assertEqual(lot.transferred_lot, "F0326-62")
		self.assertEqual(production_order.docstatus, 1)
		self.assertEqual(production_order.item, "AISHWARYA PRINT (S/Box)")
		self.assertEqual(work_order.docstatus, 0)
		self.assertEqual(work_order.lot, lot.name)
		self.assertTrue(work_order.deliverables)
		self.assertTrue(work_order.receivables)
		self.assertTrue(work_order.work_order_calculated_items)
		# F16 Process Cost is scoped by the production-group dimension (Lot).
		# The new alternative Lot must therefore receive its own approved rate
		# before its draft Work Order can be submitted.
		source_process_cost = frappe.get_doc("Process Cost", "PC-00688")
		process_cost = frappe.copy_doc(source_process_cost)
		process_cost.from_date = nowdate()
		process_cost.to_date = add_days(nowdate(), 1)
		process_cost.lot = lot.name
		process_cost.docstatus = 0
		process_cost.workflow_state = "Draft"
		process_cost.approved_by = None
		process_cost.insert(ignore_permissions=True)
		process_cost = apply_workflow(process_cost, "Submit")
		process_cost = apply_workflow(process_cost, "Approve")
		self.assertEqual(process_cost.docstatus, 1)

		work_order.flags.ignore_permissions = True
		work_order.submit()
		self.assertTrue(
			frappe.db.exists(
				"Finishing Plan", {"work_order": work_order.name, "lot": lot.name}
			)
		)
		stock_entries = frappe.get_all(
			"Stock Entry",
			filters={
				"against": "Work Order",
				"against_id": work_order.name,
				"docstatus": 1,
				"purpose": ["in", ["Material Issue", "Material Receipt"]],
			},
			pluck="name",
		)
		self.assertEqual(len(stock_entries), 2)
		stickers = frappe.get_all(
			"Box Sticker Print",
			filters={
				"against": "Work Order",
				"against_id": work_order.name,
				"docstatus": 1,
			},
			pluck="name",
		)
		self.assertTrue(stickers)

		self.assertEqual(
			update_alternative_lot_quantity(
				doc_name=finishing_plan,
				target_lot=lot.name,
				qty_details={
					"data": {
						"data": {
							"Military Green": {
								"check_value": 1,
								"values": {"110 cm": {"conversion_qty": 1}},
							}
						}
					}
				},
			),
			work_order.name,
		)
		stock_entries = frappe.get_all(
			"Stock Entry",
			filters={
				"against": "Work Order",
				"against_id": work_order.name,
				"docstatus": 1,
				"purpose": ["in", ["Material Issue", "Material Receipt"]],
			},
			pluck="name",
		)
		self.assertEqual(len(stock_entries), 4)

		work_order.reload()
		work_order.flags.ignore_permissions = True
		work_order.cancel()
		self.assertFalse(
			frappe.db.exists("Finishing Plan", {"work_order": work_order.name})
		)
		self.assertTrue(
			all(frappe.db.get_value("Stock Entry", name, "docstatus") == 2 for name in stock_entries)
		)
		self.assertTrue(
			all(frappe.db.get_value("Box Sticker Print", name, "docstatus") == 2 for name in stickers)
		)


def _rows_by_identity(rows):
	result = {}
	for row in rows:
		item_variant = row.get("item_variant")
		uom = row.get("uom")
		result[(item_variant, uom)] = round(
			result.get((item_variant, uom), 0) + float(row.get("qty") or 0), 3
		)
	return result


def _calculated_by_identity(rows):
	result = {}
	for row in rows:
		item_variant = row.get("item_variant")
		result[item_variant] = round(
			result.get(item_variant, 0) + float(row.get("quantity") or 0), 3
		)
	return result
