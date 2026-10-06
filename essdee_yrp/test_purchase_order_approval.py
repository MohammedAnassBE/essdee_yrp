import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

PROPERTY_SETTERS = Path(__file__).parent / "fixtures" / "property_setter.json"
CUSTOM_DOCPERMS = Path(__file__).parent / "fixtures" / "custom_docperm.json"


class TestPurchaseOrderApprovalState(TestCase):
	def _doc(self, *items, managed=True, status="Draft", docstatus=0):
		return frappe._dict(
			{
				"doctype": "Purchase Order",
				"name": "YRP-PO-TEST",
				"is_yrp_managed": 1 if managed else 0,
				"docstatus": docstatus,
				"status": status,
				"yrp_fulfillment_status": "Draft",
				"flags": frappe._dict(),
				"items": [frappe._dict({"item_code": item}) for item in items],
			}
		)

	def test_status_property_setter_includes_pending_approval_once(self):
		with PROPERTY_SETTERS.open() as source:
			rows = json.load(source)
		row = next(item for item in rows if item["name"] == "Purchase Order-status-options")
		self.assertEqual(row["value"].splitlines().count("Pending Approval"), 1)

	def test_system_manager_has_purchase_order_submit_permission_fixture(self):
		from essdee_yrp import hooks

		with CUSTOM_DOCPERMS.open() as source:
			rows = json.load(source)
		row = next(
			item
			for item in rows
			if item["parent"] == "Purchase Order" and item["role"] == "System Manager"
		)
		self.assertEqual((row["read"], row["write"], row["create"], row["submit"]), (1, 1, 1, 1))
		fixture = next(item for item in hooks.fixtures if item.get("dt") == "Custom DocPerm")
		self.assertIn("Purchase Order", fixture["filters"][0][2])

	@patch("essdee_yrp.purchase_order_approval.frappe.get_all")
	def test_mixed_rows_trigger_on_one_exact_purchase_yarn_item(self, get_all):
		from essdee_yrp.purchase_order_approval import requires_yarn_approval

		get_all.return_value = [
			frappe._dict({"name": "CLOTH", "item_group": "Purchase - Fabric"}),
			frappe._dict({"name": "YARN", "item_group": "Purchase - Yarn"}),
		]
		self.assertTrue(requires_yarn_approval(self._doc("CLOTH", "YARN")))
		get_all.assert_called_once_with(
			"Item",
			filters={"name": ["in", ["CLOTH", "YARN"]]},
			fields=["name", "item_group"],
			limit_page_length=0,
		)

	@patch("essdee_yrp.purchase_order_approval.frappe.get_all")
	def test_child_similar_and_empty_rows_do_not_trigger(self, get_all):
		from essdee_yrp.purchase_order_approval import requires_yarn_approval

		get_all.return_value = [
			frappe._dict({"name": "CHILD", "item_group": "Purchase - Yarn / Dyed"}),
			frappe._dict({"name": "SIMILAR", "item_group": "Purchase Yarn"}),
		]
		self.assertFalse(requires_yarn_approval(self._doc("CHILD", "SIMILAR")))
		get_all.reset_mock()
		self.assertFalse(requires_yarn_approval(self._doc()))
		get_all.assert_not_called()

	@patch("essdee_yrp.purchase_order_approval.get_live_request", return_value=None)
	@patch("essdee_yrp.purchase_order_approval.requires_yarn_approval", return_value=True)
	def test_draft_save_sets_only_standard_status(self, requires, get_live):
		from essdee_yrp.purchase_order_approval import apply_draft_approval_status

		doc = self._doc("YARN")
		apply_draft_approval_status(doc)
		self.assertEqual(doc.status, "Pending Approval")
		self.assertEqual(doc.yrp_fulfillment_status, "Draft")

	@patch("essdee_yrp.purchase_order_approval.get_live_request", return_value=None)
	@patch("essdee_yrp.purchase_order_approval.requires_yarn_approval", return_value=False)
	def test_pending_approval_returns_to_draft_when_last_yarn_item_is_removed(
		self, requires, get_live
	):
		from essdee_yrp.purchase_order_approval import apply_draft_approval_status

		doc = self._doc("CLOTH", status="Pending Approval")
		apply_draft_approval_status(doc)
		self.assertEqual(doc.status, "Draft")
		self.assertEqual(doc.yrp_fulfillment_status, "Draft")

	@patch("essdee_yrp.purchase_order_approval.requires_yarn_approval")
	def test_non_yrp_purchase_order_is_untouched(self, requires):
		from essdee_yrp.purchase_order_approval import apply_draft_approval_status

		doc = self._doc("YARN", managed=False)
		apply_draft_approval_status(doc)
		self.assertEqual(doc.status, "Draft")
		requires.assert_not_called()

	@patch("essdee_yrp.purchase_order_approval.requires_yarn_approval")
	def test_rejection_flag_preserves_draft_once(self, requires):
		from essdee_yrp.purchase_order_approval import apply_draft_approval_status

		doc = self._doc("YARN")
		doc.flags.purchase_order_approval_rejection = True
		apply_draft_approval_status(doc)
		self.assertEqual(doc.status, "Draft")
		requires.assert_not_called()


