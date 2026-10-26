from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import ipd_ui
from essdee_yrp.merch import ipd_workspace as workspace
from essdee_yrp.merch.ipd import revert_alerts
from essdee_yrp.telegram_approval.client import TelegramAPIError


def approved_ipd():
	return SimpleNamespace(
		name="TEST-IPD",
		item="TEST-ITEM",
		check_permission=Mock(),
		add_comment=Mock(),
	)


def recipient(chat_id, enabled=1, name=None):
	return frappe._dict(recipient_name=name, telegram_chat_id=chat_id, enabled=enabled)


class TestIpdRevertReason(IntegrationTestCase):
	def revert(self, reason, doc=None):
		doc = doc or approved_ipd()
		with (
			patch.object(ipd_ui, "get_approval_roles", return_value=["System Manager"]),
			patch.object(ipd_ui.frappe, "get_roles", return_value=["System Manager"]),
			patch.object(ipd_ui.frappe, "get_doc", return_value=doc),
			patch.object(ipd_ui.attribute_db, "set_value") as set_value,
			patch.object(ipd_ui.frappe, "clear_document_cache"),
			patch.object(ipd_ui, "get_fullname", return_value="Senior Merch"),
			patch.object(ipd_ui, "queue_revert_alert") as queue_alert,
		):
			result = ipd_ui.revert_ipd_approval("TEST-IPD", reason)
		return result, doc, set_value, queue_alert

	def test_blank_reason_is_refused_before_any_change(self):
		for reason in (None, "", "   \n "):
			with (
				self.subTest(reason=reason),
				patch.object(ipd_ui, "get_approval_roles", return_value=["System Manager"]),
				patch.object(ipd_ui.frappe, "get_roles", return_value=["System Manager"]),
				patch.object(ipd_ui.frappe, "get_doc") as get_doc,
				patch.object(ipd_ui, "queue_revert_alert") as queue_alert,
				self.assertRaisesRegex(frappe.ValidationError, "Enter a reason for reverting the approval."),
			):
				ipd_ui.revert_ipd_approval("TEST-IPD", reason)
			get_doc.assert_not_called()
			queue_alert.assert_not_called()

	def test_reason_is_recorded_as_timeline_comment(self):
		result, doc, set_value, _queue = self.revert("  Wrong <b>size</b> ratio \n")
		self.assertEqual(result, {"status": "success"})
		set_value.assert_called_once()
		doc.add_comment.assert_called_once_with(
			"Comment", "Approval reverted by Senior Merch: Wrong &lt;b&gt;size&lt;/b&gt; ratio"
		)

	def test_revert_queues_alert_with_stripped_reason(self):
		_result, doc, _set_value, queue_alert = self.revert(" Fabric changed ")
		queue_alert.assert_called_once_with(doc, "Fabric changed")

	def test_workspace_command_passes_payload_reason(self):
		doc = approved_ipd()
		with patch.object(workspace.ipd_ui, "revert_ipd_approval") as revert:
			workspace.revert_approval(doc, {"reason": "Fabric changed"})
		revert.assert_called_once_with("TEST-IPD", "Fabric changed")


class TestIpdRevertAlerts(IntegrationTestCase):
	def test_message_lists_ipd_user_time_and_reason(self):
		message = revert_alerts.get_revert_alert_message(
			approved_ipd(), "Senior Merch", "26-10-2026 14:05", "Fabric changed"
		)
		self.assertEqual(
			message,
			"IPD Approval Reverted\nIPD: TEST-IPD (TEST-ITEM)\nBy: Senior Merch\n"
			"At: 26-10-2026 14:05\nReason: Fabric changed",
		)

	def test_alert_is_queued_after_commit_for_enabled_recipients_only(self):
		settings = SimpleNamespace(
			ipd_revert_alert_recipients=[recipient("111"), recipient("222", enabled=0), recipient("-333")]
		)
		with (
			patch.object(revert_alerts.frappe, "get_cached_doc", return_value=settings),
			patch.object(revert_alerts.frappe, "enqueue") as enqueue,
			patch.object(revert_alerts, "get_fullname", return_value="Senior Merch"),
		):
			revert_alerts.queue_revert_alert(approved_ipd(), "Fabric changed")
		enqueue.assert_called_once()
		args, kwargs = enqueue.call_args
		self.assertEqual(args, ("essdee_yrp.merch.ipd.revert_alerts.send_revert_alert",))
		self.assertEqual(kwargs["queue"], "short")
		self.assertTrue(kwargs["enqueue_after_commit"])
		self.assertEqual(kwargs["chat_ids"], ["111", "-333"])
		self.assertIn("Reason: Fabric changed", kwargs["message"])
		self.assertIn("By: Senior Merch", kwargs["message"])

	def test_nothing_is_queued_without_recipients(self):
		settings = SimpleNamespace(ipd_revert_alert_recipients=[recipient("222", enabled=0)])
		with (
			patch.object(revert_alerts.frappe, "get_cached_doc", return_value=settings),
			patch.object(revert_alerts.frappe, "enqueue") as enqueue,
		):
			revert_alerts.queue_revert_alert(approved_ipd(), "Fabric changed")
		enqueue.assert_not_called()

	def telegram_settings(self, enabled=1, token="token"):
		return SimpleNamespace(enabled=enabled, get_password=Mock(return_value=token))

	def test_send_messages_every_recipient_and_logs_failures(self):
		client = Mock()
		client.send_message.side_effect = [TelegramAPIError("chat not found"), None]
		with (
			patch.object(revert_alerts.frappe, "get_cached_doc", return_value=self.telegram_settings()),
			patch.object(revert_alerts, "TelegramClient", return_value=client),
			patch.object(revert_alerts.frappe, "log_error") as log_error,
		):
			revert_alerts.send_revert_alert(["111", "-333"], "IPD Approval Reverted")
		self.assertEqual(
			[call.args for call in client.send_message.call_args_list],
			[("111", "IPD Approval Reverted"), ("-333", "IPD Approval Reverted")],
		)
		log_error.assert_called_once()

	def test_send_is_skipped_when_telegram_is_disabled_or_has_no_token(self):
		for settings in (self.telegram_settings(enabled=0), self.telegram_settings(token=None)):
			with (
				self.subTest(settings=settings),
				patch.object(revert_alerts.frappe, "get_cached_doc", return_value=settings),
				patch.object(revert_alerts, "TelegramClient") as client_class,
			):
				revert_alerts.send_revert_alert(["111"], "IPD Approval Reverted")
			client_class.assert_not_called()
