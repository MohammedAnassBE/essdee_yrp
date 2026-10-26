import frappe
from frappe.utils import format_datetime, get_fullname, now_datetime

from essdee_yrp.telegram_approval.client import TelegramClient
from essdee_yrp.telegram_approval.service import SETTINGS_DOCTYPE as TELEGRAM_SETTINGS_DOCTYPE

MRP_SETTINGS_DOCTYPE = "SD YRP MRP Settings"


def get_revert_alert_message(doc, reverted_by, reverted_at, reason):
	return "\n".join(
		(
			"IPD Approval Reverted",
			f"IPD: {doc.name} ({doc.item})",
			f"By: {reverted_by}",
			f"At: {reverted_at}",
			f"Reason: {reason}",
		)
	)


def get_revert_alert_chat_ids():
	settings = frappe.get_cached_doc(MRP_SETTINGS_DOCTYPE)
	return [
		row.telegram_chat_id.strip()
		for row in settings.ipd_revert_alert_recipients or []
		if row.enabled and (row.telegram_chat_id or "").strip()
	]


def queue_revert_alert(doc, reason):
	"""Telegram the enabled IPD revert alert recipients once the revert commits."""
	chat_ids = get_revert_alert_chat_ids()
	if not chat_ids:
		return
	message = get_revert_alert_message(
		doc,
		get_fullname(frappe.session.user),
		format_datetime(now_datetime(), "dd-MM-yyyy HH:mm"),
		reason,
	)
	frappe.enqueue(
		"essdee_yrp.merch.ipd.revert_alerts.send_revert_alert",
		queue="short",
		enqueue_after_commit=True,
		chat_ids=chat_ids,
		message=message,
	)


def send_revert_alert(chat_ids, message):
	settings = frappe.get_cached_doc(TELEGRAM_SETTINGS_DOCTYPE)
	token = settings.enabled and settings.get_password("bot_token", raise_exception=False)
	if not token:
		return
	client = TelegramClient(token)
	for chat_id in chat_ids:
		try:
			client.send_message(chat_id, message)
		except Exception:
			frappe.log_error(title=f"IPD revert alert to {chat_id} failed")
