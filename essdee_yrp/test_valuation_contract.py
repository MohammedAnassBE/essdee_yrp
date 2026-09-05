import json
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.api.mrp_stock_transfer import (
	_preflight_grn_stock_cancel,
	_validate_grn,
)
from essdee_yrp.api.work_order import _normalize_generated_uom_rows
from essdee_yrp.fabric_grn import QTY_TOLERANCE, _aggregate_rows
from essdee_yrp.fabric_tracking import _apply_grn
from essdee_yrp.hooks import doc_events, override_doctype_class
from essdee_yrp.overrides.goods_received_note import EssdeeGoodsReceivedNote
from yrp.yrp.doctype.goods_received_note.goods_received_note import GoodsReceivedNote


class TestEssdeeValuationContract(UnitTestCase):
	def test_fabric_grn_quantity_tolerance_is_defined(self):
		self.assertEqual(QTY_TOLERANCE, 0.000001)

	def test_grn_uses_controller_without_lot_tracking_hooks(self):
		self.assertEqual(
			override_doctype_class["Goods Received Note"],
			"essdee_yrp.overrides.goods_received_note.EssdeeGoodsReceivedNote",
		)
		grn_events = doc_events["Goods Received Note"]
		self.assertIn(
			"essdee_yrp.fabric_grn.before_validate",
			grn_events["before_validate"],
		)
		self.assertNotIn(
			"essdee_yrp.fabric_tracking.on_grn_submit",
			grn_events.get("on_submit", []),
		)
		self.assertNotIn(
			"essdee_yrp.fabric_tracking.on_grn_cancel",
			grn_events.get("on_cancel", []),
		)

	def test_grn_child_schema_contains_full_lineage_contract(self):
		path = Path(__file__).parent / (
			"essdee_yrp/doctype/yrp_grn_deliverable/yrp_grn_deliverable.json"
		)
		data = json.loads(path.read_text())
		fields = {row["fieldname"]: row for row in data["fields"]}
		for fieldname in (
			"goods_received_note_item",
			"received_item_variant",
			"material_value",
			"consumption_sle",
			"output_receipt_sle",
			"stock_dimensions",
		):
			self.assertIn(fieldname, fields)
		self.assertEqual(fields["work_order_deliverable"]["fieldtype"], "Link")
		self.assertTrue(fields["goods_received_note_item"]["reqd"])

	def test_non_fabric_grn_still_runs_base_submit_and_cancel_guards(self):
		doc = EssdeeGoodsReceivedNote({"doctype": "Goods Received Note"})
		with (
			patch(
				"essdee_yrp.overrides.goods_received_note.is_calculable_fabric_grn",
				return_value=False,
			),
			patch.object(GoodsReceivedNote, "before_submit") as base_submit,
			patch.object(GoodsReceivedNote, "before_cancel") as base_cancel,
		):
			doc.before_submit()
			doc.before_cancel()

		base_submit.assert_called_once_with()
		base_cancel.assert_called_once_with()

	def test_fabric_submit_populates_exact_plan_before_base_valuation(self):
		doc = EssdeeGoodsReceivedNote(
			{
				"doctype": "Goods Received Note",
				"against": "Work Order",
				"against_id": "WO-TEST",
			}
		)
		plan = [{"goods_received_note_item": "GRN-ROW-1"}]
		with (
			patch(
				"essdee_yrp.overrides.goods_received_note.is_calculable_fabric_grn",
				return_value=True,
			),
			patch(
				"essdee_yrp.overrides.goods_received_note._lock_work_order"
			) as lock_work_order,
			patch(
				"essdee_yrp.overrides.goods_received_note.calculate_consumption_plan",
				return_value=plan,
			),
			patch(
				"essdee_yrp.overrides.goods_received_note.populate_grn_deliverables"
			) as populate,
			patch.object(GoodsReceivedNote, "before_submit") as base_submit,
		):
			doc.before_submit()

		lock_work_order.assert_called_once_with("WO-TEST")
		populate.assert_called_once_with(doc, plan)
		base_submit.assert_called_once_with()
		self.assertEqual(doc.flags.essdee_deliverable_consumption, plan)

	def test_consumption_aggregation_never_blends_different_outputs(self):
		rows = [
			{
				"goods_received_note_item": "OUT-1",
				"received_item_variant": "RED-CLOTH",
				"item_variant": "GREIGE-CLOTH",
				"qty": 2,
				"uom": "Kg",
				"reference_item_variant": "RED-CLOTH",
			},
			{
				"goods_received_note_item": "OUT-1",
				"received_item_variant": "RED-CLOTH",
				"item_variant": "GREIGE-CLOTH",
				"qty": 1,
				"uom": "Kg",
				"reference_item_variant": "RED-CLOTH",
			},
			{
				"goods_received_note_item": "OUT-2",
				"received_item_variant": "BLUE-CLOTH",
				"item_variant": "GREIGE-CLOTH",
				"qty": 4,
				"uom": "Kg",
				"reference_item_variant": "BLUE-CLOTH",
			},
		]

		result = _aggregate_rows(rows)

		self.assertEqual(len(result), 2)
		self.assertEqual(
			{row["goods_received_note_item"]: row["qty"] for row in result},
			{"OUT-1": 3.0, "OUT-2": 4.0},
		)

	def test_generated_rows_keep_physical_stock_qty_when_master_uom_changes(self):
		rows = [
			{
				"item_variant": "PACKED-ITEM",
				"qty": 20,
				"pending_quantity": 20,
				"stock_update": 10,
				"uom": "Piece",
			}
		]
		with (
			patch(
				"yrp.stock.uom.resolve_item_uom",
				return_value=frappe._dict(
					uom="Box", stock_uom="Piece", conversion_factor=10
				),
			),
			patch(
				"yrp.stock.utils.get_conversion_factor",
				return_value={"stock_uom": "Piece", "conversion_factor": 1},
			),
		):
			_normalize_generated_uom_rows(rows)

		self.assertEqual(rows[0]["uom"], "Box")
		self.assertEqual(rows[0]["qty"], 2)
		self.assertEqual(rows[0]["pending_quantity"], 2)
		self.assertEqual(rows[0]["stock_update"], 1)

	def test_mrp_transfer_rejects_return_grn_server_side(self):
		doc = frappe._dict(
			doctype="Goods Received Note",
			docstatus=1,
			against="Work Order",
			is_return=1,
		)
		with patch("frappe.has_permission"):
			with self.assertRaisesRegex(
				frappe.ValidationError, "Return Goods Received Notes"
			):
				_validate_grn(doc)

	def test_return_grn_does_not_increment_forward_fabric_tracking(self):
		grn = frappe._dict(
			against="Work Order",
			against_id="WO-TEST",
			is_return=1,
		)
		with patch("frappe.get_cached_doc") as get_cached_doc:
			_apply_grn(grn, 1)
		get_cached_doc.assert_not_called()

	def test_cross_site_cancel_preflights_period_and_valuation_ownership(self):
		doc = frappe._dict(
			doctype="Goods Received Note",
			name="GRN-TEST",
			posting_date="2026-08-24",
		)
		with (
			patch(
				"yrp.stock.dimensions.get_dimension_fieldnames",
				return_value=["lot", "received_type"],
			),
			patch(
				"yrp.stock.stock_ledger._validate_sl_entries_period"
			) as validate_period,
			patch(
				"yrp.stock.stock_ledger._lock_voucher_sles_for_cancel"
			) as lock_sles,
			patch(
				"yrp.stock.stock_ledger._validate_no_active_valuation_for_cancel"
			) as validate_ownership,
		):
			_preflight_grn_stock_cancel(doc)

		entry = {
			"voucher_type": "Goods Received Note",
			"voucher_no": "GRN-TEST",
			"posting_date": "2026-08-24",
		}
		validate_period.assert_called_once_with([entry])
		lock_sles.assert_called_once_with([entry], ["lot", "received_type"])
		validate_ownership.assert_called_once_with([entry])
