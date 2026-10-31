"""Purchase Order coordination service for the Fabric Store workspace."""

from __future__ import annotations

from collections.abc import Mapping

import frappe
from frappe import _
from frappe.utils import cint, formatdate, getdate
from yrp.stock.api import get_stock_dimensions_for_ui
from yrp.stock.save_stock_items import group_items_for_ui, ungroup_items_from_ui
from yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note import (
	get_purchase_order_defaults,
)
from yrp.yrp.doctype.yrp_purchase_order.yrp_purchase_order import (
	YRPPurchaseOrderMixin,
	close_purchase_order,
	get_purchase_order_manager_roles,
	refresh_status,
	reopen_purchase_order,
)

from essdee_yrp.fabric_store.documents.common import (
	assert_expected_modified,
	filter_authorized_capabilities,
	get_document_permissions,
	get_effective_fields,
	get_supplier_notification_capabilities,
	get_workspace_base,
	prepare_supplier_notification,
	send_supplier_notification,
)
from essdee_yrp.print_registry import get_document_print_formats
from essdee_yrp.purchase_order_against import AGAINST_FIELDS, get_purchase_order_against
from essdee_yrp.purchase_order_approval import (
	PENDING_APPROVAL_STATUS,
	SYSTEM_MANAGER_ROLE,
	_validate_not_locked_for_edit,
	approve_purchase_order,
	get_live_request,
	reject_purchase_order,
	send_purchase_order_request,
	validate_approval_submit,
)
from essdee_yrp.purchase_order_lots import update_po_lot_links

# Keeping the controller type explicit documents the authority used by doc.insert,
# doc.save, and doc.submit; this service never duplicates its price or tax maths.
PURCHASE_ORDER_CONTROLLER = YRPPurchaseOrderMixin

PURCHASE_ORDER_FIELDS = (
	"supplier",
	"supplier_name",
	"transaction_date",
	"schedule_date",
	"company",
	"set_warehouse",
	"deliver_to_supplier",
	"default_delivery_location",
	"default_lot",
	"currency",
	"terms_and_condition",
	"comments",
	"open_status",
	"yrp_fulfillment_status",
	"approved_by",
	*AGAINST_FIELDS,
)

PURCHASE_ORDER_RECORD_FIELDS = (
	"status",
	"open_status",
	"yrp_fulfillment_status",
	"is_yrp_managed",
	"supplier",
	"supplier_name",
	"transaction_date",
	"schedule_date",
	"set_warehouse",
	"currency",
	"total",
	"grand_total",
)

PURCHASE_ORDER_TOTALS = (
	"total_qty",
	"total",
	"total_discount",
	"net_total",
	"total_tax",
	"total_taxes_and_charges",
	"grand_total",
)

PURCHASE_ORDER_EDITOR_FIELDS = (
	"naming_series",
	"supplier",
	"transaction_date",
	"schedule_date",
	"company",
	"set_warehouse",
	"deliver_to_supplier",
	"default_delivery_location",
	"currency",
	"terms_and_condition",
	"comments",
)

PURCHASE_ORDER_NOTIFICATION_HIDDEN_STATUSES = {
	"Closed",
	"Cancelled",
	"Partially Cancelled",
}


def _get_purchase_order(name: str, permission: str = "read"):
	doc = frappe.get_doc("Purchase Order", name)
	doc.check_permission(permission)
	return doc


def _dependency(adapter, name: str, default):
	return getattr(adapter, name, default) if adapter is not None else default


def _linked_lots(doc) -> list[str]:
	return list(
		dict.fromkeys(
			row.get("lot")
			for row in (doc.get("sd_lot") or [])
			if row.get("lot")
		)
	)


