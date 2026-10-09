"""Permission-safe read contract for the Sales web workspace."""

from __future__ import annotations

from collections.abc import Mapping

import frappe
from frappe import _
from frappe.utils import cint, flt
from yrp.utils import get_variant_attr_details

from essdee_yrp import production_order_workflow as workflow
from essdee_yrp.sales import ppo_report


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
EDITOR_FIELDS = (
	"naming_series",
	"item",
	"production_detail",
	"production_term",
	"delivery_date",
	"dont_deliver_after",
	"comments",
	"skip_box_sticker_print",
)
EDITOR_FIELD_SCHEMA = {
	"naming_series": {"label": _("Series"), "fieldtype": "Select", "options": "\nPPO-", "reqd": True},
	"item": {"label": _("Item"), "fieldtype": "Link", "options": "Item", "reqd": True},
	"production_detail": {"label": _("Production Detail"), "fieldtype": "Link", "options": "YRP Item Production Detail", "reqd": False},
	"production_term": {"label": _("Production Term"), "fieldtype": "Link", "options": "YRP Production Term", "reqd": True},
	"delivery_date": {"label": _("Delivery Date"), "fieldtype": "Date", "options": "", "reqd": True},
	"dont_deliver_after": {"label": _("Don't Deliver After"), "fieldtype": "Date", "options": "", "reqd": True},
	"comments": {"label": _("Comments"), "fieldtype": "Small Text", "options": "", "reqd": False},
	"skip_box_sticker_print": {"label": _("Skip Box Sticker Print"), "fieldtype": "Check", "options": "", "reqd": False},
}
WORKFLOW_COMMANDS = {
	"request_ppo_approval": ("request_ppo_approval", ()),
	"approve_ppo": ("approve_ppo", ()),
	"request_changes": ("request_ppo_changes", ("reason",)),
	"update_quantity_ratio": (
		"update_quantity_and_ratio",
		("size_quantities", "size_ratios", "requested_by", "reason"),
	),
	"approve_quantity_ratio": ("approve_quantity_and_ratio", ()),
	"update_price": ("update_price", ("item_details",)),
	"change_dates": ("update_production_order_date", ("date_field", "new_date", "reason")),
	"change_status": ("change_status", ("new_status", "reason")),
	"approve_status": ("approve_status_change", ()),
	"transfer_quantity": ("transfer_quantity_to_ppo", ("target_production_order", "reason")),
	"approve_transfer": ("approve_quantity_transfer", ()),
	"create_lot": ("create_lot", ("lot_name",)),
	"link_lot": ("link_lot", ("lot_name",)),
	"reopen": ("reopen_production_order", ()),
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


def _parse_mapping(value, label: str) -> dict:
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except (TypeError, ValueError):
			frappe.throw(_("{0} is not valid JSON.").format(label))
	if not isinstance(value, Mapping):
		frappe.throw(_("{0} must be an object.").format(label))
	return dict(value)


def _assert_expected_modified(doc, expected_modified=None) -> None:
	if expected_modified and str(doc.modified) != str(expected_modified):
		frappe.throw(
			_("{0} changed after you opened it. Refresh and try again.").format(doc.name),
			frappe.TimestampMismatchError,
		)


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
	variant_attributes = {}
	for row in rows or []:
		size = _value(row, "size") or _value(row, "size_type_value")
		variant = _value(row, "item_variant")
		if not size and variant:
			if variant not in variant_attributes:
				variant_attributes[variant] = get_variant_attr_details(variant)
			attributes = variant_attributes[variant]
			size = attributes.get("Size") or next(iter(attributes.values()), "")
		result.append(
			{
				"name": _value(row, "name"),
				"item": _value(row, "item"),
				"item_variant": _value(row, "item_variant"),
				"size": size,
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
	result = []
	variant_attributes = {}
	for row in rows or []:
		variant = _value(row, "item_variant")
		size = _value(row, "size") or _value(row, "size_type_value")
		if not size and variant:
			if variant not in variant_attributes:
				variant_attributes[variant] = get_variant_attr_details(variant)
			attributes = variant_attributes[variant]
			size = attributes.get("Size") or next(iter(attributes.values()), "")
		result.append(
			{
				"name": _value(row, "name"),
				"item": _value(row, "item"),
				"item_variant": variant,
				"size": size,
				"lot": _value(row, "lot"),
				"quantity": flt(_value(row, "quantity")),
			}
		)
	return result


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
			"dates": [_serialize_child_row(row) for row in doc.get("date_change_history") or []],
			"transfers": [_serialize_child_row(row) for row in doc.get("quantity_transfer_history") or []],
			"prices": onload.get("price_requests") or [],
			"comments": doc.get("comment_log") or "",
		},
		"permissions": permissions,
		"capabilities": _production_order_actions(doc, permissions, onload),
	}


def _serialize_child_row(row) -> dict:
	"""Return child-table values without assuming the Document is iterable."""
	if hasattr(row, "as_dict"):
		return dict(row.as_dict())
	return dict(row)


def _editor_field(doc, fieldname: str) -> dict:
	schema = dict(EDITOR_FIELD_SCHEMA[fieldname])
	field = getattr(getattr(doc, "meta", None), "get_field", lambda _name: None)(fieldname)
	if field:
		schema.update(
			{
				"label": field.label or schema["label"],
				"fieldtype": field.fieldtype or schema["fieldtype"],
				"options": field.options or schema["options"],
				"reqd": bool(field.reqd or schema["reqd"]),
			}
		)
	value = doc.get(fieldname)
	if fieldname == "naming_series" and not value:
		value = "PPO-"
	return {"fieldname": fieldname, **schema, "value": value}


@frappe.whitelist()
def get_production_order_editor(name: str | None = None, source=None) -> dict:
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		doc.check_permission("write")
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a draft Production Order can be edited."))
	else:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(DOCTYPE)
		for fieldname, value in _parse_mapping(source or {}, _("Source")).items():
			if fieldname in EDITOR_FIELDS:
				doc.set(fieldname, value)

	item = doc.get("item")
	matrix = {}
	if item:
		matrix = workflow.get_order_editor_context(
			item=item,
			production_order=doc.name if name else doc.get("amended_from"),
		)
	return {
		"record": {"name": doc.name if name else "", "docstatus": cint(doc.docstatus)},
		"fields": [_editor_field(doc, fieldname) for fieldname in EDITOR_FIELDS],
		"matrix": matrix,
		"modified": doc.get("modified") if name else None,
	}


def _parse_item_details(value) -> list:
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except (TypeError, ValueError):
			frappe.throw(_("Production Order item details are not valid JSON."))
	if not isinstance(value, list) or not value:
		frappe.throw(_("Add at least one Production Order item quantity."))
	if any(not isinstance(group, Mapping) for group in value):
		frappe.throw(_("Production Order item details are malformed."))
	return value


@frappe.whitelist()
def save_production_order(values, name: str | None = None, submit: bool = False, expected_modified=None) -> dict:
	values = _parse_mapping(values, _("Production Order values"))
	item_details = _parse_item_details(values.get("item_details"))
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		doc.check_permission("write")
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a draft Production Order can be saved here."))
		_assert_expected_modified(doc, expected_modified)
	else:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(DOCTYPE)

	for fieldname in EDITOR_FIELDS:
		if fieldname in values:
			doc.set(fieldname, values[fieldname])
	doc.set("item_details", frappe.as_json(item_details))
	if name:
		doc.save()
	else:
		doc.insert()
	if submit:
		workflow.request_ppo_approval(production_order=doc.name)
	return get_production_order_workspace(doc.name)


def _command_kwargs(name: str, command: str, payload: Mapping, required_fields: tuple[str, ...]) -> dict:
	missing = [fieldname for fieldname in required_fields if payload.get(fieldname) in (None, "")]
	if missing:
		frappe.throw(_("Missing values for {0}.").format(", ".join(missing)))
	kwargs = {fieldname: payload.get(fieldname) for fieldname in required_fields}
	if command == "transfer_quantity":
		kwargs["source_production_order"] = name
	else:
		kwargs["production_order"] = name
	return kwargs


@frappe.whitelist()
def execute_production_order_command(
	name: str,
	command: str,
	payload=None,
	expected_modified=None,
) -> dict:
	if command not in {*WORKFLOW_COMMANDS, "cancel", "delete", "amend"}:
		frappe.throw(_("Unsupported Production Order action: {0}").format(command))
	payload = _parse_mapping(payload or {}, _("Action values"))
	doc = frappe.get_doc(DOCTYPE, name)
	_assert_expected_modified(doc, expected_modified)
	doc.run_method("onload")
	actions = _production_order_actions(doc, _permission_flags(doc), doc.get("__onload") or {})
	capability = actions.get(command) or {}
	if not capability.get("allowed"):
		frappe.throw(
			capability.get("reason") or _("This Production Order action is not available."),
			frappe.PermissionError,
		)

	if command == "cancel":
		doc.check_permission("cancel")
		doc.cancel()
	elif command == "delete":
		doc.check_permission("delete")
		frappe.delete_doc(DOCTYPE, name)
		return {"deleted": True, "record": {"name": name}}
	elif command == "amend":
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		amended = frappe.copy_doc(doc)
		amended.docstatus = 0
		amended.set("status", "Draft")
		amended.set("amended_from", doc.name)
		amended.insert()
		return get_production_order_workspace(amended.name)
	else:
		doc.check_permission("read")
		function_name, required_fields = WORKFLOW_COMMANDS[command]
		function = getattr(workflow, function_name)
		function(**_command_kwargs(name, command, payload, required_fields))
	return get_production_order_workspace(name)


@frappe.whitelist()
def get_ppo_report(filters=None) -> dict:
	return ppo_report.get_ppo_report(filters)


@frappe.whitelist()
def get_ppo_dispatch_summary(production_order: str) -> dict:
	return ppo_report.get_ppo_dispatch_summary(production_order)


@frappe.whitelist()
def get_ppo_dispatch_summary_bulk(production_orders) -> dict:
	return ppo_report.get_ppo_dispatch_summary_bulk(production_orders)


@frappe.whitelist()
def download_ppo_report(from_date=None, to_date=None, product_category=None, status=None, item=None):
	return ppo_report.download_ppo_report(from_date, to_date, product_category, status, item)
