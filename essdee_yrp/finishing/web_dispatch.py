"""Permission-aware /web workspace for Finishing Plan Dispatch documents."""

from __future__ import annotations

import copy

import frappe
from frappe import _
from frappe.utils import cint, flt

from essdee_yrp.cut_panel_store.common import assert_expected_modified, parse_json_object
from essdee_yrp.essdee_yrp.doctype.sd_yrp_finishing_plan_dispatch import (
	sd_yrp_finishing_plan_dispatch as dispatch_service,
)
from essdee_yrp.print_registry import get_document_print_formats

DOCTYPE = "SD YRP Finishing Plan Dispatch"
RECORD_FIELDS = (
	"name",
	"docstatus",
	"naming_series",
	"stock_entry",
	"fp_total_dispatched",
	"modified",
	"owner",
	"creation",
)
STOCK_FIELDS = ("from_location", "to_location", "goods_value", "vehicle_no")


def quantity(value, label):
	try:
		number = flt(value) if value not in (None, "") else 0
	except TypeError, ValueError:
		frappe.throw(_("{0} must be a number.").format(label))
	if number < 0:
		frappe.throw(_("{0} cannot be negative.").format(label))
	return number


def merge_sizes(fresh, posted):
	values = posted.get("values") or {}
	unknown = set(values) - set(fresh["values"])
	if unknown:
		frappe.throw(
			_("Size {0} is not available in {1}.").format(", ".join(sorted(unknown)), fresh["doc_name"])
		)
	for size, value in fresh["values"].items():
		value["dispatch_qty"] = quantity(
			(values.get(size) or {}).get("dispatch_qty"), f"{fresh['doc_name']} {size}"
		)


def merge_batches(fresh, posted):
	available = {batch.get("batch_row") for batch in fresh.get("packing_batches") or []}
	batches = []
	for batch in posted.get("batch_dispatches") or []:
		if batch.get("batch_row") not in available:
			frappe.throw(
				_("Packing batch {0} is not available in {1}.").format(
					batch.get("batch_row"), fresh["doc_name"]
				)
			)
		boxes = quantity(batch.get("box_quantity"), f"{fresh['doc_name']} {batch.get('batch_row')}")
		if boxes:
			batches.append({"batch_row": batch["batch_row"], "box_quantity": boxes})
	fresh["batch_dispatches"] = batches


def colour_grid(posted):
	grid = posted.get("colour_grid") or {}
	if not isinstance(grid, dict):
		frappe.throw(_("Colour details must be an object."))
	return {
		str(colour): {str(size): quantity(value, f"{colour} {size}") for size, value in (sizes or {}).items()}
		for colour, sizes in grid.items()
	}


def reject_negative(posted):
	for size, value in (posted.get("values") or {}).items():
		quantity((value or {}).get("dispatch_qty"), f"{posted.get('doc_name')} {size}")
	for batch in posted.get("batch_dispatches") or []:
		quantity(batch.get("box_quantity"), f"{posted.get('doc_name')} {batch.get('batch_row')}")


def authoritative_items(posted_items):
	"""Rebuild the dispatch grid from server balances, keeping only the requested quantities."""

	posted_items = frappe.parse_json(posted_items) if isinstance(posted_items, str) else posted_items or []
	if not isinstance(posted_items, list):
		frappe.throw(_("Finishing Items must be a list."))
	fresh_by_plan = {row["doc_name"]: row for row in dispatch_service.fetch_fp_items()}
	items = []
	for posted in posted_items:
		reject_negative(posted)
		if not dispatch_service._has_dispatch_request(posted):
			continue
		if posted.get("doc_name") not in fresh_by_plan:
			frappe.throw(
				_("Finishing Plan {0} has no packed balance to dispatch. Fetch Items again.").format(
					posted.get("doc_name")
				)
			)
		fresh = copy.deepcopy(fresh_by_plan[posted["doc_name"]])
		merge_sizes(fresh, posted)
		merge_batches(fresh, posted)
		fresh["colour_grid"] = colour_grid(posted)
		items.append(fresh)
	return items


