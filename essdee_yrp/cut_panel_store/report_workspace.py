"""Permission-safe report services for the Cut Panel Store web workspace."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.cut_panel_store.common import parse_json_object
from essdee_yrp.essdee_yrp.report.sd_yrp_cut_bundle_balance.sd_yrp_cut_bundle_balance import (
	execute as _execute_cut_bundle_balance,
)


CUT_BUNDLE_REPORT = "SD YRP Cut Bundle Balance"
CUT_BUNDLE_LEDGER = "SD YRP Cut Bundle Movement Ledger"
ALLOWED_FILTERS = {"lot", "supplier"}
CUT_BUNDLE_COLUMNS = (
	{"fieldname": "name", "fieldtype": "Link", "options": CUT_BUNDLE_LEDGER, "label": _("Name")},
	{"fieldname": "lot", "fieldtype": "Link", "options": "SD YRP Lot", "label": _("Lot")},
	{"fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "label": _("Supplier")},
	{"fieldname": "supplier_name", "fieldtype": "Data", "label": _("Supplier Name")},
	{"fieldname": "item", "fieldtype": "Link", "options": "Item", "label": _("Item")},
	{"fieldname": "lay_no", "fieldtype": "Int", "label": _("Lay No")},
	{"fieldname": "bundle_no", "fieldtype": "Int", "label": _("Bundle No")},
	{"fieldname": "size", "fieldtype": "Data", "label": _("Size")},
	{"fieldname": "colour", "fieldtype": "Data", "label": _("Colour")},
	{"fieldname": "shade", "fieldtype": "Data", "label": _("Shade")},
	{"fieldname": "panel", "fieldtype": "Data", "label": _("Panel")},
	{"fieldname": "qty", "fieldtype": "Int", "label": _("Quantity")},
)


def _require_cut_bundle_report_access() -> None:
	if not (
		frappe.has_permission(CUT_BUNDLE_LEDGER, ptype="read")
		and frappe.has_permission(CUT_BUNDLE_LEDGER, ptype="report")
	):
		frappe.throw(_("You do not have permission to view Cut Bundle Balance."), frappe.PermissionError)
	report = frappe.get_doc("Report", CUT_BUNDLE_REPORT)
	report.check_permission("read")


def _report_filters(filters=None) -> dict:
	values = parse_json_object(filters, label=_("Filters"))
	unknown = sorted(set(values) - ALLOWED_FILTERS)
	if unknown:
		frappe.throw(_("Cut Bundle Balance supports only Lot and Supplier filters."))
	result = {}
	for fieldname in ("lot", "supplier"):
		value = values.get(fieldname)
		if value in (None, ""):
			continue
		if not isinstance(value, str):
			frappe.throw(_("{0} must be a document name.").format(_(fieldname.replace("_", " ").title())))
		result[fieldname] = value.strip()
	return result


def _safe_result(rows) -> list[dict]:
	fieldnames = [column["fieldname"] for column in CUT_BUNDLE_COLUMNS]
	result = []
	for source in rows or []:
		getter = source.get if hasattr(source, "get") else lambda fieldname: getattr(source, fieldname, None)
		quantity = flt(getter("qty"))
		if quantity <= 0:
			continue
		row = {fieldname: getter(fieldname) for fieldname in fieldnames}
		row["qty"] = quantity
		result.append(row)
	return result


@frappe.whitelist()
def get_cut_bundle_balance(filters=None) -> dict:
	"""Run the allow-listed report and return a stable browser-safe projection."""

	_require_cut_bundle_report_access()
	filters = _report_filters(filters)
	_columns, rows = _execute_cut_bundle_balance(filters)
	result = _safe_result(rows)
	return {
		"columns": [dict(column) for column in CUT_BUNDLE_COLUMNS],
		"result": result,
		"summary": {
			"rows": len(result),
			"quantity": sum(flt(row["qty"]) for row in result),
		},
	}
