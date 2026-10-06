"""Permission-aware ``/web`` workspace for Cutting Bulk Lay Sheets.

The native DocType controller remains the workflow authority.  This module only
normalises browser input, projects a compact workspace payload, and wraps native
mutations so every request is permission checked and returns refreshed state.
"""

from __future__ import annotations

from copy import deepcopy

import frappe
from frappe import _
from frappe.utils import cint, nowdate

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_bulk_lay_sheets import (
	sd_yrp_cutting_bulk_lay_sheets as native,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import (
	get_cut_sheet_data,
	get_parts,
	save_web_laysheet_details,
)


DOCTYPE = "SD YRP Cutting Bulk Lay Sheets"
ROW_DOCTYPE = "SD YRP Cutting Bulk Lay Sheet Detail"
LAYSHEET_DOCTYPE = "SD YRP Cutting LaySheet"
TRANSFER_DOCTYPE = "SD YRP Lot Transfer"
DC_DOCTYPE = "YRP Delivery Challan"
LOT_DOCTYPE = "SD YRP Lot"
PLAN_DOCTYPE = "SD YRP Cutting Plan"
MARKER_DOCTYPE = "SD YRP Cutting Marker"

EDITABLE_FIELDS = {
	"main_lot",
	"from_location",
	"posting_date",
	"cutting_spreader",
	"cutter",
	"lot_details",
}
EDITABLE_ROW_FIELDS = {"name", "_row_key", "lot", "cutting_plan", "cutting_marker"}


def _parse_json(value, fallback):
	if value in (None, ""):
		return deepcopy(fallback)
	if isinstance(value, (dict, list)):
		return deepcopy(value)
	return frappe.parse_json(value)


def _doc_value(doc, fieldname, default=None):
	value = getattr(doc, fieldname, None)
	if value is not None and not callable(value):
		return value
	return doc.get(fieldname, default) if hasattr(doc, "get") else default


def _as_dict(row):
	as_dict = getattr(row, "as_dict", None)
	if callable(as_dict):
		return as_dict()
	return dict(row)


def _assert_not_stale(doc, expected_modified=None):
	if expected_modified and str(_doc_value(doc, "modified")) != str(expected_modified):
		frappe.throw(
			_("{0} changed after you opened it. Refresh and try again.").format(doc.name),
			frappe.TimestampMismatchError,
		)


def _normalise_values(values, existing_doc=None):
	values = _parse_json(values, {})
	if not isinstance(values, dict):
		frappe.throw(_("Cutting Bulk Lay Sheets values must be an object."))
	unknown = set(values) - EDITABLE_FIELDS
	if unknown:
		frappe.throw(
			_("These Cutting Bulk Lay Sheets fields cannot be changed here: {0}.").format(
				", ".join(sorted(unknown))
			)
		)

	rows = _parse_json(values.get("lot_details"), [])
	if not isinstance(rows, list):
		frappe.throw(_("Split Lots must be a list."))
	existing_names = {
		_doc_value(row, "name")
		for row in (_doc_value(existing_doc, "lot_details", []) or [])
		if _doc_value(row, "name")
	}
	seen_names = set()
	normalised_rows = []
	for index, row in enumerate(rows, start=1):
		if not isinstance(row, dict):
			frappe.throw(_("Split Lot row {0} must be an object.").format(index))
		unknown_row = set(row) - EDITABLE_ROW_FIELDS
		if unknown_row:
			frappe.throw(
				_("Split Lot row {0} contains fields that cannot be changed here: {1}.").format(
					index, ", ".join(sorted(unknown_row))
				)
			)
		name = row.get("name") or None
		if name:
			if name not in existing_names:
				frappe.throw(_("Split Lot row {0} does not belong to this document.").format(name))
			if name in seen_names:
				frappe.throw(_("Split Lot row {0} is repeated.").format(name))
			seen_names.add(name)
		clean = {
			"lot": row.get("lot"),
			"cutting_plan": row.get("cutting_plan"),
			"cutting_marker": row.get("cutting_marker"),
		}
		if name:
			clean["name"] = name
		normalised_rows.append(clean)

	return {
		"main_lot": values.get("main_lot"),
		"from_location": values.get("from_location"),
		"posting_date": values.get("posting_date"),
		"cutting_spreader": values.get("cutting_spreader"),
		"cutter": values.get("cutter"),
		"lot_details": normalised_rows,
	}


def _assert_source_permissions(values):
	"""Require read access to every source record used to derive child workflows."""

	references = {(LOT_DOCTYPE, values.get("main_lot"))}
	for row in values.get("lot_details") or []:
		references.update(
			{
				(LOT_DOCTYPE, row.get("lot")),
				(PLAN_DOCTYPE, row.get("cutting_plan")),
				(MARKER_DOCTYPE, row.get("cutting_marker")),
			}
		)
	for doctype, name in references:
		if not name:
			continue
		related = frappe.get_doc(doctype, name)
		_require_permission(doctype, "read", related)


def _allowed(doctype, ptype, doc=None):
	kwargs = {"ptype": ptype}
	if doc is not None:
		kwargs["doc"] = doc
	return bool(frappe.has_permission(doctype, **kwargs))


def _permission_flags(doc=None):
	return {
		"can_read": _allowed(DOCTYPE, "read", doc),
		"can_create": _allowed(DOCTYPE, "create"),
		"can_write": bool(doc is not None and _allowed(DOCTYPE, "write", doc)),
		"can_print": bool(doc is not None and _allowed(DOCTYPE, "print", doc)),
	}


def _related_permissions(doctype, doc=None):
	return {
		"can_read": _allowed(doctype, "read", doc),
		"can_create": _allowed(doctype, "create"),
		"can_write": _allowed(doctype, "write", doc),
		"can_submit": _allowed(doctype, "submit", doc),
		"can_print": _allowed(doctype, "print", doc),
	}


def _require_permission(doctype, ptype, doc=None):
	if not _allowed(doctype, ptype, doc):
		frappe.throw(
			_("You do not have {0} permission for {1}.").format(ptype, doctype),
			frappe.PermissionError,
		)


def _assert_action_permission(doc_name, related_doctype=None, ptype=None, related_doc=None):
	doc = frappe.get_doc(DOCTYPE, doc_name)
	_require_permission(DOCTYPE, "write", doc)
	if related_doctype and ptype:
		_require_permission(related_doctype, ptype, related_doc)
	return doc


def _related_doc(doctype, name):
	return frappe.get_doc(doctype, name) if name else None


def _row_related_permissions(row):
	return {
		"laysheet": _related_permissions(
			LAYSHEET_DOCTYPE,
			_related_doc(LAYSHEET_DOCTYPE, row.get("cutting_laysheet")),
		),
		"lot_transfer": _related_permissions(
			TRANSFER_DOCTYPE,
			_related_doc(TRANSFER_DOCTYPE, row.get("lot_transfer")),
		),
		"delivery_challan": _related_permissions(
			DC_DOCTYPE,
			_related_doc(DC_DOCTYPE, row.get("delivery_challan")),
		),
	}


def _row_record(row, status=None):
	status = status or _doc_value(row, "status") or native.get_entry_status(row)
	return {
		"name": _doc_value(row, "name"),
		"idx": cint(_doc_value(row, "idx", 0)),
		"lot": _doc_value(row, "lot"),
		"cutting_plan": _doc_value(row, "cutting_plan"),
		"cutting_marker": _doc_value(row, "cutting_marker"),
		"work_order": _doc_value(row, "work_order"),
		"cutting_laysheet": _doc_value(row, "cutting_laysheet"),
		"lot_transfer": _doc_value(row, "lot_transfer"),
		"delivery_challan": _doc_value(row, "delivery_challan"),
		"status": status,
	}


def _record(doc, include_rows=True):
	record = {
		"name": _doc_value(doc, "name"),
		"modified": _doc_value(doc, "modified"),
		"docstatus": cint(_doc_value(doc, "docstatus", 0)),
		"main_lot": _doc_value(doc, "main_lot"),
		"from_location": _doc_value(doc, "from_location"),
		"posting_date": _doc_value(doc, "posting_date") or nowdate(),
		"cutting_spreader": _doc_value(doc, "cutting_spreader"),
		"cutter": _doc_value(doc, "cutter"),
		"status": _doc_value(doc, "status") or "Setup",
		"active_cutting_laysheet": _doc_value(doc, "active_cutting_laysheet"),
	}
	if include_rows:
		record["lot_details"] = [_row_record(row) for row in (_doc_value(doc, "lot_details", []) or [])]
	return record


@frappe.whitelist()
def get_editor(name=None):
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		_require_permission(DOCTYPE, "read", doc)
	else:
		_require_permission(DOCTYPE, "create")
		doc = frappe.new_doc(DOCTYPE)
		if not _doc_value(doc, "posting_date"):
			doc.posting_date = nowdate()
	return {
		"record": _record(doc),
		"permissions": _permission_flags(doc if name else None),
		"setup_locked": any(
			bool(_doc_value(row, "cutting_laysheet"))
			for row in (_doc_value(doc, "lot_details", []) or [])
		),
	}


@frappe.whitelist()
def save(values, name=None, expected_modified=None):
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		_require_permission(DOCTYPE, "write", doc)
		_assert_not_stale(doc, expected_modified)
	else:
		_require_permission(DOCTYPE, "create")
		doc = frappe.new_doc(DOCTYPE)

	values = _normalise_values(values, doc if name else None)
	_assert_source_permissions(values)
	doc.update(values)
	if name:
		doc.save()
	else:
		doc.insert()
	return get_workspace(doc.name)


def _row_actions(row, permissions):
	status = row["status"]
	has_laysheet = bool(row["cutting_laysheet"])
	return {
		"can_activate": bool(has_laysheet and permissions["laysheet"]["can_read"]),
		"can_generate_bundles": bool(
			has_laysheet
			and not row["lot_transfer"]
			and status in {"Ready to Generate", "Create Lot Transfer"}
			and permissions["laysheet"]["can_write"]
		),
		"can_create_lot_transfer": bool(
			status in {"Create Lot Transfer", "Lot Transfer Cancelled"}
			and permissions["lot_transfer"]["can_create"]
		),
		"can_submit_lot_transfer": bool(
			status == "Submit Lot Transfer" and permissions["lot_transfer"]["can_submit"]
		),
		"can_create_delivery_challan": bool(
			status in {"Make Delivery Challan", "Delivery Challan Cancelled", "Delivery Challan Missing"}
			and permissions["delivery_challan"]["can_create"]
		),
		"can_submit_delivery_challan": bool(
			status == "Submit Delivery Challan" and permissions["delivery_challan"]["can_submit"]
		),
		"can_approve_grammage": bool(
			status == "Approval Pending" and permissions["laysheet"]["can_write"]
		),
		"can_print_labels": bool(
			status == "Ready to Print"
			and permissions["laysheet"]["can_write"]
			and permissions["laysheet"]["can_print"]
		),
	}


def _bulk_actions(rows, permissions):
	transfer_names = {row["lot_transfer"] for row in rows if row["lot_transfer"]}
	shared_transfer = len(transfer_names) == 1 and bool(rows) and all(
		row["lot_transfer"] in transfer_names for row in rows
	)
	create_dc_statuses = {
		"Make Delivery Challan",
		"Delivery Challan Cancelled",
		"Delivery Challan Missing",
	}
	completed_dc_statuses = {"Ready to Print", "Approval Pending", "Completed"}
	return {
		"can_create_laysheets": bool(
			any(not row["cutting_laysheet"] for row in rows)
			and permissions["laysheet"]["can_create"]
		),
		"can_create_bulk_lot_transfer": bool(
			rows
			and all(row["status"] in {"Create Lot Transfer", "Lot Transfer Cancelled"} for row in rows)
			and permissions["lot_transfer"]["can_create"]
		),
		"can_submit_bulk_lot_transfer": bool(
			shared_transfer
			and all(row["status"] == "Submit Lot Transfer" for row in rows)
			and permissions["lot_transfer"]["can_submit"]
		),
		"shared_lot_transfer": next(iter(transfer_names)) if shared_transfer else None,
		"can_create_bulk_delivery_challans": bool(
			any(row["status"] in create_dc_statuses for row in rows)
			and all(row["status"] in create_dc_statuses | completed_dc_statuses for row in rows)
			and permissions["delivery_challan"]["can_create"]
		),
	}


@frappe.whitelist()
def get_workspace(name):
	doc = frappe.get_doc(DOCTYPE, name)
	_require_permission(DOCTYPE, "read", doc)
	permissions = {
		**_permission_flags(doc),
		"laysheet": _related_permissions(LAYSHEET_DOCTYPE),
		"lot_transfer": _related_permissions(TRANSFER_DOCTYPE),
		"delivery_challan": _related_permissions(DC_DOCTYPE),
	}
	rows = []
	for source in _doc_value(doc, "lot_details", []) or []:
		row = _row_record(source, native.get_entry_status(source))
		row["actions"] = _row_actions(row, _row_related_permissions(row))
		rows.append(row)

	active_laysheet = None
	active_name = _doc_value(doc, "active_cutting_laysheet")
	if active_name:
		active_doc = frappe.get_doc(LAYSHEET_DOCTYPE, active_name)
		active_permissions = _related_permissions(LAYSHEET_DOCTYPE, active_doc)
		permissions["laysheet"] = active_permissions
		if active_permissions["can_read"]:
			active_laysheet = native.get_laysheet_editor_data(doc.name, active_name)
	return {
		"record": _record(doc, include_rows=False),
		"setup_locked": any(bool(row["cutting_laysheet"]) for row in rows),
		"rows": rows,
		"active_laysheet": active_laysheet,
		"bundles": (active_laysheet or {}).get("bundles") or [],
		"permissions": permissions,
		"bulk_actions": _bulk_actions(rows, permissions),
	}


def _action_result(doc_name, result):
	return {"result": result, "workspace": get_workspace(doc_name)}


@frappe.whitelist()
def create_laysheets(doc_name):
	_assert_action_permission(doc_name, LAYSHEET_DOCTYPE, "create")
	return _action_result(doc_name, native.create_laysheets(doc_name))


@frappe.whitelist()
def set_active_laysheet(doc_name, cutting_laysheet):
	doc = _assert_action_permission(doc_name)
	row = native.get_entry_for_laysheet(doc.name, cutting_laysheet)
	laysheet = frappe.get_doc(LAYSHEET_DOCTYPE, row.cutting_laysheet)
	_require_permission(LAYSHEET_DOCTYPE, "read", laysheet)
	return _action_result(doc_name, native.set_active_laysheet(doc_name, cutting_laysheet))


@frappe.whitelist()
def save_active_editor(doc_name, detail_name, item_details, item_accessory_details=None, expected_modified=None):
	doc = _assert_action_permission(doc_name)
	row = native.get_entry(doc, detail_name)
	if not row.cutting_laysheet:
		frappe.throw(_("Create the Lay Sheet first."))
	laysheet = frappe.get_doc(LAYSHEET_DOCTYPE, row.cutting_laysheet)
	_require_permission(LAYSHEET_DOCTYPE, "write", laysheet)
	if row.lot_transfer and native.get_docstatus(TRANSFER_DOCTYPE, row.lot_transfer) != 2:
		frappe.throw(_("Lay Sheet {0} cannot be edited after its Lot Transfer is created.").format(laysheet.name))
	details = _parse_json(item_details, [])
	if isinstance(details, dict):
		details = details.get("cloth_items") or []
	accessories = _parse_json(item_accessory_details, [])
	save_web_laysheet_details(
		cutting_plan=laysheet.cutting_plan,
		cutting_order=laysheet.cutting_order,
		cutting_laysheet=laysheet.name,
		cloth_details=details,
		accessory_details=accessories,
		modified=expected_modified,
	)
	if doc.active_cutting_laysheet != row.cutting_laysheet:
		doc.db_set("active_cutting_laysheet", row.cutting_laysheet, update_modified=False)
	return get_workspace(doc.name)


def _validated_bundle_groups(cutting_marker, groups):
	authoritative = get_parts(cutting_marker)
	groups = _parse_json(groups, [])
	if not isinstance(groups, list):
		frappe.throw(_("Bundle groups must be a list."))
	expected_parts = [row.get("part") for row in authoritative]
	received_parts = [row.get("part") for row in groups if isinstance(row, dict)]
	if len(received_parts) != len(expected_parts) or sorted(received_parts) != sorted(expected_parts):
		frappe.throw(_("Marker panels changed. Reload the Lay Sheet and try again."))
	clean = []
	for row in groups:
		try:
			value = int(row.get("value"))
		except (TypeError, ValueError):
			frappe.throw(_("Every Marker panel needs a valid bundle group."))
		if value < 1:
			frappe.throw(_("Bundle group numbers must be greater than zero."))
		clean.append({"part": row.get("part"), "value": value})
	return clean


@frappe.whitelist()
def generate_bundles(
	doc_name,
	detail_name,
	groups,
	bundle_generated_date,
	maximum_no_of_plys=None,
	maximum_allow_percentage=None,
):
	doc = _assert_action_permission(doc_name)
	row = native.get_entry(doc, detail_name)
	if not row.cutting_laysheet:
		frappe.throw(_("Create the Lay Sheet first."))
	laysheet = frappe.get_doc(LAYSHEET_DOCTYPE, row.cutting_laysheet)
	_require_permission(LAYSHEET_DOCTYPE, "write", laysheet)
	clean_groups = _validated_bundle_groups(laysheet.cutting_marker, groups)
	result = get_cut_sheet_data(
		doc_name=laysheet.name,
		cutting_marker=laysheet.cutting_marker,
		laysheet_details=[_as_dict(item) for item in (laysheet.cutting_laysheet_details or [])],
		manual_item_details=[_as_dict(item) for item in (laysheet.cutting_laysheet_manual_items or [])],
		items=clean_groups,
		max_plys=cint(maximum_no_of_plys or laysheet.maximum_no_of_plys),
		maximum_allow=cint(maximum_allow_percentage or laysheet.maximum_allow_percentage),
		bundle_generated_date=bundle_generated_date,
	)
	return _action_result(doc_name, result)


@frappe.whitelist()
def create_lot_transfer(doc_name, detail_name):
	_assert_action_permission(doc_name, TRANSFER_DOCTYPE, "create")
	return _action_result(doc_name, native.create_lot_transfer(doc_name, detail_name))


@frappe.whitelist()
def create_bulk_lot_transfer(doc_name):
	_assert_action_permission(doc_name, TRANSFER_DOCTYPE, "create")
	return _action_result(doc_name, native.create_bulk_lot_transfer(doc_name))


@frappe.whitelist()
def submit_lot_transfer(doc_name, detail_name):
	doc = _assert_action_permission(doc_name)
	row = native.get_entry(doc, detail_name)
	if not row.lot_transfer:
		frappe.throw(_("Create the Lot Transfer first."))
	transfer = frappe.get_doc(TRANSFER_DOCTYPE, row.lot_transfer)
	if transfer.cutting_bulk_lay_sheet != doc.name:
		frappe.throw(_("Lot Transfer {0} is not linked to this Bulk Lay Sheet.").format(transfer.name))
	if cint(transfer.docstatus) == 2:
		frappe.throw(_("Lot Transfer {0} is cancelled. Create a new transfer.").format(transfer.name))
	if cint(transfer.docstatus) == 0:
		_require_permission(TRANSFER_DOCTYPE, "submit", transfer)
		transfer.submit()
	native.refresh_bulk_status(doc.name)
	return _action_result(doc.name, transfer.name)


@frappe.whitelist()
def submit_bulk_lot_transfer(doc_name):
	doc = _assert_action_permission(doc_name)
	transfer_names = {
		_doc_value(row, "lot_transfer")
		for row in (_doc_value(doc, "lot_details", []) or [])
		if _doc_value(row, "lot_transfer")
	}
	if not transfer_names:
		frappe.throw(_("Create the Bulk Lot Transfer first."))
	for transfer_name in transfer_names:
		transfer = frappe.get_doc(TRANSFER_DOCTYPE, transfer_name)
		if _doc_value(transfer, "cutting_bulk_lay_sheet") != doc.name:
			frappe.throw(
				_("Lot Transfer {0} is not linked to this Bulk Lay Sheet.").format(transfer.name)
			)
		_require_permission(TRANSFER_DOCTYPE, "submit", transfer)
	return _action_result(doc_name, native.submit_bulk_lot_transfer(doc_name))


@frappe.whitelist()
def prepare_delivery_challan(doc_name, detail_name):
	_assert_action_permission(doc_name, DC_DOCTYPE, "create")
	return native.prepare_delivery_challan(doc_name, detail_name)


@frappe.whitelist()
def get_delivery_challan_setup(doc_name):
	_assert_action_permission(doc_name, DC_DOCTYPE, "create")
	return native.get_delivery_challan_naming_series(doc_name)


@frappe.whitelist()
def create_delivery_challan(doc_name, detail_name, naming_series, vehicle_no):
	_assert_action_permission(doc_name, DC_DOCTYPE, "create")
	result = native.create_delivery_challan(doc_name, detail_name, naming_series, vehicle_no)
	return _action_result(doc_name, result)


@frappe.whitelist()
def create_bulk_delivery_challans(doc_name, naming_series, vehicle_no):
	_assert_action_permission(doc_name, DC_DOCTYPE, "create")
	result = native.create_bulk_delivery_challans(doc_name, naming_series, vehicle_no)
	return _action_result(doc_name, result)


@frappe.whitelist()
def submit_delivery_challan(doc_name, detail_name):
	doc = _assert_action_permission(doc_name)
	row = native.get_entry(doc, detail_name)
	challan = _related_doc(DC_DOCTYPE, row.delivery_challan)
	_require_permission(DC_DOCTYPE, "submit", challan)
	return _action_result(doc_name, native.submit_delivery_challan(doc_name, detail_name))


@frappe.whitelist()
def approve_grammage(doc_name, detail_name):
	doc = _assert_action_permission(doc_name)
	row = native.get_entry(doc, detail_name)
	_require_permission(LAYSHEET_DOCTYPE, "write", _related_doc(LAYSHEET_DOCTYPE, row.cutting_laysheet))
	return _action_result(doc_name, native.approve_laysheet_grammage(doc_name, detail_name))


@frappe.whitelist()
def get_print_context(doc_name, detail_name):
	doc = _assert_action_permission(doc_name)
	row = native.get_entry(doc, detail_name)
	laysheet = _related_doc(LAYSHEET_DOCTYPE, row.cutting_laysheet)
	_require_permission(LAYSHEET_DOCTYPE, "write", laysheet)
	_require_permission(LAYSHEET_DOCTYPE, "print", laysheet)
	return native.get_label_print_context(doc_name, detail_name)


@frappe.whitelist()
def complete_label_print(doc_name, detail_name, goods_received_note=None):
	doc = _assert_action_permission(doc_name)
	row = native.get_entry(doc, detail_name)
	laysheet = _related_doc(LAYSHEET_DOCTYPE, row.cutting_laysheet)
	_require_permission(LAYSHEET_DOCTYPE, "write", laysheet)
	_require_permission(LAYSHEET_DOCTYPE, "print", laysheet)
	result = native.mark_labels_printed(doc_name, detail_name, goods_received_note)
	return _action_result(doc_name, result)
