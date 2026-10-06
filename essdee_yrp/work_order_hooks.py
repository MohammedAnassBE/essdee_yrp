# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt
import json

import frappe
from frappe import _
from frappe.utils import cstr, flt
from yrp import attribute_links as attribute_db
from yrp.yrp.doctype.yrp_item.yrp_item import get_parent_item


def onload(doc, method=None):
	"""Render Essdee Work Order items as logical rows with Size columns."""
	del method
	if not doc.get("production_detail"):
		return

	from yrp.stock.save_stock_items import group_items_for_ui

	from essdee_yrp.item_matrix import normalize_item_matrix_row_indexes

	doc.set_onload(
		"deliverable_details",
		group_items_for_ui(
			normalize_item_matrix_row_indexes(doc.get("deliverables") or []),
			"YRP Work Order Deliverables",
		),
	)
	doc.set_onload(
		"receivable_details",
		group_items_for_ui(
			normalize_item_matrix_row_indexes(doc.get("receivables") or []),
			"YRP Work Order Receivables",
		),
	)


def validate(doc, method=None):
	set_includes_packing(doc)
	preserve_dynamic_packing_piece_uom(doc)
	validate_lot_process_selection(doc)
	if doc.is_new():
		from essdee_yrp.cloth_execution import stamp_cloth_execution_version

		# API/import callers can reach validation with Production Detail derived
		# by the hook above, after controller.before_insert had no value to stamp.
		stamp_cloth_execution_version(doc)
	validate_fabric_execution_immutable(doc)
	# Draft reservations must still be current when their execution contract is
	# saved. Submitted lifecycle updates are protected by immutability and are
	# rechecked by the DC/GRN authority instead of trapping a valid submitted WO
	# after another Work Order consumes later stock.
	if int(doc.get("docstatus") or 0) == 0:
		from essdee_yrp.fabric_source import validate_work_order_source_allocations

		validate_work_order_source_allocations(doc)


def validate_fabric_execution_immutable(doc):
	"""Allow generated contract changes only through Calculate/lifecycle code."""
	flags = doc.flags or frappe._dict()
	if flags.get("essdee_fabric_calculate") or flags.get("essdee_fabric_lifecycle"):
		return
	previous = doc.get_doc_before_save()
	if not previous:
		return
	previous_snapshot, previous_managed = _fabric_execution_snapshot(previous)
	current_snapshot, current_managed = _fabric_execution_snapshot(doc)
	if not (previous_managed or current_managed):
		return
	if previous_snapshot != current_snapshot:
		frappe.throw(
			_(
				"Calculated fabric deliverables and receivables can be changed only "
				"through Calculate. Reopen the popup to rebuild the execution contract."
			)
		)


def _fabric_execution_snapshot(doc):
	from essdee_yrp.cloth_execution import get_row_execution_parameters
	from yrp.stock.dimensions import get_dimension_fieldnames

	managed = any(
		get_row_execution_parameters(row).get("fabric_execution_key")
		for table in ("deliverables", "receivables")
		for row in (doc.get(table) or [])
	)
	dimension_fields = tuple(get_dimension_fieldnames())
	fields = {
		"deliverables": (
			"item_variant",
			"qty",
			"uom",
			"is_calculated",
			"received_type",
			"set_combination",
			"fabric_reference_variant",
			"fabric_reference_allocations",
			"additional_parameters",
			"source_grn",
			"source_grn_item",
		) + dimension_fields,
		"receivables": (
			"item_variant",
			"qty",
			"uom",
			"set_combination",
			"fabric_reference_variant",
			"fabric_reference_allocations",
			"additional_parameters",
		) + dimension_fields,
	}
	rows = []
	if managed:
		for table, fieldnames in fields.items():
			for row in doc.get(table) or []:
				payload = {"table": table}
				for fieldname in fieldnames:
					value = row.get(fieldname)
					if fieldname == "qty":
						value = flt(value, 6)
					else:
						value = cstr(value) if value is not None else ""
					payload[fieldname] = value
				rows.append(payload)
		rows.sort(key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")))
	header = {
		fieldname: cstr(doc.get(fieldname) or "")
		for fieldname in (
			"lot",
			"production_detail",
			"process_name",
			"item",
			"fabric_source_process",
			"fabric_source_process_step",
			"cloth_execution_version",
			"is_rework",
			"parent_wo",
			"rework_type",
		)
	}
	return (
		json.dumps(
			{"header": header, "rows": rows},
			sort_keys=True,
			separators=(",", ":"),
		),
		managed,
	)


def preserve_dynamic_packing_piece_uom(doc):
	"""Keep new dynamic packing receivable counters in their physical Piece UOM."""
	if not (doc.get("production_detail") and doc.get("lot") and doc.get("includes_packing")):
		return
	ipd = frappe.get_cached_doc("YRP Item Production Detail", doc.production_detail)
	if not (ipd.get("based_on_other_attribute_mapping") and ipd.get("packing_mode") == "Size Ratio Packing"):
		return
	piece_uom = attribute_db.get_value("SD YRP Lot", doc.lot, "packing_uom")
	if not piece_uom:
		frappe.throw(_("Packing UOM is required on Lot {0}.").format(doc.lot))
	for row in doc.get("receivables") or []:
		parent_item = get_parent_item(row.item_variant)
		if parent_item == ipd.item:
			row.uom = piece_uom


def set_includes_packing(doc):
	"""Copy Essdee's Process packing rule without coupling base Work Order."""
	if not doc.meta.get_field("includes_packing"):
		return
	doc.includes_packing = 0
	if doc.get("process_name") and frappe.get_meta("YRP Process").get_field("includes_packing"):
		doc.includes_packing = frappe.db.get_value("YRP Process", doc.process_name, "includes_packing") or 0


def validate_lot_process_selection(doc):
	"""Keep the Work Order's Item/IPD tied to its selected Process and Lot.

	The clients require an explicit filtered Item selection, and API/import
	callers receive the same guard. Production Detail is derived and never
	accepted as an independent user choice.
	"""
	if not doc.get("process_name") or not doc.get("lot"):
		return

	from essdee_yrp.api.work_order import _get_work_order_selection_context

	context = _get_work_order_selection_context(doc.lot, doc.process_name, check_permission=False)
	options = context["options"]
	if not options:
		scope = _("cloth IPDs") if context["is_cloth_process"] else _("garment IPD")
		frappe.throw(
			_("Lot {0} has no {1} configured for process {2}.").format(doc.lot, scope, doc.process_name)
		)

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