class TestPurchaseOrderApprovalTransitions(TestCase):
	def _doc(self, status="Pending Approval", docstatus=0, managed=True):
		doc = Mock()
		doc.doctype = "Purchase Order"
		doc.name = "YRP-PO-TEST"
		doc.is_yrp_managed = 1 if managed else 0
		doc.status = status
		doc.docstatus = docstatus
		doc.flags = frappe._dict()
		doc.items = [frappe._dict({"item_code": "YARN"})]
		doc.get.side_effect = lambda key: getattr(doc, key)
		return doc

	def _call(self, method, *args):
		return getattr(method, "__wrapped__", method)(*args)

	def _raise(self, message, *args, **kwargs):
		raise RuntimeError(message)

	@patch("essdee_yrp.purchase_order_approval.requires_yarn_approval", return_value=True)
	@patch("essdee_yrp.purchase_order_approval.frappe.get_roles", return_value=["Purchase Manager"])
	@patch("essdee_yrp.purchase_order_approval.frappe.throw")
	def test_non_system_manager_cannot_submit_managed_yarn_po(self, throw, get_roles, requires):
		from essdee_yrp.purchase_order_approval import validate_approval_submit

		throw.side_effect = self._raise
		with self.assertRaisesRegex(RuntimeError, "Only System Manager"):
			validate_approval_submit(self._doc(status="To Receive", docstatus=1))

	@patch("essdee_yrp.purchase_order_approval.requires_yarn_approval", return_value=True)
	@patch("essdee_yrp.purchase_order_approval.frappe.get_roles", return_value=["System Manager"])
	def test_system_manager_can_submit_directly_from_draft_or_pending(self, get_roles, requires):
		from essdee_yrp.purchase_order_approval import validate_approval_submit

		validate_approval_submit(self._doc(status="Draft"))
		validate_approval_submit(self._doc(status="Pending Approval"))

	@patch("essdee_yrp.purchase_order_approval.requires_yarn_approval")
	@patch("essdee_yrp.purchase_order_approval.frappe.get_roles", return_value=["Purchase Manager"])
	def test_non_managed_purchase_order_keeps_native_submit_flow(self, get_roles, requires):
		from essdee_yrp.purchase_order_approval import validate_approval_submit

		validate_approval_submit(self._doc(managed=False))
		requires.assert_not_called()

	@patch("essdee_yrp.purchase_order_approval.finalize_live_request")
	@patch("essdee_yrp.purchase_order_approval.requires_yarn_approval", return_value=True)
	@patch("essdee_yrp.purchase_order_approval.frappe.get_roles", return_value=["System Manager"])
	@patch("essdee_yrp.purchase_order_approval._get_locked_purchase_order")
	def test_approve_locks_and_submits_to_target_status(
		self, get_locked, get_roles, requires, finalize
	):
		from essdee_yrp.purchase_order_approval import approve_purchase_order

		doc = self._doc()
		def submit():
			doc.docstatus = 1
			doc.status = "To Receive"
			doc.approved_by = "manager@example.com"
		doc.submit.side_effect = submit
		get_locked.return_value = doc
		result = self._call(approve_purchase_order, "YRP-PO-TEST")
		get_locked.assert_called_once_with("YRP-PO-TEST")
		doc.submit.assert_called_once_with()
		self.assertEqual(result["status"], "To Receive")
		self.assertEqual(doc.approved_by, "manager@example.com")

	@patch("essdee_yrp.purchase_order_approval.finalize_live_request")
	@patch("essdee_yrp.purchase_order_approval.requires_yarn_approval", return_value=True)
	@patch("essdee_yrp.purchase_order_approval.frappe.get_roles", return_value=["System Manager"])
	@patch("essdee_yrp.purchase_order_approval._get_locked_purchase_order")
	def test_reject_returns_pending_po_to_draft(self, get_locked, get_roles, requires, finalize):
		from essdee_yrp.purchase_order_approval import reject_purchase_order

		doc = self._doc()
		get_locked.return_value = doc
		result = self._call(reject_purchase_order, "YRP-PO-TEST", "Rate exceeds budget")
		self.assertEqual(doc.status, "Draft")
		self.assertTrue(doc.flags.purchase_order_approval_rejection)
		doc.save.assert_called_once_with(ignore_permissions=True)
		doc.add_comment.assert_called_once_with(
			"Comment",
			"Purchase Order approval rejected: Rate exceeds budget",
		)
		self.assertEqual(result["status"], "Draft")

	@patch("essdee_yrp.purchase_order_approval.finalize_live_request")
	@patch("essdee_yrp.purchase_order_approval._in_telegram_action", return_value=False)
	def test_on_submit_preserves_desk_approve_audit_label(self, in_telegram, finalize):
		from essdee_yrp.purchase_order_approval import finalize_purchase_order_submission

		doc = self._doc(status="To Receive", docstatus=1)
		doc.flags.purchase_order_approval_action = "approve"
		finalize_purchase_order_submission(doc)
		finalize.assert_called_once_with("YRP-PO-TEST", "Approved", "Approve PO")


