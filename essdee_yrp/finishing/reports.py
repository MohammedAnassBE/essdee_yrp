"""Finishing packing/dispatch read models used by Desk reports and DPR views."""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate
from yrp import attribute_links as attribute_db
from yrp.attribute_links import value as _attribute_value
from yrp.attribute_read_context import attribute_read_scope
from yrp.utils import update_if_string_instance
from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import (
	get_ipd_primary_values,
)

from essdee_yrp.dynamic_packing import DYNAMIC_PACKING_VERSION


def get_configured_set_item_parts(ipd_doc):
	if not ipd_doc.is_set_item:
		return set()
	return {
		_attribute_value(row.set_item_attribute_value)
		for row in ipd_doc.get("set_item_combination_details") or []
		if _attribute_value(row.set_item_attribute_value)
	}


def apply_set_item_multiplier_to_packing_report(packing, ipd_doc):
	"""Convert garment sets to component pieces, without changing box counts."""
	parts_count = len(get_configured_set_item_parts(ipd_doc)) or 1
	if parts_count == 1:
		return packing
	packing.size_pieces = {
		size: flt(quantity * parts_count, 3) for size, quantity in packing.size_pieces.items()
	}
	packing.total_pieces = flt(packing.total_pieces * parts_count, 3)
	return packing


def load_variant_attributes(variants):
	"""Attribute values keyed by variant, then attribute, in one query."""
	variants = tuple({variant for variant in variants if variant})
	if not variants:
		return {}
	attributes = {}
	for row in frappe.db.sql(
		"""SELECT parent, attribute, attribute_value FROM `tabItem Variant Attribute`
		WHERE parent IN %(variants)s""",
		{"variants": variants},
		as_dict=True,
	):
		attributes.setdefault(row.parent, {})[row.attribute] = _attribute_value(row.attribute_value)
	return attributes


def load_packing_grns(grn_names):
	"""GRN packing totals with their items and variant attributes, in three queries."""
	grn_names = list(dict.fromkeys(grn_names or []))
	if not grn_names:
		return {}
	grns = {
		row.name: frappe._dict(row, item_rows=[])
		for row in frappe.get_all(
			"YRP Goods Received Note",
			filters={"name": ["in", grn_names]},
			fields=["name", "packing_calculation_version", "total_packing_boxes"],
			limit_page_length=0,
		)
	}
	items = (
		frappe.get_all(
			"YRP Goods Received Note Item",
			filters={
				"parent": ["in", list(grns)],
				"parenttype": "YRP Goods Received Note",
				"parentfield": "items",
			},
			fields=["parent", "item_variant", "quantity"],
			order_by="parent asc, idx asc",
			limit_page_length=0,
		)
		if grns
		else []
	)
	attributes = load_variant_attributes(row.item_variant for row in items)
	for row in items:
		row.attributes = attributes.get(row.item_variant) or {}
		grns[row.parent].item_rows.append(row)
	return grns


def get_packing_grn_report_values(grn_names, ipd_doc, grns=None):
	grns = grns if grns is not None else load_packing_grns(grn_names)
	sizes = get_ipd_primary_values(ipd_doc.name)
	size_pieces = {size: 0 for size in sizes}
	total_boxes = 0
	total_pieces = 0
	has_dynamic_ratio = False
	legacy_combo = flt(ipd_doc.packing_combo)

	for grn_name in grn_names:
		grn = grns[grn_name]
		dynamic_ratio = cint(grn.packing_calculation_version) >= DYNAMIC_PACKING_VERSION
		has_dynamic_ratio = has_dynamic_ratio or dynamic_ratio
		grn_boxes = 0
		grn_pieces = 0
		for item in grn.item_rows:
			size = item.attributes.get(ipd_doc.primary_item_attribute)
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
			"size_pieces": {size: flt(quantity, 3) for size, quantity in size_pieces.items()},
			"total_boxes": flt(total_boxes, 3),
			"total_pieces": flt(total_pieces, 3),
			"dynamic_ratio_packing": has_dynamic_ratio,
			"pieces_per_box": "Mixed" if has_dynamic_ratio else legacy_combo,
		}
	)


def packed_date_filter(date=None, from_date=None, to_date=None, summary=0):
	"""Return the GRN actual_date filter for the single-day or Summary report."""
	if not cint(summary):
		if not date:
			frappe.throw(_("Date is required"))
		return date
	if not from_date or not to_date:
		frappe.throw(_("From Date and To Date are required for Summary"))
	if getdate(from_date) > getdate(to_date):
		frappe.throw(_("From Date cannot be after To Date"))
	return ["between", [from_date, to_date]]


