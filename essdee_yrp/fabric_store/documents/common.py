"""Permission-safe shared contract for Fabric Store document workspaces."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import frappe
from frappe import _
from frappe.model import get_permitted_fields
from frappe.utils import cint

from essdee_yrp.print_registry import get_document_print_formats

EFFECTIVE_FIELD_TYPES = {
	"Check",
	"Currency",
	"Data",
	"Date",
	"Datetime",
	"Dynamic Link",
	"Float",
	"Int",
	"Link",
	"Long Text",
	"Percent",
	"Select",
	"Small Text",
	"Text",
	"Time",
}


def _permitted_fields(doctype: str, permission_type: str) -> set[str]:
	try:
		return set(get_permitted_fields(doctype, permission_type=permission_type))
	except TypeError:
		return set(get_permitted_fields(doctype, permission_type))


def _document_meta(doc):
	"""Return controller metadata for real documents and lightweight test doubles."""

	return getattr(doc, "meta", None) or frappe.get_meta(doc.doctype)


def get_allow_on_submit_fields(doc, fieldnames: Iterable[str] | None = None) -> list[str]:
	"""Return visible, writable fields that Frappe permits after submission."""

	meta = _document_meta(doc)
	permitted = _permitted_fields(doc.doctype, "write")
	write_permlevels = set(meta.get_permlevel_access(permission_type="write"))
	requested = list(fieldnames) if fieldnames is not None else [
		field.fieldname for field in (meta.fields or []) if field.fieldname
	]
	allowed = []
	for fieldname in requested:
		field = meta.get_field(fieldname)
		writable = fieldname in permitted or bool(
			field
			and field.get("fieldtype") in {"Table", "Table MultiSelect"}
			and cint(field.get("permlevel")) in write_permlevels
		)
		if (
			field is None
			or not writable
			or not bool(field.get("allow_on_submit"))
			or bool(field.get("hidden"))
			or bool(field.get("read_only"))
		):
			continue
		allowed.append(fieldname)
	return allowed


def get_document_permissions(doctype: str, doc=None) -> dict[str, bool]:
	"""Return effective permissions constrained by the document lifecycle."""

	docstatus = cint(doc.docstatus) if doc is not None else None

	def allowed(ptype: str, *, record_sensitive: bool = True) -> bool:
		kwargs = {"ptype": ptype}
		if doc is not None and record_sensitive:
			kwargs["doc"] = doc
		return bool(frappe.has_permission(doctype, **kwargs))

	permissions = {
		"can_read": allowed("read"),
		"can_create": allowed("create", record_sensitive=False),
		"can_write": allowed("write"),
		"can_update_after_submit": False,
		"can_submit": allowed("submit"),
		"can_cancel": allowed("cancel"),
		"can_amend": allowed("amend"),
		"can_print": allowed("print"),
	}
	raw_write = permissions["can_write"]
	if doc is not None:
		permissions["can_update_after_submit"] = bool(
			docstatus == 1 and raw_write and get_allow_on_submit_fields(doc)
		)
		permissions["can_write"] = bool(docstatus == 0 and permissions["can_write"])
		permissions["can_submit"] = bool(docstatus == 0 and permissions["can_submit"])
		permissions["can_cancel"] = bool(docstatus == 1 and permissions["can_cancel"])
		permissions["can_amend"] = bool(docstatus == 2 and permissions["can_amend"])
	return permissions


COMPLETION_STOCK_ENTRY_PURPOSES = {
	"YRP Delivery Challan": "DC Completion",
	"YRP Goods Received Note": "GRN Completion",
}


def get_draft_completion_stock_entry(doctype: str, name: str) -> str | None:
	"""Return the newest draft completion Stock Entry for a DC or GRN, if any.

	Native submit validation caps each draft at the pending quantity, so older
	duplicate drafts stay safe and surface one at a time after a discard.
	"""

	drafts = frappe.get_all(
		"YRP Stock Entry",
		filters={
			"against": doctype,
			"against_id": name,
			"purpose": COMPLETION_STOCK_ENTRY_PURPOSES[doctype],
			"docstatus": 0,
		},
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	return drafts[0] if drafts else None


def get_effective_fields(doc, fieldnames: Iterable[str]) -> list[dict]:
	"""Serialize readable allowlisted fields with their effective UI rules."""

	meta = _document_meta(doc)
	permitted = _permitted_fields(doc.doctype, "read")
	allow_on_submit = set(get_allow_on_submit_fields(doc, fieldnames))
	fields = []
	for fieldname in fieldnames:
		field = meta.get_field(fieldname)
		if (
			field is None
			or fieldname not in permitted
			or bool(field.hidden)
			or field.fieldtype not in EFFECTIVE_FIELD_TYPES
		):
			continue
		fields.append(
			{
				"fieldname": fieldname,
				"label": field.label or fieldname.replace("_", " ").title(),
				"fieldtype": field.fieldtype,
				"options": field.options or "",
				**({"link_doctype": doc.get(field.options)} if field.fieldtype == "Dynamic Link" else {}),
				"reqd": bool(field.reqd),
				"allow_on_submit": bool(field.get("allow_on_submit")),
				"read_only": bool(
					field.read_only
					or (cint(doc.docstatus) != 0 and fieldname not in allow_on_submit)
				),
				"depends_on": field.depends_on or "",
				"mandatory_depends_on": field.mandatory_depends_on or "",
				"read_only_depends_on": field.read_only_depends_on or "",
				"value": doc.get(fieldname),
			}
		)
	return fields


def filter_authorized_capabilities(
	capabilities: Mapping[str, Mapping] | None,
	permissions: Mapping[str, bool],
) -> dict[str, dict]:
	"""Return only eligible capabilities that the current user may invoke."""

	authorized = {}
	for action, capability in (capabilities or {}).items():
		permission = capability.get("permission")
		if capability.get("eligible", True) is False:
			continue
		if permission and not permissions.get(f"can_{permission}", False):
			continue
		authorized[action] = {
			key: value
			for key, value in capability.items()
			if key not in {"permission", "eligible"}
		}
	return authorized


def assert_expected_modified(doc, expected_modified: str | None) -> None:
	"""Reject writes based on a stale document snapshot."""

	if expected_modified and str(doc.modified) != str(expected_modified):
		frappe.throw(
			_("{0} changed after you opened it. Refresh and try again.").format(doc.name),
			frappe.TimestampMismatchError,
		)


def _notification_base_allowed(
	doc,
	doctype: str,
	*,
	hidden_statuses: Iterable[str] = (),
	supplier_key: str = "supplier",
	throw: bool = False,
) -> bool:
	available = bool(
		doc.name
		and cint(doc.docstatus) != 2
		and doc.get(supplier_key)
		and doc.get("status") not in set(hidden_statuses or ())
	)
	if not available:
		if throw:
			frappe.throw(_("Notifications are not available for this {0}.").format(_(doctype)))
		return False
	return bool(
		frappe.has_permission(
			doctype,
			ptype="write",
			doc=doc,
			throw=throw,
		)
	)


def _whatsapp_supplier_configuration(doctype: str, fallback_key: str) -> tuple[bool, str]:
	from yrp.whatsapp_notification import get_enabled_whatsapp_doctypes

	enabled = (get_enabled_whatsapp_doctypes() or {}).get("doctypes") or {}
	return doctype in enabled, enabled.get(doctype) or fallback_key


def _supplier_has_mobile(doc, supplier_key: str) -> bool:
	try:
		details = frappe.get_doc("Supplier", doc.get(supplier_key)).get_primary_contact_details()
	except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError):
		return False
	return bool((details or {}).get("mobile"))


def get_supplier_notification_capabilities(
	doc,
	doctype: str,
	*,
	hidden_statuses: Iterable[str] = (),
	supplier_key: str = "supplier",
) -> dict[str, bool]:
	"""Return only notification channels that can open a useful send panel."""

	available = {"sms": False, "whatsapp": False}
	sms_allowed = _notification_base_allowed(
		doc,
		doctype,
		hidden_statuses=hidden_statuses,
		supplier_key=supplier_key,
	)

	if sms_allowed and _supplier_has_mobile(doc, supplier_key):
		try:
			sms_settings = frappe.get_cached_doc("YRP SMS Settings")
			available["sms"] = bool(
				sms_settings.enabled
				and sms_settings.get_templates_for_doctype(doctype)
			)
		except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError):
			available["sms"] = False

	try:
		whatsapp_enabled, whatsapp_supplier_key = _whatsapp_supplier_configuration(
			doctype,
			supplier_key,
		)
		if (
			whatsapp_enabled
			and _notification_base_allowed(
				doc,
				doctype,
				hidden_statuses=hidden_statuses,
				supplier_key=whatsapp_supplier_key,
			)
			and _supplier_has_mobile(doc, whatsapp_supplier_key)
		):
			for name in frappe.get_all(
				"YRP WhatsApp Template",
				filters={"status": "APPROVED"},
				pluck="name",
			):
				if frappe.get_doc("YRP WhatsApp Template", name).is_applicable_for(doctype):
					available["whatsapp"] = True
					break
	except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError):
		available["whatsapp"] = False
	return available


def prepare_supplier_notification(
	doc,
	doctype: str,
	channel: str,
	*,
	hidden_statuses: Iterable[str] = (),
	supplier_key: str = "supplier",
) -> dict:
	"""Delegate notification context building to the established YRP services."""

	channel = str(channel or "").strip().lower()
	effective_supplier_key = supplier_key
	if channel in {"whatsapp", "whats_app"}:
		_channel_enabled, effective_supplier_key = _whatsapp_supplier_configuration(
			doctype,
			supplier_key,
		)
	_notification_base_allowed(
		doc,
		doctype,
		hidden_statuses=hidden_statuses,
		supplier_key=effective_supplier_key,
		throw=True,
	)
	if channel == "sms":
		from yrp.notification import get_flow_sms_context

		context = get_flow_sms_context(doctype, doc.name, effective_supplier_key)
	elif channel in {"whatsapp", "whats_app"}:
		from yrp.whatsapp_notification import get_whatsapp_context

		channel = "whatsapp"
		context = get_whatsapp_context(doctype, doc.name, effective_supplier_key)
	else:
		frappe.throw(_("Unsupported notification channel: {0}").format(channel or _("empty")))
	return {"channel": channel, "context": context}


def send_supplier_notification(
	doc,
	doctype: str,
	channel: str,
	payload: Mapping,
	*,
	hidden_statuses: Iterable[str] = (),
	supplier_key: str = "supplier",
) -> dict:
	"""Delegate a permission-checked send to the existing logged YRP endpoint."""

	channel = str(channel or "").strip().lower()
	effective_supplier_key = supplier_key
	if channel in {"whatsapp", "whats_app"}:
		_channel_enabled, effective_supplier_key = _whatsapp_supplier_configuration(
			doctype,
			supplier_key,
		)
	_notification_base_allowed(
		doc,
		doctype,
		hidden_statuses=hidden_statuses,
		supplier_key=effective_supplier_key,
		throw=True,
	)
	if channel == "sms":
		from yrp.notification import send_flow_sms_notification

		result = send_flow_sms_notification(
			doctype,
			doc.name,
			payload.get("template_name"),
			mobile_no=payload.get("mobile_no"),
			params=payload.get("params"),
			supplier_key=effective_supplier_key,
		)
	elif channel in {"whatsapp", "whats_app"}:
		from yrp.whatsapp_notification import send_whatsapp_notification

		channel = "whatsapp"
		result = send_whatsapp_notification(
			doctype,
			doc.name,
			payload.get("template_name"),
			payload.get("language_code"),
			params=payload.get("params"),
			mobile_no=payload.get("mobile_no"),
			header_file=payload.get("header_file"),
			supplier_key=effective_supplier_key,
		)
	else:
		frappe.throw(_("Unsupported notification channel: {0}").format(channel or _("empty")))
	return {"channel": channel, "result": result}


def get_workspace_base(
	doc,
	*,
	fieldnames: Iterable[str],
	totals: Iterable[str] = (),
	capabilities: Mapping[str, Mapping] | None = None,
) -> dict:
	"""Build the stable base payload shared by routed and embedded workspaces."""

	permissions = get_document_permissions(doc.doctype, doc)
	docstatus = cint(doc.docstatus)
	record = {
		"doctype": doc.doctype,
		"name": doc.name,
		"docstatus": docstatus,
		"status": {0: _("Draft"), 1: _("Submitted"), 2: _("Cancelled")}.get(
			docstatus, _("Draft")
		),
		"modified": doc.get("modified"),
	}
	total_values = []
	for fieldname in totals:
		field = doc.meta.get_field(fieldname)
		total_values.append(
			{
				"fieldname": fieldname,
				"label": (field.label if field and field.label else fieldname.replace("_", " ").title()),
				"value": doc.get(fieldname),
			}
		)
	return {
		"record": record,
		"fields": get_effective_fields(doc, fieldnames),
		"allow_on_submit_fields": get_allow_on_submit_fields(doc),
		"totals": total_values,
		"permissions": permissions,
		"capabilities": filter_authorized_capabilities(capabilities, permissions),
		"print_formats": get_document_print_formats(doc) if permissions["can_print"] else [],
	}