def _permission_filtered_related_rows(doctype: str, relationship_filters: dict) -> list[dict]:
	"""Resolve an exact relationship without bypassing row-level read permission.

	The relationship fields are custom fields and may not themselves be selectable by
	the current user.  Fetching only their linked names internally, then intersecting
	those names through ``get_list`` keeps the response permission filtered.
	"""

	linked_names = frappe.get_all(
		doctype,
		filters=relationship_filters,
		pluck="name",
		order_by="modified desc",
		limit_page_length=0,
	)
	if not linked_names:
		return []
	return [
		dict(row)
		for row in frappe.get_list(
			doctype,
			filters={"name": ["in", linked_names]},
			fields=["name", "docstatus", "modified"],
			order_by="modified desc",
			limit_page_length=100,
		)
	]


def _related_documents(doc, adapter=None) -> dict[str, list[dict]]:
	frappe_api = _dependency(adapter, "frappe", frappe)
	related = {"delivery_challans": [], "goods_received_notes": []}
	if frappe_api.has_permission("YRP Delivery Challan", ptype="read"):
		related["delivery_challans"] = _permission_filtered_related_rows(
			"YRP Delivery Challan",
			{"purchase_order": doc.name},
		)
	if frappe_api.has_permission("YRP Goods Received Note", ptype="read"):
		related["goods_received_notes"] = _permission_filtered_related_rows(
			"YRP Goods Received Note",
			{"against": "Purchase Order", "against_id": doc.name},
		)
	return related


def _approval_state(doc) -> dict:
	pending = bool(
		doc.get("is_yrp_managed")
		and cint(doc.docstatus) == 0
		and doc.get("status") == PENDING_APPROVAL_STATUS
	)
	live_request = get_live_request(doc.name) if pending else None
	return {
		"pending_approval": pending,
		"live_request": dict(live_request) if live_request else None,
	}


def _target_create_permission(doctype: str, adapter=None) -> bool:
	if adapter is not None:
		return bool(adapter._permission_flags(doctype).get("can_create"))
	return bool(frappe.has_permission(doctype, ptype="create"))


def _raw_purchase_order_permission(doc, permission: str, adapter=None) -> bool:
	"""Check a domain mutation without applying Draft-only workspace constraints."""

	frappe_api = _dependency(adapter, "frappe", frappe)
	return bool(frappe_api.has_permission("Purchase Order", ptype=permission, doc=doc))


def _goods_receipt_capability(doc, adapter=None) -> dict:
	if adapter is not None:
		return adapter._purchase_order_grn_capability(doc)
	if not _target_create_permission("YRP Goods Received Note"):
		return {
			"can_create": False,
			"reason": _("You do not have permission to create Goods Received Notes."),
		}
	if cint(doc.docstatus) != 1:
		return {"can_create": False, "reason": _("Submit this Purchase Order before creating a Goods Received Note.")}
	if doc.get("open_status") == "Close":
		return {"can_create": False, "reason": _("This Purchase Order is closed.")}
	if not doc.get("is_yrp_managed"):
		return {"can_create": False, "reason": _("Only YRP managed Purchase Orders can create a Goods Received Note here.")}
	try:
		defaults = get_purchase_order_defaults(doc.name)
	except (frappe.ValidationError, frappe.PermissionError) as error:
		return {"can_create": False, "reason": str(error)}
	if not defaults.get("items"):
		return {"can_create": False, "reason": _("No pending quantities remain to receive.")}
	return {"can_create": True, "reason": ""}


