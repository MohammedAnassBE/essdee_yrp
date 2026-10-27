"""Permission-aware Cutting Plan CPM and stock workspace APIs.

The web workspace owns only orchestration. Existing DocType controllers remain
authoritative for stock, bundle-ledger, valuation, Work Order, and cancellation
rules. Browser payloads never own the Cutting Plan identity or stock balances.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate, nowtime
from yrp.stock.api import get_stock_dimensions_for_ui
from yrp.stock.dimensions import get_dimension_fieldnames, get_stock_dimensions
from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import (
	_get_warehouse_for_supplier,
)

from essdee_yrp.cutting.lot_transfer_quantities import apply_quantities, get_quantity_rows
from essdee_yrp.cutting.movement import (
	build_delivery_challan_defaults,
	build_stock_entry_defaults,
	get_active_root_transactions_by_movement,
	new_transaction_from_defaults,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_panel_movement.sd_yrp_cut_panel_movement import (
	get_cut_bundle_unmoved_data,
	get_total,
)
from essdee_yrp.print_registry import get_document_print_formats, print_format_scope

PLAN_DOCTYPE = "SD YRP Cutting Plan"
RELATION_DOCTYPE = "SD YRP Cutting Plan Stock Transfer"
MOVEMENT_DOCTYPE = "SD YRP Cut Panel Movement"
STOCK_ITEM_BUILDER_FILTERS = {
	"is_stock_item": 1,
	"disabled": 0,
	"variant_of": ["is", "not set"],
}

OPERATION_DOCTYPES = {
	"stock_entry": "YRP Stock Entry",
	"stock_reconciliation": "YRP Stock Reconciliation",
	"stock_update": "YRP Stock Update",
	"lot_transfer": "SD YRP Lot Transfer",
	"delivery_challan": "YRP Delivery Challan",
	"goods_received_note": "YRP Goods Received Note",
}
DOCTYPE_OPERATIONS = {doctype: operation for operation, doctype in OPERATION_DOCTYPES.items()}
PLAN_STOCK_OPERATIONS = {"stock_entry", "stock_reconciliation", "stock_update", "lot_transfer"}
MOVEMENT_OPERATIONS = {"stock_entry", "delivery_challan"}
STOCK_ENTRY_PURPOSES = {"Material Issue", "Material Consumed", "Send to Warehouse"}
STOCK_UPDATE_TYPES = {"Add", "Reduce"}
ITEM_EDITOR_OPERATIONS = {
	"stock_entry",
	"stock_reconciliation",
	"stock_update",
	"lot_transfer",
}

HEADER_FIELDS = {
	"YRP Stock Entry": (
		"purpose",
		"from_warehouse",
		"to_warehouse",
		"from_supplier",
		"to_supplier",
		"posting_date",
		"posting_time",
		"comments",
		"cut_panel_movement",
	),
	"YRP Stock Reconciliation": (
		"purpose",
		"default_warehouse",
		"default_supplier",
		"posting_date",
		"posting_time",
		"comments",
	),
	"YRP Stock Update": (
		"warehouse",
		"supplier",
		"update_type",
		"posting_date",
		"posting_time",
		"comments",
	),
	"SD YRP Lot Transfer": ("posting_date", "posting_time", "comments"),
	"YRP Delivery Challan": (
		"work_order",
		"from_location",
		"supplier",
		"from_warehouse",
		"to_warehouse",
		"posting_date",
		"posting_time",
		"process_name",
		"item",
		"cut_panel_movement",
		"total_delivered_qty",
		"comments",
	),
	"YRP Goods Received Note": (
		"against",
		"against_id",
		"supplier",
		"delivery_location",
		"posting_date",
		"posting_time",
		"cut_panel_movement",
	),
}

ITEM_TABLES = {
	"YRP Stock Entry": "items",
	"YRP Stock Reconciliation": "items",
	"YRP Stock Update": "stock_update_details",
	"SD YRP Lot Transfer": "items",
	"YRP Delivery Challan": "items",
	"YRP Goods Received Note": "items",
}

def _parse(value, default=None):
	if isinstance(value, str):
		value = frappe.parse_json(value)
	return value if value is not None else default


def _status_label(docstatus):
	return {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(cint(docstatus), "Draft")


def _get_plan(cutting_plan, permission="read"):
	plan = frappe.get_doc("SD YRP Cutting Plan", cutting_plan)
	plan.check_permission(permission)
	return plan


def _require_active_plan(plan):
	if plan.docstatus != 1:
		frappe.throw(_("Submit the Cutting Plan before creating cutting transactions."))
	if plan.version == "V1":
		frappe.throw(_("Cut Panel Movement is not supported for a V1 Cutting Plan."))
	if not plan.work_order:
		frappe.throw(_("Work Order is required in Cutting Plan {0}.").format(plan.name))


def _plan_context(plan, *, require_source=False):
	context = frappe._dict(
		cutting_plan=plan.name,
		lot=plan.lot,
		item=plan.item,
		production_detail=plan.production_detail,
		work_order=plan.work_order,
		version=plan.version,
		docstatus=plan.docstatus,
		cp_status=plan.cp_status,
		source_supplier=None,
		source_warehouse=None,
		default_received_type=frappe.db.get_single_value(
			"YRP Stock Settings", "default_received_type"
		),
	)
	if plan.work_order:
		work_order = frappe.get_doc("YRP Work Order", plan.work_order)
		work_order.check_permission("read")
		context.source_supplier = work_order.supplier
		if work_order.supplier:
			context.source_warehouse = _get_warehouse_for_supplier(work_order.supplier)
	if require_source and (not context.source_supplier or not context.source_warehouse):
		frappe.throw(
			_("Work Order {0} needs one enabled Warehouse for its Supplier.").format(
				plan.work_order
			)
		)
	return context


def _permission_flags(doctype):
	return {
		"can_read": bool(frappe.has_permission(doctype, "read")),
		"can_create": bool(frappe.has_permission(doctype, "create")),
		"can_write": bool(frappe.has_permission(doctype, "write")),
		"can_submit": bool(frappe.has_permission(doctype, "submit")),
		"can_cancel": bool(frappe.has_permission(doctype, "cancel")),
		"can_delete": bool(frappe.has_permission(doctype, "delete")),
	}


def _workspace_permissions(plan, context):
	active = bool(
		plan.docstatus == 1
		and plan.version != "V1"
		and plan.work_order
		and context.source_supplier
		and context.source_warehouse
	)
	permissions = {"movement": _permission_flags(MOVEMENT_DOCTYPE)}
	permissions["movement"]["can_create"] = bool(
		active
		and permissions["movement"]["can_read"]
		and permissions["movement"]["can_create"]
	)
	stock_read = bool(frappe.has_permission("YRP Stock Ledger Entry", "read"))
	for operation, doctype in OPERATION_DOCTYPES.items():
		flags = _permission_flags(doctype)
		flags["can_create"] = bool(active and flags["can_read"] and flags["can_create"])
		if operation in PLAN_STOCK_OPERATIONS:
			flags["can_create"] = bool(flags["can_create"] and stock_read)
		permissions[operation] = flags
	return permissions


def _movement_totals(value):
	data = _parse(value, {}) or {}
	exact_bundles = 0
	selected_panels = 0
	for colour in (data.get("data") or {}).values():
		for row in colour.get("data") or []:
			moved = [
				key
				for key, selected in row.items()
				if key.endswith("_moved") and key != "bundle_moved" and cint(selected)
			]
			if moved or cint(row.get("bundle_moved")):
				exact_bundles += 1
				selected_panels += len(moved)
	collapsed_rows = sum(
		1
		for row in data.get("collapsed_details") or []
		if cint(row.get("moved")) and flt(row.get("move_qty")) > 0
	)
	accessory_rows = sum(
		1 for row in data.get("accessory_data") or [] if flt(row.get("moved_weight")) > 0
	)
	return {
		"exact_bundles": exact_bundles,
		"selected_panels": selected_panels,
		"collapsed_rows": collapsed_rows,
		"accessory_rows": accessory_rows,
	}


def _movement_payload(doc, *, include_data=False, active_root_rows=None):
	"""`active_root_rows`: the movement's active root transactions when the caller already read them."""
	if active_root_rows is None:
		active_root_rows = []
		if doc.docstatus == 1:
			from essdee_yrp.cutting.movement import get_active_root_transactions

			active_root_rows = get_active_root_transactions(doc.name)
	active_roots = [
		{
			"doctype": row.doctype,
			"name": row.name,
			"docstatus": row.docstatus,
		}
		for row in active_root_rows
	]
	payload = {
		"name": doc.name,
		"docstatus": doc.docstatus,
		"status": _status_label(doc.docstatus),
		"movement_date": doc.movement_date,
		"posting_date": doc.posting_date,
		"posting_time": doc.posting_time,
		"from_warehouse": doc.from_warehouse,
		"lot": doc.lot,
		"item": doc.item,
		"against": doc.against,
		"against_id": doc.against_id,
		"modified": doc.modified,
		"totals": _movement_totals(doc.cut_panel_movement_json),
		"active_root_transactions": active_roots,
		"permissions": {
			"can_write": bool(doc.docstatus == 0 and frappe.has_permission(doc.doctype, "write", doc=doc)),
			"can_submit": bool(doc.docstatus == 0 and frappe.has_permission(doc.doctype, "submit", doc=doc)),
			"can_cancel": bool(doc.docstatus == 1 and frappe.has_permission(doc.doctype, "cancel", doc=doc)),
			"can_print": bool(frappe.has_permission(doc.doctype, "print", doc=doc)),
		},
		"print_formats": get_document_print_formats(doc),
	}
	if include_data:
		payload["movement_data"] = _parse(doc.cut_panel_movement_json, {}) or {}
	return payload


