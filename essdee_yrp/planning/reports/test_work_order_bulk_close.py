from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

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
			result = endpoint.close_work_orders([order.name], "NA")
			self.assertEqual(result["results"], [])
			self.assertEqual([row["work_order"] for row in result["failed"]], [order.name])
		finally:
			frappe.set_user(original_user)
