from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.page.work_order_bulk_close import work_order_bulk_close as endpoint


class TestPlanningBulkCloseEndpoints(TestCase):
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
		self.assertEqual(document.check_permission.call_args_list[0].args, ("write",))
		self.assertEqual(close.call_args_list[0].kwargs, {
			"sd_close_reason": "Others", "close_other_reason": "Stopped", "close_remarks": "Reviewed",
		})

	def test_every_document_is_checked_before_any_close(self):
		for failure in ("permission", "status"):
			with self.subTest(failure=failure):
				first = MagicMock(docstatus=1, open_status="Open")
				second = MagicMock(docstatus=1, open_status="Close" if failure == "status" else "Open")
				if failure == "permission":
					second.check_permission.side_effect = frappe.PermissionError("Denied")
				with patch.object(frappe, "get_doc", side_effect=[first, second]), patch.object(
					endpoint, "close_work_order",
				) as close:
					with self.assertRaises(frappe.PermissionError if failure == "permission" else frappe.ValidationError):
						endpoint.close_work_orders(["WO-1", "WO-2"], "NA")
					close.assert_not_called()

	def test_close_errors_propagate(self):
		with patch.object(frappe, "get_doc", return_value=MagicMock(docstatus=1, open_status="Open")), patch.object(
			endpoint, "close_work_order", side_effect=frappe.ValidationError("Stock unavailable"),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "Stock unavailable"):
				endpoint.close_work_orders(["WO-1"], "NA")


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
