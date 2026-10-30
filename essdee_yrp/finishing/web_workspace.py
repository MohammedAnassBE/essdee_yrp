"""Permission-aware /web workspace for Finishing Plans."""

from __future__ import annotations

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import cstr
from yrp.attribute_read_context import attribute_read_scope

from essdee_yrp.cut_panel_store.common import assert_expected_modified, parse_json_object
from essdee_yrp.finishing import (
	alternative,
	closure,
	insights,
	inward,
	ocr,
	old_lot,
	packing,
	transactions,
	views,
)
from essdee_yrp.finishing.alternative import get_alternative_details
from essdee_yrp.finishing.parsing import json_object
from essdee_yrp.finishing.source_entries import get_source_entries
from essdee_yrp.finishing.web_entries import ENTRY_COMMANDS
from essdee_yrp.planning.reports import inhouse_quantity
from essdee_yrp.print_registry import get_document_print_formats
from essdee_yrp.purchase.lot_cut_quantity import get_lot_cut_quantity_capability

DOCTYPE = "SD YRP Finishing Plan"
STOCK_REPORT_DOCTYPE = "YRP Stock Ledger Entry"
LOCKED_STATUSES = frozenset({"Auto Closed", "OCR Completed", "P&L Submitted"})
OLD_LOT_CLOSED_STATUSES = frozenset({"Auto Closed", "OCR Completed"})
INWARD_PRINT_FORMAT = "Essdee Finishing Plan Inward Report"

LINKED_DOCUMENT_LISTS = {
	"dc_list": ("Delivery Challans", "YRP Delivery Challan", True),
	"return_grn_list": ("Return Items", "YRP Goods Received Note", True),
	"grn_list": ("Goods Received Notes", "YRP Goods Received Note", True),
	"stock_entry_list": ("Stock Entries", "YRP Stock Entry", True),
	"ironing_excess_list": ("Ironing Excess", "YRP Stock Entry", True),
	"pack_return_list": ("Pack Returns", "YRP Goods Received Note", True),
	"lot_transfer_list": ("Lot Transfers", "SD YRP Lot Transfer", True),
	"incomplete_transfer_dc_list": ("Delivery Challans", "YRP Delivery Challan", False),
	"incomplete_transfer_grn_list": ("Goods Received Notes", "YRP Goods Received Note", False),
}

RECORD_FIELDS = (
	"name",
	"lot",
	"work_order",
	"item",
	"fp_status",
	"pieces_per_box",
	"production_detail",
	"delivery_location",
	"finishing_process",
	"finishing_start_date",
	"finishing_end_date",
	"audit_requested_date",
	"audit_completed_date",
	"is_set_item",
	"comments",
	"modified",
)

DISPATCH_LOG_FIELDS = (
	"stock_entry",
	"source_doctype",
	"source_name",
	"posting_date",
	"posting_time",
	"dispatch_boxes",
	"dispatch_pieces",
	"total_dispatched_pieces_after",
	"cutting_qty",
	"dispatch_percentage_before",
	"dispatch_percentage_after",
	"cancelled",
)


DOCUMENT_SECTIONS = {
	"delivery_challans": ("Delivery Challans", "YRP Delivery Challan"),
	"goods_received_notes": ("Goods Received Notes", "YRP Goods Received Note"),
}
REWORK_DOCTYPE = "SD YRP GRN Rework Item"
DISPATCH_DOCTYPE = "SD YRP Finishing Plan Dispatch"
WORK_ORDER_DOCTYPE = "YRP Work Order"
REPORTS = {
	"stock_balance": ("Stock Balance", ((STOCK_REPORT_DOCTYPE, "read"), (STOCK_REPORT_DOCTYPE, "report"))),
	"packing_dpr": ("Packing DPR", ((DOCTYPE, "read"), ("YRP Goods Received Note", "read"))),
	"dispatch_report": ("Dispatch Report", ((DOCTYPE, "read"), ("YRP Goods Received Note", "read"))),
	"ironing_dpr": ("Ironing DPR", ((DOCTYPE, "read"), ("YRP Delivery Challan", "read"))),
	"finishing_plan_report": ("Finishing Plan Report", ((DOCTYPE, "read"), (DOCTYPE, "report"))),
	"rejection_details": ("Rejection Details", ((REWORK_DOCTYPE, "read"),)),
	"rework_completion": ("Rework Completion", ((REWORK_DOCTYPE, "read"),)),
}