class TestPurchaseOrderRequestLifecycle(TestCase):
	def _call(self, method, *args):
		while hasattr(method, "__wrapped__"):
			method = method.__wrapped__
		return method(*args)

	def _doc(self):
		doc = Mock()
		doc.doctype = "Purchase Order"
		doc.name = "YRP-PO-0012"
		doc.is_yrp_managed = 1
		doc.status = "Pending Approval"
		doc.docstatus = 0
		doc.flags = frappe._dict()
		doc.items = [frappe._dict({"item_code": "YARN"})]
		doc.get.side_effect = lambda key: getattr(doc, key)
		return doc

	@patch("essdee_yrp.purchase_order_approval.frappe.get_cached_doc")
	def test_route_reuses_migrated_process_cost_group_idempotently(self, get_settings):
		from essdee_yrp.purchase_order_approval import ensure_purchase_order_approval_route

		settings = Mock()
		settings.routes = [frappe._dict({
			"name": "PROCESS", "enabled": 1, "reference_doctype": "YRP Process Cost", "group_chat_id": "-100123",
		})]
		def append(_field, values):
			row = frappe._dict({"name": "PO-ROUTE", **values})
			settings.routes.append(row)
			return row
		settings.append.side_effect = append
		get_settings.return_value = settings
		self.assertEqual(ensure_purchase_order_approval_route(), "PO-ROUTE")
		self.assertEqual(ensure_purchase_order_approval_route(), "PO-ROUTE")
		settings.append.assert_called_once()
		self.assertEqual(settings.routes[-1].group_chat_id, "-100123")

	@patch("essdee_yrp.purchase_order_approval.frappe.get_doc")
	@patch("essdee_yrp.purchase_order_approval.create_and_send_approval", side_effect=["REQ-ERR", "REQ-PENDING"])
	@patch("essdee_yrp.purchase_order_approval.frappe.get_cached_doc")
	@patch("essdee_yrp.purchase_order_approval.ensure_purchase_order_approval_route", return_value="PO-ROUTE")
	@patch("essdee_yrp.purchase_order_approval.get_live_request", return_value=None)
	@patch("essdee_yrp.purchase_order_approval._prepare_purchase_order_request")
	def test_error_send_can_retry_then_pending_locks(
		self, prepare, get_live, ensure_route, get_settings, create_and_send, get_doc
	):
		from essdee_yrp.purchase_order_approval import send_purchase_order_request

		prepare.return_value = self._doc()
		get_settings.return_value = frappe._dict({
			"enabled": 1,
			"routes": [frappe._dict({"name": "PO-ROUTE", "enabled": 1, "reference_doctype": "Purchase Order"})],
		})
		get_doc.side_effect = [
			frappe._dict({"name": "REQ-ERR", "status": "Error", "error": "network"}),
			frappe._dict({"name": "REQ-PENDING", "status": "Pending", "error": None}),
		]
		first = self._call(send_purchase_order_request, "YRP-PO-0012")
		second = self._call(send_purchase_order_request, "YRP-PO-0012")
		self.assertEqual(first["status"], "Error")
		self.assertEqual(second["status"], "Pending")
		self.assertEqual(create_and_send.call_count, 2)

	@patch("essdee_yrp.purchase_order_approval.frappe.throw", side_effect=RuntimeError("locked"))
	@patch("essdee_yrp.purchase_order_approval.get_live_request")
	def test_live_request_blocks_edits_but_error_does_not(self, get_live, throw):
		from essdee_yrp.purchase_order_approval import _validate_not_locked_for_edit

		get_live.return_value = frappe._dict({"name": "REQ", "status": "Pending"})
		with self.assertRaisesRegex(RuntimeError, "locked"):
			_validate_not_locked_for_edit(self._doc())
		get_live.return_value = frappe._dict({"name": "REQ", "status": "Error"})
		_validate_not_locked_for_edit(self._doc())

	@patch("essdee_yrp.purchase_order_approval.finish_request_message")
	@patch("essdee_yrp.purchase_order_approval.now_datetime", return_value="2026-10-05")
	@patch("essdee_yrp.purchase_order_approval.frappe.get_doc")
	@patch("essdee_yrp.purchase_order_approval.get_live_request")
	@patch("essdee_yrp.purchase_order_approval._current_user", return_value="manager@example.com")
	def test_desk_finalization_closes_live_message(
		self, current_user, get_live, get_doc, now, finish
	):
		from essdee_yrp.purchase_order_approval import finalize_live_request

		get_live.return_value = frappe._dict({"name": "REQ", "status": "Pending"})
		request = Mock()
		get_doc.return_value = request
		finalize_live_request("YRP-PO-0012", "Approved", "Approve PO")
		self.assertEqual(request.db_set.call_args.args[0]["status"], "Approved")
		finish.assert_called_once_with(request, "Approve PO", "manager@example.com")
