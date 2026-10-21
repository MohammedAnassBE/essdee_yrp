from unittest.mock import patch

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from essdee_yrp.finishing.alternative import (
	create_alternative_fp,
	update_alternative_lot_quantity,
)
from essdee_yrp.finishing.work_order import (
	create_or_refresh_finishing_plan,
)
from essdee_yrp.finishing.work_order import (
	on_cancel as on_packing_work_order_cancel,
)
from essdee_yrp.finishing.work_order import (
	on_submit as on_packing_work_order_submit,
)
from essdee_yrp.finishing.work_order_packing import _packing_receivables, build_packing_work_order_rows
from essdee_yrp.garment_work_order import _packing_rows
from essdee_yrp.overrides.work_order import EssdeeWorkOrder
from essdee_yrp.production_order_alternative import get_rows_by_size


class TestFinishingWorkOrderPacking(FrappeTestCase):
	def test_mapped_size_wise_planning_keeps_piece_quantities_in_both_builders(self):
		ipd = frappe._dict(
			name="TEST-IPD",
			item="TEST-ITEM",
			based_on_other_attribute_mapping=1,
			packing_mode="Size Wise Packing",
			primary_item_attribute="Size",
			pack_out_stage="Packed",
			dependent_attribute_mapping="TEST-MAPPING",
			is_set_item=0,
			stiching_item_details=[],
		)
		lot = frappe._dict(name="TEST-LOT", packing_uom="Pieces", uom="Box")
		demand = {
			"attrs": {"Size": "S"},
			"qty": 120,
			"item_variant": "INPUT-S",
			"set_combination": "{}",
			"table_index": 0,
			"row_index": "0",
		}
		principal = [{"item_variant": "INPUT-S", "quantity": 120}]

		def to_float(value, precision=None):
			return round(float(value or 0), precision) if precision else float(value or 0)

		with (
			patch("essdee_yrp.garment_work_order.flt", side_effect=to_float),
			patch(
				"essdee_yrp.garment_work_order.build_variant_attributes",
				return_value={"Size": "S", "Stage": "Packed"},
			),
			patch("essdee_yrp.garment_work_order.get_or_create_variant", return_value="PACKED-S"),
			patch(
				"essdee_yrp.finishing.work_order_packing.build_variant_attributes",
				return_value={"Size": "S", "Stage": "Packed"},
			),
			patch("essdee_yrp.finishing.work_order_packing.get_or_create_variant", return_value="PACKED-S"),
			patch("essdee_yrp.finishing.work_order_packing.flt", side_effect=to_float),
			patch(
				"essdee_yrp.finishing.work_order_packing.get_variant_attr_details",
				return_value={"Size": "S"},
			),
		):
			calculated = _packing_rows(ipd, lot, [demand])
			receivables = _packing_receivables(ipd, lot, principal, "Accepted")

		self.assertEqual(calculated[0]["qty"], 120)
		self.assertEqual(receivables[0]["qty"], 120)
		self.assertEqual(receivables[0]["uom"], "Pieces")

	@patch("essdee_yrp.finishing.work_order.frappe.msgprint")
	@patch("essdee_yrp.finishing.work_order.create_or_refresh_finishing_plan")
	@patch("essdee_yrp.finishing.work_order._transfer_alternative_stock")
	def test_external_packing_work_order_does_not_create_finishing_plan(
		self, transfer_alternative_stock, create_finishing_plan, msgprint
	):
		doc = frappe._dict(
			name="TEST-EXTERNAL-PACKING-WO",
			includes_packing=1,
			is_rework=0,
			is_internal_unit=0,
			supplier="S-TEST",
			supplier_name="Outside Packer",
		)

		on_packing_work_order_submit(doc)

		transfer_alternative_stock.assert_not_called()
		create_finishing_plan.assert_not_called()
		msgprint.assert_called_once_with(
			"No Finishing Plan was created: Outside Packer is not a company location.",
			indicator="orange",
		)

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

		get_value.assert_called_once_with("SD YRP Finishing Plan", {"work_order": doc.name}, "name")
		delete_doc.assert_not_called()
		reverse_alternative_stock.assert_not_called()

	def test_rebuild_matches_a_migrated_packing_work_order(self):
		# This migrated F15 record is a stable 40-size/colour + four-accessory
		# packing fixture.  Its stored rows are the legacy-calculation oracle.
		work_order_name = "WO-2627-00839"
		if not frappe.db.exists("YRP Work Order", work_order_name):
			work_order_name = None
		if not work_order_name:
			self.skipTest("No migrated packing Work Order is available")

		work_order = frappe.get_doc("YRP Work Order", work_order_name)
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
			"SD YRP Finishing Plan", {"work_order": work_order_name}, "name"
		)
		if not finishing_plan_name:
			self.skipTest("Migrated Finishing Plan oracle is not available")
		before = frappe.get_doc("SD YRP Finishing Plan", finishing_plan_name)
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

		self.assertEqual(create_or_refresh_finishing_plan(work_order_name), finishing_plan_name)
		after = frappe.get_doc("SD YRP Finishing Plan", finishing_plan_name)
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
		if not frappe.db.exists("SD YRP Finishing Plan", finishing_plan) or not frappe.db.exists(
			"YRP Item Production Detail", production_detail
		):
			self.skipTest("Migrated alternative-plan oracle is unavailable")
		blank_lot = frappe.db.get_value(
			"SD YRP Lot",
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
		lot = frappe.get_doc("SD YRP Lot", result["lot"])
		production_order = frappe.get_doc("YRP Production Order", result["production_order"])
		work_order = frappe.get_doc("YRP Work Order", result["work_order"])
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
		source_process_cost = frappe.get_doc("YRP Process Cost", "PC-00688")
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

		# Like production_api, a packing Work Order needs a deliberate Lot-wise
		# price; the MRP inherited from the cloned Production Order does not count.
		production_order.reload()
		size_row = get_rows_by_size(production_order)["110 cm"]
		production_order.append(
			"lot_price_overrides", {"lot": lot.name, "size": "110 cm", "mrp": size_row.mrp}
		).db_insert()

		work_order.flags.ignore_permissions = True
		work_order.submit()
		self.assertTrue(
			frappe.db.exists("SD YRP Finishing Plan", {"work_order": work_order.name, "lot": lot.name})
		)
		stock_entries = frappe.get_all(
			"YRP Stock Entry",
			filters={
				"against": "YRP Work Order",
				"against_id": work_order.name,
				"docstatus": 1,
				"purpose": ["in", ["Material Issue", "Material Receipt"]],
			},
			pluck="name",
		)
		self.assertEqual(len(stock_entries), 2)
		stickers = frappe.get_all(
			"SD YRP Box Sticker Print",
			filters={
				"against": "YRP Work Order",
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
			"YRP Stock Entry",
			filters={
				"against": "YRP Work Order",
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
		self.assertFalse(frappe.db.exists("SD YRP Finishing Plan", {"work_order": work_order.name}))
		self.assertTrue(
			all(frappe.db.get_value("YRP Stock Entry", name, "docstatus") == 2 for name in stock_entries)
		)
		self.assertTrue(
			all(frappe.db.get_value("SD YRP Box Sticker Print", name, "docstatus") == 2 for name in stickers)
		)


class TestPackingWorkOrderSubmitRestriction(FrappeTestCase):
	packing_issue = "Already Work Order was Created for Packing"

	def setUp(self):
		super().setUp()
		point = f"packing_submit_{frappe.generate_hash(length=12)}"
		frappe.db.savepoint(point)
		self.addCleanup(frappe.db.rollback, save_point=point)
		self.lot = f"TEST-PACKING-LOT-{frappe.generate_hash(length=12)}"

	def _packing_work_order(self, *, docstatus=0, is_rework=0):
		doc = frappe.get_doc(
			{
				"doctype": "YRP Work Order",
				"name": frappe.generate_hash(length=12),
				"lot": self.lot,
				"includes_packing": 1,
				"docstatus": docstatus,
				"is_rework": is_rework,
			}
		)
		doc.db_insert()
		return doc

	@patch("essdee_yrp.overrides.work_order.WorkOrder.get_submit_readiness_issues", return_value=[])
	@patch("essdee_yrp.finishing.box_sticker.get_missing_box_sticker_prices", return_value=[])
	def test_second_packing_work_order_is_blocked(self, missing_prices, base_issues):
		self._packing_work_order(docstatus=1)
		doc = self._packing_work_order()

		issues = doc.get_submit_readiness_issues()

		self.assertIn(self.packing_issue, issues)
		self.assertEqual(issues.count(self.packing_issue), 1)
		with self.assertRaisesRegex(frappe.ValidationError, self.packing_issue):
			doc.run_method("before_submit")

	def test_submitted_packing_work_order_does_not_count_itself(self):
		doc = self._packing_work_order(docstatus=1)

		self.assertIs(doc.has_submitted_packing_work_order, False)

	@patch("essdee_yrp.overrides.work_order.WorkOrder.get_submit_readiness_issues", return_value=[])
	@patch("essdee_yrp.finishing.box_sticker.get_missing_box_sticker_prices", return_value=[])
	def test_cancelled_packing_work_orders_do_not_block(self, missing_prices, base_issues):
		self._packing_work_order(docstatus=2)
		doc = self._packing_work_order()

		self.assertIs(doc.has_submitted_packing_work_order, False)
		self.assertNotIn(self.packing_issue, doc.get_submit_readiness_issues())

	@patch("essdee_yrp.overrides.work_order.WorkOrder.get_submit_readiness_issues", return_value=[])
	@patch("essdee_yrp.finishing.box_sticker.get_missing_box_sticker_prices", return_value=[])
	def test_draft_packing_work_orders_do_not_block(self, missing_prices, base_issues):
		self._packing_work_order(docstatus=0)
		doc = self._packing_work_order()

		self.assertIs(doc.has_submitted_packing_work_order, False)
		self.assertNotIn(self.packing_issue, doc.get_submit_readiness_issues())

	@patch("essdee_yrp.overrides.work_order.WorkOrder.get_submit_readiness_issues", return_value=[])
	def test_non_packing_work_order_does_not_query_or_lock(self, base_issues):
		doc = EssdeeWorkOrder({"doctype": "YRP Work Order", "lot": self.lot, "includes_packing": 0})

		with (
			patch("essdee_yrp.overrides.work_order.frappe.db.sql") as sql,
			patch("essdee_yrp.overrides.work_order.frappe.db.get_value") as get_value,
		):
			self.assertEqual(doc.get_submit_readiness_issues(), [])
			get_value.assert_not_called()
			sql.assert_not_called()

	@patch("essdee_yrp.overrides.work_order.WorkOrder.get_submit_readiness_issues", return_value=[])
	@patch("essdee_yrp.finishing.box_sticker.get_missing_box_sticker_prices", return_value=["M"])
	def test_rework_packing_work_order_is_blocked(self, missing_prices, base_issues):
		self._packing_work_order(docstatus=1)
		doc = self._packing_work_order(is_rework=1)

		issues = doc.get_submit_readiness_issues()

		self.assertEqual(issues[0], self.packing_issue)
		self.assertIn("Lot-wise price is not set", issues[1])

	def test_packing_work_order_without_lot_does_not_query_or_lock(self):
		doc = EssdeeWorkOrder({"doctype": "YRP Work Order", "includes_packing": 1})

		with (
			patch("essdee_yrp.overrides.work_order.frappe.db.sql") as sql,
			patch("essdee_yrp.overrides.work_order.frappe.db.get_value") as get_value,
		):
			self.assertIs(doc.has_submitted_packing_work_order, False)
			get_value.assert_not_called()
			sql.assert_not_called()


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
		result[item_variant] = round(result.get(item_variant, 0) + float(row.get("quantity") or 0), 3)
	return result
