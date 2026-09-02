"""Physical box/piece calculations for Essdee Finishing Plans."""

import frappe
from frappe.utils import cint, flt

from essdee_yrp.dynamic_packing import LEGACY_BATCH_TRACKING_VERSION
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import (
	get_ipd_primary_values,
)


def get_dynamic_packed_qty(finishing_doc, grn_names):
	"""Return exact packed/dispatched boxes and pieces for batch-tracked GRNs."""
	data = frappe._dict(
		{
			"sizes": {},
			"total_packed": 0,
			"total_dispatched": 0,
			"total_packed_boxes": 0,
			"total_dispatched_boxes": 0,
			"dynamic_ratio_packing": True,
			"packing_batches": [],
		}
	)
	for size in get_ipd_primary_values(finishing_doc.production_detail):
		data.sizes[size] = _empty_size_summary()

	for grn_name in grn_names:
		grn = frappe.get_doc('YRP Goods Received Note', grn_name)
		version = cint(grn.packing_calculation_version)
		for batch in grn.get("packing_batches") or []:
			ratio = update_if_string_instance(batch.ratio_json) or {}
			boxes = flt(batch.box_quantity)
			dispatched_boxes = flt(batch.dispatched_boxes)
			for size, per_box in ratio.items():
				row = data.sizes.setdefault(size, _empty_size_summary())
				row["packed"] += boxes * flt(per_box)
				row["dispatched"] += dispatched_boxes * flt(per_box)
				row["packed_boxes"] += boxes
				row["dispatched_boxes"] += dispatched_boxes

			data.packing_batches.append(
				{
					"grn": grn_name,
					"batch_row": batch.name,
					"batch_id": batch.batch_id,
					"colour": batch.colour,
					"box_quantity": boxes,
					"dispatched_boxes": dispatched_boxes,
					"available_boxes": max(boxes - dispatched_boxes, 0),
					"pieces_per_box": flt(batch.pieces_per_box),
					"total_pieces": flt(batch.total_pieces),
					"ratio": ratio,
					"packing_calculation_version": version,
				}
			)
			data.total_packed_boxes += boxes
			data.total_dispatched_boxes += dispatched_boxes

	data.total_packed = sum(flt(row["packed"]) for row in data.sizes.values())
	data.total_dispatched = sum(flt(row["dispatched"]) for row in data.sizes.values())
	return data


def get_finishing_packing_summary(finishing_doc):
	if isinstance(finishing_doc, str):
		finishing_doc = frappe.get_doc('SD YRP Finishing Plan', finishing_doc)

	grn_names = []
	if finishing_doc.work_order:
		grn_names = frappe.get_all(
			'YRP Goods Received Note',
			filters={
				"against": 'YRP Work Order',
				"against_id": finishing_doc.work_order,
				"lot": finishing_doc.lot,
				"docstatus": 1,
				"is_return": 0,
				"includes_packing": 1,
				"from_finishing": 1,
				"packing_calculation_version": [">=", LEGACY_BATCH_TRACKING_VERSION],
			},
			pluck="name",
		)

	if grn_names:
		return get_dynamic_packed_qty(finishing_doc, grn_names)
	return frappe._dict(
		{
			"dynamic_ratio_packing": False,
			"sizes": {},
			"packing_batches": [],
			"total_packed": 0,
			"total_dispatched": 0,
			"total_packed_boxes": 0,
			"total_dispatched_boxes": 0,
		}
	)


