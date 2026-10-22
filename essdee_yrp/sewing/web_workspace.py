"""Permission-aware capabilities for the Sewing web workspace."""

from __future__ import annotations

import frappe
from frappe import _

from essdee_yrp.finishing.web_reports import can_view_dispatch_report
from essdee_yrp.planning.reports import inhouse_quantity
from essdee_yrp.purchase.lot_cut_quantity import get_lot_cut_quantity_capability
from essdee_yrp.sewing.fi_dates import is_production_planner

DOCUMENT_SECTIONS = {
	"delivery_challans": ("Delivery Challans", "YRP Delivery Challan"),
	"goods_received_notes": ("Goods Received Notes", "YRP Goods Received Note"),
}

PLAN_RESOURCES = {
	"entry": ("Sewing Plan Entry", "SD YRP Sewing Plan Entry Detail"),
	"plan": ("Sewing Plan", "SD YRP Sewing Plan"),
	"goods_received_note": ("Goods Received Note", "YRP Goods Received Note"),
}

REPORT_LABELS = {
	"status_summary": "Status Summary",
	"dpr": "DPR",
	"scr": "SCR",
	"monthly_summary": "Monthly Summary",
	"item_summary": "Item Summary",
}


def _permission_flags(doctype: str) -> dict[str, bool]:
	return {
		f"can_{ptype}": bool(frappe.has_permission(doctype, ptype=ptype))
		for ptype in ("read", "create", "write", "delete", "submit", "report")
	}


def _report_capability(label: str) -> dict:
	return {
		"label": _(label),
		"can_read": True,
		"can_create": False,
		"can_write": False,
		"can_delete": False,
		"can_submit": False,
		"can_report": True,
	}


def has_report_access() -> bool:
	return all(frappe.has_permission("SD YRP Sewing Plan", ptype=ptype) for ptype in ("read", "report"))


@frappe.whitelist()
def get_capabilities() -> dict:
	"""Expose section access and independent resource permissions for the session.

	These are UI capabilities; domain endpoints still enforce record permissions
	and operation eligibility when called.
	"""

	plan_actions = {
		key: {"label": _(label), "doctype": doctype, **_permission_flags(doctype)}
		for key, (label, doctype) in PLAN_RESOURCES.items()
	}
	plan = plan_actions["plan"]
	entry = plan_actions["entry"]
	grn = plan_actions["goods_received_note"]
	work_order = {
		"doctype": "YRP Work Order",
		"label": _("Work Orders"),
		**_permission_flags("YRP Work Order"),
	}
	sections = {}
	if plan["can_read"]:
		sections["plans"] = {
			"label": _("Sewing Plan"),
			"can_read": plan["can_read"],
			"can_create": entry["can_create"],
			"can_write": plan["can_write"],
			"can_delete": entry["can_delete"],
			"can_submit": grn["can_create"] and grn["can_submit"],
			"can_report": plan["can_report"],
			"can_update_fi_dates": is_production_planner(),
		}
	if work_order["can_read"]:
		sections["work_orders"] = work_order
	for key, (label, doctype) in DOCUMENT_SECTIONS.items():
		flags = _permission_flags(doctype)
		if flags["can_read"]:
			sections[key] = {"doctype": doctype, "label": _(label), **flags}

	reports = {}
	if plan["can_read"] and plan["can_report"]:
		sections["reports"] = _report_capability("Reports")
		sections["attendance"] = _report_capability("Attendance Report")
		reports = {key: _report_capability(label) for key, label in REPORT_LABELS.items()}
		if can_view_dispatch_report():
			reports["finishing_dispatch"] = _report_capability("Finishing Plan Dispatch")
		reports["lot_cut_quantity"] = {
			**_report_capability("Lot Cut Quantity"),
			"can_read_cutting_plan": get_lot_cut_quantity_capability()["can_read_cutting_plan"],
		}
		if inhouse_quantity.can_view():
			reports["inhouse_quantity"] = _report_capability("In-house Quantity")

	from essdee_yrp.desk_web_reports import department_report_capabilities

	reports.update({
		key: _report_capability(capability["label"])
		for key, capability in department_report_capabilities("sewing", bool(reports)).items()
	})

	return {"sections": sections, "plan_actions": plan_actions, "reports": reports}