def _permission_flags(
	doctype: str, ptypes=("read", "create", "write", "delete", "report")
) -> dict[str, bool]:
	return {f"can_{ptype}": bool(frappe.has_permission(doctype, ptype=ptype)) for ptype in ptypes}


def has_report_access() -> bool:
	return any(
		all(frappe.has_permission(doctype, ptype=ptype) for doctype, ptype in checks)
		for _label, checks in REPORTS.values()
	)


def _readable_reports() -> dict:
	reports = {
		key: {"label": _(label), "can_read": True}
		for key, (label, checks) in REPORTS.items()
		if all(frappe.has_permission(doctype, ptype=ptype) for doctype, ptype in checks)
	}
	if reports:
		reports["lot_cut_quantity"] = get_lot_cut_quantity_capability()
		if inhouse_quantity.can_view():
			reports["inhouse_quantity"] = {"label": _("In-house Quantity"), "can_read": True, "can_report": True}

	from essdee_yrp.desk_web_reports import department_report_capabilities

	reports.update(department_report_capabilities("finishing", bool(reports)))
	return reports


def _section(label, doctype, flags):
	return {"label": _(label), "doctype": doctype, **flags}


@frappe.whitelist()
def get_capabilities() -> dict:
	"""Return the Finishing launcher cards the session user can open."""

	sections = {}
	plans = _permission_flags(DOCTYPE)
	if plans["can_read"]:
		sections["plans"] = _section("Finishing Plan", DOCTYPE, plans)
	reports = _readable_reports()
	if reports:
		sections["reports"] = {
			"label": _("Reports"),
			"can_read": True,
			"can_create": False,
			"reports": reports,
		}
	rework = _permission_flags(REWORK_DOCTYPE, ("read", "write"))
	if rework["can_read"]:
		sections["rework_details"] = _section("Rework Details", REWORK_DOCTYPE, rework)
	dispatches = _permission_flags(DISPATCH_DOCTYPE, ("read", "create", "write", "submit", "cancel"))
	if dispatches["can_read"]:
		sections["dispatches"] = _section("Finishing Plan Dispatch", DISPATCH_DOCTYPE, dispatches)
	work_orders = _permission_flags(WORK_ORDER_DOCTYPE, ("read", "create"))
	if work_orders["can_read"]:
		sections["work_orders"] = _section("Work Orders", WORK_ORDER_DOCTYPE, work_orders)
	for key, (label, doctype) in DOCUMENT_SECTIONS.items():
		flags = _permission_flags(doctype, ("read", "create"))
		if flags["can_read"]:
			sections[key] = _section(label, doctype, flags)
	return {"sections": sections}


def get_plan(name: str):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	return doc


def get_plan_actions(doc) -> dict[str, bool]:
	"""Mirror the Frappe 15 Finishing Plan button rules; commands recheck them."""

	status = doc.fp_status or "Planned"
	roles = set(frappe.get_roles())
	open_plan = status not in LOCKED_STATUSES
	can_write = open_plan and bool(frappe.has_permission(DOCTYPE, ptype="write", doc=doc))
	accounts_role = closure.get_accounts_user_role()
	merch_role = frappe.db.get_single_value("SD YRP MRP Settings", "merch_user_role")
	view_p_and_l = "System Manager" in roles or bool(merch_role and merch_role in roles)
	return {
		"complete_ocr": status in ("Audit Completed", "Auto Closed") and "System Manager" in roles,
		"complete_audit": open_plan and status == "Ready for Audit" and accounts_role in roles,
		"request_audit": can_write and status in ("Dispatched", "Fully Dispatched"),
		"fetch_rejected_quantity": can_write,
		"create_entries": can_write,
		"cancel_linked_document": can_write,
		"print_inward": open_plan and bool(frappe.has_permission(DOCTYPE, ptype="print", doc=doc)),
		"fetch_old_lot": can_write and status not in OLD_LOT_CLOSED_STATUSES,
		"view_p_and_l": view_p_and_l,
		"manage_p_and_l": view_p_and_l
		and status == "OCR Completed"
		and bool(frappe.has_permission(DOCTYPE, ptype="write", doc=doc)),
	}


def get_linked_documents(doc) -> list[dict]:
	"""Linked document groups; `cancellable` also needs the user's cancel permission on the doctype."""
	groups = []
	cancel_permissions = {}
	for key, (label, doctype, cancellable) in LINKED_DOCUMENT_LISTS.items():
		entries = json_object(doc.get(key))
		documents = [{"name": name, "date": _entry_date(value)} for name, value in entries.items()]
		if cancellable and doctype not in cancel_permissions:
			cancel_permissions[doctype] = has_cancel_permission(doctype)
		groups.append(
			{
				"key": key,
				"label": _(label),
				"doctype": doctype,
				"cancellable": cancellable and cancel_permissions[doctype],
				"documents": documents,
			}
		)
	return groups


