"""Permission-safe read contract for the Sales web workspace."""

from __future__ import annotations

from collections.abc import Mapping

import frappe
from frappe import _
from frappe.utils import cint, flt


DOCTYPE = "YRP Production Order"
PERMISSION_TYPES = ("read", "create", "write", "delete", "submit", "cancel", "print", "report")
RECORD_FIELDS = (
	"status",
	"item",
	"production_detail",
	"production_term",
	"posting_date",
	"delivery_date",
	"dont_deliver_after",
	"lead_time_given",
	"comments",
	"price_approval_status",
	"skip_box_sticker_print",
	"submitted_by",
	"submitted_time",
	"transferred_to_ppo",
	"transferred_on",
)
FIELD_LABELS = {
	"item": _("Item"),
	"production_detail": _("Production Detail"),
	"production_term": _("Production Term"),
	"posting_date": _("Posting Date"),
	"delivery_date": _("Delivery Date"),
	"dont_deliver_after": _("Don't Deliver After"),
	"lead_time_given": _("Lead Time (Days)"),
	"comments": _("Comments"),
	"price_approval_status": _("Price Approval"),
	"skip_box_sticker_print": _("Skip Box Sticker Print"),
	"submitted_by": _("Submitted By"),
	"submitted_time": _("Submitted Time"),
	"transferred_to_ppo": _("Transferred To PPO"),
	"transferred_on": _("Transferred On"),
}
ACTION_LABELS = {
	"save": _("Edit"),
	"delete": _("Delete"),
	"cancel": _("Cancel"),
	"amend": _("Amend"),
	"print": _("Print"),
	"request_ppo_approval": _("Request PPO Approval"),
	"approve_ppo": _("Approve & Submit PPO"),
	"request_changes": _("Request Changes"),
	"update_price": _("Update Price"),
	"change_dates": _("Change Dates"),
	"change_status": _("Change Status"),
	"update_quantity_ratio": _("Update Quantity & Ratio"),
	"approve_quantity_ratio": _("Approve Quantity & Ratio"),
	"approve_status": _("Approve Status Change"),
	"transfer_quantity": _("Transfer Quantity"),
	"approve_transfer": _("Approve Transfer Quantity"),
	"create_lot": _("Create Lot"),
	"link_lot": _("Link Lot"),
	"reopen": _("Reopen Production Order"),
}


def _permission_flags(doc=None) -> dict[str, bool]:
	return {
		f"can_{permission}": bool(frappe.has_permission(DOCTYPE, ptype=permission, doc=doc))
		for permission in PERMISSION_TYPES
	}


def _value(source, key, default=None):
	if isinstance(source, Mapping):
		return source.get(key, default)
	getter = getattr(source, "get", None)
	return getter(key, default) if callable(getter) else getattr(source, key, default)


def _action(allowed: bool, label: str, reason: str = "") -> dict:
	return {"allowed": bool(allowed), "label": label, "reason": "" if allowed else reason}


@frappe.whitelist()
def get_capabilities() -> dict:
	permissions = _permission_flags()
	if not permissions["can_read"]:
		return {"sections": {}, "reports": {}}

	sections = {
		"production_orders": {
			"label": _("Production Orders"),
			"doctype": DOCTYPE,
			**permissions,
		}
	}
	reports = {}
	if permissions["can_report"]:
		sections["reports"] = {
			"label": _("Reports"),
			"can_read": True,
			"can_report": True,
		}
		reports["ppo_report"] = {
			"label": _("PPO Report"),
			"can_read": True,
			"can_export": bool(permissions["can_report"]),
		}
	return {"sections": sections, "reports": reports}


def _serialize_matrix(rows) -> list[dict]:
	result = []
	for row in rows or []:
		result.append(
			{
				"name": _value(row, "name"),
				"item": _value(row, "item"),
				"item_variant": _value(row, "item_variant"),
				"size": _value(row, "size") or _value(row, "size_type_value"),
				"attributes_json": _value(row, "attributes_json"),
				"quantity": flt(_value(row, "quantity")),
				"ratio": flt(_value(row, "ratio")),
				"prices": {
					"mrp": flt(_value(row, "mrp")),
					"retail_price": flt(_value(row, "retail_price")),
					"wholesale_price": flt(_value(row, "wholesale_price")),
					"production_order_mrp": flt(_value(row, "production_order_mrp")),
				},
			}
		)
	return result


def _serialize_ordered(rows) -> list[dict]:
	return [
		{
			"name": _value(row, "name"),
			"item": _value(row, "item"),
			"item_variant": _value(row, "item_variant"),
			"lot": _value(row, "lot"),
			"quantity": flt(_value(row, "quantity")),
		}
		for row in rows or []
	]