def _get_movements(plan):
	if not frappe.has_permission(MOVEMENT_DOCTYPE, "read"):
		return []
	names = frappe.get_list(
		MOVEMENT_DOCTYPE,
		filters={"cutting_plan": plan.name, "movement_from_cutting": 1},
		pluck="name",
		order_by="modified desc",
		limit_page_length=500,
	)
	docs = [frappe.get_doc(MOVEMENT_DOCTYPE, name) for name in names]
	roots = get_active_root_transactions_by_movement(doc.name for doc in docs if doc.docstatus == 1)
	return [_movement_payload(doc, active_root_rows=roots.get(doc.name, [])) for doc in docs]


def _transaction_permissions(doc):
	return {
		"can_submit": bool(doc.docstatus == 0 and frappe.has_permission(doc.doctype, "submit", doc=doc)),
		"can_cancel": bool(doc.docstatus == 1 and frappe.has_permission(doc.doctype, "cancel", doc=doc)),
		"can_delete": bool(doc.docstatus == 0 and frappe.has_permission(doc.doctype, "delete", doc=doc)),
		"can_print": bool(frappe.has_permission(doc.doctype, "print", doc=doc)),
	}


def _transaction_item_groups(doc, table_field):
	"""Return the same parent-item/attribute matrix shown by the Desk editor.

	The transaction document stores one physical child row per Item Variant.
	Those variant codes are an implementation detail, so the web workspace uses
	the canonical YRP projection and Essdee's logical-row normalization before
	rendering a saved document.
	"""
	rows = doc.get(table_field) or []
	if not rows:
		return []

	from yrp.stock.save_stock_items import group_items_for_ui

	from essdee_yrp.item_matrix import normalize_item_matrix_row_indexes

	if doc.doctype == "SD YRP Lot Transfer":
		from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_transfer.sd_yrp_lot_transfer import (
			ITEM_EDITOR_CONFIG,
		)

		display_rows = normalize_item_matrix_row_indexes(
			rows,
			extra_group_fields=("from_lot", "to_lot"),
		)
		return group_items_for_ui(
			display_rows,
			doc.doctype,
			config=ITEM_EDITOR_CONFIG,
		)

	if doc.doctype == "YRP Goods Received Note":
		# GRN has additional packing/cutting projections. Its controller already
		# chooses the correct one; reuse that exact Desk payload when available.
		doc.run_method("onload")
		item_details = (doc.get("__onload") or {}).get("item_details")
		if item_details:
			return _parse(item_details, []) or []

	display_rows = normalize_item_matrix_row_indexes(rows)
	return group_items_for_ui(display_rows, doc.doctype)


def _transaction_payload(doc, *, include_items=False, plan=None):
	payload = {
		"doctype": doc.doctype,
		"operation": DOCTYPE_OPERATIONS.get(doc.doctype),
		"name": doc.name,
		"docstatus": doc.docstatus,
		"status": _status_label(doc.docstatus),
		"posting_date": doc.get("posting_date"),
		"posting_time": doc.get("posting_time"),
		"purpose": doc.get("purpose"),
		"update_type": doc.get("update_type"),
		"modified": doc.modified,
		"permissions": _transaction_permissions(doc),
		"print_formats": get_document_print_formats(doc),
	}
	if include_items:
		payload["details"] = [
			{"label": doc.meta.get_label(fieldname), "fieldname": fieldname, "value": doc.get(fieldname)}
			for fieldname in HEADER_FIELDS.get(doc.doctype, ())
			if doc.meta.get_field(fieldname) and doc.get(fieldname) not in (None, "")
		]
		table_field = ITEM_TABLES.get(doc.doctype)
		rows = (doc.get(table_field) or []) if table_field else []
		# Do not send raw Item Variant rows to the browser. The matrix below is
		# the user-facing contract and contains the same quantities grouped by
		# parent Item and attributes, exactly like the Desk item component.
		payload["item_row_count"] = len(rows)
		payload["item_groups"] = (
			_transaction_item_groups(doc, table_field) if table_field else []
		)
		if plan:
			payload["quantity_rows"] = get_quantity_rows(plan, doc)
	return payload


def _transaction_references(plan):
	"""Merge the new plan registry with historical CPM-native target links."""
	references = []
	seen = set()
	for relation in plan.get("stock_transfers") or []:
		key = (relation.against, relation.against_id)
		if key in seen:
			continue
		seen.add(key)
		references.append(key)

	if frappe.has_permission(MOVEMENT_DOCTYPE, "read"):
		for movement in frappe.get_list(
			MOVEMENT_DOCTYPE,
			filters={
				"cutting_plan": plan.name,
				"movement_from_cutting": 1,
				"against_id": ["is", "set"],
			},
			fields=["against", "against_id"],
			order_by="modified desc",
			limit_page_length=500,
		):
			key = (movement.against, movement.against_id)
			if key in seen or movement.against not in DOCTYPE_OPERATIONS:
				continue
			seen.add(key)
			references.append(key)
	return references


