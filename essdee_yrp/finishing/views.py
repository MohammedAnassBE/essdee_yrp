"""Read models consumed by the Finishing Plan Desk components."""

import frappe
from frappe.utils import flt

from essdee_yrp.dynamic_packing import LEGACY_BATCH_TRACKING_VERSION
from essdee_yrp.finishing.packing import get_dynamic_packed_qty
from essdee_yrp.finishing.parsing import json_object
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.item.item import get_attribute_details
from yrp.yrp.doctype.item_production_detail.item_production_detail import (
	get_ipd_primary_values,
)


def build_plan_views(doc):
	context = _get_ipd_context(doc)
	views = _build_quantity_views(doc, context)
	views["inward_details"] = _build_inward_details(doc, context)
	views["rework_details"] = _build_rework_details(doc, context)
	views["rejection_details"] = _build_rejection_details(doc, context)
	views["packed_qty"] = get_packed_qty(doc)
	views["old_lot_data"] = (
		reshape_old_lot_rows_for_ui(doc, context["ipd_doc"])
		if doc.get("finishing_old_lot_items")
		else {"data": [], "colours": []}
	)
	views["old_lot_given_matrix"] = _build_transfer_matrix(
		doc.get("finishing_old_lot_given_items") or [],
		context["primary_values"],
		"destination_fp",
		"destination_lot",
		"loose_piece_given",
		"loose_piece_set_given",
	)
	views["old_lot_received_matrix"] = _build_transfer_matrix(
		doc.get("finishing_old_lot_received_items") or [],
		context["primary_values"],
		"source_fp",
		"source_lot",
		"loose_piece_taken",
		"loose_piece_set_taken",
	)
	return views


def get_packed_qty(doc):
	dynamic_grns = frappe.get_all(
		"Goods Received Note",
		filters={
			"against": "Work Order",
			"against_id": doc.work_order,
			"lot": doc.lot,
			"docstatus": 1,
			"is_return": 0,
			"includes_packing": 1,
			"from_finishing": 1,
			"packing_calculation_version": [">=", LEGACY_BATCH_TRACKING_VERSION],
		},
		pluck="name",
	)
	if dynamic_grns:
		return get_dynamic_packed_qty(doc, dynamic_grns)

	box_quantity = {"sizes": {}, "total_packed": 0, "total_dispatched": 0}
	for row in doc.get("finishing_plan_grn_details") or []:
		variant = frappe.get_cached_doc("Item Variant", row.item_variant)
		primary_attribute = get_attribute_details(variant.item)["primary_attribute"]
		size = next(
			(
				attribute.attribute_value
				for attribute in variant.attributes
				if attribute.attribute == primary_attribute
			),
			None,
		)
		if not size:
			continue
		value = box_quantity["sizes"].setdefault(
			size, {"packed": 0, "dispatched": 0, "cur_dispatch": 0}
		)
		value["packed"] += flt(row.quantity)
		value["dispatched"] += flt(row.dispatched)
		box_quantity["total_packed"] += flt(row.quantity)
		box_quantity["total_dispatched"] += flt(row.dispatched)
	return box_quantity


def before_save(doc):
	"""Keep the denormalized reworked total on each Finishing Plan Detail row."""
	from essdee_yrp.finishing.state import (
		get_finishing_plan_dict,
		get_finishing_plan_list,
	)

	items = get_finishing_plan_dict(doc)
	for values in items.values():
		values["reworked"] = 0
	for row in doc.get("finishing_plan_reworked_details") or []:
		combination = _json_object(row.set_combination)
		key = (row.item_variant, tuple(sorted(combination.items())))
		if key not in items:
			frappe.throw(
				f"Rework item {row.item_variant} has no matching Finishing Plan detail"
			)
		items[key]["reworked"] += flt(row.reworked_quantity)
	doc.set("finishing_plan_details", get_finishing_plan_list(items))


def _get_ipd_context(doc):
	ipd_name = doc.production_detail or frappe.db.get_value(
		"Lot", doc.lot, "production_detail"
	)
	ipd_doc = frappe.get_cached_doc("Item Production Detail", ipd_name)
	return {
		"ipd_doc": ipd_doc,
		"ipd": ipd_name,
		"is_set_item": bool(ipd_doc.is_set_item),
		"pack_attr": ipd_doc.packing_attribute,
		"primary_attr": ipd_doc.primary_item_attribute,
		"set_attr": ipd_doc.set_item_attribute,
		"primary_values": get_ipd_primary_values(ipd_name),
	}


