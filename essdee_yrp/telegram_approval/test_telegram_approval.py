import json
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
import requests
from datetime import datetime
from jinja2 import Template


class TestTelegramRuntimeContract(TestCase):
	def _call(self, method, *args):
		while hasattr(method, "__wrapped__"):
			method = method.__wrapped__
		return method(*args)

	def test_runtime_uses_sd_yrp_doctype_names(self):
		from essdee_yrp.telegram_approval import service

		self.assertEqual(service.SETTINGS_DOCTYPE, "SD YRP Telegram Approval Settings")
		self.assertEqual(service.REQUEST_DOCTYPE, "SD YRP Telegram Approval Request")

	@patch("essdee_yrp.telegram_approval.client.requests.post")
	def test_client_never_exposes_bot_token_on_connection_error(self, post):
		from essdee_yrp.telegram_approval.client import TelegramAPIError, TelegramClient

		post.side_effect = requests.ConnectionError("URL contained secret-token")
		with self.assertRaises(TelegramAPIError) as error:
			TelegramClient("secret-token").get_me()
		self.assertNotIn("secret-token", str(error.exception))

	@patch("essdee_yrp.telegram_approval.api.frappe.msgprint")
	@patch("essdee_yrp.telegram_approval.api._", side_effect=lambda value: value)
	@patch("essdee_yrp.telegram_approval.api.get_client")
	@patch("essdee_yrp.telegram_approval.api.get_settings")
	@patch("essdee_yrp.telegram_approval.api.frappe.only_for")
	def test_configure_webhook_uses_essdee_endpoint(
		self, only_for, get_settings, get_client, translate, msgprint
	):
		from essdee_yrp.telegram_approval.api import configure_webhook

		settings = Mock()
		settings.bot_token = "configured"
		settings.webhook_secret = "existing"
		settings.public_webhook_base_url = "https://erp.example.com/"
		settings.get_password.return_value = "secret"
		get_settings.return_value = settings
		result = self._call(configure_webhook)
		self.assertEqual(
			result["url"],
			"https://erp.example.com/api/method/essdee_yrp.telegram_approval.api.webhook",
		)
		get_client.return_value.set_webhook.assert_called_once_with(result["url"], "secret")

	@patch("essdee_yrp.telegram_approval.api._process_callback_query")
	@patch("essdee_yrp.telegram_approval.api.get_settings")
	@patch("essdee_yrp.telegram_approval.api.frappe")
	def test_webhook_compares_secret_before_dispatch(self, frappe_module, get_settings, process):
		from essdee_yrp.telegram_approval.api import webhook

		settings = Mock(enabled=1, webhook_secret="set")
		settings.get_password.return_value = "expected-secret"
		get_settings.return_value = settings
		frappe_module.get_request_header.return_value = "expected-secret"
		frappe_module.request.get_json.return_value = {"callback_query": {"id": "CB-1"}}
		with patch("essdee_yrp.telegram_approval.api.hmac.compare_digest", return_value=True) as compare:
			self.assertEqual(self._call(webhook), {"ok": True})
		compare.assert_called_once_with("expected-secret", "expected-secret")
		process.assert_called_once_with({"id": "CB-1"})

	def test_clean_error_strips_html_and_truncates(self):
		from essdee_yrp.telegram_approval.api import _clean_error

		cleaned = _clean_error(Exception("<b>Denied</b>" + "x" * 300))
		self.assertFalse("<" in cleaned or ">" in cleaned)
		self.assertLessEqual(len(cleaned), 200)


