from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import test_work_order_reopen as reopen_fixtures
from essdee_yrp.essdee_yrp.page.work_order_bulk_close import work_order_bulk_close as endpoint


class TestPlanningBulkCloseEndpoints(TestCase):
	def setUp(self):
		for name in ("savepoint", "rollback"):
			patcher = patch.object(frappe.db, name)
			setattr(self, name, patcher.start())
			self.addCleanup(patcher.stop)

	def test_existing_close_function_receives_all_reasons_and_returns_statuses(self):
		document = MagicMock(docstatus=1, open_status="Open")
		with patch.object(frappe, "get_doc", return_value=document), patch.object(
			endpoint, "close_work_order", side_effect=[{"status": "Close"}, {"status": "Close Request"}],
		) as close:
			result = endpoint.close_work_orders(
				["WO-1", "WO-2"], "Others", "Stopped", "Reviewed",
			)
		self.assertEqual(result["results"], [
			{"work_order": "WO-1", "open_status": "Close"},
			{"work_order": "WO-2", "open_status": "Close Request"},
		])
		self.assertEqual(result["failed"], [])
		self.assertEqual(document.check_permission.call_args_list[0].args, ("write",))
		self.assertEqual(close.call_args_list[0].kwargs, {
			"sd_close_reason": "Others", "close_other_reason": "Stopped", "close_remarks": "Reviewed",
		})

	def test_a_failed_order_is_rolled_back_and_reported_while_others_close(self):
		for failure in ("permission", "status", "close"):
			with self.subTest(failure=failure):
				self.rollback.reset_mock()
				first = MagicMock(docstatus=1, open_status="Open")
				second = MagicMock(docstatus=1, open_status="Close" if failure == "status" else "Open")
				if failure == "permission":
					second.check_permission.side_effect = frappe.PermissionError("Denied")
				effects = [{"status": "Close"}, frappe.ValidationError("<b>Stock</b> unavailable"), {"status": "Close"}]
				with patch.object(frappe, "get_doc", side_effect=[first, second, first]), patch.object(
					endpoint, "close_work_order", side_effect=effects if failure == "close" else [{"status": "Close"}] * 2,
				), patch.object(frappe, "clear_messages") as clear:
					result = endpoint.close_work_orders(["WO-1", "WO-2", "WO-3"], "NA")
				self.assertEqual([row["work_order"] for row in result["results"]], ["WO-1", "WO-3"])
				self.assertEqual([row["work_order"] for row in result["failed"]], ["WO-2"])
				expected = {"permission": "Denied", "status": "Work Order WO-2 is no longer open.", "close": "Stock unavailable"}
				self.assertEqual(result["failed"][0]["error"], expected[failure])
				self.rollback.assert_called_once_with(save_point="work_order_bulk_close_2")
				clear.assert_called()

	def test_bulk_flags_are_set_during_close_and_restored(self):
		seen = {}

		def close(name, **kwargs):
			seen.update(bulk=frappe.flags.work_order_bulk_close, quiet=frappe.flags.suppress_work_order_close_alert)
			return {"status": "Close"}

		frappe.flags.work_order_bulk_close = None
		with patch.object(frappe, "get_doc", return_value=MagicMock(docstatus=1, open_status="Open")), patch.object(
			endpoint, "close_work_order", side_effect=close,
		):
			endpoint.close_work_orders(["WO-1"], "NA")
		self.assertEqual(seen, {"bulk": True, "quiet": True})
		self.assertIsNone(frappe.flags.work_order_bulk_close)

	def test_empty_selection_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			endpoint.close_work_orders([], "NA")


class TestPlanningBulkCloseLive(IntegrationTestCase):
	def test_guest_cannot_load_open_orders(self):
		original_user = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				endpoint.get_open_work_orders("unused")
		finally:
			frappe.set_user(original_user)

	def test_live_preview_shape_and_guest_document_permissions(self):
		orders = frappe.get_list("YRP Work Order", filters={"docstatus": 1, "open_status": "Open"}, fields=["name", "supplier"], page_length=1)
		if not orders:
			self.skipTest("Requires a migrated submitted open Work Order")
		order = orders[0]
		rows = endpoint.get_open_work_orders(order.supplier)
		self.assertIn(order.name, [row.name for row in rows])
		preview = endpoint.get_work_order_close_details(order.name)
		self.assertEqual(set(preview), {"summary", "recut_details", "debits"})
		original_user = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				endpoint.get_work_order_close_details(order.name)
			with self.assertRaises(frappe.PermissionError):
				endpoint.close_work_orders([order.name], "NA")
		finally:
			frappe.set_user(original_user)