def has_cancel_permission(doctype: str) -> bool:
	return bool(frappe.has_permission(doctype, ptype="cancel"))


def _entry_date(value) -> str:
	if isinstance(value, dict):
		return cstr(value.get("datetime"))
	return value if isinstance(value, str) else ""


def get_dispatch_logs(doc) -> list[dict]:
	return [
		{field: row.get(field) for field in DISPATCH_LOG_FIELDS}
		for row in doc.get("finishing_plan_dispatch_logs") or []
	]


@frappe.whitelist()
def get_plan_workspace(name: str) -> dict:
	"""Return the Finishing Plan header, actions, linked documents and dispatch history."""

	with attribute_read_scope():
		doc = get_plan(name)
		actions = get_plan_actions(doc)
		return {
			"record": {field: doc.get(field) for field in RECORD_FIELDS},
			"locked": (doc.fp_status or "") in LOCKED_STATUSES,
			"actions": actions,
			"permissions": {
				"can_read": True,
				"can_write": bool(frappe.has_permission(DOCTYPE, ptype="write", doc=doc)),
				"can_print": bool(frappe.has_permission(DOCTYPE, ptype="print", doc=doc)),
			},
			"print_formats": get_document_print_formats(doc),
			"primary_values": transactions.get_primary_values(doc.lot, doc.production_detail)
			if actions["print_inward"]
			else [],
			"linked_documents": get_linked_documents(doc),
			"dispatch_logs": get_dispatch_logs(doc),
			"entry_options": get_entry_options(doc) if actions["create_entries"] else {},
		}


def get_entry_options(doc) -> dict:
	"""Defaults and choices the Frappe 15 entry dialogs read from the form."""

	return {
		"delivery_location": doc.delivery_location,
		"alternative_items": alternative.check_is_alternative_item(doc.item) or [],
		"alternate_lots": alternative.get_fp_alternate_lots(doc.lot) if doc.lot else [],
	}


def _matrix_payload(context, data, **extra):
	return {
		"primary_values": context["primary_values"],
		"data": data,
		"is_set_item": context["is_set_item"],
		"set_attr": context["set_attr"],
		**extra,
	}


def _details_tab(doc):
	context = views.get_ipd_context(doc)
	data = views.build_quantity_views(doc, context)["finishing_inward"]
	return _matrix_payload(context, data, process=doc.finishing_process)


def _item_details_tab(doc):
	context = views.get_ipd_context(doc)
	data = views.build_quantity_views(doc, context)["finishing_qty"]
	return _matrix_payload(context, data, rework_details=views.build_rework_details(doc, context))


def _grn_tab(doc):
	return {
		"primary_values": transactions.get_primary_values(doc.lot, doc.production_detail),
		"packed": views.get_packed_qty(doc),
		"packing_config": packing.get_ipd_packing_config(doc.lot),
	}


def _inward_tab(doc):
	context = views.get_ipd_context(doc)
	return _matrix_payload(context, views.build_inward_details(doc, context))


def _old_lot_tab(doc):
	matrices = views.build_old_lot_matrices(doc, views.get_ipd_context(doc))
	available = old_lot.fetch_from_old_lot(doc.name) if get_plan_actions(doc)["fetch_old_lot"] else None
	return {
		"given": matrices["old_lot_given_matrix"],
		"received": matrices["old_lot_received_matrix"],
		"available": available,
		"entries": get_source_entries(doc, "lot_transfer_list"),
	}


def _ocr_tab(doc):
	context = views.get_ipd_context(doc)
	return {
		"ocr_data": ocr.get_ocr_details(doc),
		"primary_values": context["primary_values"],
		"item": doc.item,
	}


def _p_and_l_tab(doc):
	if not get_plan_actions(doc)["view_p_and_l"]:
		frappe.throw(_("You are not permitted to view Finishing Plan P&L documents."), frappe.PermissionError)
	return {"documents": closure.get_p_and_l_documents(doc.name)}


def _ironing_excess_tab(doc):
	context = views.get_ipd_context(doc)
	return _matrix_payload(
		context,
		views.build_quantity_views(doc, context)["finishing_ironing"],
		entries=get_source_entries(doc, "ironing_excess_list"),
	)


def _pack_return_tab(doc):
	context = views.get_ipd_context(doc)
	return _matrix_payload(context, views.build_quantity_views(doc, context)["pack_return"])


