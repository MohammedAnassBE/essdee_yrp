"""Finishing Plan OCR read model and percentage summaries."""

import frappe
from frappe.utils import flt

from essdee_yrp.finishing.packing import get_finishing_packing_summary
from essdee_yrp.finishing.parsing import json_object
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.item_production_detail.item_production_detail import (
	get_ipd_primary_values,
)


@frappe.whitelist()
def get_fp_ocr_details(doc_name):
	doc = frappe.get_doc("Finishing Plan", doc_name)
	doc.check_permission("read")
	ocr_data = get_ocr_details(doc)
	metrics = {
		"get_total_difference": {},
		"get_total": {},
		"get_ocr_value": {},
		"get_cut_to_dispatch": {},
		"get_cut_to_inward": {},
		"get_inward_to_dispatch": {},
		"get_loose_piece": {},
		"get_rejection": {},
		"get_rework": {},
		"get_not_received": {},
		"get_unaccountable": {},
		"get_order_to_dispatch": {},
	}
	for part, values in ocr_data.items():
		cutting_available = (
			values["cutting"]
			+ values["old_lot"]
			+ values["ironing_excess"]
		)
		inward_available = (
			values["sewing_received"]
			+ values["old_lot"]
			+ values["ironing_excess"]
			- values["transferred"]
		)
		metrics["get_total"][part] = (
			values["packed_box_qty"]
			+ values["rejected"]
			+ values["loose_piece_set"]
			+ values["loose_piece"]
			+ values["pending"]
			- values["sewing_received"]
			- values["old_lot"]
			- values["ironing_excess"]
		)
		metric_rows = {
			"get_cut_to_dispatch": {
				"val1": cutting_available - values["transferred"],
				"val2": values["dispatched_piece"],
			},
			"get_cut_to_inward": {
				"val1": values["cutting"],
				"val2": values["sewing_received"],
			},
			"get_inward_to_dispatch": {
				"val1": inward_available,
				"val2": values["dispatched_piece"],
			},
			"get_loose_piece": {
				"val1": cutting_available,
				"val2": values["loose_piece"] + values["loose_piece_set"],
			},
			"get_rejection": {
				"val1": cutting_available,
				"val2": values["rejected"],
			},
			"get_rework": {
				"val1": cutting_available,
				"val2": values["pending"],
			},
			"get_not_received": {
				"val1": cutting_available,
				"val2": values["sewing_received"] - values["cutting"],
			},
			"get_unaccountable": {
				"val1": cutting_available,
				"val2": inward_available
				- values["dispatched_piece"]
				- values["rejected"]
				- values["loose_piece_set"]
				- values["loose_piece"]
				- values["pending"],
			},
			"get_order_to_dispatch": {
				"val1": values.get("order_qty", 0),
				"val2": values["dispatched_piece"],
			},
		}
		for name, metric in metric_rows.items():
			metrics[name][part] = metric
		metrics["get_ocr_value"][part] = round(
			get_ocr_percentage(metric_rows["get_cut_to_dispatch"])
			+ get_ocr_percentage(metric_rows["get_loose_piece"])
			+ get_ocr_percentage(metric_rows["get_rejection"])
			+ get_ocr_percentage(metric_rows["get_rework"])
			+ get_ocr_percentage(metric_rows["get_not_received"], make_pos=True),
			2,
		)
		metrics["get_total_difference"][part] = {
			size: (
				row["packed_box_qty"]
				+ row["rejected"]
				+ row["loose_piece_set"]
				+ row["loose_piece"]
				+ row["pending"]
				- row["sewing_received"]
				- row["old_lot"]
				- row["ironing_excess"]
			)
			for size, row in values["total"].items()
		}
	return ocr_data, metrics, get_ipd_primary_values(doc.production_detail)