def dispatch_permissions(doc):
	def allowed(ptype):
		return bool(frappe.has_permission(DOCTYPE, ptype=ptype, doc=doc))

	draft, submitted = doc.docstatus == 0, doc.docstatus == 1
	stock_open = (
		not doc.stock_entry or frappe.db.get_value("YRP Stock Entry", doc.stock_entry, "docstatus") == 2
	)
	return {
		"can_read": True,
		"can_write": draft and allowed("write"),
		"can_submit": draft and allowed("submit"),
		"can_cancel": submitted and allowed("cancel"),
		"can_dispatch_stock": submitted and allowed("write") and stock_open,
		"can_print": allowed("print"),
	}


@frappe.whitelist()
def fetch_dispatch_items():
	if not frappe.has_permission(DOCTYPE, ptype="create"):
		frappe.throw(_("Not permitted to create Finishing Plan Dispatch."), frappe.PermissionError)
	return dispatch_service.fetch_fp_items()


@frappe.whitelist()
def get_dispatch_workspace(name: str | None = None) -> dict:
	"""Return the dispatch grid, record and permissions for a new or saved dispatch."""

	if not name:
		return {
			"record": {
				"name": "",
				"docstatus": 0,
				"naming_series": dispatch_service.get_current_fiscal_naming_series(),
			},
			"items": fetch_dispatch_items(),
			"permissions": {
				"can_read": True,
				"can_write": True,
				"can_submit": bool(frappe.has_permission(DOCTYPE, ptype="submit")),
			},
			"print_formats": [],
		}
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	doc.run_method("onload")
	return {
		"record": {field: doc.get(field) for field in RECORD_FIELDS},
		"items": (doc.get_onload() or {}).get("items") or [],
		"permissions": dispatch_permissions(doc),
		"print_formats": get_document_print_formats(doc),
	}


def save_values(doc, items, submit):
	doc.finishing_items = frappe.as_json(authoritative_items(items))
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	if cint(submit):
		doc.check_permission("submit")
		doc.submit()


@frappe.whitelist()
def save_dispatch(items, name: str | None = None, submit=0, expected_modified: str | None = None) -> dict:
	"""Create or update a draft dispatch from server-rebuilt rows, optionally submitting it."""

	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		if doc.docstatus != 0:
			frappe.throw(_("Only a draft Finishing Plan Dispatch can be edited."))
		doc.check_permission("write")
		assert_expected_modified(doc, expected_modified)
	else:
		if not frappe.has_permission(DOCTYPE, ptype="create"):
			frappe.throw(_("Not permitted to create Finishing Plan Dispatch."), frappe.PermissionError)
		doc = frappe.new_doc(DOCTYPE)
		doc.naming_series = dispatch_service.get_current_fiscal_naming_series()
	save_values(doc, items, submit)
	return get_dispatch_workspace(doc.name)


def dispatch_stock(doc, values):
	missing = [field for field in STOCK_FIELDS if values.get(field) in (None, "")]
	if missing:
		frappe.throw(_("Enter {0}.").format(", ".join(field.replace("_", " ").title() for field in missing)))
	name = dispatch_service.create_stock_dispatch(
		doc_name=doc.name, **{field: values[field] for field in STOCK_FIELDS}
	)
	return {"doctype": "YRP Stock Entry", "name": name}


def cancel_dispatch(doc, _values):
	doc.cancel()


COMMANDS = {
	"dispatch_stock": ("can_dispatch_stock", dispatch_stock),
	"cancel": ("can_cancel", cancel_dispatch),
}


@frappe.whitelist()
def execute_dispatch_command(
	name: str, command: str, payload=None, expected_modified: str | None = None
) -> dict:
	"""Run one dispatch command after rechecking its availability and freshness."""

	if command not in COMMANDS:
		frappe.throw(_("Unknown Finishing Plan Dispatch command: {0}").format(command))
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	assert_expected_modified(doc, expected_modified)
	flag, handler = COMMANDS[command]
	if not dispatch_permissions(doc)[flag]:
		frappe.throw(_("This action is not available for the Finishing Plan Dispatch in its current state."))
	result = handler(doc, parse_json_object(payload, label=_("Command payload")))
	return {**get_dispatch_workspace(name), "result": result}
