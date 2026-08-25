from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.overrides.goods_received_note import (
	_return_stock_ledger_entries,
	_update_returned_deliverables,
	_validate_return_quantities,
)


class TestFinishingGRNReturn(IntegrationTestCase):
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
		self.assertEqual(entries[1]["rate"], 25)


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