@frappe.whitelist()
def get_ipd_packing_config(lot):
	"""Return the configuration used by Finishing packing entry dialogs."""
	ipd_name = frappe.db.get_value('SD YRP Lot', lot, "production_detail")
	if not ipd_name:
		frappe.throw(f"Lot {lot} has no Item Production Detail")
	ipd = frappe.get_cached_doc('YRP Item Production Detail', ipd_name)
	colours = []
	for row in ipd.get("item_attributes") or []:
		attribute = row.get("attribute") or row.get("item_attribute")
		if attribute == ipd.packing_attribute and row.mapping:
			mapping = frappe.get_cached_doc('YRP Item Item Attribute Mapping', row.mapping)
			colours = [value.attribute_value for value in mapping.get("values") or []]
			break
	return {
		"based_on_other_attribute_mapping": ipd.based_on_other_attribute_mapping,
		"packing_mode": ipd.packing_mode,
		"dynamic_ratio_packing": bool(
			ipd.based_on_other_attribute_mapping
			and ipd.packing_mode == "Size Ratio Packing"
		),
		"packing_combo": ipd.packing_combo,
		"primary_attribute": ipd.primary_item_attribute,
		"packing_attribute": ipd.packing_attribute,
		"packing_size_details": [
			{"attribute_value": row.attribute_value, "quantity": row.quantity}
			for row in ipd.get("packing_size_details") or []
		],
		"colours": colours,
	}


def prepare_dynamic_batch_dispatch(finishing_doc, dispatches):
	"""Lock, validate, and expand physical boxes to size-wise stock quantities."""
	dispatches = update_if_string_instance(dispatches) or []
	if not isinstance(dispatches, list) or not dispatches:
		frappe.throw("Select at least one packing batch to dispatch")

	seen = set()
	normalized = []
	for index, request in enumerate(dispatches, 1):
		request = update_if_string_instance(request) or {}
		batch_row = request.get("batch_row")
		if not batch_row or batch_row in seen:
			frappe.throw(f"Invalid or duplicate packing batch in dispatch row {index}")
		seen.add(batch_row)
		boxes = flt(request.get("box_quantity"))
		if boxes <= 0 or boxes != int(boxes):
			frappe.throw(
				f"Dispatch boxes in row {index} should be a positive whole number"
			)

		locked = frappe.db.sql(
			"""
				SELECT name, parent, batch_id, colour, box_quantity,
					dispatched_boxes, pieces_per_box, ratio_json
				FROM `tabSD YRP GRN Packing Batch`
				WHERE name = %s FOR UPDATE
			""",
			batch_row,
			as_dict=True,
		)
		if not locked:
			frappe.throw(f"Packing batch {batch_row} does not exist")
		batch = locked[0]
		grn = frappe.get_cached_doc('YRP Goods Received Note', batch.parent)
		version = cint(grn.packing_calculation_version)
		if (
			grn.docstatus != 1
			or grn.against != 'YRP Work Order'
			or grn.against_id != finishing_doc.work_order
			or grn.lot != finishing_doc.lot
			or version < LEGACY_BATCH_TRACKING_VERSION
		):
			frappe.throw(f"Packing batch {batch_row} does not belong to this Finishing Plan")

		available = flt(batch.box_quantity) - flt(batch.dispatched_boxes)
		if boxes > available:
			frappe.throw(
				f"Only {available:g} boxes are available in "
				f"{grn.name} / {batch.batch_id or batch_row}"
			)
		ratio = update_if_string_instance(batch.ratio_json) or {}
		size_pieces = {
			size: int(boxes) * flt(per_box) for size, per_box in ratio.items()
		}
		box_uom, piece_uom = frappe.get_cached_value(
			'SD YRP Lot', finishing_doc.lot, ["uom", "packing_uom"]
		)
		if version == LEGACY_BATCH_TRACKING_VERSION:
			pieces_per_box = flt(batch.pieces_per_box)
			if not pieces_per_box:
				frappe.throw(f"Packing batch {batch_row} has no pieces-per-box value")
			stock_quantities = {
				size: pieces / pieces_per_box for size, pieces in size_pieces.items()
			}
			stock_uom = box_uom
		else:
			stock_quantities = dict(size_pieces)
			stock_uom = piece_uom
		normalized.append(
			{
				"batch_row": batch_row,
				"grn": grn.name,
				"batch_id": batch.batch_id,
				"colour": batch.colour,
				"box_quantity": int(boxes),
				"pieces_per_box": flt(batch.pieces_per_box),
				"ratio": ratio,
				"size_pieces": size_pieces,
				"stock_quantities": stock_quantities,
				"stock_uom": stock_uom,
				"packing_calculation_version": version,
			}
		)
	return normalized