def get_ocr_details(doc):
	ipd_name = doc.production_detail or frappe.db.get_value(
		"Lot", doc.lot, "production_detail"
	)
	is_set_item, packing_attribute, primary_attribute, set_attribute, major_part = (
		frappe.db.get_value(
			"Item Production Detail",
			ipd_name,
			[
				"is_set_item",
				"packing_attribute",
				"primary_item_attribute",
				"set_item_attribute",
				"major_attribute_value",
			],
		)
	)
	ocr_data = {}
	parts = set()
	for row in doc.get("finishing_plan_details") or []:
		attributes = get_variant_attr_details(row.item_variant)
		part = attributes.get(set_attribute) if is_set_item else "Item"
		parts.add(part)
		size = attributes.get(primary_attribute)
		part_data = ocr_data.setdefault(part, _empty_part())
		part_data["total"].setdefault(size, _empty_size())
		combination = json_object(row.set_combination)
		major_colour = combination.get("major_colour", "")
		colour = major_colour
		if is_set_item:
			colour = (
				f"{attributes.get(packing_attribute, '')} ({major_colour}) @ {part or ''}"
			)
		colour_data = part_data["data"].setdefault(
			colour,
			{
				"values": {},
				"colour": attributes.get(packing_attribute, ""),
				"part": part if is_set_item else None,
				"colour_total": _empty_cell(),
			},
		)
		colour_data["values"].setdefault(size, _empty_cell())

		values = {
			"cutting": flt(row.cutting_qty),
			"dc_qty": flt(row.dc_qty),
			"transferred": flt(row.transferred_qty),
			"ironing_excess": flt(row.ironing_excess),
			"old_lot": flt(row.lot_transferred),
			"sewing_received": flt(row.delivered_quantity),
			"loose_piece": flt(row.return_qty),
			"loose_piece_set": flt(row.pack_return_qty),
			"rejected": flt(row.rejected_qty),
		}
		for fieldname, quantity in values.items():
			part_data[fieldname] += quantity
			total_field = "cutting_qty" if fieldname == "cutting" else fieldname
			part_data["total"][size][total_field] += quantity
			if fieldname in _empty_cell():
				colour_data["values"][size][fieldname] += quantity
				colour_data["colour_total"][fieldname] += quantity
		inward = values["sewing_received"] + values["ironing_excess"] + values["old_lot"]
		part_data["total_inward"] += inward
		part_data["total"][size]["total_inward"] += inward

	_apply_packing(doc, ocr_data, parts or {"Item"}, primary_attribute)
	_apply_old_lot_adjustments(
		doc,
		ocr_data,
		is_set_item,
		packing_attribute,
		primary_attribute,
		set_attribute,
		major_part,
	)
	_apply_rework(doc, ocr_data, is_set_item, packing_attribute, primary_attribute, set_attribute)
	_apply_order_quantity(doc, ocr_data, is_set_item, primary_attribute, set_attribute)
	return ocr_data


def _apply_packing(doc, ocr_data, parts, primary_attribute):
	packing = get_finishing_packing_summary(doc)
	for row in doc.get("finishing_plan_grn_details") or []:
		size = get_variant_attr_details(row.item_variant).get(primary_attribute)
		if packing.dynamic_ratio_packing:
			packed_pieces = flt(row.quantity)
			dispatched_pieces = flt(row.dispatched)
			size_summary = packing.sizes.get(size, {})
			packed_boxes = flt(size_summary.get("packed_boxes"))
			dispatched_boxes = flt(size_summary.get("dispatched_boxes"))
		else:
			packed_boxes = flt(row.quantity)
			dispatched_boxes = flt(row.dispatched)
			packed_pieces = packed_boxes * flt(doc.pieces_per_box)
			dispatched_pieces = dispatched_boxes * flt(doc.pieces_per_box)
		for part in parts:
			if part not in ocr_data:
				continue
			part_data = ocr_data[part]
			part_data["packed_box_qty"] += packed_pieces
			part_data["packed_box"] += packed_boxes
			part_data["dispatched_piece"] += dispatched_pieces
			part_data["dispatched_box"] += dispatched_boxes
			part_data["total"].setdefault(size, _empty_size())
			part_data["total"][size]["packed_box"] += packed_boxes
			part_data["total"][size]["packed_box_qty"] += packed_pieces
			part_data["total"][size]["dispatched_box"] += dispatched_boxes
			part_data["total"][size]["dispatched_piece"] += dispatched_pieces
	if packing.dynamic_ratio_packing:
		for part in parts:
			if part in ocr_data:
				ocr_data[part]["packed_box"] = packing.total_packed_boxes
				ocr_data[part]["dispatched_box"] = packing.total_dispatched_boxes