def _production_order_actions(doc, permissions: dict, onload: Mapping) -> dict:
	docstatus = cint(doc.docstatus)
	status = doc.get("status") or ("Draft" if docstatus == 0 else "Submitted")
	manage = bool(onload.get("can_manage_production_order"))
	can_write = manage and permissions["can_write"]
	closed = docstatus == 1 and status == "Closed"
	request = onload.get("pending_production_order_request") or {}
	request_type = request.get("request_type")
	can_approve_request = bool(onload.get("can_approve_production_order_request"))
	incoming_transfer = onload.get("incoming_quantity_transfer_request") or {}
	linked_lots = onload.get("linked_lots") or []
	ordered = doc.get("production_ordered_details") or []
	transferred = bool(doc.get("transferred_to_ppo"))
	has_pending = bool(doc.get("quantity_ratio_request") or doc.get("status_change_request"))

	denied = _("This action is not available for the current document state or your permissions.")
	actions = {key: _action(False, label, denied) for key, label in ACTION_LABELS.items()}
	actions["print"] = _action(permissions["can_print"], ACTION_LABELS["print"], denied)
	actions["save"] = _action(docstatus == 0 and can_write, ACTION_LABELS["save"], denied)
	actions["delete"] = _action(docstatus == 0 and permissions["can_delete"], ACTION_LABELS["delete"], denied)
	actions["cancel"] = _action(docstatus == 1 and permissions["can_cancel"] and not closed, ACTION_LABELS["cancel"], denied)
	actions["amend"] = _action(docstatus == 2 and permissions["can_create"], ACTION_LABELS["amend"], denied)
	actions["request_ppo_approval"] = _action(
		docstatus == 0 and status == "Draft" and manage and bool(onload.get("can_request_ppo_approval")),
		ACTION_LABELS["request_ppo_approval"],
		denied,
	)
	can_approve_ppo = docstatus == 0 and status == "PPO Request" and bool(onload.get("can_approve_ppo"))
	actions["approve_ppo"] = _action(can_approve_ppo, ACTION_LABELS["approve_ppo"], denied)
	actions["request_changes"] = _action(can_approve_ppo, ACTION_LABELS["request_changes"], denied)

	if docstatus == 1 and can_write and not closed:
		for key in ("update_price", "change_dates", "create_lot", "link_lot"):
			actions[key] = _action(True, ACTION_LABELS[key])
		status_change_allowed = (
			status not in {"Item Changed", "Not Processed", "Pending Request"}
			and not incoming_transfer
			and not has_pending
			and not linked_lots
			and not transferred
		)
		actions["change_status"] = _action(status_change_allowed, ACTION_LABELS["change_status"], denied)
		quantity_allowed = (
			status == "Open"
			and not incoming_transfer
			and not has_pending
			and not ordered
			and not transferred
		)
		actions["update_quantity_ratio"] = _action(quantity_allowed, ACTION_LABELS["update_quantity_ratio"], denied)
		transfer_allowed = (
			status in {"Item Changed", "Not Processed"}
			and bool(onload.get("alternative_items"))
			and not incoming_transfer
			and not ordered
			and not transferred
		)
		actions["transfer_quantity"] = _action(transfer_allowed, ACTION_LABELS["transfer_quantity"], denied)

	actions["approve_quantity_ratio"] = _action(
		docstatus == 1 and status == "Pending Request" and can_approve_request and request_type == "quantity_ratio",
		ACTION_LABELS["approve_quantity_ratio"],
		denied,
	)
	actions["approve_status"] = _action(
		docstatus == 1 and status == "Pending Request" and can_approve_request and request_type == "status",
		ACTION_LABELS["approve_status"],
		denied,
	)
	actions["approve_transfer"] = _action(
		docstatus == 1 and bool(incoming_transfer) and bool(onload.get("can_approve_quantity_transfer_request")),
		ACTION_LABELS["approve_transfer"],
		denied,
	)
	actions["reopen"] = _action(
		closed and "System Manager" in frappe.get_roles(),
		ACTION_LABELS["reopen"],
		denied,
	)
	return actions


@frappe.whitelist()
def get_production_order_workspace(production_order: str) -> dict:
	doc = frappe.get_doc(DOCTYPE, production_order)
	doc.check_permission("read")
	doc.run_method("onload")
	onload = doc.get("__onload") or {}
	permissions = _permission_flags(doc)
	matrix = _serialize_matrix(doc.get("production_order_details"))
	ordered = _serialize_ordered(doc.get("production_ordered_details"))
	record = {
		"doctype": DOCTYPE,
		"name": doc.name,
		"docstatus": cint(doc.docstatus),
		"modified": doc.get("modified"),
		"total_quantity": sum(flt(row["quantity"]) for row in matrix),
	}
	for fieldname in RECORD_FIELDS:
		record[fieldname] = doc.get(fieldname)

	fields = [
		{"fieldname": fieldname, "label": FIELD_LABELS.get(fieldname, fieldname), "value": record.get(fieldname)}
		for fieldname in RECORD_FIELDS
		if record.get(fieldname) not in (None, "")
	]
	return {
		"record": record,
		"fields": fields,
		"matrix": matrix,
		"ordered": ordered,
		"linked_lots": onload.get("linked_lots") or [],
		"histories": {
			"dates": [dict(row) for row in doc.get("date_change_history") or []],
			"transfers": [dict(row) for row in doc.get("quantity_transfer_history") or []],
			"prices": onload.get("price_requests") or [],
			"comments": doc.get("comment_log") or "",
		},
		"permissions": permissions,
		"capabilities": _production_order_actions(doc, permissions, onload),
	}