def rebuild_finishing_packing_quantities(finishing_doc):
	"""Idempotently rebuild plan quantities from all submitted packing GRNs."""
	if isinstance(finishing_doc, str):
		finishing_doc = frappe.get_doc('SD YRP Finishing Plan', finishing_doc)

	grns = frappe.get_all(
		'YRP Goods Received Note',
		filters={
			"against": 'YRP Work Order',
			"against_id": finishing_doc.work_order,
			"lot": finishing_doc.lot,
			"docstatus": 1,
			"is_return": 0,
			"includes_packing": 1,
			"from_finishing": 1,
		},
		fields=[
			"name",
			"packing_calculation_version",
			"total_packing_boxes",
			"total_packing_pieces",
		],
	)
	batch_tracked = any(
		cint(grn.packing_calculation_version) >= LEGACY_BATCH_TRACKING_VERSION
		for grn in grns
	)
	if batch_tracked:
		untracked = [
			grn.name
			for grn in grns
			if cint(grn.packing_calculation_version) < LEGACY_BATCH_TRACKING_VERSION
		]
		if untracked:
			frappe.throw(
				"Cannot rebuild Finishing Plan packing quantities while untracked legacy "
				f"GRNs remain: {', '.join(untracked)}"
			)

	quantities = {}
	tracked_dispatched = {}
	primary_attribute = frappe.get_cached_value(
		'YRP Item Production Detail',
		finishing_doc.production_detail,
		"primary_item_attribute",
	)
	for grn in grns:
		multiplier = 1
		version = cint(grn.packing_calculation_version)
		if version == LEGACY_BATCH_TRACKING_VERSION:
			boxes = flt(grn.total_packing_boxes)
			pieces = flt(grn.total_packing_pieces)
			if not boxes or not pieces:
				frappe.throw(f"Migrated packing totals are missing in GRN {grn.name}")
			multiplier = pieces / boxes

		variant_by_size = {}
		for item in frappe.get_all(
			'YRP Goods Received Note Item',
			filters={"parent": grn.name, "docstatus": 1},
			fields=["item_variant", "quantity"],
		):
			quantities[item.item_variant] = (
				quantities.get(item.item_variant, 0) + flt(item.quantity) * multiplier
			)
			attributes = get_variant_attr_details(item.item_variant)
			if attributes.get(primary_attribute):
				variant_by_size[attributes[primary_attribute]] = item.item_variant

		if version >= LEGACY_BATCH_TRACKING_VERSION:
			for batch in frappe.get_all(
				'SD YRP GRN Packing Batch',
				filters={"parent": grn.name},
				fields=["dispatched_boxes", "ratio_json"],
			):
				ratio = update_if_string_instance(batch.ratio_json) or {}
				for size, per_box in ratio.items():
					item_variant = variant_by_size.get(size)
					if item_variant:
						tracked_dispatched[item_variant] = (
							tracked_dispatched.get(item_variant, 0)
							+ flt(batch.dispatched_boxes) * flt(per_box)
						)

	existing = {
		row.item_variant: row
		for row in finishing_doc.get("finishing_plan_grn_details") or []
	}
	rows = []
	for item_variant in dict.fromkeys([*existing, *quantities]):
		rows.append(
			{
				"item_variant": item_variant,
				"quantity": flt(quantities.get(item_variant), 9),
				"dispatched": (
					flt(tracked_dispatched.get(item_variant), 9)
					if batch_tracked
					else flt(existing[item_variant].dispatched, 9)
					if item_variant in existing
					else 0
				),
			}
		)
	finishing_doc.set("finishing_plan_grn_details", rows)
	return finishing_doc


def _empty_size_summary():
	return {
		"packed": 0,
		"dispatched": 0,
		"packed_boxes": 0,
		"dispatched_boxes": 0,
		"cur_dispatch": 0,
	}
