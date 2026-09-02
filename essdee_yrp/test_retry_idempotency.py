from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.cutting import movement
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet import (
	sd_yrp_cutting_laysheet as cutting_laysheet,
)
from essdee_yrp.finishing import transactions


class TestRetryIdempotency(UnitTestCase):
	def test_collapsed_bundle_submit_retry_locks_voucher_and_skips_duplicate(self):
		doc = frappe._dict(
			doctype='YRP Delivery Challan',
			name="DC-U44",
			lot="LOT-U44",
			cut_panel_movement=None,
			allow_non_bundle=1,
		)
		with (
			patch.object(movement, "_bundle_tracking_disabled", return_value=False),
			patch.object(movement, "_is_implicit_collapsed_return", return_value=False),
			patch.object(movement.frappe.db, "get_value", return_value=doc.name) as get_value,
			patch.object(movement.frappe.db, "exists", return_value="CBML-U44"),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_bundle_movement_ledger.sd_yrp_cut_bundle_movement_ledger.update_collapsed_bundle"
			) as update_collapsed,
		):
			movement.apply_transaction(doc)

		get_value.assert_called_once_with(
			doc.doctype, doc.name, "name", for_update=True
		)
		update_collapsed.assert_not_called()

	def test_bundle_cancel_retry_without_active_ledger_is_a_noop(self):
		doc = frappe._dict(
			doctype='YRP Delivery Challan',
			name="DC-U44-CANCEL",
			lot="LOT-U44",
			cut_panel_movement=None,
			allow_non_bundle=1,
		)
		with (
			patch.object(movement, "_bundle_tracking_disabled", return_value=False),
			patch.object(movement, "_is_implicit_collapsed_return", return_value=False),
			patch.object(movement.frappe.db, "get_value", return_value=doc.name),
			patch.object(movement.frappe.db, "exists", return_value=None),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_bundle_movement_ledger.sd_yrp_cut_bundle_movement_ledger.update_collapsed_bundle"
			) as update_collapsed,
		):
			movement.apply_transaction(doc, cancelled=True)

		update_collapsed.assert_not_called()

	def test_laysheet_bundle_retry_locks_before_checking_completion_marker(self):
		doc = frappe._dict(doctype='SD YRP Cutting LaySheet', name="CLS-U44")
		with (
			patch.object(cutting_laysheet, "_lock_cutting_laysheet") as lock,
			patch.object(cutting_laysheet.frappe.db, "exists", return_value="CBML-U44"),
			patch.object(cutting_laysheet, "cut_bundle_ledger") as create_ledger,
		):
			cutting_laysheet.create_cut_bundle_ledger(doc)

		lock.assert_called_once_with(doc.name)
		create_ledger.assert_not_called()

	def test_finishing_grn_retry_returns_submitted_winner_without_new_document(self):
		work_order = MagicMock()
		with (
			patch.object(transactions.frappe, "get_doc", return_value=work_order),
			patch.object(
				transactions.frappe.db, "get_value", return_value="WO-U44"
			) as get_value,
			patch.object(transactions, "_validate_work_order_context") as validate,
			patch.object(
				transactions,
				"_get_existing_finishing_grn",
				return_value=frappe._dict(name="GRN-U44", docstatus=1),
			),
			patch.object(transactions.frappe, "new_doc") as new_doc,
		):
			result = transactions.create_grn(
				"WO-U44",
				"LOT-U44",
				"ITEM-U44",
				{},
				"SUPPLIER-U44",
				"2026-08-27",
				request_id="u44-request-1",
			)

		self.assertEqual(result, "GRN-U44")
		work_order.check_permission.assert_called_once_with("read")
		work_order.reload.assert_called_once_with()
		get_value.assert_called_once_with(
			'YRP Work Order', "WO-U44", "name", for_update=True
		)
		validate.assert_called_once_with(work_order, "LOT-U44", "ITEM-U44")
		new_doc.assert_not_called()

	def test_finishing_grn_request_marker_rejects_unsafe_or_oversized_values(self):
		for request_id in ("unsafe marker", "x" * 129, "<script>"):
			with self.subTest(request_id=request_id):
				with self.assertRaises(frappe.ValidationError):
					transactions._finishing_grn_request_marker(request_id)

	def test_finishing_grn_submitted_marker_lookup_is_current_and_locked(self):
		with patch.object(
			transactions.frappe.db,
			"sql",
			return_value=[frappe._dict(name="GRN-U44", docstatus=1)],
		) as sql:
			result = transactions._get_existing_finishing_grn(
				"WO-U44", "LOT-U44", "[essdee-finishing-grn-request:u44]"
			)

		self.assertEqual(result.name, "GRN-U44")
		self.assertIn("FOR UPDATE", sql.call_args.args[0])
		self.assertTrue(sql.call_args.kwargs["as_dict"])
