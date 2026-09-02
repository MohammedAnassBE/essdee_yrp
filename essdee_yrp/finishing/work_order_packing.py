"""Build Essdee garment packing Work Orders over the generic YRP document.

The legacy implementation calculated these rows inside the F15 Work Order
controller.  In F16 the Work Order controller remains generic; this adapter
owns only the garment packing projection used by Finishing and alternative
items.
"""

import math

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.garment_bom import calculate_essdee_accessory_bom
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.yrp_item.yrp_item import build_variant_attributes, get_or_create_variant


def create_alternative_packing_work_order(source_work_order, target_lot):
	"""Create the draft packing Work Order for an alternative Lot."""
	source = frappe.get_doc('YRP Work Order', source_work_order)
	source.check_permission("read")
	lot = frappe.get_doc('SD YRP Lot', target_lot)
	if not lot.production_detail or not lot.item:
		frappe.throw(_("Alternative Lot {0} is not configured").format(target_lot))
	if not lot.get("is_transferred") or not lot.get("transferred_lot"):
		frappe.throw(_("Lot {0} is not an alternative Lot").format(target_lot))

	work_order = frappe.new_doc('YRP Work Order')
	for fieldname in (
		"supplier",
		"supplier_address",
		"delivery_address",
		"delivery_location",
		"planned_start_date",
		"planned_end_date",
		"expected_delivery_date",
		"terms_and_condition",
	):
		if work_order.meta.get_field(fieldname):
			work_order.set(fieldname, source.get(fieldname))
	work_order.lot = lot.name
	work_order.item = lot.item
	work_order.production_detail = lot.production_detail
	work_order.process_name = source.process_name

	rows = build_packing_work_order_rows(lot, work_order.process_name)
	work_order.set("deliverables", rows["deliverables"])
	work_order.set("receivables", rows["receivables"])
	work_order.set("work_order_calculated_items", rows["calculated_items"])
	work_order.total_quantity = rows["total_quantity"]
	work_order.planned_quantity = rows["total_quantity"]
	if work_order.meta.get_field("wo_colours"):
		work_order.wo_colours = rows["colour_summary"]
	work_order.insert(ignore_permissions=True)
	return work_order.name


def build_packing_work_order_rows(lot, process_name):
	"""Return the three Work Order child tables for one garment packing Lot.

	This follows the F15 packing branch: Lot rows are the principal inputs,
	Item BOM rows for the packing process are additional deliverables, and the
	pack-out variants are receivables.  It deliberately does not post stock.
	"""
	lot = frappe.get_doc('SD YRP Lot', lot) if isinstance(lot, str) else lot
	ipd = frappe.get_cached_doc('YRP Item Production Detail', lot.production_detail)
	if process_name != ipd.packing_process and not _group_contains(
		process_name, ipd.packing_process
	):
		frappe.throw(
			_("Process {0} does not include packing process {1}").format(
				process_name, ipd.packing_process
			)
		)

	principal = _principal_rows(lot)
	if not principal:
		frappe.throw(_("Lot {0} has no quantity to pack").format(lot.name))
	default_received_type = frappe.db.get_single_value(
		'YRP YRP Stock Settings', "default_received_type"
	)
	deliverables = []
	calculated_items = []
	for index, row in enumerate(principal):
		common = {
			"item_variant": row["item_variant"],
			"lot": lot.name,
			"table_index": row["table_index"],
			"row_index": row["row_index"],
			"set_combination": row["set_combination"],
		}
		deliverables.append(
			{
				**common,
				"qty": row["quantity"],
				"pending_quantity": row["quantity"],
				"uom": lot.packing_uom,
				"received_type": default_received_type,
				"is_calculated": 1,
			}
		)
		calculated_items.append(
			{
				"item_variant": row["item_variant"],
				"quantity": row["quantity"],
				"table_index": row["table_index"],
				"row_index": index,
				"set_combination": row["set_combination"],
			}
		)

	demands = [
		{"item_variant": row["item_variant"], "qty": row["quantity"]}
		for row in principal
	]
	for index, row in enumerate(
		_accessory_rows(ipd, lot, demands, process_name), start=len(deliverables)
	):
		deliverables.append(
			{
				"item_variant": row["item_variant"],
				"lot": lot.name,
				"qty": flt(row["required_qty"], 3),
				"pending_quantity": flt(row["required_qty"], 3),
				"uom": row["uom"],
				"received_type": default_received_type,
				"table_index": index,
				"row_index": str(index),
				"set_combination": "{}",
				"is_calculated": 1,
			}
		)

	receivables = _packing_receivables(ipd, lot, principal, default_received_type)
	return {
		"deliverables": deliverables,
		"receivables": receivables,
		"calculated_items": calculated_items,
		"total_quantity": sum(flt(row["qty"]) for row in receivables),
		"colour_summary": _colour_summary(ipd, principal),
	}