def _get_transactions(plan):
	transactions = defaultdict(list)
	for doctype, name in _transaction_references(plan):
		operation = DOCTYPE_OPERATIONS.get(doctype)
		if not operation or not frappe.db.exists(doctype, name):
			continue
		doc = frappe.get_doc(doctype, name)
		if not frappe.has_permission(doc.doctype, "read", doc=doc):
			continue
		transactions[operation].append(_transaction_payload(doc))
	for rows in transactions.values():
		rows.sort(key=lambda row: str(row.get("modified") or ""), reverse=True)
	return {operation: transactions.get(operation, []) for operation in OPERATION_DOCTYPES}


@frappe.whitelist()
def get_workspace(cutting_plan):
	"""Load the CPM workspace only when its web tab is activated."""
	plan = _get_plan(cutting_plan)
	context = _plan_context(plan)
	with print_format_scope():
		return {
			"context": context,
			"permissions": _workspace_permissions(plan, context),
			"movements": _get_movements(plan),
			"transactions": _get_transactions(plan),
		}


def _assert_movement_belongs(plan, movement):
	if movement.cutting_plan != plan.name or not cint(movement.movement_from_cutting):
		frappe.throw(_("Cut Panel Movement {0} does not belong to this Cutting Plan.").format(movement.name))


def _movement_identity(doc, plan, context):
	doc.cutting_plan = plan.name
	doc.lot = plan.lot
	doc.item = plan.item
	doc.from_warehouse = context.source_supplier
	doc.movement_from_cutting = 1


def _draft_movement_message(plan, context):
	existing = frappe.db.exists(
		MOVEMENT_DOCTYPE,
		{"lot": plan.lot, "from_warehouse": context.source_supplier, "docstatus": 0},
	)
	if existing:
		return _("Submit or delete draft Cut Panel Movement {0} for {1} / {2} first.").format(
			existing, context.source_supplier, plan.lot
		)
	return ""


def _movement_editor_payload(plan, context, doc=None):
	posting_date = doc.posting_date if doc else nowdate()
	posting_time = doc.posting_time if doc else nowtime()
	if doc:
		movement_data = _parse(doc.cut_panel_movement_json, {}) or {}
	else:
		movement_data = {
			"panels": [],
			"data": {},
			"accessory_data": [],
			"collapsed_details": [],
			"is_set_item": 0,
		}
	return {
		"context": context,
		"record": _movement_payload(doc, include_data=True) if doc else None,
		"defaults": {
			"posting_date": posting_date,
			"posting_time": posting_time,
			"edit_posting_date_and_time": cint(doc.edit_posting_date_and_time) if doc else 0,
		},
		"movement_data": movement_data,
		"permissions": {
			"can_create": bool(frappe.has_permission(MOVEMENT_DOCTYPE, "create")),
			"can_submit": bool(frappe.has_permission(MOVEMENT_DOCTYPE, "submit")),
		},
	}


@frappe.whitelist()
def get_movement_editor(cutting_plan, movement=None):
	plan = _get_plan(cutting_plan)
	if not movement:
		_require_active_plan(plan)
		context = _plan_context(plan, require_source=True)
		frappe.has_permission(MOVEMENT_DOCTYPE, "create", throw=True)
		return {
			**_movement_editor_payload(plan, context),
			"create_blocker": _draft_movement_message(plan, context),
		}
	context = _plan_context(plan)
	doc = frappe.get_doc(MOVEMENT_DOCTYPE, movement)
	doc.check_permission("read")
	_assert_movement_belongs(plan, doc)
	return _movement_editor_payload(plan, context, doc)


@frappe.whitelist()
def generate_movement_bundles(cutting_plan, posting_date=None, posting_time=None):
	"""Generate current bundle availability only after an explicit UI action."""
	plan = _get_plan(cutting_plan)
	_require_active_plan(plan)
	context = _plan_context(plan, require_source=True)
	frappe.has_permission(MOVEMENT_DOCTYPE, "create", throw=True)
	if message := _draft_movement_message(plan, context):
		frappe.throw(message)
	return get_cut_bundle_unmoved_data(
		context.source_supplier,
		plan.lot,
		posting_date or nowdate(),
		posting_time or nowtime(),
		1,
		cutting_plan=plan.name,
		get_collapsed=True,
	)


def _validate_movement_data(value):
	data = _parse(value, {}) or {}
	if not isinstance(data, dict):
		frappe.throw(_("Movement Details must be a JSON object."))
	for row in data.get("collapsed_details") or []:
		if flt(row.get("move_qty")) < 0:
			frappe.throw(_("Collapsed move qty cannot be negative."))
	for row in data.get("accessory_data") or []:
		if flt(row.get("moved_weight")) < 0:
			frappe.throw(_("Accessory moving weight cannot be negative."))
		if flt(row.get("moved_weight")) > flt(row.get("weight")):
			frappe.throw(_("Accessory moving weight cannot exceed its available weight."))
	return data


def _json_identity(value):
	value = _parse(value, {}) or {}
	return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _exact_bundle_key(colour, row):
	return (
		colour,
		row.get("lay_no"),
		row.get("bundle_no"),
		row.get("size"),
		row.get("shade"),
		_json_identity(row.get("set_combination")),
	)


def _collapsed_key(row):
	return (
		row.get("colour"),
		row.get("size"),
		row.get("panel"),
		row.get("shade"),
		row.get("lay_no"),
		row.get("bundle_no"),
		_json_identity(row.get("set_combination")),
	)


def _accessory_key(row):
	return (
		row.get("cloth_name"),
		row.get("cloth_type"),
		row.get("colour"),
		row.get("dia"),
		row.get("shade"),
	)


def _apply_authoritative_movement_selection(available, selected):
	"""Copy selection flags onto authoritative quantities and dimensions."""
	selected_exact = {}
	for colour, detail in (selected.get("data") or {}).items():
		for row in detail.get("data") or []:
			selected_exact[_exact_bundle_key(colour, row)] = row

	panels = available.get("panels") or []
	for colour, detail in (available.get("data") or {}).items():
		group_panels = panels if isinstance(panels, list) else panels.get(detail.get("part"), [])
		for row in detail.get("data") or []:
			selection = selected_exact.get(_exact_bundle_key(colour, row), {})
			for panel in group_panels:
				if flt(row.get(panel)) > 0:
					row[f"{panel}_moved"] = bool(selection.get(f"{panel}_moved"))
			selected_flags = [
				bool(row.get(f"{panel}_moved"))
				for panel in group_panels
				if flt(row.get(panel)) > 0
			]
			row["bundle_moved"] = bool(selected_flags and all(selected_flags))

	selected_collapsed = {
		_collapsed_key(row): row for row in selected.get("collapsed_details") or []
	}
	for row in available.get("collapsed_details") or []:
		selection = selected_collapsed.get(_collapsed_key(row), {})
		move_qty = flt(selection.get("move_qty"), 3) if cint(selection.get("moved")) else 0
		if move_qty > flt(row.get("quantity"), 3):
			frappe.throw(_("Collapsed move qty cannot exceed its available quantity."))
		row["moved"] = bool(move_qty > 0)
		row["move_qty"] = move_qty

	selected_accessories = {
		_accessory_key(row): row for row in selected.get("accessory_data") or []
	}
	for row in available.get("accessory_data") or []:
		selection = selected_accessories.get(_accessory_key(row), {})
		moved_weight = flt(selection.get("moved_weight"), 3)
		if moved_weight > flt(row.get("weight"), 3):
			frappe.throw(_("Accessory moving weight cannot exceed its available weight."))
		row["moved_weight"] = moved_weight
	return available