def _capability_candidates(doc, approval: Mapping, grn: Mapping, adapter=None) -> dict[str, dict]:
	docstatus = cint(doc.docstatus)
	roles = set(frappe.get_roles())
	is_manager = bool(roles.intersection(get_purchase_order_manager_roles()))
	is_approver = SYSTEM_MANAGER_ROLE in roles
	is_managed = bool(doc.get("is_yrp_managed"))
	is_open = doc.get("open_status") != "Close"
	can_update_submitted = _raw_purchase_order_permission(doc, "write", adapter)
	pending_approval = bool(approval.get("pending_approval"))
	has_live_request = bool(approval.get("live_request"))
	can_send_request = bool(
		pending_approval
		and not has_live_request
		and (
			adapter._permission_flags("Purchase Order").get("can_create")
			if adapter is not None
			else frappe.has_permission("Purchase Order", ptype="create")
		)
	)
	notifications = (
		get_supplier_notification_capabilities(
			doc,
			"Purchase Order",
			hidden_statuses=PURCHASE_ORDER_NOTIFICATION_HIDDEN_STATUSES,
		)
		if is_managed
		else {"sms": False, "whatsapp": False}
	)
	return {
		"save": {
			"label": _("Edit"),
			"permission": "write",
			"eligible": docstatus == 0 and not has_live_request,
		},
		"submit": {
			"label": _("Submit"),
			"permission": "submit",
			"eligible": docstatus == 0 and not pending_approval and not has_live_request,
		},
		"cancel": {"label": _("Cancel Document"), "permission": "cancel", "eligible": docstatus == 1},
		"amend": {"label": _("Amend"), "permission": "amend", "eligible": docstatus == 2},
		"refresh_status": {"label": _("Refresh Status"), "eligible": is_managed and can_update_submitted},
		"close": {"label": _("Close"), "eligible": is_managed and docstatus == 1 and is_open and is_manager},
		"reopen": {"label": _("Reopen"), "eligible": is_managed and docstatus == 1 and not is_open and is_manager},
		"send_approval_request": {"label": _("Send Request"), "eligible": can_send_request},
		"approve": {"label": _("Approve PO"), "eligible": pending_approval and is_approver},
		"reject": {"label": _("Reject PO"), "eligible": pending_approval and is_approver},
		"update_linked_lots": {"label": _("Manage Linked Lots"), "eligible": is_managed and docstatus == 1 and is_open and can_update_submitted},
		"create_delivery_challan": {
			"label": _("Create Delivery Challan"),
			"eligible": docstatus == 1 and _target_create_permission("YRP Delivery Challan", adapter),
			"work_order_required": True,
			"source_context": {"purchase_order": doc.name},
		},
		"create_goods_received_note": {
			"label": _("Create GRN"),
			"eligible": bool(grn.get("can_create")),
			"source_context": {"purchase_order": doc.name},
		},
		"prepare_sms": {"label": _("Send SMS"), "eligible": notifications["sms"]},
		"prepare_whatsapp": {
			"label": _("Send WhatsApp"),
			"eligible": notifications["whatsapp"],
		},
	}


def _legacy_workspace_base(doc, capabilities: Mapping, adapter) -> dict:
	record = adapter._serialize_document(doc, fields=PURCHASE_ORDER_RECORD_FIELDS)
	record.update(
		{
			fieldname: doc.get(fieldname)
			for fieldname in PURCHASE_ORDER_RECORD_FIELDS
			if fieldname not in {"doctype", "name", "docstatus", "modified"}
		}
	)
	permissions = record["permissions"]
	fields = [
		field
		for field in adapter._document_details(doc)
		if field["fieldname"] in set(PURCHASE_ORDER_FIELDS)
	]
	totals = []
	for fieldname in PURCHASE_ORDER_TOTALS:
		field = doc.meta.get_field(fieldname)
		totals.append(
			{
				"fieldname": fieldname,
				"label": field.label if field and field.label else fieldname.replace("_", " ").title(),
				"value": doc.get(fieldname),
			}
		)
	return {
		"record": record,
		"fields": fields,
		"totals": totals,
		"permissions": permissions,
		"capabilities": filter_authorized_capabilities(capabilities, permissions),
		"print_formats": adapter.get_document_print_formats(doc),
	}


