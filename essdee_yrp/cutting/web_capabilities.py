"""Permission-aware navigation capabilities for the Cutting web workspace."""

from __future__ import annotations

import frappe


WORKSPACE_DOCTYPES = {
	"cutting-plans": "SD YRP Cutting Plan",
	"cutting-orders": "SD YRP Cutting Order",
	"bulk-lay-sheets": "SD YRP Cutting Bulk Lay Sheets",
	"lay-sheet-planner": "SD YRP Cutting Laysheet Planner",
}


def _doctype_capability(doctype: str) -> dict[str, bool]:
	return {
		"can_read": bool(frappe.has_permission(doctype, ptype="read")),
		"can_create": bool(frappe.has_permission(doctype, ptype="create")),
	}


def _can_read_reports() -> bool:
	can_read_cutting = bool(frappe.has_permission("SD YRP Cutting LaySheet", ptype="read"))
	can_read_stock = bool(
		frappe.has_permission("YRP Stock Ledger Entry", ptype="read")
		and frappe.has_permission("YRP Stock Ledger Entry", ptype="report")
	)
	return can_read_cutting or can_read_stock


@frappe.whitelist()
def get_capabilities() -> dict[str, dict[str, bool]]:
	"""Return effective permissions for each independent Cutting destination."""

	capabilities = {
		key: _doctype_capability(doctype)
		for key, doctype in WORKSPACE_DOCTYPES.items()
	}
	capabilities["reports"] = {
		"can_read": _can_read_reports(),
		"can_create": False,
	}
	return capabilities
