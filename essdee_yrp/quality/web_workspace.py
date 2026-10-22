import frappe
from frappe import _
from frappe.utils import cint, nowdate

from essdee_yrp.api.duplicate import build_duplicate_values
from essdee_yrp.desk_web_reports import can_run_desk_report
from essdee_yrp.essdee_yrp.doctype.sd_yrp_essdee_quality_inspection.sd_yrp_essdee_quality_inspection import (
	can_request_inspection_debit,
	get_against_details,
	get_debit_details,
)
from essdee_yrp.print_registry import get_document_print_formats
from essdee_yrp.web_common import action, assert_expected_modified, parse_mapping, permission_flags

DOCTYPE = "SD YRP Essdee Quality Inspection"
WORK_ORDER = "YRP Work Order"
RFT_REPORT = "SD YRP Qualily Inspection RFT"
PERMISSION_TYPES = ("read", "write", "create", "submit", "cancel", "amend", "delete", "print")
EDITABLE_FIELDS = (
	"against_id",
	"is_third_party",
	"third_party_supplier",
	"inspection_type",
	"unit_name",
	"offer_qty",
	"description",
	"checking_level",
	"major_aql_level",
	"minor_aql_level",
	"major_defect_found",
	"minor_defect_found",
	"spi_found",
	"result",
	"measurement_deviation",
	"remarks_and_suggestions",
	"upload_quality_approval_sheet",
)
RECORD_FIELDS = (
	"name",
	"docstatus",
	"modified",
	"amended_from",
	"naming_series",
	"against",
	"posting_date",
	"item",
	"lot",
	"supplier",
	"supplier_name",
	"third_party_supplier_name",
	"order_qty",
	"sample_piece_count",
	"major_defect_maximum_allowed",
	"minor_defect_maximum_allowed",
	"calculated_result",
	"inspector",
	"inspector_name",
	*EDITABLE_FIELDS,
)


@frappe.whitelist()
def get_capabilities() -> dict:
	can_read_inspections = bool(frappe.has_permission(DOCTYPE, ptype="read"))
	reports = {}
	if can_run_desk_report(RFT_REPORT):
		reports["quality_inspection_rft"] = {"label": _("Quality Inspection RFT"), "can_read": True, "can_report": True}
	return {
		"sections": {
			"inspections": {
				"label": _("Essdee Quality Inspection"),
				"can_read": can_read_inspections,
				"can_create": bool(frappe.has_permission(DOCTYPE, ptype="create")),
			},
			"work_orders": {
				"label": _("Work Orders"),
				"can_read": can_read_inspections and bool(frappe.has_permission(WORK_ORDER, ptype="read")),
				"can_create": False,
			},
			"reports": {"label": _("Reports"), "can_read": bool(reports)},
		},
		"reports": reports,
	}


@frappe.whitelist()
def get_inspection_workspace(name: str) -> dict:
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	doc.run_method("onload")
	permissions = permission_flags(DOCTYPE, PERMISSION_TYPES, doc)
	return {
		"record": {fieldname: doc.get(fieldname) for fieldname in RECORD_FIELDS},
		"colour_size_data": doc.get_onload().get("colour_size_data"),
		"debit_details": doc.get_onload().get("debit_details") or [],
		"permissions": permissions,
		"actions": inspection_actions(doc, permissions),
		"print_formats": get_document_print_formats(doc),
	}


def inspection_actions(doc, permissions: dict) -> dict:
	draft, submitted, cancelled = (cint(doc.docstatus) == status for status in (0, 1, 2))
	return {
		"edit": action(draft and permissions["can_write"], _("Edit")),
		"submit": action(draft and permissions["can_submit"], _("Submit")),
		"update_status": action(
			submitted and doc.result == "Hold" and permissions["can_write"], _("Update Status")
		),
		"create_debit": action(submitted and can_request_inspection_debit(doc), _("Create Debit")),
		"share": action(submitted, _("Share")),
		"cancel": action(submitted and permissions["can_cancel"], _("Cancel")),
		"amend": action(cancelled and permissions["can_amend"], _("Amend")),
		"delete": action(not submitted and permissions["can_delete"], _("Delete")),
	}