def get_purchase_order_workspace(name: str, *, _adapter=None) -> dict:
	"""Return the complete permission-filtered Purchase Order workspace."""

	get_doc = _dependency(
		_adapter,
		"_get_supported_document",
		lambda doctype, docname: _get_purchase_order(docname),
	)
	doc = get_doc("Purchase Order", name)
	approval = _approval_state(doc)
	grn = _goods_receipt_capability(doc, _adapter)
	capability_candidates = _capability_candidates(doc, approval, grn, _adapter)
	if _adapter is not None:
		workspace = _legacy_workspace_base(doc, capability_candidates, _adapter)
		group_items = _adapter.group_items_for_ui
	else:
		workspace = get_workspace_base(
			doc,
			fieldnames=PURCHASE_ORDER_FIELDS,
			totals=PURCHASE_ORDER_TOTALS,
			capabilities=capability_candidates,
		)
		group_items = group_items_for_ui

	item_groups = group_items(doc.get("items") or [], "Purchase Order")
	workspace["record"].update(
		{
			fieldname: doc.get(fieldname)
			for fieldname in PURCHASE_ORDER_RECORD_FIELDS
			if fieldname not in {"doctype", "name", "docstatus", "modified"}
		}
	)
	workspace.update(
		{
			"matrices": {"items": item_groups},
			"related": _related_documents(doc, _adapter),
			"approval": approval,
			"linked_lots": _linked_lots(doc),
			# Compatibility aliases consumed by the existing Purchase Order page.
			"details": workspace["fields"],
			"item_groups": item_groups,
			"item_row_count": len(doc.get("items") or []),
			"grn": grn,
		}
	)
	return workspace


def get_purchase_order_editor(name: str | None = None, source=None, *, _adapter=None) -> dict:
	"""Return the grouped editor contract for a new or Draft Purchase Order."""

	frappe_api = _dependency(_adapter, "frappe", frappe)
	permission_flags = _dependency(_adapter, "_permission_flags", get_document_permissions)
	group_items = _dependency(_adapter, "group_items_for_ui", group_items_for_ui)
	stock_dimensions = _dependency(_adapter, "get_stock_dimensions_for_ui", get_stock_dimensions_for_ui)
	if name:
		get_doc = _dependency(
			_adapter,
			"_get_supported_document",
			lambda doctype, docname: _get_purchase_order(docname),
		)
		doc = get_doc("Purchase Order", name)
		frappe_api.has_permission("Purchase Order", ptype="write", doc=doc, throw=True)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only Draft Purchase Orders can be edited."))
		_validate_not_locked_for_edit(doc)
		permissions = permission_flags("Purchase Order", doc)
		if doc.get("status") == PENDING_APPROVAL_STATUS:
			permissions["can_submit"] = False
	else:
		frappe_api.has_permission("Purchase Order", ptype="create", throw=True)
		doc = frappe_api.new_doc("Purchase Order")
		doc.is_yrp_managed = 1
		source = source if isinstance(source, dict) else frappe.parse_json(source or "{}")
		if not isinstance(source, dict):
			frappe.throw(_("Source must be an object."))
		if source.get("duplicate_from"):
			original = _get_purchase_order(source["duplicate_from"])
			doc.update({fieldname: original.get(fieldname) for fieldname in PURCHASE_ORDER_EDITOR_FIELDS})
			rows = [row.as_dict() if callable(getattr(row, "as_dict", None)) else dict(row) for row in (original.get("items") or [])]
			setter = getattr(doc, "set", None)
			if callable(setter):
				setter("items", rows)
			else:
				doc["items"] = rows
		doc.update(get_purchase_order_against(source.get("against"), source.get("against_id")))
		permissions = {
			"can_create": True,
			"can_write": False,
			"can_submit": bool(frappe_api.has_permission("Purchase Order", ptype="submit")),
		}

	values = {fieldname: doc.get(fieldname) for fieldname in (*PURCHASE_ORDER_EDITOR_FIELDS, *AGAINST_FIELDS)}
	values["is_yrp_managed"] = 1
	dimensions = []
	for source in stock_dimensions():
		dimension = dict(source)
		dimension["locked"] = False
		dimensions.append(dimension)
	default_dimensions = get_purchase_order_default_dimensions(dimensions, frappe_api)
	return {
		"doctype": "Purchase Order",
		"name": doc.get("name") or "",
		"modified": doc.get("modified") or "",
		"values": values,
		"fields": get_effective_fields(doc, (*PURCHASE_ORDER_EDITOR_FIELDS, *AGAINST_FIELDS)),
		"item_groups": group_items(doc.get("items") or [], "Purchase Order"),
		"dimensions": dimensions,
		"locked_dimensions": [],
		"default_dimensions": default_dimensions,
		"item_filters": {
			"disabled": 0,
			"variant_of": ["is", "not set"],
			"is_purchase_item": 1,
			"is_stock_item": 1,
		},
		"price_validation_enabled": bool(
			cint(frappe_api.db.get_single_value("YRP Settings", "enable_price_validation"))
		),
		"permissions": {
			**permissions,
			"can_create_item_price": bool(
				frappe_api.has_permission("YRP Item Price", ptype="create")
			),
		},
	}


