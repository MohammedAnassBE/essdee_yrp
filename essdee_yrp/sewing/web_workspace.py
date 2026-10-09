"""Permission-aware capabilities for the Sewing web workspace."""

from __future__ import annotations

import frappe
from frappe import _


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
		}
	if work_order["can_read"]:
		sections["work_orders"] = work_order

	reports = {}
	if plan["can_read"] and plan["can_report"]:
		sections["reports"] = _report_capability("Reports")
		sections["attendance"] = _report_capability("Attendance Report")
		reports = {key: _report_capability(label) for key, label in REPORT_LABELS.items()}

	return {"sections": sections, "plan_actions": plan_actions, "reports": reports}