@frappe.whitelist()
def get_finishing_packed_details(
	date=None,
	lot_list=None,
	item_list=None,
	from_date=None,
	to_date=None,
	summary=0,
):
	"""Date-wise size pieces and physical box totals from packing GRNs."""
	lot_list = _normalize_list(lot_list)
	item_list = _normalize_list(item_list)
	grns = frappe.get_list(
		"YRP Goods Received Note",
		filters={
			"against": "YRP Work Order",
			"includes_packing": 1,
			"docstatus": 1,
			"actual_date": packed_date_filter(date, from_date, to_date, summary),
		},
		fields=["name", "lot", "actual_date"],
	)
	date_lot_grns = {}
	for grn in grns:
		if lot_list and grn.lot not in lot_list:
			continue
		date_lot_grns.setdefault((str(grn.actual_date or date), grn.lot), []).append(grn.name)

	packing_grns = load_packing_grns(name for names in date_lot_grns.values() for name in names)
	lots = {}
	result = []
	with attribute_read_scope():
		for (report_date, lot), grn_names in sorted(date_lot_grns.items()):
			if lot not in lots:
				lots[lot] = attribute_db.get_value(
					"SD YRP Lot", lot, ["item", "production_detail"], as_dict=True
				)
			lot_values = lots[lot]
			if not lot_values or not lot_values.production_detail:
				continue
			if item_list and lot_values.item not in item_list:
				continue
			ipd_doc = frappe.get_cached_doc("YRP Item Production Detail", lot_values.production_detail)
			packing = apply_set_item_multiplier_to_packing_report(
				get_packing_grn_report_values(grn_names, ipd_doc, packing_grns), ipd_doc
			)
			if not any(packing.size_pieces.values()):
				continue
			result.append(
				{
					"date": report_date,
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


def get_finishing_dispatch_report(from_date, to_date, lot_list=None, item_list=None):
	"""Packed vs dispatched boxes and pieces per lot, loaded in a fixed number of queries."""
	lot_list = _normalize_list(lot_list)
	item_list = _normalize_list(item_list)
	with attribute_read_scope():
		lot_grns = get_dispatch_report_lot_grns(from_date, to_date, lot_list)
		lot_dispatches = get_dispatch_report_lot_dispatches(from_date, to_date, lot_list)
		lots = load_report_lots([*lot_grns, *lot_dispatches], item_list)
		packing_grns = load_packing_grns(name for names in lot_grns.values() for name in names)
		packed_rows = [
			get_packed_dispatch_row(lot, lots[lot], grn_names, packing_grns)
			for lot, grn_names in lot_grns.items()
			if lot in lots
		]
		attributes = load_variant_attributes(
			item["row"].item for values in lot_dispatches.values() for item in values["items"]
		)
		dispatched_rows = [
			get_dispatched_row(lot, lots[lot], values, attributes)
			for lot, values in lot_dispatches.items()
			if lot in lots
		]
	return merge_dispatch_rows(packed_rows, dispatched_rows)


def get_dispatch_report_lot_grns(from_date, to_date, lot_list):
	grns = frappe.get_list(
		"YRP Goods Received Note",
		filters={
			"against": "YRP Work Order",
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
		lot_grns = {lot: names for lot, names in lot_grns.items() if lot in lot_list}
	return lot_grns


def load_report_lots(lot_names, item_list):
	"""Lots that have a production detail and match the item filter."""
	lot_names = list({lot for lot in lot_names if lot})
	if not lot_names:
		return {}
	rows = attribute_db.get_all(
		"SD YRP Lot",
		filters={"name": ["in", lot_names]},
		fields=["name", "item", "production_detail"],
	)
	return {
		row.name: row for row in rows if row.production_detail and (not item_list or row.item in item_list)
	}


def get_packed_dispatch_row(lot, lot_values, grn_names, packing_grns):
	packing = get_packing_grn_report_values(
		grn_names,
		frappe.get_cached_doc("YRP Item Production Detail", lot_values.production_detail),
		packing_grns,
	)
	return {
		"lot": lot,
		"item": lot_values.item,
		"sizes": packing.sizes,
		"size_qty": packing.size_pieces,
		"pieces_per_box": packing.pieces_per_box,
		"dynamic_ratio_packing": packing.dynamic_ratio_packing,
		"total_boxes": packing.total_boxes,
		"total_pieces": packing.total_pieces,
	}


def get_dispatch_report_lot_dispatches(from_date, to_date, lot_list):
	# The public web endpoint already authorizes this narrowly scoped report
	# using Finishing Plan + GRN read access. Stock Entry is an implementation
	# source here, not an additional user-facing permission requirement.
	stock_entries = frappe.get_all(
		"YRP Stock Entry",
		filters={
			"against": ["in", ["SD YRP Finishing Plan", "SD YRP Finishing Plan Dispatch"]],
			"purpose": "Material Issue",
			"docstatus": 1,
			"posting_date": ["between", [from_date, to_date]],
		},
		fields=["name", "packing_batch_dispatch_json"],
	)
	batches = {
		entry.name: update_if_string_instance(entry.packing_batch_dispatch_json) or []
		for entry in stock_entries
	}
	batch_lot = get_dispatch_batch_lot_resolver(batches.values())
	entry_items = get_stock_entry_items(list(batches))
	lot_dispatches = {}
	for name, entry_batches in batches.items():
		dynamic_boxes_by_lot = {}
		for batch in entry_batches:
			lot = batch_lot(batch)
			if lot:
				dynamic_boxes_by_lot[lot] = dynamic_boxes_by_lot.get(lot, 0) + flt(batch.get("box_quantity"))
		add_entry_dispatches(lot_dispatches, entry_items.get(name, []), dynamic_boxes_by_lot)
	if lot_list:
		lot_dispatches = {lot: values for lot, values in lot_dispatches.items() if lot in lot_list}
	return lot_dispatches


def get_dispatch_batch_lot_resolver(batch_lists):
	"""Resolve a dispatch batch's lot from its Finishing Plan, falling back to its GRN."""
	batches = [batch for batch_list in batch_lists for batch in batch_list]
	plan_lots = get_lots_by_name("SD YRP Finishing Plan", {batch.get("finishing_plan") for batch in batches})
	grn_lots = get_lots_by_name("YRP Goods Received Note", {batch.get("grn") for batch in batches})

	def resolve(batch):
		lot = plan_lots.get(batch.get("finishing_plan")) if batch.get("finishing_plan") else None
		if not lot and batch.get("grn"):
			lot = grn_lots.get(batch["grn"])
		return lot

	return resolve


def get_lots_by_name(doctype, names):
	names = [name for name in names if name]
	if not names:
		return {}
	rows = frappe.get_all(doctype, filters={"name": ["in", names]}, fields=["name", "lot"])
	return {row.name: row.lot for row in rows}


def get_stock_entry_items(stock_entry_names):
	if not stock_entry_names:
		return {}
	items = {}
	for row in frappe.get_all(
		"YRP Stock Entry Detail",
		filters={"parent": ["in", stock_entry_names]},
		fields=["parent", "item", "qty", "lot"],
	):
		items.setdefault(row.parent, []).append(row)
	return items


def add_entry_dispatches(lot_dispatches, entry_items, dynamic_boxes_by_lot):
	for lot in {row.lot for row in entry_items if row.lot}:
		bucket = lot_dispatches.setdefault(lot, {"items": [], "dynamic_boxes": 0, "has_dynamic": False})
		if lot in dynamic_boxes_by_lot:
			bucket["dynamic_boxes"] += dynamic_boxes_by_lot[lot]
			bucket["has_dynamic"] = True
	for row in entry_items:
		if row.lot:
			lot_dispatches[row.lot]["items"].append(
				{"row": row, "dynamic_dispatch": row.lot in dynamic_boxes_by_lot}
			)


def get_dispatched_row(lot, lot_values, values, attributes):
	ipd = frappe.get_cached_doc("YRP Item Production Detail", lot_values.production_detail)
	sizes = get_ipd_primary_values(ipd.name)
	size_quantity = {size: 0 for size in sizes}
	total_boxes = flt(values["dynamic_boxes"])
	total_pieces = 0
	for item_data in values["items"]:
		row = item_data["row"]
		size = (attributes.get(row.item) or {}).get(ipd.primary_item_attribute)
		if not size:
			continue
		pieces = flt(row.qty)
		if not item_data["dynamic_dispatch"]:
			total_boxes += flt(row.qty)
			pieces *= flt(ipd.packing_combo)
		size_quantity.setdefault(size, 0)
		size_quantity[size] += pieces
		total_pieces += pieces
	return {
		"lot": lot,
		"item": lot_values.item,
		"sizes": sizes,
		"size_qty": size_quantity,
		"pieces_per_box": ("Mixed" if values["has_dynamic"] else flt(ipd.packing_combo)),
		"dynamic_ratio_packing": values["has_dynamic"],
		"total_boxes": total_boxes,
		"total_pieces": total_pieces,
	}


def merge_dispatch_rows(packed_rows, dispatched_rows):
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
