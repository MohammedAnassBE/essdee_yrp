from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import SDYRPCuttingPlan


def plan(status, weights):
	rows = [SimpleNamespace(weight=weight, required_weight=10) for weight in weights]
	return SimpleNamespace(cp_status=status, cutting_plan_cloth_details=rows)


class TestCuttingPlanFabricStatus(TestCase):
	def status(self, doc):
		with patch.object(frappe.db, "get_single_value", return_value=0):
			return SDYRPCuttingPlan._fabric_receipt_status(doc)

	def test_no_received_fabric_keeps_plan_planned(self):
		self.assertEqual(self.status(plan("Planned", [0, 0])), "Planned")

	def test_cancelled_receipt_returns_plan_to_planned(self):
		self.assertEqual(self.status(plan("Fabric Partially Received", [0, 0])), "Planned")

	def test_some_received_fabric_is_partial(self):
		self.assertEqual(self.status(plan("Planned", [4, 0])), "Fabric Partially Received")

	def test_all_received_fabric_is_ready(self):
		self.assertEqual(self.status(plan("Planned", [10, 10])), "Ready to Cut")


class TestCuttingPlanWorkOrderLot(TestCase):
	def check(self, work_order_lot):
		doc = SimpleNamespace(lot="LOT-A", work_order="WO-1")
		with patch.object(frappe.db, "get_value", return_value=work_order_lot):
			SDYRPCuttingPlan.validate_work_order_lot(doc)

	def test_work_order_of_another_lot_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Work Order WO-1 belongs to Lot LOT-B"):
			self.check("LOT-B")

	def test_work_order_of_same_lot_is_accepted(self):
		self.check("LOT-A")

	def test_plan_without_work_order_is_accepted(self):
		SDYRPCuttingPlan.validate_work_order_lot(SimpleNamespace(lot="LOT-A", work_order=None))


class TestStockTransferHistoryLinks(TestCase):
	def test_cancelled_transaction_row_is_history_not_a_cancelled_link(self):
		from frappe.model.document import Document

		from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan_stock_transfer.sd_yrp_cutting_plan_stock_transfer import (
			SDYRPCuttingPlanStockTransfer,
		)

		row = SDYRPCuttingPlanStockTransfer.__new__(SDYRPCuttingPlanStockTransfer)
		with patch.object(Document, "get_invalid_links", return_value=(["missing"], ["cancelled DC"])):
			self.assertEqual(row.get_invalid_links(is_submittable=True), (["missing"], []))


class TestCuttingPlanTransactionCancel(TestCase):
	def exemptions(self, linked, existing=()):
		from essdee_yrp.cutting.web_workspace import add_cutting_plan_link_exemption

		doc = frappe._dict(doctype="YRP Delivery Challan", name="DC-1", ignore_linked_doctypes=existing)
		with patch.object(frappe.db, "exists", return_value=linked):
			add_cutting_plan_link_exemption(doc)
		return doc.ignore_linked_doctypes

	def test_plan_linked_transaction_can_cancel_past_its_history_row(self):
		self.assertEqual(
			self.exemptions(True, ("YRP Stock Ledger Entry",)),
			("YRP Stock Ledger Entry", "SD YRP Cutting Plan"),
		)

	def test_unlinked_transaction_keeps_its_exemptions(self):
		self.assertEqual(self.exemptions(False, ("YRP Stock Ledger Entry",)), ("YRP Stock Ledger Entry",))


class TestMovementTransactionDefaults(TestCase):
	def test_editor_payload_is_stored_as_text_and_rows_stay_child_rows(self):
		from essdee_yrp.cutting.movement import new_transaction_from_defaults

		grouped = [{"items": [{"name": "CLOTH", "values": {"default": {"qty": 2}}}]}]
		doc = new_transaction_from_defaults(
			"YRP Stock Entry",
			{"purpose": "Send to Warehouse", "item_details": grouped, "items": [{"item": "CLOTH-RED", "qty": 2}]},
		)
		self.assertEqual(frappe.parse_json(doc.item_details), grouped)
		self.assertEqual(doc.items[0].item, "CLOTH-RED")
		doc.get_valid_dict()


class TestTransitReceiptKeepsMovementOwner(TestCase):
	def receipt(self):
		doc = frappe._dict(
			doctype="YRP Stock Entry",
			name="STE-RECEIVE",
			purpose="Receive at Warehouse",
			outgoing_stock_entry="STE-SEND",
			against=None,
			against_id=None,
			cut_panel_movement=None,
			allow_non_bundle=0,
		)
		doc.meta = frappe._dict(get_field=lambda fieldname: fieldname == "allow_non_bundle")
		return doc

	def test_transit_receipt_inherits_bundle_context_from_outgoing_entry(self):
		from essdee_yrp.cutting.movement import set_completion_cut_panel_movement

		doc = self.receipt()
		meta = frappe._dict(get_field=lambda fieldname: fieldname in {"cut_panel_movement", "allow_non_bundle"})
		values = {"cut_panel_movement": "CPM-1", "allow_non_bundle": 1}
		with (
			patch.object(frappe, "get_meta", return_value=meta),
			patch.object(frappe.db, "get_value", side_effect=lambda dt, name, field: values[field]) as get_value,
		):
			set_completion_cut_panel_movement(doc)
		self.assertEqual((doc.cut_panel_movement, doc.allow_non_bundle), ("CPM-1", 1))
		get_value.assert_any_call("YRP Stock Entry", "STE-SEND", "cut_panel_movement")

	def test_transit_receipt_is_not_a_competing_root_transaction(self):
		from essdee_yrp.cutting.movement import validate_transaction_link

		doc = self.receipt()
		doc.cut_panel_movement = "CPM-1"
		with patch.object(frappe.db, "get_value") as get_value:
			validate_transaction_link(doc)
		get_value.assert_not_called()


class TestCompletionMovementSourceIsAuthoritative(TestCase):
	def test_transit_receipt_replaces_a_stale_movement_with_the_outgoing_entry_one(self):
		from essdee_yrp.cutting.movement import set_completion_cut_panel_movement

		doc = TestTransitReceiptKeepsMovementOwner.receipt(self)
		doc.cut_panel_movement = "CPM-STALE"
		meta = frappe._dict(get_field=lambda fieldname: fieldname in {"cut_panel_movement", "allow_non_bundle"})
		values = {"cut_panel_movement": None, "allow_non_bundle": 0}
		with (
			patch.object(frappe, "get_meta", return_value=meta),
			patch.object(frappe.db, "get_value", side_effect=lambda dt, name, field: values[field]),
		):
			set_completion_cut_panel_movement(doc)
		self.assertIsNone(doc.cut_panel_movement)


class TestCuttingPlanTransactionDelete(TestCase):
	def test_deleting_a_draft_removes_its_plan_history_row(self):
		from essdee_yrp.cutting.web_workspace import remove_cutting_plan_link

		doc = frappe._dict(doctype="SD YRP Lot Transfer", name="LT-1")
		with patch.object(frappe.db, "delete") as delete:
			remove_cutting_plan_link(doc)
		delete.assert_called_once_with(
			"SD YRP Cutting Plan Stock Transfer", {"against": "SD YRP Lot Transfer", "against_id": "LT-1"}
		)
