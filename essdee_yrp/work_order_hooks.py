# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.utils import cstr, flt


def validate(doc, method=None):
	set_includes_packing(doc)
	validate_lot_process_selection(doc)
	validate_fabric_execution_immutable(doc)
	from essdee_yrp.fabric_source import validate_work_order_source_allocations

	validate_work_order_source_allocations(doc)


def before_update_after_submit(doc, method=None):
	"""Submitted fabric execution contracts are immutable."""
	validate_fabric_execution_immutable(doc)
	from essdee_yrp.fabric_source import validate_work_order_source_allocations

	validate_work_order_source_allocations(doc)


def validate_fabric_execution_immutable(doc):
	"""Only Calculate may replace generated input/output contract fields."""
	if doc.flags.get("essdee_fabric_calculate") or doc.flags.get("essdee_fabric_lifecycle"):
		return
	previous = doc.get_doc_before_save()
	if not previous:
		return
	previous_snapshot, previous_managed = _fabric_execution_snapshot(previous)
	current_snapshot, current_managed = _fabric_execution_snapshot(doc)
	if not (previous_managed or current_managed):
		return
	if previous_snapshot != current_snapshot:
		frappe.throw(_(
			"Calculated fabric deliverables and receivables can be changed only "
			"through Calculate. Reopen the popup to rebuild the execution contract."
		))


def _fabric_execution_snapshot(doc):
	def execution_key(row):
		value = row.get("additional_parameters") or {}
		if isinstance(value, str):
			try:
				value = frappe.parse_json(value)
			except (TypeError, ValueError):
				value = {}
		return value.get("fabric_execution_key") if isinstance(value, dict) else None

	managed = bool(doc.get("is_rework")) or any(
		execution_key(row)
		for table in ("deliverables", "receivables")
		for row in (doc.get(table) or [])
	)
	rows = []
	from yrp.stock.dimensions import get_dimension_fieldnames

	dimension_fields = tuple(get_dimension_fieldnames())
	fields = {
		"deliverables": (
			"item_variant", "qty", "uom", "pending_quantity", "stock_update",
			"is_calculated", "set_combination",
			"fabric_reference_variant", "fabric_reference_allocations",
			"additional_parameters", "source_grn", "source_grn_item",
		) + dimension_fields,
		"receivables": (
			"item_variant", "qty", "uom", "pending_quantity", "stock_update",
			"set_combination", "fabric_reference_variant",
			"fabric_reference_allocations", "additional_parameters",
		) + dimension_fields,
	}
	for table, fieldnames in fields.items():
		for row in doc.get(table) or []:
			# Once any row belongs to a calculated fabric contract, snapshot the
			# complete tables. Otherwise an unkeyed row could be appended without
			# changing the protected execution subset.
			if not managed:
				continue
			payload = {
				"table": table,
				"name": cstr(row.get("name") or ""),
			}
			for fieldname in fieldnames:
				value = row.get(fieldname)
				if fieldname in ("qty", "pending_quantity", "stock_update"):
					value = flt(value, 6)
				else:
					value = cstr(value) if value is not None else ""
				payload[fieldname] = value
			rows.append(payload)
	header = {
		fieldname: cstr(doc.get(fieldname) or "")
		for fieldname in (
			"lot", "production_detail", "process_name", "item", "supplier",
			"delivery_location", "fabric_source_process",
			"fabric_source_process_step", "open_status", "is_rework",
			"parent_wo", "rework_type",
		)
	}
	return json.dumps(
		{"header": header, "rows": rows},
		sort_keys=True,
		separators=(",", ":"),
	), managed


def set_includes_packing(doc):
	"""Copy Essdee's Process packing rule without coupling base Work Order."""
	if not doc.meta.get_field("includes_packing"):
		return
	doc.includes_packing = 0
	if doc.get("process_name") and frappe.get_meta("Process").get_field("includes_packing"):
		doc.includes_packing = frappe.db.get_value(
			"Process", doc.process_name, "includes_packing"
		) or 0


def validate_lot_process_selection(doc):
	"""Keep the Work Order's Item/IPD tied to its selected Process and Lot.

	The clients auto-fill this pair, but API/import callers receive the same
	guard.  Production Detail is derived and never accepted as an independent
	user choice.
	"""
	if not doc.get("process_name") or not doc.get("lot"):
		return

	from essdee_yrp.api.work_order import _get_work_order_selection_context

	context = _get_work_order_selection_context(
		doc.lot, doc.process_name, check_permission=False
	)
	options = context["options"]
	if not options:
		scope = _("cloth IPDs") if context["is_cloth_process"] else _("garment IPD")
		frappe.throw(
			_("Lot {0} has no {1} configured for process {2}.").format(
				doc.lot, scope, doc.process_name
			)
		)

	if not doc.get("item") and len(options) == 1:
		doc.item = options[0]["item"]

	item_matches = [option for option in options if option["item"] == doc.get("item")]
	if not item_matches:
		frappe.throw(
			_("Item {0} is not available for process {1} in Lot {2}. Valid items: {3}.").format(
				doc.get("item") or _("(not selected)"),
				doc.process_name,
				doc.lot,
				", ".join(context["item_options"]) or _("none"),
			)
		)
	if len(item_matches) > 1:
		frappe.throw(
			_(
				"Item {0} has multiple Production Details for process {1} in Lot {2}. "
				"Keep one Lot fabric row per cloth Item/IPD."
			).format(doc.item, doc.process_name, doc.lot)
		)

	expected_ipd = item_matches[0]["production_detail"]
	if doc.get("production_detail") and doc.production_detail != expected_ipd:
		frappe.throw(
			_("Production Detail {0} does not match Item {1} in Lot {2}; expected {3}.").format(
				doc.production_detail, doc.item, doc.lot, expected_ipd
			)
		)
	doc.production_detail = expected_ipd


def validate_cloth_process_item(doc):
	"""Compatibility alias for integrations importing the previous hook."""
	if not doc.get("process_name") or not doc.get("lot"):
		return
	validate_lot_process_selection(doc)