def _authoritative_movement_data(plan, context, doc, selected):
	available = get_cut_bundle_unmoved_data(
		context.source_supplier,
		plan.lot,
		doc.posting_date or nowdate(),
		doc.posting_time or nowtime(),
		1,
		cutting_plan=plan.name,
		get_collapsed=True,
	)
	return _apply_authoritative_movement_selection(available, selected)


def _assert_not_stale(doc, expected_modified):
	if expected_modified and str(doc.modified) != str(expected_modified):
		frappe.throw(_("This document changed after it was opened. Reload and try again."))


@frappe.whitelist()
def save_movement(cutting_plan, values, movement=None, submit=False, expected_modified=None):
	plan = _get_plan(cutting_plan)
	_require_active_plan(plan)
	context = _plan_context(plan, require_source=True)
	values = _parse(values, {}) or {}
	movement_data = _validate_movement_data(values.get("movement_data"))
	if movement:
		doc = frappe.get_doc(MOVEMENT_DOCTYPE, movement)
		doc.check_permission("write")
		_assert_movement_belongs(plan, doc)
		_assert_not_stale(doc, expected_modified)
		if doc.docstatus != 0:
			frappe.throw(_("Only a Draft Cut Panel Movement can be edited."))
	else:
		frappe.has_permission(MOVEMENT_DOCTYPE, "create", throw=True)
		doc = frappe.new_doc(MOVEMENT_DOCTYPE)

	_movement_identity(doc, plan, context)
	doc.edit_posting_date_and_time = cint(values.get("edit_posting_date_and_time"))
	if doc.edit_posting_date_and_time:
		doc.posting_date = values.get("posting_date") or nowdate()
		doc.posting_time = values.get("posting_time") or nowtime()
	movement_data = _authoritative_movement_data(plan, context, doc, movement_data)
	doc.movement_data = movement_data
	# The legacy controller historically skipped movement_data on first insert.
	# Persist the normalized structure explicitly while keeping its submit filter.
	doc.cut_panel_movement_json = get_total(json.loads(json.dumps(movement_data)))
	doc.save()
	if cint(submit):
		doc.check_permission("submit")
		doc.submit()
	return _movement_payload(doc, include_data=True)


@frappe.whitelist()
def change_movement_status(cutting_plan, movement, action):
	plan = _get_plan(cutting_plan)
	doc = frappe.get_doc(MOVEMENT_DOCTYPE, movement)
	_assert_movement_belongs(plan, doc)
	if action == "submit":
		_require_active_plan(plan)
		doc.check_permission("submit")
		if doc.docstatus != 0:
			frappe.throw(_("Only a Draft Cut Panel Movement can be submitted."))
		context = _plan_context(plan, require_source=True)
		movement_data = _authoritative_movement_data(
			plan,
			context,
			doc,
			_validate_movement_data(doc.cut_panel_movement_json),
		)
		doc.movement_data = movement_data
		doc.cut_panel_movement_json = get_total(json.loads(json.dumps(movement_data)))
		doc.save()
		doc.submit()
	elif action == "cancel":
		doc.check_permission("cancel")
		if doc.docstatus != 1:
			frappe.throw(_("Only a Submitted Cut Panel Movement can be cancelled."))
		doc.cancel()
	else:
		frappe.throw(_("Unsupported Cut Panel Movement action."))
	return _movement_payload(doc, include_data=True)


def _stock_selection_key(row):
	identity = {
		"item": row.get("item"),
		"warehouse": row.get("warehouse"),
	}
	for fieldname in get_dimension_fieldnames():
		identity[fieldname] = row.get(fieldname)
	return json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)


def _plan_stock_rows(plan, context):
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_stock_summary.sd_yrp_stock_summary import (
		get_stock_summary,
	)

	rows = get_stock_summary(
		lot=[{"lot": plan.lot}],
		warehouse=context.source_warehouse,
	) or []
	result = []
	for source in rows:
		row = dict(source)
		row["selection_key"] = _stock_selection_key(row)
		result.append(row)
	return sorted(
		result,
		key=lambda row: (
			str(row.get("item_name") or ""),
			str(row.get("item") or ""),
			str(row.get("received_type") or ""),
		),
	)


def _plan_stock_item_groups(rows):
	"""Project live stock balances into the Desk parent-item matrix shape."""
	if not rows:
		return []
	from yrp.stock.save_stock_items import group_items_for_ui

	from essdee_yrp.item_matrix import normalize_item_matrix_row_indexes

	display_rows = []
	for source in rows:
		row = frappe._dict(source)
		row.uom = row.get("stock_uom")
		display_rows.append(row)
	display_rows = normalize_item_matrix_row_indexes(display_rows)
	return group_items_for_ui(
		display_rows,
		"SD YRP Lot Transfer",
		config={
			"child_doctype": None,
			"item_field": "item",
			"qty_field": "bal_qty",
			"value_fields": ["selection_key"],
			"entry_fields": ["lot", "received_type", "warehouse", "set_combination"],
		},
	)


@frappe.whitelist()
def get_plan_stock(cutting_plan):
	plan = _get_plan(cutting_plan)
	_require_active_plan(plan)
	context = _plan_context(plan, require_source=True)
	rows = _plan_stock_rows(plan, context)
	return {
		"context": context,
		"row_count": len(rows),
		"item_groups": _plan_stock_item_groups(rows),
	}


def _assert_item_editor_operation(operation):
	if operation not in ITEM_EDITOR_OPERATIONS:
		frappe.throw(_("Item entry is not supported for stock operation {0}.").format(operation))
	return OPERATION_DOCTYPES[operation]


def _assert_warehouse_access(warehouse):
	if not warehouse:
		frappe.throw(_("Warehouse is required."))
	doc = frappe.get_cached_doc("Warehouse", warehouse)
	doc.check_permission("read")
	if cint(doc.get("disabled")):
		frappe.throw(_("Warehouse {0} is disabled.").format(warehouse))
	# Stock posting enforces the same user-permission boundary on submit. Check
	# it at editor/save time as well so an inaccessible warehouse cannot be
	# persisted in a Draft through this workspace.
	if frappe.session.user != "Administrator":
		doc.check_user_permission()
	return doc


def _dimension_defaults(plan, context):
	return {
		"lot": plan.lot,
		"received_type": context.default_received_type,
	}


def _stock_editor_dimensions(plan, context):
	defaults = _dimension_defaults(plan, context)
	result = []
	for source in get_stock_dimensions_for_ui():
		dimension = dict(source)
		fieldname = dimension["fieldname"]
		dimension["default_value"] = defaults.get(fieldname)
		dimension["locked"] = fieldname == "lot"
		result.append(dimension)
	return result


def _lot_transfer_editor_dimensions(plan, context):
	"""Expose the legacy Lot Transfer row inputs through the shared item builder.

	The source lot and Warehouse remain server-owned by the Cutting Plan.  The
	operator chooses a target lot per logical item row, matching the Desk
	``ItemLotFetch`` workflow without first loading every live stock balance.
	"""
	return [
		{
			"fieldname": "from_lot",
			"label": _("From Lot"),
			"options": "SD YRP Lot",
			"mandatory": 1,
			"default_value": plan.lot,
			"locked": True,
		},
		{
			"fieldname": "to_lot",
			"label": _("To Lot"),
			"options": "SD YRP Lot",
			"mandatory": 1,
			"filters": {"name": ["!=", plan.lot]},
		},
		{
			"fieldname": "received_type",
			"label": _("Received Type"),
			"options": "YRP Received Type",
			"mandatory": 1,
			"default_value": context.default_received_type,
		},
	]