def get_purchase_order_default_dimensions(dimensions, frappe_api=frappe) -> dict:
	"""Prefill Received Type on new item rows from YRP Stock Settings."""
	if not any(dimension["fieldname"] == "received_type" for dimension in dimensions):
		return {}
	received_type = frappe_api.db.get_single_value("YRP Stock Settings", "default_received_type")
	return {"received_type": received_type} if received_type else {}


def save_purchase_order_document(
	values,
	*,
	name: str | None = None,
	submit: bool = False,
	expected_modified: str | None = None,
	_adapter=None,
) -> dict:
	"""Save using the Purchase Order controller and its pricing/tax hooks."""

	frappe_api = _dependency(_adapter, "frappe", frappe)
	ungroup_items = _dependency(_adapter, "ungroup_items_from_ui", ungroup_items_from_ui)
	values = values if isinstance(values, dict) else frappe.parse_json(values or "{}")
	item_details = values.get("item_details") or []
	if not isinstance(item_details, list) or not item_details:
		frappe.throw(_("Add at least one Item."))

	if name:
		get_doc = _dependency(
			_adapter,
			"_get_supported_document",
			lambda doctype, docname: _get_purchase_order(docname),
		)
		doc = get_doc("Purchase Order", name)
		frappe_api.has_permission("Purchase Order", ptype="write", doc=doc, throw=True)
		assert_expected_modified(doc, expected_modified)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only Draft Purchase Orders can be edited."))
	else:
		frappe_api.has_permission("Purchase Order", ptype="create", throw=True)
		doc = frappe_api.new_doc("Purchase Order")

	# Reject a forged submit before insert/save produces any persistent side effect.
	if submit:
		frappe_api.has_permission("Purchase Order", ptype="submit", doc=doc, throw=True)

	header = {
		fieldname: values.get(fieldname)
		for fieldname in PURCHASE_ORDER_EDITOR_FIELDS
		if fieldname in values
	}
	header["is_yrp_managed"] = 1
	if not name:
		header.update(get_purchase_order_against(values.get("against"), values.get("against_id")))
	doc.update(header)
	rows = ungroup_items(item_details, "Purchase Order")
	if not rows:
		frappe.throw(_("Enter a quantity greater than zero for at least one Item."))
	_prepare_purchase_order_item_rows(rows, values)
	doc.set("items", rows)
	doc.set("item_details", None)
	if submit:
		# Validate approval authority before insert/save so a forged combined
		# save-and-submit request cannot create a Draft as a side effect.
		validate_approval_submit(doc)
	if name:
		doc.save()
	else:
		doc.insert()
	if submit:
		doc.submit()
	workspace_loader = _dependency(_adapter, "get_purchase_order_workspace", get_purchase_order_workspace)
	return workspace_loader(doc.name)