class TestTelegramCallbackSecurity(TestCase):
	def setUp(self):
		self.translation = patch("essdee_yrp.telegram_approval.api._", side_effect=lambda value: value)
		self.translation.start()

	def tearDown(self):
		self.translation.stop()

	def _request(self, **overrides):
		values = {
			"name": "REQ123",
			"status": "Pending",
			"group_chat_id": "-100123",
			"telegram_message_id": "55",
			"route_snapshot": json.dumps({"process_type": "Field State"}),
			"reference_doctype": "Purchase Order",
			"reference_name": "YRP-PO-0012",
			"state_field": "status",
			"source_value": "Pending Approval",
		}
		values.update(overrides)
		return frappe._dict(values)

	def _callback(self, **overrides):
		values = {
			"id": "CB-1",
			"data": "ta:REQ123:a",
			"message": {"chat": {"id": "-100123"}, "message_id": "55"},
			"from": {"id": "7788"},
		}
		values.update(overrides)
		return values

	@patch("essdee_yrp.telegram_approval.api._answer_callback")
	@patch("essdee_yrp.telegram_approval.api.get_client")
	@patch("essdee_yrp.telegram_approval.api.frappe")
	def test_callback_locks_request_row_and_rejects_repeated_action(
		self, frappe_module, get_client, answer
	):
		from essdee_yrp.telegram_approval.api import _process_callback_query

		frappe_module.db.exists.return_value = True
		frappe_module.get_doc.return_value = self._request(status="Approved")
		_process_callback_query(self._callback())
		frappe_module.db.sql.assert_called_once_with(
			"select name from `tabSD YRP Telegram Approval Request` where name = %s for update",
			"REQ123",
		)
		answer.assert_called_once()
		frappe_module.set_user.assert_not_called()

	@patch("essdee_yrp.telegram_approval.api._answer_callback")
	@patch("essdee_yrp.telegram_approval.api.get_client")
	@patch("essdee_yrp.telegram_approval.api.frappe")
	def test_wrong_group_is_rejected_before_membership_lookup(self, frappe_module, get_client, answer):
		from essdee_yrp.telegram_approval.api import _process_callback_query

		frappe_module.db.exists.return_value = True
		frappe_module.get_doc.return_value = self._request()
		_process_callback_query(
			self._callback(message={"chat": {"id": "-999"}, "message_id": "55"})
		)
		get_client.return_value.get_chat_member.assert_not_called()
		answer.assert_called_once()

	@patch("essdee_yrp.telegram_approval.api._answer_callback")
	@patch("essdee_yrp.telegram_approval.api.get_client")
	@patch("essdee_yrp.telegram_approval.api.frappe")
	def test_non_member_is_rejected(self, frappe_module, get_client, answer):
		from essdee_yrp.telegram_approval.api import _process_callback_query

		frappe_module.db.exists.return_value = True
		frappe_module.get_doc.return_value = self._request()
		get_client.return_value.get_chat_member.return_value = {"status": "left"}
		_process_callback_query(self._callback())
		frappe_module.db.get_value.assert_not_called()
		answer.assert_called_once()

	@patch("essdee_yrp.telegram_approval.api._answer_callback")
	@patch("essdee_yrp.telegram_approval.api.get_client")
	@patch("essdee_yrp.telegram_approval.api.frappe")
	def test_unmapped_member_is_rejected(self, frappe_module, get_client, answer):
		from essdee_yrp.telegram_approval.api import _process_callback_query

		frappe_module.db.exists.return_value = True
		frappe_module.get_doc.return_value = self._request()
		get_client.return_value.get_chat_member.return_value = {"status": "member"}
		frappe_module.db.get_value.return_value = None
		_process_callback_query(self._callback())
		frappe_module.db.get_value.assert_called_once_with(
			"User", {"telegram_user_id": "7788", "enabled": 1}, "name"
		)
		answer.assert_called_once()


class TestTelegramSettingsValidation(TestCase):
	def _raise(self, message, *args, **kwargs):
		raise RuntimeError(message)

	@patch(
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_telegram_approval_settings.sd_yrp_telegram_approval_settings.frappe.throw"
	)
	@patch(
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_telegram_approval_settings.sd_yrp_telegram_approval_settings._",
		side_effect=lambda value: value,
	)
	def test_duplicate_enabled_routes_are_rejected(self, translate, throw):
		from essdee_yrp.essdee_yrp.doctype.sd_yrp_telegram_approval_settings.sd_yrp_telegram_approval_settings import (
			SDYRPTelegramApprovalSettings,
		)

		throw.side_effect = self._raise
		route = frappe._dict(
			{
				"enabled": 1,
				"reference_doctype": "YRP Process Cost",
				"trigger_field": "workflow_state",
				"trigger_value": "Approval Pending",
				"group_chat_id": "-100123",
				"process_type": "Workflow",
			}
		)
		settings = frappe._dict({"enabled": 0, "routes": [route, frappe._dict(route)]})
		with self.assertRaisesRegex(RuntimeError, "Duplicate"):
			SDYRPTelegramApprovalSettings.validate(settings)