def _row_identity(row, context):
	combination = _json_object(row.set_combination)
	attributes = get_variant_attr_details(row.item_variant)
	major_colour = combination.get("major_colour") or attributes.get(
		context["pack_attr"], ""
	)
	part = None
	colour = major_colour
	if context["is_set_item"]:
		variant_colour = attributes.get(context["pack_attr"], "")
		part = attributes.get(context["set_attr"])
		colour = f"{variant_colour} ({major_colour}) @ {part or ''}"
	return frappe._dict(
		{
			"combination": combination,
			"attributes": attributes,
			"size": attributes.get(context["primary_attr"]),
			"part": part,
			"colour": colour,
			"variant_colour": attributes.get(context["pack_attr"], ""),
		}
	)


def _json_object(value):
	return json_object(value)


def _build_inward_details(doc, context):
	data = {"data": {}, "total": {}}
	for row in doc.get("finishing_plan_details") or []:
		identity = _row_identity(row, context)
		block = _ensure_inward_block(data, identity)
		accepted = (
			flt(row.accepted_qty) + flt(row.lot_transferred) + flt(row.ironing_excess)
		)
		block["colour_total"]["accepted"] += accepted
		block["values"][identity.size]["accepted"] += accepted

	for row in doc.get("finishing_plan_reworked_details") or []:
		identity = _row_identity(row, context)
		block = _ensure_inward_block(data, identity)
		pending = max(
			flt(row.quantity) - flt(row.reworked_quantity) - flt(row.rejected_qty), 0
		)
		for fieldname, value in (
			("reworked", flt(row.reworked_quantity)),
			("rejected", flt(row.rejected_qty)),
			("pending", pending),
		):
			block["colour_total"][fieldname] += value
			block["values"][identity.size][fieldname] += value
	return data


def _ensure_inward_block(data, identity):
	block = data["data"].setdefault(
		identity.colour,
		{
			"values": {},
			"colour": identity.variant_colour,
			"part": identity.part,
			"colour_total": {
				"accepted": 0,
				"reworked": 0,
				"pending": 0,
				"rejected": 0,
			},
		},
	)
	block["values"].setdefault(
		identity.size,
		{"accepted": 0, "reworked": 0, "pending": 0, "rejected": 0},
	)
	data["total"].setdefault(identity.size, 0)
	return block


def _build_rework_details(doc, context):
	data = {"data": {}, "total": {}}
	for row in doc.get("finishing_plan_reworked_details") or []:
		identity = _row_identity(row, context)
		block = data["data"].setdefault(
			identity.colour,
			{
				"values": {},
				"colour": identity.variant_colour,
				"part": identity.part,
				"colour_total": {
					"rework_qty": 0,
					"reworked": 0,
					"pending": 0,
					"rejected": 0,
				},
			},
		)
		block["values"].setdefault(
			identity.size,
			{"rework_qty": 0, "reworked": 0, "pending": 0, "rejected": 0},
		)
		pending = max(
			flt(row.quantity) - flt(row.reworked_quantity) - flt(row.rejected_qty), 0
		)
		for fieldname, value in (
			("rework_qty", flt(row.quantity)),
			("reworked", flt(row.reworked_quantity)),
			("pending", pending),
			("rejected", flt(row.rejected_qty)),
		):
			block["colour_total"][fieldname] += value
			block["values"][identity.size][fieldname] += value
		data["total"].setdefault(identity.size, 0)
	return data


