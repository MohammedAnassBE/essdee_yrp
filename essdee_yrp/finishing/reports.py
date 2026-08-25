"""Finishing packing/dispatch read models used by Desk reports and DPR views."""

import frappe
from frappe.utils import cint, flt

from essdee_yrp.dynamic_packing import DYNAMIC_PACKING_VERSION
from yrp.utils import get_variant_attr_details
from yrp.utils import update_if_string_instance
from yrp.yrp.doctype.item_production_detail.item_production_detail import (
	get_ipd_primary_values,
)


def get_configured_set_item_parts(ipd_doc):
	if not ipd_doc.is_set_item:
		return set()
	return {
		row.set_item_attribute_value
		for row in ipd_doc.get("set_item_combination_details") or []
		if row.set_item_attribute_value
	}


def apply_set_item_multiplier_to_packing_report(packing, ipd_doc):
	"""Convert garment sets to component pieces, without changing box counts."""
	parts_count = len(get_configured_set_item_parts(ipd_doc)) or 1
	if parts_count == 1:
		return packing
	packing.size_pieces = {
		size: flt(quantity * parts_count, 3)
		for size, quantity in packing.size_pieces.items()
	}
	packing.total_pieces = flt(packing.total_pieces * parts_count, 3)
	return packing


def get_packing_grn_report_values(grn_names, ipd_doc):
	sizes = get_ipd_primary_values(ipd_doc.name)
	size_pieces = {size: 0 for size in sizes}
	total_boxes = 0
	total_pieces = 0
	has_dynamic_ratio = False
	legacy_combo = flt(ipd_doc.packing_combo)

	for grn_name in grn_names:
		grn = frappe.get_cached_doc("Goods Received Note", grn_name)
		dynamic_ratio = cint(grn.packing_calculation_version) >= DYNAMIC_PACKING_VERSION
		has_dynamic_ratio = has_dynamic_ratio or dynamic_ratio
		grn_boxes = 0
		grn_pieces = 0
		for item in grn.items:
			size = get_variant_attr_details(item.item_variant).get(
				ipd_doc.primary_item_attribute
			)
			if not size:
				continue
			pieces = flt(item.quantity)
			if not dynamic_ratio:
				grn_boxes += flt(item.quantity)
				pieces *= legacy_combo
			size_pieces.setdefault(size, 0)
			size_pieces[size] += pieces
			grn_pieces += pieces
		if dynamic_ratio:
			grn_boxes = flt(grn.total_packing_boxes)
		total_boxes += grn_boxes
		total_pieces += grn_pieces

	return frappe._dict(
		{
			"sizes": sizes,
			"size_pieces": {
				size: flt(quantity, 3) for size, quantity in size_pieces.items()
			},
			"total_boxes": flt(total_boxes, 3),
			"total_pieces": flt(total_pieces, 3),
			"dynamic_ratio_packing": has_dynamic_ratio,
			"pieces_per_box": "Mixed" if has_dynamic_ratio else legacy_combo,
		}
	)


@frappe.whitelist()
def get_finishing_packed_details(date, lot_list=None, item_list=None):
	lot_list = _normalize_list(lot_list)
	item_list = _normalize_list(item_list)
	grns = frappe.get_list(
		"Goods Received Note",
		filters={
			"against": "Work Order",
			"includes_packing": 1,
			"docstatus": 1,
			"actual_date": date,
		},
		fields=["name", "lot"],
	)
	lot_grns = {}
	for grn in grns:
		lot_grns.setdefault(grn.lot, []).append(grn.name)
	if lot_list:
		lot_grns = {
			lot: names for lot, names in lot_grns.items() if lot in lot_list
		}

	result = []
	for lot, grn_names in lot_grns.items():
		lot_values = frappe.db.get_value(
			"Lot", lot, ["item", "production_detail"], as_dict=True
		)
		if not lot_values or not lot_values.production_detail:
			continue
		if item_list and lot_values.item not in item_list:
			continue
		ipd_doc = frappe.get_cached_doc(
			"Item Production Detail", lot_values.production_detail
		)
		packing = apply_set_item_multiplier_to_packing_report(
			get_packing_grn_report_values(grn_names, ipd_doc), ipd_doc
		)
		if not any(packing.size_pieces.values()):
			continue
		result.append(
			{
				"lot": lot,
				"item": lot_values.item,
				"sizes": packing.sizes,
				"size_qty": packing.size_pieces,
				"pieces_per_box": packing.pieces_per_box,
				"dynamic_ratio_packing": packing.dynamic_ratio_packing,
				"total_boxes": packing.total_boxes,
				"total_pieces": packing.total_pieces,
			}
		)
	return {"data": result, "sizes": _ordered_sizes(result)}


