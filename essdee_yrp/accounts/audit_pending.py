import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today


def can_view() -> bool:
	from essdee_yrp.accounts.web_capabilities import can_view_accounts_reports

	return can_view_accounts_reports() and bool(
		frappe.has_permission("SD YRP Finishing Plan", ptype="read")
	)


def require_access() -> None:
	if not can_view():
		frappe.throw(_("You do not have permission to view Audit Pending Finishing Plans."), frappe.PermissionError)


def run(filters, progress=None) -> dict:
	require_access()
	filters = filters or {}
	conditions = {"fp_status": "Ready for Audit"}
	for fieldname in ("lot", "item"):
		if filters.get(fieldname):
			conditions[fieldname] = filters[fieldname]
	from_date, to_date = filters.get("from_date"), filters.get("to_date")
	if bool(from_date) != bool(to_date):
		frappe.throw(_("Select both Requested From and To dates."))
	if from_date and to_date:
		if getdate(from_date) > getdate(to_date):
			frappe.throw(_("Requested From must be on or before To."))
		conditions["audit_requested_date"] = ["between", [from_date, to_date]]
	rows = frappe.get_list(
		"SD YRP Finishing Plan",
		filters=conditions,
		fields=["name", "lot", "item", "work_order", "audit_requested_date", "finishing_end_date"],
		order_by="audit_requested_date asc",
		limit_page_length=0,
	)
	current_date = today()
	for row in rows:
		row["days_pending"] = (
			date_diff(current_date, row["audit_requested_date"]) if row.get("audit_requested_date") else None
		)
	return {
		"columns": get_columns(),
		"result": rows,
		"summary": {
			"plans": len(rows),
			"oldest_days": max((row["days_pending"] for row in rows if row["days_pending"] is not None), default=0),
		},
	}


def get_columns() -> list[dict]:
	return [
		{"fieldname": "name", "label": _("Finishing Plan"), "fieldtype": "Link", "options": "SD YRP Finishing Plan", "width": 180},
		{"fieldname": "lot", "label": _("Lot"), "fieldtype": "Link", "options": "SD YRP Lot", "width": 160},
		{"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 180},
		{"fieldname": "work_order", "label": _("Work Order"), "fieldtype": "Link", "options": "YRP Work Order", "width": 180},
		{"fieldname": "audit_requested_date", "label": _("Audit Requested"), "fieldtype": "Date", "width": 150},
		{"fieldname": "days_pending", "label": _("Days Pending"), "fieldtype": "Int", "width": 130},
		{"fieldname": "finishing_end_date", "label": _("Finishing End Date"), "fieldtype": "Date", "width": 160},
	]


def dependency_doctypes(filters=None) -> list[str]:
	return ["SD YRP Finishing Plan", "SD YRP Lot", "Item", "YRP Work Order"]