@frappe.whitelist()
def get_stock_operation_editor(cutting_plan, operation):
	"""Return the server-owned context for the grouped YRP stock item editor."""
	doctype = _assert_item_editor_operation(operation)
	plan = _get_plan(cutting_plan)
	_require_active_plan(plan)
	context = _plan_context(plan, require_source=True)
	frappe.has_permission(doctype, "create", throw=True)
	frappe.has_permission("Item", "read", throw=True)
	_assert_warehouse_access(context.source_warehouse)
	dimensions = (
		_lot_transfer_editor_dimensions(plan, context)
		if operation == "lot_transfer"
		else _stock_editor_dimensions(plan, context)
	)
	dimension_defaults = {
		dimension["fieldname"]: dimension.get("default_value")
		for dimension in dimensions
		if dimension.get("default_value") not in (None, "")
	}
	return {
		"context": context,
		"operation": operation,
		"dimensions": dimensions,
		"default_dimensions": dimension_defaults,
		"locked_dimensions": [row["fieldname"] for row in dimensions if row.get("locked")],
		"defaults": {
			"purpose": "Stock Reconciliation" if operation == "stock_reconciliation" else None,
			"update_type": "Reduce" if operation == "stock_update" else None,
			"source_warehouse": context.source_warehouse,
			"dimensions": dimension_defaults,
		},
		"locked_fields": [
			"source_warehouse",
			*[f"dimensions.{row['fieldname']}" for row in dimensions if row.get("locked")],
		],
		"purpose_options": sorted(STOCK_ENTRY_PURPOSES) if operation == "stock_entry" else [],
		"update_type_options": ["Add", "Reduce"] if operation == "stock_update" else [],
		"item_filters": dict(STOCK_ITEM_BUILDER_FILTERS),
		"permissions": {
			"can_create": True,
			"can_submit": bool(frappe.has_permission(doctype, "submit")),
		},
	}


def _get_stock_item_schema_data(item):
	from yrp.yrp.doctype.yrp_item.yrp_item import (
		get_attribute_details,
		get_attribute_values,
		validate_cancelled_item,
		validate_disabled,
		validate_is_stock_item,
	)

	selected = frappe.get_doc("Item", item)
	selected.check_permission("read")
	if selected.variant_of:
		frappe.throw(_("Select the template Item {0} instead of its variant {1}.").format(selected.variant_of, selected.name))
	validate_is_stock_item(selected.name, selected.is_stock_item)
	validate_cancelled_item(selected.name, selected.docstatus)
	validate_disabled(selected.name, selected.disabled)

	schema = dict(get_attribute_details(selected.name))
	parent = frappe.get_doc("Item", schema["item"])
	parent.check_permission("read")
	validate_is_stock_item(parent.name, parent.is_stock_item)
	validate_cancelled_item(parent.name, parent.docstatus)
	validate_disabled(parent.name, parent.disabled)

	attribute_names = [row.attribute for row in parent.get("attributes") or []]
	schema["attribute_values"] = get_attribute_values(parent.name, attribute_names)
	return schema


@frappe.whitelist()
def get_stock_item_schema(cutting_plan, operation, item):
	"""Return canonical template metadata and its currently allowed values."""
	doctype = _assert_item_editor_operation(operation)
	plan = _get_plan(cutting_plan)
	_require_active_plan(plan)
	_plan_context(plan, require_source=True)
	frappe.has_permission(doctype, "create", throw=True)
	if not item:
		frappe.throw(_("Item is required."))
	return _get_stock_item_schema_data(item)


def _as_non_negative_number(value, label):
	try:
		number = float(value or 0)
	except (TypeError, ValueError):
		frappe.throw(_("{0} must be a number.").format(label))
	if not math.isfinite(number) or number < 0:
		frappe.throw(_("{0} cannot be negative.").format(label))
	return number


def _normalize_dimensions(plan, context, value, dimensions):
	value = value or {}
	if not isinstance(value, dict):
		frappe.throw(_("Stock dimensions must be a JSON object."))
	allowed = {row["fieldname"]: row for row in dimensions}
	unknown = sorted(set(value) - set(allowed))
	if unknown:
		frappe.throw(_("Unknown stock dimensions: {0}.").format(", ".join(unknown)))

	defaults = _dimension_defaults(plan, context)
	if "lot" in allowed and value.get("lot") not in (None, "", plan.lot):
		frappe.throw(_("Lot is controlled by Cutting Plan {0}.").format(plan.name))
	normalized = {}
	for fieldname, dimension in allowed.items():
		dimension_value = value.get(fieldname) or defaults.get(fieldname)
		if dimension.get("mandatory") and not dimension_value:
			frappe.throw(_("{0} is required.").format(dimension.get("label") or fieldname))
		if dimension_value:
			options = dimension.get("dimension_doctype") or dimension.get("options")
			if options:
				dimension_doc = frappe.get_doc(options, dimension_value)
				dimension_doc.check_permission("read")
			normalized[fieldname] = dimension_value
	return normalized


def _normalize_lot_transfer_dimensions(plan, context, value):
	value = value or {}
	if not isinstance(value, dict):
		frappe.throw(_("Lot Transfer details must be a JSON object."))
	allowed = {"from_lot", "to_lot", "received_type"}
	unknown = sorted(set(value) - allowed)
	if unknown:
		frappe.throw(_("Unknown Lot Transfer fields: {0}.").format(", ".join(unknown)))

	from_lot = value.get("from_lot") or plan.lot
	to_lot = value.get("to_lot")
	received_type = value.get("received_type") or context.default_received_type
	if from_lot != plan.lot:
		frappe.throw(_("From Lot is controlled by Cutting Plan {0}.").format(plan.name))
	if not to_lot:
		frappe.throw(_("To Lot is required."))
	if to_lot == from_lot:
		frappe.throw(_("From Lot and To Lot must be different."))
	if not received_type:
		frappe.throw(_("Received Type is required."))
	for doctype, name in (
		("SD YRP Lot", from_lot),
		("SD YRP Lot", to_lot),
		("YRP Received Type", received_type),
	):
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("read")
	return {
		"from_lot": from_lot,
		"to_lot": to_lot,
		"warehouse": context.source_warehouse,
		"received_type": received_type,
	}


def _applicable_item_schema(schema, attributes):
	attributes = attributes or {}
	if not isinstance(attributes, dict):
		frappe.throw(_("Item attributes must be a JSON object."))
	dependent = schema.get("dependent_attribute")
	if dependent:
		dependent_value = attributes.get(dependent)
		if not dependent_value:
			frappe.throw(_("Attribute {0} is required.").format(dependent))
		stage = (schema.get("dependent_attribute_details") or {}).get("attr_list", {}).get(
			dependent_value
		)
		if not stage:
			frappe.throw(_("{0} is not allowed for attribute {1}.").format(dependent_value, dependent))
		primary = stage.get("primary_attribute") or ""
		primary_values = stage.get("primary_attribute_values") or []
		required = set(stage.get("attributes") or []) - ({primary} if primary else set())
		required.add(dependent)
		default_uom = stage.get("uom") or schema.get("default_uom")
	else:
		primary = schema.get("primary_attribute") or ""
		primary_values = schema.get("primary_attribute_values") or []
		required = set(schema.get("attributes") or [])
		default_uom = schema.get("default_uom")

	provided = set(attributes)
	if provided != required:
		frappe.throw(
			_("Item attributes changed. Expected {0}; received {1}.").format(
				", ".join(sorted(required)) or _("none"),
				", ".join(sorted(provided)) or _("none"),
			)
		)
	allowed_values = schema.get("attribute_values") or {}
	for attribute, value in attributes.items():
		if value not in (allowed_values.get(attribute) or []):
			frappe.throw(_("{0} is not allowed for attribute {1}.").format(value, attribute))
	return primary, primary_values, default_uom