@frappe.whitelist()
def get_finishing_dispatch_report(
	from_date, to_date, lot_list=None, item_list=None
):
	lot_list = _normalize_list(lot_list)
	item_list = _normalize_list(item_list)
	grns = frappe.get_list(
		"Goods Received Note",
		filters={
			"against": "Work Order",
			"includes_packing": 1,
			"docstatus": 1,
			"is_return": 0,
			"posting_date": ["between", [from_date, to_date]],
		},
		fields=["name", "lot"],
	)
	lot_grns = {}
	for grn in grns:
		lot_grns.setdefault(grn.lot, []).append(grn.name)
	if lot_list:
		lot_grns = {
			lot: names for lot, names in lot_grns.items() if lot in lot_list
		}

	packed_rows = []
	for lot, grn_names in lot_grns.items():
		lot_values = frappe.db.get_value(
			"Lot", lot, ["item", "production_detail"], as_dict=True
		)
		if not lot_values or not lot_values.production_detail:
			continue
		if item_list and lot_values.item not in item_list:
			continue
		packing = get_packing_grn_report_values(
			grn_names,
			frappe.get_cached_doc(
				"Item Production Detail", lot_values.production_detail
			),
		)
		packed_rows.append(
			{
				"lot": lot,
				"item": lot_values.item,
				"sizes": packing.sizes,
				"size_qty": packing.size_pieces,
				"pieces_per_box": packing.pieces_per_box,
				"dynamic_ratio_packing": packing.dynamic_ratio_packing,
				"total_boxes": packing.total_boxes,
				"total_pieces": packing.total_pieces,
			}
		)

	stock_entries = frappe.get_list(
		"Stock Entry",
		filters={
			"against": ["in", ["Finishing Plan", "Finishing Plan Dispatch"]],
			"purpose": "Material Issue",
			"docstatus": 1,
			"posting_date": ["between", [from_date, to_date]],
		},
		fields=["name", "packing_batch_dispatch_json"],
	)
	lot_dispatches = {}
	for stock_entry in stock_entries:
		dynamic_boxes_by_lot = {}
		for batch in update_if_string_instance(
			stock_entry.packing_batch_dispatch_json
		) or []:
			batch_lot = None
			if batch.get("finishing_plan"):
				batch_lot = frappe.get_cached_value(
					"Finishing Plan", batch["finishing_plan"], "lot"
				)
			if not batch_lot and batch.get("grn"):
				batch_lot = frappe.get_cached_value(
					"Goods Received Note", batch["grn"], "lot"
				)
			if batch_lot:
				dynamic_boxes_by_lot[batch_lot] = (
					dynamic_boxes_by_lot.get(batch_lot, 0)
					+ flt(batch.get("box_quantity"))
				)
		entry_items = frappe.get_all(
			"Stock Entry Detail",
			filters={"parent": stock_entry.name},
			fields=["item", "qty", "lot"],
		)
		for lot in {row.lot for row in entry_items if row.lot}:
			bucket = lot_dispatches.setdefault(
				lot, {"items": [], "dynamic_boxes": 0, "has_dynamic": False}
			)
			if lot in dynamic_boxes_by_lot:
				bucket["dynamic_boxes"] += dynamic_boxes_by_lot[lot]
				bucket["has_dynamic"] = True
		for row in entry_items:
			if row.lot:
				lot_dispatches[row.lot]["items"].append(
					{
						"row": row,
						"dynamic_dispatch": row.lot in dynamic_boxes_by_lot,
					}
				)
	if lot_list:
		lot_dispatches = {
			lot: values
			for lot, values in lot_dispatches.items()
			if lot in lot_list
		}

	dispatched_rows = []
	for lot, values in lot_dispatches.items():
		lot_values = frappe.db.get_value(
			"Lot", lot, ["item", "production_detail"], as_dict=True
		)
		if not lot_values or not lot_values.production_detail:
			continue
		if item_list and lot_values.item not in item_list:
			continue
		ipd = frappe.get_cached_doc(
			"Item Production Detail", lot_values.production_detail
		)
		sizes = get_ipd_primary_values(ipd.name)
		size_quantity = {size: 0 for size in sizes}
		total_boxes = flt(values["dynamic_boxes"])
		total_pieces = 0
		for item_data in values["items"]:
			row = item_data["row"]
			size = get_variant_attr_details(row.item).get(ipd.primary_item_attribute)
			if not size:
				continue
			pieces = flt(row.qty)
			if not item_data["dynamic_dispatch"]:
				total_boxes += flt(row.qty)
				pieces *= flt(ipd.packing_combo)
			size_quantity.setdefault(size, 0)
			size_quantity[size] += pieces
			total_pieces += pieces
		dispatched_rows.append(
			{
				"lot": lot,
				"item": lot_values.item,
				"sizes": sizes,
				"size_qty": size_quantity,
				"pieces_per_box": (
					"Mixed" if values["has_dynamic"] else flt(ipd.packing_combo)
				),
				"dynamic_ratio_packing": values["has_dynamic"],
				"total_boxes": total_boxes,
				"total_pieces": total_pieces,
			}
		)

	by_lot = {}
	for row in packed_rows:
		by_lot[row["lot"]] = {
			"lot": row["lot"],
			"item": row["item"],
			"sizes": row["sizes"],
			"pieces_per_box": row["pieces_per_box"],
			"packed_qty": row["size_qty"],
			"packed_total_boxes": row["total_boxes"],
			"packed_total_pieces": row["total_pieces"],
			"dispatched_qty": {},
			"dispatched_total_boxes": 0,
			"dispatched_total_pieces": 0,
		}
	for row in dispatched_rows:
		entry = by_lot.setdefault(
			row["lot"],
			{
				"lot": row["lot"],
				"item": row["item"],
				"sizes": row["sizes"],
				"pieces_per_box": row["pieces_per_box"],
				"packed_qty": {},
				"packed_total_boxes": 0,
				"packed_total_pieces": 0,
				"dispatched_qty": {},
				"dispatched_total_boxes": 0,
				"dispatched_total_pieces": 0,
			},
		)
		entry["dispatched_qty"] = row["size_qty"]
		entry["dispatched_total_boxes"] = row["total_boxes"]
		entry["dispatched_total_pieces"] = row["total_pieces"]
		if row["dynamic_ratio_packing"]:
			entry["pieces_per_box"] = "Mixed"
		for size in row["sizes"]:
			if size not in entry["sizes"]:
				entry["sizes"].append(size)
	return {"data": list(by_lot.values()), "sizes": _ordered_sizes(by_lot.values())}


def _normalize_list(value):
	if isinstance(value, str):
		value = frappe.parse_json(value)
	return list(value or [])


def _ordered_sizes(rows):
	ordered = []
	seen = set()
	for row in rows:
		for size in row["sizes"]:
			if size not in seen:
				seen.add(size)
				ordered.append(size)
	return ordered