def _build_quantity_views(doc, context):
	finishing_inward = {"data": {}, "total": {}, "over_all": {}}
	finishing_quantity = {"data": {}, "total": {}}
	finishing_ironing = {"data": {}, "total": {}, "total_qty": {"ironing": 0}}
	pack_return = {"data": {}, "total": {}, "total_qty": 0}
	for row in doc.get("finishing_plan_details") or []:
		identity = _row_identity(row, context)
		part = identity.part or "item"
		inward = _ensure_quantity_inward(finishing_inward, identity, part)
		quantity = _ensure_quantity_balance(finishing_quantity, identity)
		ironing = _ensure_ironing(finishing_ironing, identity)
		packing_return = _ensure_pack_return(pack_return, identity)

		cutting = flt(row.cutting_qty)
		received = flt(row.delivered_quantity)
		delivered = flt(row.inward_quantity)
		difference = received - delivered
		cut_sew_difference = delivered - cutting
		for target in (
			inward["colour_total"],
			inward["values"][identity.size],
			finishing_inward["total"][part][identity.size],
			finishing_inward["over_all"][part],
		):
			target["cutting"] += cutting
			target["received"] += received
			target["delivered"] += delivered
			target["difference"] += difference
			target["cut_sew_diff"] += cut_sew_difference

		accepted = (
			flt(row.accepted_qty)
			+ flt(row.reworked)
			+ flt(row.lot_transferred)
			+ flt(row.ironing_excess)
		)
		balance = (
			accepted
			- flt(row.dc_qty)
			- flt(row.return_qty)
			- flt(row.pack_return_qty)
			- flt(row.transferred_qty)
		)
		for target in (quantity["colour_total"], quantity["values"][identity.size]):
			target["accepted"] += accepted
			target["dc_qty"] += flt(row.dc_qty)
			target["balance"] += balance
			target["balance_dc"] += balance
			target["return_qty"] += flt(row.return_qty)
			target["pack_return"] += flt(row.pack_return_qty)

		ironing["values"][identity.size]["ironing"] += flt(row.ironing_excess)
		ironing["colour_total"]["ironing"] += flt(row.ironing_excess)
		finishing_ironing["total"][identity.size]["ironing"] += flt(
			row.ironing_excess
		)
		finishing_ironing["total_qty"]["ironing"] += flt(row.ironing_excess)

		packing_return["values"][identity.size]["pack_returned_qty"] += flt(
			row.pack_return_qty
		)
		packing_return["colour_total"] += flt(row.pack_return_qty)
		pack_return["total"][identity.size] += flt(row.pack_return_qty)
		pack_return["total_qty"] += flt(row.pack_return_qty)

	return {
		"primary_values": context["primary_values"],
		"finishing_inward": finishing_inward,
		"finishing_qty": finishing_quantity,
		"finishing_ironing": finishing_ironing,
		"is_set_item": context["is_set_item"],
		"set_attr": context["set_attr"],
		"pack_return": pack_return,
	}


def _ensure_quantity_inward(data, identity, part):
	block = data["data"].setdefault(
		identity.colour,
		{
			"values": {},
			"part": identity.part,
			"colour": identity.variant_colour,
			"set_combination": identity.combination,
			"colour_total": _empty_inward_totals(),
		},
	)
	block["values"].setdefault(identity.size, _empty_inward_totals())
	data["total"].setdefault(part, {})
	data["total"][part].setdefault(identity.size, _empty_inward_totals())
	data["over_all"].setdefault(part, _empty_inward_totals())
	return block


def _empty_inward_totals():
	return {
		"cutting": 0,
		"received": 0,
		"delivered": 0,
		"difference": 0,
		"cut_sew_diff": 0,
	}


def _ensure_quantity_balance(data, identity):
	block = data["data"].setdefault(
		identity.colour,
		{
			"values": {},
			"part": identity.part,
			"check_value": True,
			"colour": identity.variant_colour,
			"set_combination": identity.combination,
			"colour_total": _empty_balance_totals(),
		},
	)
	block["values"].setdefault(identity.size, _empty_balance_totals())
	data["total"].setdefault(identity.size, 0)
	return block


def _empty_balance_totals():
	return {
		"accepted": 0,
		"dc_qty": 0,
		"balance": 0,
		"balance_dc": 0,
		"return_qty": 0,
		"pack_return": 0,
	}


def _ensure_ironing(data, identity):
	block = data["data"].setdefault(
		identity.colour,
		{
			"values": {},
			"part": identity.part,
			"colour": identity.variant_colour,
			"set_combination": identity.combination,
			"colour_total": {"ironing": 0, "ironing_dc": 0},
		},
	)
	block["values"].setdefault(identity.size, {"ironing": 0, "ironing_dc": 0})
	data["total"].setdefault(identity.size, {"ironing": 0})
	return block


def _ensure_pack_return(data, identity):
	block = data["data"].setdefault(
		identity.colour,
		{
			"values": {},
			"part": identity.part,
			"colour": identity.variant_colour,
			"set_combination": identity.combination,
			"colour_total": 0,
		},
	)
	block["values"].setdefault(
		identity.size, {"pack_returned_qty": 0, "pack_return": 0}
	)
	data["total"].setdefault(identity.size, 0)
	return block