def _apply_old_lot_adjustments(
	doc,
	ocr_data,
	is_set_item,
	packing_attribute,
	primary_attribute,
	set_attribute,
	major_part,
):
	def apply(row, loose_piece, loose_piece_set):
		if not row.item_variant:
			return
		attributes = get_variant_attr_details(row.item_variant)
		part = attributes.get(set_attribute) if is_set_item else "Item"
		size = attributes.get(primary_attribute)
		colour = attributes.get(packing_attribute)
		if is_set_item and part != major_part:
			major_colour = json_object(row.set_combination).get(
				"major_colour"
			)
			if major_colour:
				colour = f"{colour} ({major_colour})"
		if part not in ocr_data or colour not in ocr_data[part]["data"]:
			return
		if size not in ocr_data[part]["data"][colour]["values"]:
			return
		cell = ocr_data[part]["data"][colour]["values"][size]
		colour_total = ocr_data[part]["data"][colour]["colour_total"]
		for target in (cell, colour_total, ocr_data[part]["total"][size], ocr_data[part]):
			target["loose_piece"] += loose_piece
			target["loose_piece_set"] += loose_piece_set

	for row in doc.get("finishing_old_lot_given_items") or []:
		apply(row, -flt(row.loose_piece_given), -flt(row.loose_piece_set_given))
	for row in doc.get("finishing_old_lot_received_items") or []:
		apply(row, flt(row.loose_piece_taken), flt(row.loose_piece_set_taken))


def _apply_rework(
	doc, ocr_data, is_set_item, packing_attribute, primary_attribute, set_attribute
):
	for row in doc.get("finishing_plan_reworked_details") or []:
		attributes = get_variant_attr_details(row.item_variant)
		part = attributes.get(set_attribute) if is_set_item else "Item"
		if part not in ocr_data:
			continue
		size = attributes.get(primary_attribute)
		major_colour = json_object(row.set_combination).get(
			"major_colour", ""
		)
		colour = major_colour
		if is_set_item:
			colour = (
				f"{attributes.get(packing_attribute, '')} ({major_colour}) @ {part or ''}"
			)
		if colour not in ocr_data[part]["data"]:
			continue
		pending = max(
			flt(row.quantity) - flt(row.reworked_quantity) - flt(row.rejected_qty), 0
		)
		for fieldname, quantity in (
			("rejected", flt(row.rejected_qty)),
			("pending", pending),
		):
			ocr_data[part]["data"][colour]["colour_total"][fieldname] += quantity
			ocr_data[part]["data"][colour]["values"][size][fieldname] += quantity
			ocr_data[part]["total"][size][fieldname] += quantity
			ocr_data[part][fieldname] += quantity


def _apply_order_quantity(doc, ocr_data, is_set_item, primary_attribute, set_attribute):
	lot_doc = frappe.get_cached_doc("Lot", doc.lot)
	for row in lot_doc.get("lot_order_details") or []:
		if not row.item_variant:
			continue
		attributes = get_variant_attr_details(row.item_variant)
		part = attributes.get(set_attribute) if is_set_item else "Item"
		if part not in ocr_data:
			continue
		size = attributes.get(primary_attribute)
		ocr_data[part]["total"].setdefault(size, _empty_size())
		ocr_data[part]["order_qty"] += flt(row.quantity)
		ocr_data[part]["total"][size]["order_qty"] += flt(row.quantity)


def _empty_part():
	return {
		"data": {},
		"total": {},
		"cutting": 0,
		"dc_qty": 0,
		"transferred": 0,
		"packed_box": 0,
		"packed_box_qty": 0,
		"dispatched_box": 0,
		"dispatched_piece": 0,
		"rejected": 0,
		"loose_piece": 0,
		"loose_piece_set": 0,
		"pending": 0,
		"sewing_received": 0,
		"old_lot": 0,
		"ironing_excess": 0,
		"total_inward": 0,
		"order_qty": 0,
	}


def _empty_size():
	return {
		"cutting_qty": 0,
		"dc_qty": 0,
		"transferred": 0,
		"packed_box": 0,
		"packed_box_qty": 0,
		"dispatched_box": 0,
		"dispatched_piece": 0,
		"rejected": 0,
		"loose_piece": 0,
		"loose_piece_set": 0,
		"pending": 0,
		"sewing_received": 0,
		"old_lot": 0,
		"ironing_excess": 0,
		"total_inward": 0,
		"order_qty": 0,
	}


def _empty_cell():
	return {
		"loose_piece": 0,
		"pending": 0,
		"rejected": 0,
		"loose_piece_set": 0,
		"sewing_received": 0,
	}


def get_ocr_percentage(values, make_pos=False):
	value1 = flt(values.get("val1"))
	value2 = flt(values.get("val2"))
	if not value1:
		value1 = 1
	percentage = (value2 / value1) * 100
	if make_pos and percentage < 0:
		percentage *= -1
	return round(percentage, 2)


def get_ocr_style(value):
	if flt(value) < 0:
		return "background: #f57f87;"
	if flt(value) > 0:
		return "background:#98ebae"
	return "background:#ebc96e;"