class TestPurchaseOrderTelegramRuntime(TestCase):
	def setUp(self):
		self.render_template = patch(
			"essdee_yrp.telegram_approval.renderers.frappe.render_template",
			side_effect=lambda template, context: Template(template).render(context),
		)
		self.format_currency = patch(
			"essdee_yrp.telegram_approval.renderers._format_currency",
			side_effect=lambda value: f"{float(value or 0):,.2f}",
		)
		self.format_date = patch(
			"essdee_yrp.telegram_approval.renderers.format_date",
			side_effect=lambda value: datetime.strptime(str(value), "%Y-%m-%d").strftime("%d-%m-%Y"),
		)
		self.translation = patch(
			"essdee_yrp.telegram_approval.adapters._", side_effect=lambda value: value
		)
		for item in (self.render_template, self.format_currency, self.format_date, self.translation):
			item.start()

	def tearDown(self):
		for item in (self.translation, self.format_date, self.format_currency, self.render_template):
			item.stop()

	def _route(self, **overrides):
		values = {
			"process_type": "Field State",
			"target_field": "status",
			"trigger_field": "status",
			"trigger_value": "Pending Approval",
			"approve_action": "Approve PO",
			"reject_action": "Reject PO",
			"approve_value": "Ordered",
			"reject_value": "Draft",
			"approve_roles": "System Manager",
			"reject_roles": "System Manager",
		}
		values.update(overrides)
		return frappe._dict(values)

	def _doc(self, status="Pending Approval"):
		doc = Mock()
		doc.doctype = "Purchase Order"
		doc.name = "YRP-PO-0012"
		doc.status = status
		doc.get.side_effect = lambda key: getattr(doc, key)
		doc.meta.has_field.return_value = True
		return doc

	def test_purchase_order_message_includes_every_target_row(self):
		from essdee_yrp.purchase_order_approval import PURCHASE_ORDER_MESSAGE_TEMPLATE
		from essdee_yrp.telegram_approval.renderers import render_message

		doc = frappe._dict(
			{
				"doctype": "Purchase Order",
				"name": "YRP-PO-0012",
				"supplier_name": "Yarn Supplier",
				"supplier": "SUP-1",
				"transaction_date": "2026-10-05",
				"po_date": "2026-10-05",
				"grand_total": 1275,
				"items": [
					frappe._dict({"item_code": "YARN-RED", "qty": 10, "lot": "LOT-1", "rate": 75}),
					frappe._dict({"item_code": "YARN-BLUE", "qty": 5, "lot": "LOT-2", "rate": 105}),
				],
			}
		)
		message = render_message(
			doc,
			frappe._dict({"trigger_value": "Pending Approval", "message_template": PURCHASE_ORDER_MESSAGE_TEMPLATE}),
		)
		for value in ("YRP-PO-0012", "Yarn Supplier", "05-10-2026", "YARN-RED", "LOT-1", "YARN-BLUE", "LOT-2", "1,275.00"):
			self.assertIn(value, message)

	@patch("essdee_yrp.telegram_approval.service._expire_stale_requests")
	@patch("essdee_yrp.telegram_approval.service.frappe.enqueue")
	@patch("essdee_yrp.telegram_approval.service.get_settings")
	def test_purchase_order_document_event_is_manual_only(self, get_settings, enqueue, expire):
		from essdee_yrp.telegram_approval.service import handle_document_event

		get_settings.return_value = frappe._dict(
			{
				"enabled": 1,
				"routes": [frappe._dict({
					"name": "PO-ROUTE", "enabled": 1, "reference_doctype": "Purchase Order",
					"trigger_field": "status", "trigger_value": "Pending Approval",
				})],
			}
		)
		doc = frappe._dict({"doctype": "Purchase Order", "name": "YRP-PO-0012", "status": "Pending Approval", "flags": {}})
		doc.get_doc_before_save = Mock(return_value=frappe._dict({"status": "Draft"}))
		handle_document_event(doc)
		enqueue.assert_not_called()
		expire.assert_called_once_with(doc)

	@patch("essdee_yrp.telegram_approval.service._expire_stale_requests")
	@patch("essdee_yrp.telegram_approval.service.get_settings")
	def test_submitted_purchase_order_defers_to_on_submit_finalization(self, get_settings, expire):
		from essdee_yrp.telegram_approval.service import handle_document_event

		get_settings.return_value = frappe._dict(
			{
				"enabled": 1,
				"routes": [
					frappe._dict({"enabled": 1, "reference_doctype": "Purchase Order"})
				],
			}
		)
		doc = frappe._dict(
			{
				"doctype": "Purchase Order",
				"name": "YRP-PO-0012",
				"docstatus": 1,
				"status": "To Receive",
			}
		)
		handle_document_event(doc)
		expire.assert_not_called()

	@patch("essdee_yrp.telegram_approval.adapters.frappe.get_doc")
	@patch("essdee_yrp.telegram_approval.adapters._current_user", return_value="manager@example.com")
	@patch("essdee_yrp.purchase_order_approval.approve_purchase_order")
	def test_telegram_approve_uses_source_marker_but_target_controller_status(
		self, approve, current_user, get_doc
	):
		from essdee_yrp.telegram_approval.adapters import _apply_purchase_order_action

		doc = self._doc()
		updated = self._doc(status="To Receive")
		updated.docstatus = 1
		get_doc.return_value = updated
		result = _apply_purchase_order_action(
			doc, self._route(), "a", "Approve PO", "status", "Ordered"
		)
		approve.assert_called_once_with("YRP-PO-0012")
		self.assertEqual(result.status, "To Receive")

	def test_target_value_manipulation_is_rejected(self):
		from essdee_yrp.telegram_approval.adapters import (
			TelegramApprovalStateError,
			_apply_purchase_order_action,
		)

		with self.assertRaises(TelegramApprovalStateError):
			_apply_purchase_order_action(
				self._doc(), self._route(approve_value="Draft"), "a", "Approve PO", "status", "Draft"
			)