class TestApproveCloseRequests(TestCase):
	def setUp(self):
		for name in ("savepoint", "rollback"):
			patcher = patch.object(frappe.db, name)
			setattr(self, name, patcher.start())
			self.addCleanup(patcher.stop)

	def test_only_the_closing_approver_role_may_approve(self):
		with (
			patch.object(endpoint, "_is_wo_close_manager", return_value=False),
			patch.object(endpoint, "_get_wo_close_approver_role", return_value="WO Approver"),
			patch.object(endpoint, "close_work_order") as close,
		):
			with self.assertRaisesRegex(frappe.PermissionError, "WO Approver"):
				endpoint.approve_close_requests(["WO-1"])
		close.assert_not_called()

	def test_empty_selection_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Select at least one"):
			endpoint.approve_close_requests([])

	def test_pending_requests_close_with_their_stored_reasons_and_others_are_reported(self):
		pending = MagicMock(docstatus=1, open_status="Close Request")
		pending.get.side_effect = {
			"sd_close_reason": "Others", "close_reason": None,
			"close_other_reason": "Stopped", "close_remarks": "Checked",
		}.get
		docs = {
			"WO-1": pending,
			"WO-2": MagicMock(docstatus=1, open_status="Open"),
			"WO-3": pending,
			"WO-4": MagicMock(docstatus=1, open_status="Close Request"),
		}
		docs["WO-4"].check_permission.side_effect = frappe.PermissionError("No access to WO-4")
		effects = [{"status": "Close"}, frappe.ValidationError("<b>GRN</b> missing")]
		with (
			patch.object(endpoint, "_is_wo_close_manager", return_value=True),
			patch.object(frappe, "get_doc", side_effect=lambda doctype, name, **kwargs: docs[name]),
			patch.object(endpoint, "close_work_order", side_effect=effects) as close,
			patch.object(frappe, "clear_messages"),
		):
			result = endpoint.approve_close_requests(["WO-1", "WO-2", "WO-3", "WO-4"])
		self.assertEqual(result["approved"], ["WO-1"])
		self.assertEqual(result["failed"], [
			{"work_order": "WO-2", "error": "Work Order WO-2 does not have a pending Close Request."},
			{"work_order": "WO-3", "error": "GRN missing"},
			{"work_order": "WO-4", "error": "No access to WO-4"},
		])
		self.assertEqual(close.call_args_list[0].kwargs, {
			"sd_close_reason": "Others", "close_reason": None,
			"close_other_reason": "Stopped", "close_remarks": "Checked",
		})
		self.assertEqual(
			[call.kwargs["save_point"] for call in self.rollback.call_args_list],
			["work_order_approve_close_2", "work_order_approve_close_3", "work_order_approve_close_4"],
		)


class TestBulkCloseAndApproveLive(IntegrationTestCase):
	"""Real close ledgers on throwaway Work Orders; all rolled back."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")
		real_get_single_value = frappe.db.get_single_value

		def get_single_value(doctype, fieldname, *args, **kwargs):
			if doctype == "YRP Settings" and fieldname == "work_order_closing_approver_role":
				return "System Manager"
			return real_get_single_value(doctype, fieldname, *args, **kwargs)

		patcher = patch.object(frappe.db, "get_single_value", side_effect=get_single_value)
		patcher.start()
		self.addCleanup(patcher.stop)

	def _closable(self):
		return reopen_fixtures.TestWorkOrderReopen._closable_work_order(self)

	def _balance(self, bucket):
		return reopen_fixtures.TestWorkOrderReopen._balance(self, bucket)

	def _not_an_approver(self):
		return patch("essdee_yrp.work_order_close._is_wo_close_manager", return_value=False)

	def test_bulk_close_of_an_external_order_closes_directly_and_writes_off_stock(self):
		work_order, bucket = self._closable()
		self.assertFalse(work_order.is_internal_unit)
		opening = self._balance(bucket)
		with self._not_an_approver() as manager:
			result = endpoint.close_work_orders([work_order.name], "NA")
		manager.assert_not_called()
		self.assertEqual(result, {"results": [{"work_order": work_order.name, "open_status": "Close"}], "failed": []})
		work_order.reload()
		self.assertEqual(work_order.open_status, "Close")
		self.assertEqual(work_order.closed_by, "Administrator")
		self.assertAlmostEqual(self._balance(bucket), opening - 3)
		self.assertTrue(frappe.db.exists(
			"YRP Stock Ledger Entry",
			{"voucher_type": "YRP Work Order", "voucher_no": work_order.name, "is_cancelled": 0},
		))

	def test_single_close_without_the_approver_role_still_requests_approval(self):
		work_order, bucket = self._closable()
		opening = self._balance(bucket)
		with self._not_an_approver(), patch.object(frappe, "msgprint"):
			result = endpoint.close_work_order(work_order.name, sd_close_reason="Sewing Shortage")
		self.assertEqual(result, {"status": "Close Request", "deducted_qty": 0.0})
		self.assertEqual(frappe.db.get_value("YRP Work Order", work_order.name, "open_status"), "Close Request")
		self.assertAlmostEqual(self._balance(bucket), opening)

	def test_approve_close_closes_pending_requests_and_reports_the_rest(self):
		pending, bucket = self._closable()
		still_open, _bucket = self._closable()
		with self._not_an_approver(), patch.object(frappe, "msgprint"):
			endpoint.close_work_order(pending.name, sd_close_reason="Sewing Shortage")
		opening = self._balance(bucket)

		result = endpoint.approve_close_requests([pending.name, still_open.name])

		self.assertEqual(result["approved"], [pending.name])
		self.assertEqual(result["failed"], [{
			"work_order": still_open.name,
			"error": f"Work Order {still_open.name} does not have a pending Close Request.",
		}])
		pending.reload()
		self.assertEqual((pending.open_status, pending.sd_close_reason), ("Close", "Sewing Shortage"))
		self.assertAlmostEqual(self._balance(bucket), opening - 3)
		self.assertEqual(frappe.db.get_value("YRP Work Order", still_open.name, "open_status"), "Open")

	def test_users_without_permission_cannot_bulk_close_or_approve(self):
		user = frappe.get_doc({
			"doctype": "User",
			"email": f"bulk-close-{frappe.generate_hash(length=8)}@example.com",
			"first_name": "Bulk Close Test",
			"send_welcome_email": 0,
		}).insert(ignore_permissions=True)
		frappe.set_user(user.name)
		with self.assertRaises(frappe.PermissionError):
			endpoint.close_work_orders(["WO-ANY"], "NA")
		with self.assertRaises(frappe.PermissionError):
			endpoint.approve_close_requests(["WO-ANY"])