def _principal_rows(lot):
	rows = []
	for index, row in enumerate(lot.get("lot_order_details") or []):
		quantity = flt(row.cut_qty if row.get("cut_qty") is not None else row.quantity)
		if quantity <= 0:
			continue
		rows.append(
			{
				"item_variant": row.item_variant,
				"quantity": quantity,
				"table_index": row.table_index or index,
				"row_index": str(row.row_index if row.row_index is not None else index),
				"set_combination": row.set_combination or "{}",
			}
		)
	return rows


def _accessory_rows(ipd, lot, demands, process_name):
	processes = {process_name}
	if frappe.db.get_value('YRP Process', process_name, "is_group"):
		processes.update(
			frappe.get_all(
				'YRP Process Details', filters={"parent": process_name}, pluck="process_name"
			)
		)
	return [
		row
		for row in calculate_essdee_accessory_bom(ipd.name, demands, lot)
		if row.get("process_name") in processes
	]


def _packing_receivables(ipd, lot, principal, default_received_type):
	dynamic_ratio = bool(
		ipd.based_on_other_attribute_mapping
		and ipd.packing_mode == "Size Ratio Packing"
	)
	parts_count = _set_parts_count(ipd)
	aggregated = {}
	for row in principal:
		attributes = get_variant_attr_details(row["item_variant"])
		size = attributes.get(ipd.primary_item_attribute)
		if not size:
			continue
		quantity = flt(row["quantity"])
		if not dynamic_ratio:
			quantity /= parts_count
			quantity = math.ceil(
				quantity * _uom_factor(ipd.item, lot.packing_uom, lot.uom)
			)
		variant = get_or_create_variant(
			ipd.item,
			build_variant_attributes(
				{ipd.primary_item_attribute: size}, ipd.pack_out_stage, ipd.name
			),
		)
		entry = aggregated.setdefault(
			variant,
			{
				"item_variant": variant,
				"lot": lot.name,
				"qty": 0,
				"pending_quantity": 0,
				"uom": lot.packing_uom if dynamic_ratio else lot.uom,
				"received_type": default_received_type,
				"table_index": 0,
				"row_index": str(len(aggregated)),
				"set_combination": "{}",
			},
		)
		entry["qty"] += quantity
		entry["pending_quantity"] += quantity
	for entry in aggregated.values():
		entry["qty"] = flt(entry["qty"], 3)
		entry["pending_quantity"] = entry["qty"]
	return list(aggregated.values())


def _uom_factor(item, from_uom, to_uom):
	if not to_uom or from_uom == to_uom:
		return 1
	factors = {
		row.uom: flt(row.conversion_factor)
		for row in frappe.get_cached_doc('YRP Item', item).get("uom_conversion_details") or []
	}
	from_factor = factors.get(from_uom)
	to_factor = factors.get(to_uom)
	if not from_factor or not to_factor:
		frappe.throw(
			_("Missing UOM conversion from {0} to {1} on Item {2}").format(
				from_uom, to_uom, item
			)
		)
	return from_factor / to_factor


def _set_parts_count(ipd):
	if not ipd.is_set_item:
		return 1
	parts = {
		row.set_item_attribute_value
		for row in ipd.get("set_item_combination_details") or []
		if row.set_item_attribute_value
	}
	return len(parts) or 1


def _colour_summary(ipd, principal):
	colours = []
	for row in principal:
		colour = get_variant_attr_details(row["item_variant"]).get(ipd.packing_attribute)
		if colour and colour not in colours:
			colours.append(colour)
	return ", ".join(colours)


def _group_contains(group, process):
	if not group or not frappe.db.get_value('YRP Process', group, "is_group"):
		return False
	return bool(
		frappe.db.exists(
			'YRP Process Details', {"parent": group, "process_name": process}
		)
	)