def _prepare_purchase_order_item_rows(rows, values) -> None:
	"""Apply visible header defaults and explain invalid item delivery dates.

	Legacy Purchase Orders can contain an item-level ``schedule_date`` which is
	not represented by the standard header Required By field.  Validate that
	value before the ERPNext controller raises its generic ``Row #`` message.
	"""

	order_date = values.get("transaction_date")
	default_required_by = values.get("schedule_date") or order_date
	default_delivery_location = values.get("default_delivery_location")
	for index, row in enumerate(rows, start=1):
		if not row.get("delivery_location") and default_delivery_location:
			row["delivery_location"] = default_delivery_location
		if not row.get("schedule_date") and default_required_by:
			row["schedule_date"] = default_required_by
		if not row.get("expected_delivery_date") and row.get("schedule_date"):
			row["expected_delivery_date"] = row.get("schedule_date")

		if not order_date or not row.get("schedule_date"):
			continue
		if getdate(row.get("schedule_date")) >= getdate(order_date):
			continue

		item_label = row.get("item_code") or row.get("item_name") or _("Item row {0}").format(index)
		frappe.throw(
			_(
				"Item {0} has Required By {1}, which is before Order Date {2}. "
				"Edit the item and choose a Required By date on or after the Order Date."
			).format(
				frappe.bold(item_label),
				frappe.bold(formatdate(row.get("schedule_date"), "dd-MM-yyyy")),
				frappe.bold(formatdate(order_date, "dd-MM-yyyy")),
			),
		)


def execute_purchase_order_command(
	name: str,
	command: str,
	payload=None,
	expected_modified: str | None = None,
) -> dict:
	"""Execute one allowlisted Purchase Order command through its owner service."""

	commands = {
		"refresh_status",
		"close",
		"reopen",
		"send_approval_request",
		"approve",
		"reject",
		"update_linked_lots",
		"prepare_sms",
		"prepare_whatsapp",
		"send_sms",
		"send_whatsapp",
	}
	if command not in commands:
		frappe.throw(_("Unsupported Purchase Order command: {0}").format(command))
	doc = _get_purchase_order(name)
	assert_expected_modified(doc, expected_modified)
	payload = payload if isinstance(payload, dict) else frappe.parse_json(payload or "{}")
	if command in {"prepare_sms", "prepare_whatsapp", "send_sms", "send_whatsapp"}:
		if not doc.get("is_yrp_managed"):
			frappe.throw(_("Notifications are available only for YRP managed Purchase Orders."))
		channel = command.removeprefix("prepare_").removeprefix("send_")
		if command.startswith("prepare_"):
			return prepare_supplier_notification(
				doc,
				"Purchase Order",
				channel,
				hidden_statuses=PURCHASE_ORDER_NOTIFICATION_HIDDEN_STATUSES,
			)
		return send_supplier_notification(
			doc,
			"Purchase Order",
			channel,
			payload,
			hidden_statuses=PURCHASE_ORDER_NOTIFICATION_HIDDEN_STATUSES,
		)

	if command == "refresh_status":
		refresh_status(name)
	elif command == "close":
		close_purchase_order(name)
	elif command == "reopen":
		reopen_purchase_order(name)
	elif command == "send_approval_request":
		send_purchase_order_request(name)
	elif command == "approve":
		approve_purchase_order(name)
	elif command == "reject":
		reason = str(payload.get("reason") or "").strip()
		if not reason:
			frappe.throw(_("Enter a reason before rejecting this Purchase Order."))
		reject_purchase_order(name, reason=reason)
	elif command == "update_linked_lots":
		update_po_lot_links(
			name,
			add_lots=payload.get("add_lots"),
			remove_lots=payload.get("remove_lots"),
			comment=payload.get("comment"),
		)
	return get_purchase_order_workspace(name)