def _build_rejection_details(doc, context):
	data = {}
	grand_total = 0
	for document_name in frappe.get_all(
		"GRN Rework Item", filters={"lot": doc.lot}, pluck="name"
	):
		rework_doc = frappe.get_doc("GRN Rework Item", document_name)
		for row in rework_doc.get("grn_rework_item_details") or []:
			rework_quantity = flt(row.quantity)
			rejection_quantity = flt(row.rejection)
			if not rework_quantity and not rejection_quantity:
				continue
			identity = _row_identity(row, context)
			received_type = row.received_type or "Unspecified"
			block = data.setdefault(received_type, {}).setdefault(
				identity.colour,
				{
					"part": identity.part,
					"rework": {"values": {}, "total": 0},
					"rejection": {"values": {}, "total": 0},
				},
			)
			block["rework"]["values"][identity.size] = (
				block["rework"]["values"].get(identity.size, 0) + rework_quantity
			)
			block["rework"]["total"] += rework_quantity
			block["rejection"]["values"][identity.size] = (
				block["rejection"]["values"].get(identity.size, 0) + rejection_quantity
			)
			block["rejection"]["total"] += rejection_quantity
			grand_total += rejection_quantity
	return {
		"primary_values": context["primary_values"],
		"data": data,
		"grand_rejection_total": grand_total,
		"is_set_item": context["is_set_item"],
		"set_attr": context["set_attr"],
	}


def reshape_old_lot_rows_for_ui(doc, ipd_doc=None):
	if ipd_doc is None:
		ipd_doc = frappe.get_cached_doc(
			"Item Production Detail",
			doc.production_detail
			or frappe.db.get_value("Lot", doc.lot, "production_detail"),
		)
	primary_values = get_ipd_primary_values(ipd_doc.name)
	groups = {}
	for row in doc.get("finishing_old_lot_items") or []:
		key = (row.source_lot, row.warehouse, row.warehouse_name)
		group = groups.setdefault(key, {"data": {}, "total": {}})
		colour = row.colour
		block = group["data"].setdefault(
			colour,
			{
				"values": {},
				"part": row.part,
				"colour": colour,
				"set_combination": row.set_combination,
				"colour_total": _empty_old_lot_totals(),
			},
		)
		for size in primary_values:
			block["values"].setdefault(size, _empty_old_lot_totals())
			group["total"].setdefault(size, 0)
		if row.size not in primary_values:
			continue
		values = {
			"balance_loose_piece": flt(row.balance_loose_piece),
			"balance_loose_piece_set": flt(row.balance_loose_piece_set),
			"transfer_loose_piece": flt(row.transfer_loose_piece),
			"transfer_loose_piece_set": flt(row.transfer_loose_piece_set),
		}
		for fieldname, quantity in values.items():
			block["values"][row.size][fieldname] += quantity
			block["colour_total"][fieldname] += quantity
		group["total"][row.size] += (
			values["balance_loose_piece"] + values["balance_loose_piece_set"]
		)

	data = []
	for (source_lot, warehouse, warehouse_name), group in groups.items():
		data.append(
			{
				"lot": source_lot,
				"warehouse": warehouse,
				"warehouse_name": warehouse_name,
				"primary_values": primary_values,
				"old_lot_inward": group,
				"is_set_item": ipd_doc.is_set_item,
				"set_attr": ipd_doc.set_item_attribute,
			}
		)
	colours = [
		row.attribute_value for row in ipd_doc.get("packing_attribute_details") or []
	]
	return {"data": data, "colours": colours}


def _empty_old_lot_totals():
	return {
		"balance_loose_piece": 0,
		"balance_loose_piece_set": 0,
		"transfer_loose_piece": 0,
		"transfer_loose_piece_set": 0,
	}


def _build_transfer_matrix(
	rows,
	primary_values,
	counterpart_plan_field,
	counterpart_lot_field,
	loose_piece_field,
	loose_piece_set_field,
):
	groups = {}
	for row in rows:
		key = (
			row.get(counterpart_plan_field),
			row.get(counterpart_lot_field),
			row.colour,
			row.part or "",
		)
		group = groups.setdefault(
			key,
			{
				"fp": row.get(counterpart_plan_field),
				"lot": row.get(counterpart_lot_field),
				"colour": row.colour,
				"part": row.part,
				"lp": {size: 0 for size in primary_values},
				"lps": {size: 0 for size in primary_values},
				"lts": [],
				"lp_total": 0,
				"lps_total": 0,
			},
		)
		if row.size in group["lp"]:
			loose_piece = flt(row.get(loose_piece_field))
			loose_piece_set = flt(row.get(loose_piece_set_field))
			group["lp"][row.size] += loose_piece
			group["lps"][row.size] += loose_piece_set
			group["lp_total"] += loose_piece
			group["lps_total"] += loose_piece_set
		if row.lot_transfer and row.lot_transfer not in group["lts"]:
			group["lts"].append(row.lot_transfer)
	return {"primary_values": primary_values, "groups": list(groups.values())}
