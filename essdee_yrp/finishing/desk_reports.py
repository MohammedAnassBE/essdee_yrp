"""Columns and access checks shared by the Finishing Desk reports."""

import frappe
from frappe import _
from frappe.utils import getdate

from essdee_yrp.finishing.report_sources import REWORK_DOCTYPE, require_read
from essdee_yrp.finishing.web_workspace import REPORTS


def check_access(report):
	checks = REPORTS[report][1] if report in REPORTS else ((REWORK_DOCTYPE, "read"),)
	for doctype, _ptype in checks:
		require_read(doctype)


def column(fieldname, label, fieldtype="Data", options=None, width=120):
	result = {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width}
	if options:
		result["options"] = options
	return result


def lot_columns():
	return [column("lot", "Lot", "Link", "SD YRP Lot"), column("item", "Item", "Link", "Item")]


def size_columns(sizes):
	return [column(f"size_{index}", str(size), "Float", width=85) for index, size in enumerate(sizes)]


def size_values(sizes, values):
	return {f"size_{index}": values.get(size, 0) for index, size in enumerate(sizes)}


def ordered_sizes(groups, field):
	return list(dict.fromkeys(size for group in groups for size in group.get(field, [])))


def date_range(filters, start="from_date", end="to_date"):
	for field in (start, end):
		if not filters.get(field):
			frappe.throw(_("{0} is required").format(_(field.replace("_", " ").title())))
	if getdate(filters[start]) > getdate(filters[end]):
		frappe.throw(
			_("{0} cannot be after {1}").format(
				_(start.replace("_", " ").title()), _(end.replace("_", " ").title())
			)
		)


def dpr_filters(filters):
	filters = frappe._dict(filters or {})
	if frappe.utils.cint(filters.summary):
		date_range(filters)
	elif not filters.date:
		frappe.throw(_("Date is required"))
	return {key: filters.get(key) for key in ("date", "from_date", "to_date", "summary", "lots", "items")}