def _normalize_value_cells(operation, entry, primary, primary_values, secondary_uom=None):
	values = entry.get("values") or {}
	if not isinstance(values, dict) or not values:
		frappe.throw(_("At least one quantity value is required for Item {0}.").format(entry.get("name")))
	allowed_keys = set(primary_values) if primary else {"default"}
	unknown = sorted(set(values) - allowed_keys)
	if unknown:
		frappe.throw(_("Unknown {0} values: {1}.").format(primary or _("quantity"), ", ".join(unknown)))

	normalized = {}
	positive_qty = False
	for key, source in values.items():
		if not isinstance(source, dict):
			frappe.throw(_("Quantity details for {0} must be a JSON object.").format(key))
		qty = _as_non_negative_number(source.get("qty"), _("Quantity"))
		positive_qty = positive_qty or qty > 0
		# Other operations take the rate from the source valuation bucket in the
		# YRP controllers. A counted balance carries the rate the user entered.
		rate = _as_non_negative_number(source.get("rate"), _("Rate")) if operation == "stock_reconciliation" else 0
		cell = {"qty": qty, "rate": rate}
		if source.get("secondary_qty") not in (None, ""):
			cell["secondary_qty"] = _as_non_negative_number(
				source.get("secondary_qty"), _("Secondary Quantity")
			)
			if secondary_uom:
				cell["secondary_uom"] = secondary_uom
		normalized[key] = cell
	if operation != "stock_reconciliation" and not positive_qty:
		frappe.throw(_("Quantity must be greater than zero for Item {0}.").format(entry.get("name")))
	return normalized


def _normalize_stock_item_details(plan, context, operation, item_details):
	item_details = _parse(item_details, []) or []
	if not isinstance(item_details, list) or not item_details:
		frappe.throw(_("Add at least one Item."))
	dimensions = [dict(row) for row in get_stock_dimensions()]
	seen = set()
	normalized_groups = []
	schema_cache = {}
	for group in item_details:
		if not isinstance(group, dict) or not isinstance(group.get("items"), list):
			frappe.throw(_("Invalid grouped Item details."))
		for entry in group["items"]:
			if not isinstance(entry, dict) or not entry.get("name"):
				frappe.throw(_("Every Item row needs an Item."))
			requested_item = entry["name"]
			if requested_item not in schema_cache:
				schema_cache[requested_item] = _get_stock_item_schema_data(requested_item)
			schema = schema_cache[requested_item]
			lot_transfer_fields = None
			if operation == "lot_transfer":
				lot_transfer_fields = _normalize_lot_transfer_dimensions(
					plan, context, entry.get("dimensions")
				)
				dimension_values = {}
			else:
				dimension_values = _normalize_dimensions(
					plan, context, entry.get("dimensions"), dimensions
				)
			attributes = dict(entry.get("attributes") or {})
			primary, primary_values, default_uom = _applicable_item_schema(schema, attributes)
			values = _normalize_value_cells(
				operation, entry, primary, primary_values, schema.get("secondary_uom")
			)

			for value_key in values:
				identity_dimensions = (
					lot_transfer_fields if lot_transfer_fields is not None else dimension_values
				)
				identity = (
					schema["item"],
					tuple(sorted(identity_dimensions.items())),
					tuple(sorted(attributes.items())),
					primary or "default",
					value_key,
				)
				if identity in seen:
					frappe.throw(_("Duplicate Item and stock-dimension combination is not allowed."))
				seen.add(identity)

			normalized_entry = {
				"name": schema["item"],
				"dimensions": dimension_values,
				"attributes": attributes,
				"primary_attribute": primary,
				"dependent_attribute": schema.get("dependent_attribute") or "",
				"values": values,
				"default_uom": default_uom,
				"secondary_uom": schema.get("secondary_uom") or "",
			}
			if lot_transfer_fields:
				normalized_entry.update(lot_transfer_fields)
			if operation in ("stock_reconciliation", "stock_entry"):
				normalized_entry["allow_zero_valuation_rate"] = cint(
					entry.get("allow_zero_valuation_rate")
				)
			if operation == "stock_reconciliation":
				normalized_entry["make_qty_zero"] = cint(entry.get("make_qty_zero"))
			normalized_groups.append(
				{
					"attributes": sorted(attributes),
					"primary_attribute": primary,
					"dependent_attribute": schema.get("dependent_attribute") or "",
					"dependent_attribute_details": schema.get("dependent_attribute_details") or {},
					"primary_attribute_values": primary_values,
					"items": [normalized_entry],
				}
			)
	return normalized_groups


def _resolve_stock_rows(plan, context, selection_keys):
	selection_keys = _parse(selection_keys, []) or []
	if not isinstance(selection_keys, list) or not selection_keys:
		frappe.throw(_("Select at least one stock row."))
	if len(selection_keys) != len(set(selection_keys)):
		frappe.throw(_("The stock selection contains duplicate rows."))
	available = {row["selection_key"]: row for row in _plan_stock_rows(plan, context)}
	missing = [key for key in selection_keys if key not in available]
	if missing:
		frappe.throw(_("Stock changed after it was loaded. Refresh the available stock and try again."))
	return [available[key] for key in selection_keys]


def _append_transaction_link(plan, doc):
	if doc.doctype not in DOCTYPE_OPERATIONS:
		frappe.throw(_("Unsupported Cutting Plan transaction type {0}.").format(doc.doctype))
	frappe.db.sql(
		"select name from `tabSD YRP Cutting Plan` where name=%s for update",
		(plan.name,),
	)
	plan.reload()
	for row in plan.get("stock_transfers") or []:
		if row.against == doc.doctype and row.against_id == doc.name:
			return row
	existing = frappe.db.get_value(
		RELATION_DOCTYPE,
		{"against": doc.doctype, "against_id": doc.name},
		["parent", "name"],
		as_dict=True,
	)
	if existing:
		if existing.parent == plan.name:
			return existing
		frappe.throw(
			_("{0} {1} is already linked to Cutting Plan {2}.").format(
				doc.doctype, doc.name, existing.parent
			)
		)
	row = plan.append("stock_transfers", {"against": doc.doctype, "against_id": doc.name})
	# The table is read-only for clients; this service has already checked the
	# plan and target permissions and owns the submitted-document update.
	plan.flags.ignore_validate_update_after_submit = True
	plan.save(ignore_permissions=True)
	return row


def add_cutting_plan_link_exemption(doc, method=None):
	"""Cutting Plan Stock Transfer rows are audit history and must not block a cancel."""
	del method
	if not frappe.db.exists(RELATION_DOCTYPE, {"against": doc.doctype, "against_id": doc.name}):
		return
	exemptions = list(doc.get("ignore_linked_doctypes") or ())
	if PLAN_DOCTYPE not in exemptions:
		exemptions.append(PLAN_DOCTYPE)
	doc.ignore_linked_doctypes = tuple(exemptions)


