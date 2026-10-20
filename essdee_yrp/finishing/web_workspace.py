"""Permission-aware /web workspace for Finishing Plans."""

from __future__ import annotations

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import cstr

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
from essdee_yrp.finishing.web_entries import ENTRY_COMMANDS
from essdee_yrp.print_registry import get_document_print_formats

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


REWORK_DOCTYPE = "SD YRP GRN Rework Item"
DISPATCH_DOCTYPE = "SD YRP Finishing Plan Dispatch"
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


def _readable_reports() -> dict:
	reports = {
		key: {"label": _(label), "can_read": True}
		for key, (label, checks) in REPORTS.items()
		if all(frappe.has_permission(doctype, ptype=ptype) for doctype, ptype in checks)
	}

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
		sections["rework_groups"] = _section("Rework Grouped Details", REWORK_DOCTYPE, rework)
	dispatches = _permission_flags(DISPATCH_DOCTYPE, ("read", "create", "write", "submit", "cancel"))
	if dispatches["can_read"]:
		sections["dispatches"] = _section("Finishing Plan Dispatch", DISPATCH_DOCTYPE, dispatches)
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
	groups = []
	for key, (label, doctype, cancellable) in LINKED_DOCUMENT_LISTS.items():
		entries = json_object(doc.get(key))
		documents = [
			{"name": name, "date": value if isinstance(value, str) else ""} for name, value in entries.items()
		]
		groups.append(
			{
				"key": key,
				"label": _(label),
				"doctype": doctype,
				"cancellable": cancellable,
				"documents": documents,
			}
		)
	return groups


def get_dispatch_logs(doc) -> list[dict]:
	return [
		{field: row.get(field) for field in DISPATCH_LOG_FIELDS}
		for row in doc.get("finishing_plan_dispatch_logs") or []
	]


@frappe.whitelist()
def get_plan_workspace(name: str) -> dict:
	"""Return the Finishing Plan header, actions, linked documents and dispatch history."""

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


def _matrix_payload(doc, plan_views, key, **extra):
	return {
		"primary_values": plan_views["primary_values"],
		"data": plan_views[key],
		"is_set_item": plan_views["is_set_item"],
		"set_attr": plan_views["set_attr"],
		**extra,
	}


def _details_tab(doc):
	plan_views = views.build_plan_views(doc)
	return _matrix_payload(doc, plan_views, "finishing_inward", process=doc.finishing_process)


def _item_details_tab(doc):
	plan_views = views.build_plan_views(doc)
	return _matrix_payload(doc, plan_views, "finishing_qty", rework_details=plan_views["rework_details"])


def _grn_tab(doc):
	return {
		"primary_values": transactions.get_primary_values(doc.lot, doc.production_detail),
		"packed": views.get_packed_qty(doc),
		"packing_config": packing.get_ipd_packing_config(doc.lot),
	}


def _old_lot_tab(doc):
	plan_views = views.build_plan_views(doc)
	available = old_lot.fetch_from_old_lot(doc.name) if get_plan_actions(doc)["fetch_old_lot"] else None
	return {
		"given": plan_views["old_lot_given_matrix"],
		"received": plan_views["old_lot_received_matrix"],
		"available": available,
	}


def _ocr_tab(doc):
	plan_views = views.build_plan_views(doc)
	return {
		"ocr_data": ocr.get_ocr_details(doc),
		"primary_values": plan_views["primary_values"],
		"item": doc.item,
	}


def _p_and_l_tab(doc):
	if not get_plan_actions(doc)["view_p_and_l"]:
		frappe.throw(_("You are not permitted to view Finishing Plan P&L documents."), frappe.PermissionError)
	return {"documents": closure.get_p_and_l_documents(doc.name)}


def _view_tab(key):
	return lambda doc: _matrix_payload(doc, views.build_plan_views(doc), key)


TAB_LOADERS = {
	"details": _details_tab,
	"item_details": _item_details_tab,
	"grn": _grn_tab,
	"inward": _view_tab("inward_details"),
	"old_lot": _old_lot_tab,
	"ironing_excess": _view_tab("finishing_ironing"),
	"pack_return": _view_tab("pack_return"),
	"ocr": _ocr_tab,
	"ocr_consumption": lambda doc: insights.get_fp_consumption_details(doc.name),
	"ocr_stock_balance": lambda doc: insights.get_fp_stock_balance_details(doc.name),
	"p_and_l": _p_and_l_tab,
	"alternatives": lambda doc: get_alternative_details(doc.lot) if doc.lot else {},
	"rejection": lambda doc: views.build_plan_views(doc)["rejection_details"],
}


@frappe.whitelist()
def get_plan_tab(name: str, tab: str) -> dict:
	"""Load one Finishing Plan tab so inactive tabs never compute their view models."""

	doc = get_plan(name)
	loader = TAB_LOADERS.get(tab)
	if not loader:
		frappe.throw(_("Unknown Finishing Plan tab: {0}").format(tab))
	return loader(doc)


def _cancel_linked_document(doc, payload):
	doctype, docname = cstr(payload.get("doctype")), cstr(payload.get("name"))
	owned = any(
		group["doctype"] == doctype
		and group["cancellable"]
		and any(document["name"] == docname for document in group["documents"])
		for group in get_linked_documents(doc)
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