@frappe.whitelist()
def get_new_inspection_defaults(
	against_id: str | None = None,
	grn: str | None = None,
	amend_from: str | None = None,
	duplicate_from: str | None = None,
) -> dict:
	"""Defaults for a new inspection from a Work Order, a GRN, a cancelled inspection or a duplicate."""
	frappe.has_permission(DOCTYPE, ptype="create", throw=True)
	if duplicate_from:
		return _copied_defaults(frappe.get_doc(build_duplicate_values(DOCTYPE, duplicate_from)))
	if amend_from:
		return {**_copied_defaults(_get_amendable(amend_from)), "amended_from": amend_from}
	if grn:
		grn_doc = frappe.get_doc("YRP Goods Received Note", grn)
		grn_doc.check_permission("read")
		if grn_doc.against != WORK_ORDER:
			frappe.throw(_("Goods Received Note {0} is not against a Work Order.").format(grn))
		against_id = grn_doc.against_id
	defaults = {
		"against": WORK_ORDER,
		"against_id": against_id or None,
		"posting_date": nowdate(),
		"checking_level": "Level 2",
		"major_aql_level": frappe.db.get_single_value("SD YRP MRP Settings", "default_major_aql_level"),
		"minor_aql_level": frappe.db.get_single_value("SD YRP MRP Settings", "default_minor_aql_level"),
	}
	if against_id:
		defaults["against_details"] = get_against_details(WORK_ORDER, against_id)
	return defaults


@frappe.whitelist()
def save_inspection(values, name: str | None = None, expected_modified: str | None = None) -> dict:
	values = parse_mapping(values, _("Values"))
	if name:
		doc = frappe.get_doc(DOCTYPE, name, for_update=True)
		doc.check_permission("write")
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a draft Quality Inspection can be edited."))
		assert_expected_modified(doc, expected_modified)
	else:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(DOCTYPE)
		doc.against = WORK_ORDER
		if values.get("amended_from"):
			source = _get_amendable(values["amended_from"])
			# Desk amend copies both result fields, so an untouched result recalculates.
			doc.amended_from, doc.calculated_result = source.name, source.calculated_result
	doc.update({fieldname: values[fieldname] for fieldname in EDITABLE_FIELDS if fieldname in values})
	if "colour_and_size_data" in values:
		doc.colour_and_size_data = _clean_selection(values["colour_and_size_data"], doc.against_id)
	doc.save()
	return get_inspection_workspace(doc.name)


def _get_amendable(name: str):
	source = frappe.get_doc(DOCTYPE, name)
	if cint(source.docstatus) != 2 or not frappe.has_permission(DOCTYPE, "amend", doc=source):
		frappe.throw(_("Only a cancelled inspection you may amend can be amended."), frappe.PermissionError)
	return source


@frappe.whitelist()
def update_inspection_result(name: str, result: str, expected_modified: str | None = None) -> dict:
	"""Hold → Pass/Fail on a submitted inspection, like Desk's Update Status."""
	doc = frappe.get_doc(DOCTYPE, name, for_update=True)
	doc.check_permission("write")
	assert_expected_modified(doc, expected_modified)
	if cint(doc.docstatus) != 1 or doc.result != "Hold":
		frappe.throw(_("Only a submitted inspection on Hold can change its result."))
	if result not in ("Pass", "Fail"):
		frappe.throw(_("Result must be Pass or Fail."))
	doc.result = result
	doc.save()
	return get_inspection_workspace(doc.name)


def _copied_defaults(source) -> dict:
	details = get_against_details(WORK_ORDER, source.against_id)
	selected = {
		"colour": {row.colour for row in source.essdee_quality_inspection_colours if row.selected},
		"size": {row.size for row in source.essdee_quality_inspection_sizes if row.selected},
	}
	for key, rows in (("colour", details["colours"]), ("size", details["sizes"])):
		for row in rows:
			row["selected"] = row[key] in selected[key]
	return {
		**{fieldname: source.get(fieldname) for fieldname in EDITABLE_FIELDS},
		"against": WORK_ORDER,
		"posting_date": nowdate(),
		"against_details": details,
	}


def _clean_selection(selection, against_id) -> dict:
	"""Keep only colours and sizes the Work Order actually delivered."""
	selection = parse_mapping(selection, _("Colours and sizes"))
	details = get_against_details(WORK_ORDER, against_id)
	unknown = {str(row.get("colour")) for row in selection.get("colours") or [] if isinstance(row, dict)} - {
		row["colour"] for row in details["colours"]
	}
	unknown |= {str(row.get("size")) for row in selection.get("sizes") or [] if isinstance(row, dict)} - {
		row["size"] for row in details["sizes"]
	}
	if unknown:
		frappe.throw(_("Work Order {0} has no delivered {1}.").format(against_id, ", ".join(sorted(unknown))))
	return {
		"colours": [
			{"colour": str(row.get("colour") or ""), "selected": cint(row.get("selected"))}
			for row in selection.get("colours") or []
			if isinstance(row, dict)
		],
		"sizes": [
			{"size": str(row.get("size") or ""), "selected": cint(row.get("selected"))}
			for row in selection.get("sizes") or []
			if isinstance(row, dict)
		],
	}