def remove_cutting_plan_link(doc, method=None):
	"""A deleted draft leaves no Cutting Plan history row behind."""
	del method
	frappe.db.delete(RELATION_DOCTYPE, {"against": doc.doctype, "against_id": doc.name})


def _submit_if_requested(doc, submit):
	if cint(submit):
		doc.check_permission("submit")
		doc.submit()
	return doc


def _create_grouped_stock_document(plan, context, operation, values):
	doctype = _assert_item_editor_operation(operation)
	frappe.has_permission(doctype, "create", throw=True)
	_assert_warehouse_access(context.source_warehouse)
	item_details = _normalize_stock_item_details(
		plan, context, operation, values.get("item_details")
	)
	doc = frappe.new_doc(doctype)
	if operation == "stock_entry":
		purpose = values.get("purpose")
		if purpose not in STOCK_ENTRY_PURPOSES:
			frappe.throw(_("Select a supported Stock Entry purpose."))
		doc.purpose = purpose
		doc.from_supplier = context.source_supplier
		doc.from_warehouse = context.source_warehouse
		if purpose == "Send to Warehouse":
			to_warehouse = values.get("to_warehouse")
			_assert_warehouse_access(to_warehouse)
			if to_warehouse == context.source_warehouse:
				frappe.throw(_("Source and target Warehouse must be different."))
			doc.to_warehouse = to_warehouse
	elif operation == "stock_reconciliation":
		purpose = values.get("purpose") or "Stock Reconciliation"
		if purpose != "Stock Reconciliation":
			frappe.throw(_("Only Stock Reconciliation is supported from a Cutting Plan."))
		doc.purpose = "Stock Reconciliation"
		doc.default_supplier = context.source_supplier
		doc.default_warehouse = context.source_warehouse
	elif operation == "stock_update":
		update_type = values.get("update_type")
		if update_type not in STOCK_UPDATE_TYPES:
			frappe.throw(_("Select Add or Reduce for Stock Update."))
		doc.update_type = update_type
		doc.supplier = context.source_supplier
		doc.warehouse = context.source_warehouse
	else:
		# Warehouse, From Lot, To Lot, and Received Type are repeated per
		# logical item row by the Lot Transfer controller's editor contract.
		# Their normalized values above are all server-validated and Warehouse
		# is always owned by the linked Work Order.
		pass

	# Keep variant creation, UOM conversion, dimension defaults, rate lookup,
	# and reconciliation target semantics inside the YRP stock layer. Stock
	# Reconciliation needs keep_zero=True here because zero is a valid counted
	# balance for every primary-attribute variant; the generic controller's
	# default flattening intentionally drops zero cells for most transactions.
	if operation == "stock_reconciliation":
		from yrp.stock.save_stock_items import ungroup_items_from_ui

		for row in ungroup_items_from_ui(
			item_details, "YRP Stock Reconciliation", keep_zero=True
		):
			row.setdefault("warehouse", context.source_warehouse)
			doc.append("items", row)
	else:
		doc.item_details = json.dumps(item_details)
	doc.comments = _("Created from Cutting Plan {0}").format(plan.name)
	doc.insert()
	return doc


@frappe.whitelist()
def save_stock_operation(cutting_plan, operation, values, submit=False):
	if operation not in PLAN_STOCK_OPERATIONS:
		frappe.throw(_("Unsupported stock operation {0}.").format(operation))
	plan = _get_plan(cutting_plan)
	_require_active_plan(plan)
	context = _plan_context(plan, require_source=True)
	values = _parse(values, {}) or {}
	doc = _create_grouped_stock_document(plan, context, operation, values)
	_submit_if_requested(doc, submit)
	_append_transaction_link(plan, doc)
	return _transaction_payload(doc, include_items=True)


def _get_plan_work_order(plan):
	work_order = frappe.get_doc("YRP Work Order", plan.work_order)
	work_order.check_permission("read")
	if work_order.docstatus != 1 or work_order.open_status == "Close":
		frappe.throw(_("Work Order {0} must be submitted and open.").format(work_order.name))
	return work_order


def _apply_same_location_delivery_context(doc, context, work_order):
	"""Stamp the Work Order's receiving location on both sides of a cutting DC."""
	doc.from_location = context.source_supplier
	doc.supplier = context.source_supplier
	doc.from_warehouse = context.source_warehouse
	doc.to_warehouse = context.source_warehouse
	doc.is_internal_unit = 0
	# Essdee address fields are mandatory custom fields. Because this workflow is
	# explicitly an in-place dispatch, the linked Work Order supplier address is
	# authoritative for both the source and receiver sides.
	address = work_order.get("supplier_address")
	address_details = work_order.get("supplier_address_details")
	for fieldname in ("from_address", "supplier_address"):
		if doc.meta.get_field(fieldname):
			doc.set(fieldname, address)
	for fieldname in ("from_address_details", "supplier_address_details"):
		if doc.meta.get_field(fieldname):
			doc.set(fieldname, address_details)
	return doc


def _delivery_groups_for_entry(groups):
	"""Return a zero-entry copy while retaining server-owned pending metadata."""
	groups = json.loads(json.dumps(groups or []))
	for group in groups:
		for entry in group.get("items") or []:
			for cell in (entry.get("values") or {}).values():
				if not isinstance(cell, dict):
					continue
				cell["qty"] = 0
				cell["delivered_quantity"] = 0
	return groups


def _correction_delivery_groups_for_entry(blocks):
	blocks = json.loads(json.dumps(blocks or []))
	for block in blocks:
		block["item_details"] = _delivery_groups_for_entry(block.get("item_details") or [])
	return blocks


def _parse_delivery_quantities(value):
	value = _parse(value, {}) or {}
	if not isinstance(value, dict):
		frappe.throw(_("Delivery quantities must be a JSON object."))
	if len(value) > 10000:
		frappe.throw(_("Too many Delivery Challan quantities were supplied."))
	normalized = {}
	for reference, qty in value.items():
		if not isinstance(reference, str) or not reference or len(reference) > 140:
			frappe.throw(_("Invalid Work Order deliverable reference."))
		normalized[reference] = _as_non_negative_number(qty, _("Delivery Quantity"))
	return normalized


def _apply_delivery_quantities(groups, quantities, known, used):
	for group in groups or []:
		for entry in group.get("items") or []:
			for cell in (entry.get("values") or {}).values():
				if not isinstance(cell, dict):
					continue
				reference = cell.get("ref_docname")
				if not reference or reference in (0, "0"):
					cell["qty"] = 0
					cell["delivered_quantity"] = 0
					continue
				known.add(reference)
				qty = quantities.get(reference, 0)
				if reference in quantities:
					used.add(reference)
				cell["qty"] = qty
				cell["delivered_quantity"] = qty


def _positive_delivery_groups(groups):
	result = []
	for group in groups or []:
		items = []
		for entry in group.get("items") or []:
			values = {
				key: cell
				for key, cell in (entry.get("values") or {}).items()
				if isinstance(cell, dict) and flt(cell.get("qty")) > 0
			}
			if values:
				items.append({**entry, "values": values})
		if items:
			result.append({**group, "items": items})
	return result


def _work_order_delivery_defaults(plan):
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import (
		get_work_order_defaults,
	)

	work_order = _get_plan_work_order(plan)
	return work_order, get_work_order_defaults(work_order.name)


