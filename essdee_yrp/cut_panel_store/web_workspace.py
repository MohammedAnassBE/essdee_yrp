"""Permission-aware entry point for the Cut Panel Store web workspace."""

from __future__ import annotations

import frappe
from frappe import _


SECTION_DOCTYPES = {
	"movements": "SD YRP Cut Panel Movement",
	"work_orders": "YRP Work Order",
	"cut_bundle_edits": "SD YRP Cut Bundle Edit",
	"box_stickers": "SD YRP Box Sticker Print",
	"excel_stickers": "YRP Excel Sticker Print",
}

SECTION_LABELS = {
	"movements": _("Cut Panel Movement"),
	"work_orders": _("Work Orders"),
	"cut_bundle_edits": _("Cut Bundle Edit"),
	"box_stickers": _("Box Sticker Print"),
	"excel_stickers": _("Excel Sticker Print"),
	"reports": _("Reports"),
}

REPORT_SOURCES = {
	"stock_balance": ("Stock Balance", "YRP Stock Ledger Entry"),
	"cut_bundle_balance": ("Cut Bundle Balance", "SD YRP Cut Bundle Movement Ledger"),
}


def _permission_flags(doctype: str) -> dict[str, bool]:
	return {
		"can_read": bool(frappe.has_permission(doctype, ptype="read")),
		"can_create": bool(frappe.has_permission(doctype, ptype="create")),
		"can_write": bool(frappe.has_permission(doctype, ptype="write")),
		"can_submit": bool(frappe.has_permission(doctype, ptype="submit")),
		"can_cancel": bool(frappe.has_permission(doctype, ptype="cancel")),
		"can_delete": bool(frappe.has_permission(doctype, ptype="delete")),
	}


def _section_capability(key: str, doctype: str) -> dict:
	return {
		"label": SECTION_LABELS[key],
		"doctype": doctype,
		**_permission_flags(doctype),
	}


def _readable_reports() -> dict:
	reports = {}
	for key, (label, doctype) in REPORT_SOURCES.items():
		if frappe.has_permission(doctype, ptype="read") and frappe.has_permission(
			doctype, ptype="report"
		):
			reports[key] = {"label": _(label), "can_read": True}
	from essdee_yrp.desk_web_reports import department_report_capabilities

	reports.update(department_report_capabilities("cut-panel-store", bool(reports)))
	return reports


@frappe.whitelist()
def get_capabilities() -> dict:
	"""Return independent capabilities for the six approved destinations."""

	sections = {}
	for key, doctype in SECTION_DOCTYPES.items():
		capability = _section_capability(key, doctype)
		if capability["can_read"]:
			sections[key] = capability

	reports = _readable_reports()
	if reports:
		sections["reports"] = {
			"label": SECTION_LABELS["reports"],
			"can_read": True,
			"can_create": False,
			"reports": reports,
		}

	return {"sections": sections}
