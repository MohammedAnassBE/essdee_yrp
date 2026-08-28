from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.overrides.goods_received_note import (
	EssdeeGoodsReceivedNote,
	_find_deliverable,
	_return_stock_ledger_entries,
	_update_returned_deliverables,
	_validate_return_quantities,
)


class TestFinishingGRNReturn(IntegrationTestCase):
	def test_direct_finishing_return_allows_received_type_reclassification_in_place(self):
		grn = _return_grn(from_finishing=1)

		grn.validate_items()

	def test_ordinary_grn_still_rejects_same_warehouse(self):
		grn = _return_grn(from_finishing=0, is_return=0)

		with self.assertRaisesRegex(
			frappe.ValidationError, "From Warehouse and To Warehouse must be different"
		):
			grn.validate_items()

	def test_explicit_return_reference_must_match_its_item(self):
		deliverable = _deliverable(item_variant="VAR-OTHER")
		work_order = _doc(name="WO-1", deliverables=[deliverable])
		row = _row(ref_doctype="Work Order Deliverables", ref_docname=deliverable.name)

		with self.assertRaisesRegex(
			frappe.ValidationError, "does not match the returned item"
		):
			_find_deliverable(work_order, row)

	def test_unreferenced_duplicate_return_deliverables_are_rejected(self):
		first = _deliverable()
		second = _deliverable()
		second.name = "WO-DEL-2"
		work_order = _doc(name="WO-1", deliverables=[first, second])

		with self.assertRaisesRegex(
			frappe.ValidationError, "matches multiple Work Order Deliverables"
		):
			_find_deliverable(work_order, _row())

	def test_return_targets_work_order_deliverable(self):
		deliverable = _deliverable(qty=10, pending_quantity=4)
		work_order = _doc(name="WO-1", deliverables=[deliverable])
		row = _row(quantity=3)
		grn = _doc(against_id="WO-1", items=[row])

		with patch(
			"essdee_yrp.overrides.goods_received_note.frappe.get_doc",
			return_value=work_order,
		):
			_validate_return_quantities(grn)

		self.assertEqual(row.ref_doctype, "Work Order Deliverables")
		self.assertEqual(row.ref_docname, deliverable.name)

	def test_return_submit_and_cancel_restore_deliverable_pending(self):
		deliverable = _deliverable(qty=10, pending_quantity=4)
		work_order = _doc(name="WO-1", deliverables=[deliverable])
		grn = _doc(against_id="WO-1", items=[_row(quantity=3)])

		with (
			patch(
				"essdee_yrp.overrides.goods_received_note.frappe.get_doc",
				return_value=work_order,
			),
			patch("essdee_yrp.overrides.goods_received_note._update_work_order_status"),
		):
			_update_returned_deliverables(grn, cancel=False)
			self.assertEqual(deliverable.pending_quantity, 7)
			_update_returned_deliverables(grn, cancel=True)

		self.assertEqual(deliverable.pending_quantity, 4)

	@patch(
		"essdee_yrp.overrides.goods_received_note.get_last_sle_rate",
		return_value=(25, True),
	)
	@patch(
		"essdee_yrp.overrides.goods_received_note.get_dimension_fieldnames",
		return_value=["lot", "received_type"],
	)
	@patch(
		"essdee_yrp.overrides.goods_received_note.frappe.db.get_single_value",
		return_value="Accepted",
	)
	@patch(
		"essdee_yrp.overrides.goods_received_note._sle_base",
		return_value={
			"item": "VAR-1",
			"lot": "LOT-1",
			"received_type": "Rejected",
		},
	)
	def test_return_posts_outgoing_default_and_incoming_selected_received_type(
		self, _sle, _default, _dimensions, _rate
	):
		grn = _doc(
			from_warehouse="FINISHING-WH",
			to_warehouse="REWORK-WH",
			items=[_row(quantity=3, stock_qty=3)],
		)

		entries = _return_stock_ledger_entries(grn)

		self.assertEqual(entries[0]["warehouse"], "FINISHING-WH")
		self.assertEqual(entries[0]["qty"], -3)
		self.assertEqual(entries[0]["received_type"], "Accepted")
		self.assertEqual(entries[1]["warehouse"], "REWORK-WH")
		self.assertEqual(entries[1]["qty"], 3)
		self.assertEqual(entries[1]["received_type"], "Rejected")
		self.assertEqual(entries[0]["outgoing_rate"], 25)
		self.assertEqual(entries[1]["rate"], 0)
		self.assertEqual(entries[0]["_transfer_key"], entries[1]["_transfer_key"])
		self.assertEqual(entries[0]["_transfer_role"], "outgoing")
		self.assertEqual(entries[1]["_transfer_role"], "incoming")

	@patch(
		"essdee_yrp.overrides.goods_received_note.get_last_sle_rate",
		side_effect=AssertionError("cancel must reverse the persisted rate"),
	)
	@patch(
		"essdee_yrp.overrides.goods_received_note.get_dimension_fieldnames",
		return_value=["lot", "received_type"],
	)
	@patch(
		"essdee_yrp.overrides.goods_received_note.frappe.db.get_single_value",
		return_value="Accepted",
	)
	@patch(
		"essdee_yrp.overrides.goods_received_note._sle_base",
		return_value={
			"item": "VAR-1",
			"lot": "LOT-1",
			"received_type": "Rejected",
		},
	)
	def test_return_cancel_uses_persisted_sle_rate(
		self, _sle, _default, _dimensions, last_rate
	):
		grn = _doc(
			from_warehouse="FINISHING-WH",
			to_warehouse="FINISHING-WH",
			items=[_row(quantity=3, stock_qty=3)],
		)

		entries = _return_stock_ledger_entries(grn, cancel=True)

		last_rate.assert_not_called()
		self.assertEqual(entries[0]["outgoing_rate"], 0)
		self.assertEqual(entries[0]["received_type"], "Accepted")
		self.assertEqual(entries[1]["received_type"], "Rejected")


def _deliverable(**values):
	row = _row(**values)
	row.name = "WO-DEL-1"
	row.db_set = lambda fieldname, value, **_kwargs: row.__setitem__(fieldname, value)
	return row


def _row(**values):
	defaults = {
		"idx": 1,
		"item_variant": "VAR-1",
		"set_combination": "{}",
		"quantity": 0,
		"stock_qty": 0,
		"qty": 0,
		"pending_quantity": 0,
		"ref_doctype": None,
		"ref_docname": None,
	}
	defaults.update(values)
	return frappe._dict(defaults)


def _doc(**values):
	doc = frappe._dict(values)
	doc.get = lambda key, default=None: doc[key] if key in doc else default
	return doc


def _return_grn(**values):
	doc = EssdeeGoodsReceivedNote(
		{
			"doctype": "Goods Received Note",
			"against": "Work Order",
			"against_id": "WO-1",
			"is_return": 1,
			"from_finishing": 1,
			"from_warehouse": "FINISHING-WH",
			"to_warehouse": "FINISHING-WH",
			"items": [{"item_variant": "VAR-1", "quantity": 1}],
			**values,
		}
	)
	return doc