@frappe.whitelist()
def get_work_order_delivery_editor(cutting_plan):
	"""Load current Work Order deliverables for quantity-only DC entry."""
	plan = _get_plan(cutting_plan)
	_require_active_plan(plan)
	context = _plan_context(plan, require_source=True)
	frappe.has_permission("YRP Delivery Challan", "create", throw=True)
	work_order, defaults = _work_order_delivery_defaults(plan)
	return {
		"context": context,
		"work_order": work_order.name,
		"item_details": _delivery_groups_for_entry(defaults.get("item_details")),
		"correction_item_details": _correction_delivery_groups_for_entry(
			defaults.get("correction_item_details")
		),
		"permissions": _permission_flags("YRP Delivery Challan"),
	}


@frappe.whitelist()
def create_work_order_delivery_challan(cutting_plan, values=None, submit=False):
	"""Create a same-location DC from authoritative Work Order deliverables."""
	plan = _get_plan(cutting_plan)
	_require_active_plan(plan)
	context = _plan_context(plan, require_source=True)
	frappe.has_permission("YRP Delivery Challan", "create", throw=True)
	work_order, defaults = _work_order_delivery_defaults(plan)
	values = _parse(values, {}) or {}
	quantities = _parse_delivery_quantities(values.get("quantities"))
	correction_quantities = _parse_delivery_quantities(values.get("correction_quantities"))
	if set(quantities).intersection(correction_quantities):
		frappe.throw(_("A Work Order deliverable cannot be entered twice."))

	item_details = defaults.get("item_details") or []
	correction_details = defaults.get("correction_item_details") or []
	known = set()
	used = set()
	_apply_delivery_quantities(item_details, quantities, known, used)
	for block in correction_details:
		_apply_delivery_quantities(
			block.get("item_details") or [], correction_quantities, known, used
		)
	unknown = (set(quantities) | set(correction_quantities)) - known
	if unknown:
		frappe.throw(
			_("Work Order deliverables changed after loading. Refresh and try again.")
		)
	if not any(qty > 0 for qty in [*quantities.values(), *correction_quantities.values()]):
		frappe.throw(_("Enter a Delivery Quantity greater than zero."))

	doc = frappe.new_doc("YRP Delivery Challan")
	doc.update(
		{
			key: value
			for key, value in defaults.items()
			if key
			not in {
				"items",
				"item_details",
				"correction_items",
				"correction_item_details",
			}
		}
	)
	doc.work_order = work_order.name
	_apply_same_location_delivery_context(doc, context, work_order)
	doc.item_details = json.dumps(_positive_delivery_groups(item_details))
	doc.correction_item_details = json.dumps([
		{**block, "item_details": groups}
		for block in correction_details
		if (groups := _positive_delivery_groups(block.get("item_details")))
	])
	if doc.meta.get_field("vehicle_no"):
		doc.vehicle_no = "NA"
	if doc.meta.get_field("supplier_document_no"):
		doc.supplier_document_no = "NA"
	doc.comments = _("Same-location Work Order delivery from Cutting Plan {0}").format(
		plan.name
	)
	doc.insert()
	_submit_if_requested(doc, submit)
	_append_transaction_link(plan, doc)
	return _transaction_payload(doc, include_items=True)


@frappe.whitelist()
def create_movement_transaction(cutting_plan, movement, operation, values=None, submit=False):
	if operation not in MOVEMENT_OPERATIONS:
		frappe.throw(_("Unsupported movement transaction {0}.").format(operation))
	plan = _get_plan(cutting_plan)
	_require_active_plan(plan)
	context = _plan_context(plan, require_source=True)
	cpm = frappe.get_doc(MOVEMENT_DOCTYPE, movement)
	cpm.check_permission("read")
	_assert_movement_belongs(plan, cpm)
	if cpm.docstatus != 1:
		frappe.throw(_("Submit Cut Panel Movement {0} first.").format(cpm.name))
	values = _parse(values, {}) or {}

	if operation == "stock_entry":
		defaults = build_stock_entry_defaults(cpm.name)
		to_warehouse = values.get("to_warehouse")
		if not to_warehouse:
			frappe.throw(_("To Warehouse is required."))
		doc = new_transaction_from_defaults("YRP Stock Entry", defaults)
		doc.to_warehouse = to_warehouse
		doc.skip_transit = cint(values.get("skip_transit"))
		doc.comments = _("Cut panels from Cutting Plan {0}").format(plan.name)
	else:
		defaults = build_delivery_challan_defaults(cpm.name, plan.work_order)
		doc = new_transaction_from_defaults("YRP Delivery Challan", defaults)
		# Cutting dispatch is an auditable in-place Work Order delivery.
		_apply_same_location_delivery_context(doc, context, _get_plan_work_order(plan))
		doc.vehicle_no = values.get("vehicle_no") or "NA"
		doc.supplier_document_no = values.get("supplier_document_no") or "NA"
		doc.comments = _("Same-location cutting dispatch from Cutting Plan {0}").format(plan.name)

	doc.insert()
	_submit_if_requested(doc, submit)
	_append_transaction_link(plan, doc)
	return _transaction_payload(doc, include_items=True)


def _get_linked_doc(plan, doctype, name):
	if doctype not in DOCTYPE_OPERATIONS:
		frappe.throw(_("Unsupported Cutting Plan transaction type."))
	registered = frappe.db.exists(
		RELATION_DOCTYPE,
		{
			"parent": plan.name,
			"parenttype": plan.doctype,
			"parentfield": "stock_transfers",
			"against": doctype,
			"against_id": name,
		},
	)
	legacy_cpm_link = frappe.db.exists(
		MOVEMENT_DOCTYPE,
		{
			"cutting_plan": plan.name,
			"movement_from_cutting": 1,
			"against": doctype,
			"against_id": name,
		},
	)
	if not registered and not legacy_cpm_link:
		frappe.throw(_("{0} {1} is not linked to this Cutting Plan.").format(doctype, name))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return doc


@frappe.whitelist()
def get_linked_transaction(cutting_plan, doctype, name):
	plan = _get_plan(cutting_plan)
	return _transaction_payload(_get_linked_doc(plan, doctype, name), include_items=True, plan=plan)


@frappe.whitelist()
def update_lot_transfer_quantities(cutting_plan, name, rows, expected_modified=None):
	"""Change only quantities (or drop rows) of a draft balance-cloth Lot Transfer."""
	plan = _get_plan(cutting_plan)
	doc = _get_linked_doc(plan, "SD YRP Lot Transfer", name)
	_assert_not_stale(doc, expected_modified)
	apply_quantities(plan, doc, rows)
	return _transaction_payload(doc, include_items=True, plan=plan)


@frappe.whitelist()
def change_linked_transaction_status(cutting_plan, doctype, name, action):
	plan = _get_plan(cutting_plan)
	doc = _get_linked_doc(plan, doctype, name)
	if action == "submit":
		doc.check_permission("submit")
		if doc.docstatus != 0:
			frappe.throw(_("Only a Draft document can be submitted."))
		doc.submit()
	elif action == "cancel":
		doc.check_permission("cancel")
		if doc.docstatus != 1:
			frappe.throw(_("Only a Submitted document can be cancelled."))
		doc.cancel()
	else:
		frappe.throw(_("Unsupported transaction action."))
	return _transaction_payload(doc, include_items=True, plan=plan)