def _rejection_tab(doc):
	return views.build_rejection_details(doc, views.get_ipd_context(doc))


TAB_LOADERS = {
	"details": _details_tab,
	"item_details": _item_details_tab,
	"grn": _grn_tab,
	"inward": _inward_tab,
	"old_lot": _old_lot_tab,
	"ironing_excess": _ironing_excess_tab,
	"pack_return": _pack_return_tab,
	"ocr": _ocr_tab,
	"ocr_consumption": lambda doc: insights.get_fp_consumption_details(doc.name),
	"ocr_stock_balance": lambda doc: insights.get_fp_stock_balance_details(doc.name),
	"p_and_l": _p_and_l_tab,
	"alternatives": lambda doc: get_alternative_details(doc.lot) if doc.lot else {},
	"rejection": _rejection_tab,
}


@frappe.whitelist()
def get_plan_tab(name: str, tab: str) -> dict:
	"""Load one Finishing Plan tab so inactive tabs never compute their view models."""

	with attribute_read_scope():
		doc = get_plan(name)
		loader = TAB_LOADERS.get(tab)
		if not loader:
			frappe.throw(_("Unknown Finishing Plan tab: {0}").format(tab))
		return loader(doc)


def _cancel_linked_document(doc, payload):
	doctype, docname = cstr(payload.get("doctype")), cstr(payload.get("name"))
	owned = any(
		list_doctype == doctype and cancellable and docname in json_object(doc.get(key))
		for key, (_label, list_doctype, cancellable) in LINKED_DOCUMENT_LISTS.items()
	)
	if not owned:
		frappe.throw(_("{0} {1} does not belong to this Finishing Plan.").format(doctype, docname))
	transactions.cancel_document(doctype, docname)


def _add_p_and_l_document(doc, payload):
	closure.add_p_and_l_document(doc.name, payload.get("file_url"), payload.get("comments"))


def _delete_p_and_l_document(doc, payload):
	documents = {row.name for row in closure.get_p_and_l_documents(doc.name)}
	if payload.get("document") not in documents:
		frappe.throw(_("This P&L document does not belong to this Finishing Plan."))
	closure.delete_p_and_l_document(payload.get("document"))


COMMANDS = {
	"request_audit": ("request_audit", lambda doc, _payload: closure.request_audit(doc.name)),
	"complete_audit": ("complete_audit", lambda doc, _payload: closure.complete_audit(doc.name)),
	"complete_ocr": ("complete_ocr", lambda doc, _payload: closure.complete_ocr(doc.name)),
	"fetch_rejected_quantity": (
		"fetch_rejected_quantity",
		lambda doc, _payload: insights.fetch_rejected_quantity(doc.name),
	),
	"cancel_linked_document": ("cancel_linked_document", _cancel_linked_document),
	"add_p_and_l_document": ("manage_p_and_l", _add_p_and_l_document),
	"delete_p_and_l_document": ("manage_p_and_l", _delete_p_and_l_document),
}
COMMANDS.update(ENTRY_COMMANDS)


@frappe.whitelist()
def execute_plan_command(name: str, command: str, payload=None, expected_modified: str | None = None) -> dict:
	"""Run one Finishing Plan command after rechecking its availability and freshness."""

	if command not in COMMANDS:
		frappe.throw(_("Unknown Finishing Plan command: {0}").format(command))
	doc = get_plan(name)
	assert_expected_modified(doc, expected_modified)
	action, handler = COMMANDS[command]
	if not get_plan_actions(doc)[action]:
		frappe.throw(_("This action is not available for the Finishing Plan in its current state."))
	result = handler(doc, parse_json_object(payload, label=_("Command payload")))
	return {**get_plan_workspace(name), "result": result}


@frappe.whitelist()
def prepare_inward_print(name: str, size: str) -> dict:
	"""Store the selected size for the Inward print format and return its print URL."""

	doc = get_plan(name)
	if not get_plan_actions(doc)["print_inward"]:
		frappe.throw(_("Finishing Inward print is not available for this Finishing Plan."))
	if size not in transactions.get_primary_values(doc.lot, doc.production_detail):
		frappe.throw(_("Select a size from this Finishing Plan."))
	inward.cache_selected_size("inward_pf_size", size, doc.name)
	return {
		"url": "/printview?"
		+ urlencode(
			{
				"doctype": DOCTYPE,
				"name": doc.name,
				"trigger_print": 1,
				"format": INWARD_PRINT_FORMAT,
				"no_letterhead": 1,
			}
		)
	}
