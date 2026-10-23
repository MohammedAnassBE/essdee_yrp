"""Calculate every Work Order input consumed by a packing GRN."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt
from yrp.attribute_links import value as _attribute_value
from yrp.stock.utils import get_stock_balance
from yrp.utils import get_variant_attr_details

from essdee_yrp.dynamic_packing import is_dynamic_packing_grn
from essdee_yrp.fabric_grn import (
	_allocate_to_work_order_deliverables,
	populate_grn_deliverables,
	validate_supplier_input_stock,
)
from essdee_yrp.finishing.loose_piece import get_loose_piece_stock_variant
from essdee_yrp.finishing.parsing import json_object
from essdee_yrp.garment_bom import calculate_essdee_accessory_bom

QTY_TOLERANCE = 0.000001


def before_validate(grn, method=None):
	del method
	if not _is_packing_grn(grn):
		return
	work_order = frappe.get_cached_doc("YRP Work Order", grn.against_id)
	ipd = frappe.get_cached_doc("YRP Item Production Detail", work_order.production_detail)
	populate_grn_deliverables(grn, _calculate_packing_inputs(grn, work_order, ipd))


def calculate_packing_consumption_plan(grn):
	"""Rebuild the complete packing input plan under the Work Order lock."""
	if not _is_packing_grn(grn):
		return []
	work_order = frappe.get_doc("YRP Work Order", grn.against_id)
	ipd = frappe.get_cached_doc("YRP Item Production Detail", work_order.production_detail)
	return _calculate_packing_inputs(grn, work_order, ipd)


def _calculate_packing_inputs(grn, work_order, ipd):
	garments = (
		_allocate_dynamic_consumed_garments(grn, work_order, ipd)
		if is_dynamic_packing_grn(grn)
		else _allocate_consumed_garments(grn, work_order, ipd)
	)
	validate_loose_piece_stock(grn, work_order, garments)
	accessories = _allocate_consumed_accessories(grn, work_order, ipd, garments)
	return [*garments, *accessories]


def _is_packing_grn(grn):
	return bool(
		grn.get("against") == "YRP Work Order"
		and grn.get("against_id")
		and grn.get("includes_packing")
		and not grn.get("is_return")
		and not grn.get("is_rework")
		and not grn.get("additional_grn")
	)


def _is_legacy_packing_grn(grn):
	return bool(_is_packing_grn(grn) and not flt(grn.get("packing_calculation_version")))


def _allocate_dynamic_consumed_garments(grn, work_order, ipd):
	"""Allocate each batch colour/size to every garment part.

	Dynamic packing stores physical boxes and ratios separately while the GRN
	output rows store their resulting piece quantities.  The batch is therefore
	the immutable colour identity; output rows alone are intentionally not used
	to guess which Work Order garment colour was packed.
	"""
	calculated = list(work_order.get("work_order_calculated_items") or [])
	deliverables = list(work_order.get("deliverables") or [])
	attributes = {_row_key(row): get_variant_attr_details(row.item_variant) for row in calculated}
	remaining_by_row = _remaining_by_row(calculated)
	outputs_by_size = _positive_outputs_by_size(grn, ipd)
	output_remaining = {
		row.name: flt(row.get("stock_qty") or row.get("quantity"))
		for rows in outputs_by_size.values()
		for row in rows
	}
	valuation_cache = {}
	result = []

	batches = list(grn.get("packing_batches") or [])
	if not batches:
		frappe.throw(_("A dynamic packing GRN requires at least one packing batch."))
	for batch in batches:
		colour = _attribute_value(batch.get("colour"))
		ratio = json_object(batch.get("ratio_json") or batch.get("ratio"))
		boxes = flt(batch.get("box_quantity"))
		for size, per_box in ratio.items():
			requested = boxes * flt(per_box)
			if requested <= 0:
				continue
			rows = [
				row
				for row in calculated
				if attributes[_row_key(row)].get(ipd.primary_item_attribute) == size
				and attributes[_row_key(row)].get(ipd.packing_attribute) == colour
			]
			if not rows:
				frappe.throw(
					_("Work Order {0} has no {1} / {2} garment row to pack.").format(
						work_order.name, colour, size
					)
				)
			for output, output_quantity in _take_output_chunks(
				outputs_by_size, output_remaining, size, requested
			):
				for group in _part_groups(rows, attributes, ipd):
					for allocated_rows, quantity in _allocate_best_effort(
						group, output_quantity, remaining_by_row, False
					):
						result.extend(
							_garment_plan_row(
								grn, work_order, deliverables, row, output, quantity, valuation_cache
							)
							for row in allocated_rows
						)

	leftover = sum(max(flt(quantity), 0) for quantity in output_remaining.values())
	if leftover > QTY_TOLERANCE:
		frappe.throw(_("Packing batch ratios do not account for {0} received pieces.").format(leftover))
	return result


def _part_groups(rows, attributes, ipd):
	"""Split a colour's rows per set part; every part consumes the full quantity."""
	if not ipd.is_set_item:
		return [rows]
	by_part = defaultdict(list)
	for row in rows:
		part = attributes[_row_key(row)].get(ipd.set_item_attribute) or json_object(row.set_combination).get(
			"major_part"
		)
		by_part[part or ""].append(row)
	return list(by_part.values())


def _garment_plan_row(grn, work_order, deliverables, calculated_row, output, quantity, valuation_cache):
	"""Map one allocated colour quantity to its Work Order input and Loose Piece valuation."""
	from yrp.stock.utils import get_conversion_factor
	from yrp.yrp.doctype.yrp_work_order.yrp_work_order import _stock_dimension_values

	source = _find_deliverable(deliverables, calculated_row)
	conversion = get_conversion_factor(source.item_variant, source.uom)
	factor = flt(conversion.get("conversion_factor")) or 1
	dimensions = _stock_dimension_values(work_order, source)
	stock_variant = get_loose_piece_stock_variant(grn, calculated_row.item_variant)
	valuation_key = (stock_variant, tuple(sorted(dimensions.items())))
	if valuation_key not in valuation_cache:
		_balance, valuation_cache[valuation_key] = get_stock_balance(
			stock_variant,
			grn.from_warehouse,
			posting_date=grn.posting_date,
			posting_time=grn.posting_time,
			with_valuation_rate=True,
			**dimensions,
		)
	return {
		"item_variant": calculated_row.item_variant,
		"goods_received_note_item": output.name,
		"received_item_variant": output.item_variant,
		"quantity": quantity / factor,
		"stock_qty": quantity,
		"uom": source.uom,
		"stock_uom": conversion.get("stock_uom") or source.uom,
		"conversion_factor": factor,
		"work_order_deliverable": source.name,
		"lot": dimensions.get("lot"),
		"received_type": dimensions.get("received_type"),
		"valuation_rate": valuation_cache[valuation_key],
		"set_combination": json_object(calculated_row.set_combination),
		"dimensions": dimensions,
	}


def validate_loose_piece_stock(grn, work_order, garments):
	"""Gate packing on the colourless Loose Piece stock the GRN consumes, per lot and type."""
	if (getattr(grn, "flags", None) or {}).get("skip_input_stock_check"):
		return
	stock_plan = [
		{**row, "item_variant": get_loose_piece_stock_variant(grn, row["item_variant"])} for row in garments
	]
	validate_supplier_input_stock(work_order, grn, stock_plan, {})


def _positive_outputs_by_size(grn, ipd):
	outputs = defaultdict(list)
	for row in grn.get("items") or []:
		if flt(row.get("stock_qty") or row.get("quantity")) <= 0:
			continue
		size = get_variant_attr_details(row.item_variant).get(ipd.primary_item_attribute)
		if not size:
			frappe.throw(
				_("Packed item {0} has no {1} attribute.").format(
					row.item_variant, ipd.primary_item_attribute
				)
			)
		outputs[size].append(row)
	return outputs


def _take_output_chunks(outputs_by_size, output_remaining, size, requested):
	remaining = flt(requested)
	chunks = []
	for output in outputs_by_size.get(size) or []:
		available = flt(output_remaining.get(output.name))
		take = min(remaining, available)
		if take > QTY_TOLERANCE:
			chunks.append((output, take))
			output_remaining[output.name] = available - take
			remaining -= take
		if remaining <= QTY_TOLERANCE:
			break
	if remaining > QTY_TOLERANCE:
		frappe.throw(
			_("Packing batches require {0} more received pieces for size {1}.").format(remaining, size)
		)
	return chunks


def _allocate_consumed_accessories(grn, work_order, ipd, garment_plan):
	"""Recalculate exact packing BOM rows and map them to delivered WO inputs."""
	if not garment_plan:
		return []
	lot = frappe.get_cached_doc("SD YRP Lot", grn.get("lot") or work_order.lot)
	process_names = {work_order.process_name}
	if frappe.db.get_value("YRP Process", work_order.process_name, "is_group"):
		process_names.update(
			frappe.get_all(
				"YRP Process Details",
				filters={"parent": work_order.process_name},
				pluck="process_name",
			)
		)
	demands = [
		{"item_variant": row["item_variant"], "qty": row["stock_qty"]}
		for row in garment_plan
		if flt(row.get("stock_qty")) > 0
	]
	bom_rows = calculate_essdee_accessory_bom(
		ipd.name,
		demands,
		lot,
		process_names=process_names,
	)
	if not bom_rows:
		return []

	outputs_by_size = _positive_outputs_by_size(grn, ipd)
	positive_outputs = [row for rows in outputs_by_size.values() for row in rows]
	if not positive_outputs:
		return []
	required = []
	for bom_row in bom_rows:
		quantity = flt(bom_row.get("required_qty"))
		if quantity <= QTY_TOLERANCE:
			continue
		accessory_size = (bom_row.get("attrs") or {}).get(ipd.primary_item_attribute)
		outputs = outputs_by_size.get(accessory_size) or positive_outputs
		for output, allocated in _split_quantity_across_outputs(quantity, outputs):
			required.append(
				{
					"goods_received_note_item": output.name,
					"received_item_variant": output.item_variant,
					"item_variant": bom_row["item_variant"],
					"qty": allocated,
					"uom": bom_row["uom"],
				}
			)
	return _allocate_to_work_order_deliverables(required, work_order, grn)


def _split_quantity_across_outputs(quantity, outputs):
	"""Allocate shared accessory value proportionally without rounding loss."""
	weighted = [
		(row, flt(row.get("stock_qty") or row.get("quantity")))
		for row in outputs
		if flt(row.get("stock_qty") or row.get("quantity")) > QTY_TOLERANCE
	]
	total_weight = sum(weight for _row, weight in weighted)
	if not weighted or total_weight <= QTY_TOLERANCE:
		return []
	allocated = 0.0
	result = []
	for index, (output, weight) in enumerate(weighted):
		share = (
			flt(quantity - allocated, 6)
			if index == len(weighted) - 1
			else flt(quantity * weight / total_weight, 6)
		)
		allocated += share
		if share > QTY_TOLERANCE:
			result.append((output, share))
	return result


def _allocate_consumed_garments(grn, work_order, ipd):
	deliverables = list(work_order.get("deliverables") or [])
	calculated = list(work_order.get("work_order_calculated_items") or [])
	remaining_by_row = _remaining_by_row(calculated)
	valuation_cache = {}
	result = []

	for output in grn.get("items") or []:
		output_stock_qty = flt(output.get("stock_qty"))
		if output_stock_qty <= 0:
			continue
		size = get_variant_attr_details(output.item_variant).get(ipd.primary_item_attribute)
		if not size:
			frappe.throw(
				_("Packed item {0} has no {1} attribute.").format(
					output.item_variant, ipd.primary_item_attribute
				)
			)
		rows = [
			row
			for row in calculated
			if get_variant_attr_details(row.item_variant).get(ipd.primary_item_attribute) == size
		]
		if not rows:
			frappe.throw(_("Work Order {0} has no {1} garment row to pack.").format(work_order.name, size))
		for allocated_rows, quantity in _allocate_best_effort(
			rows, output_stock_qty, remaining_by_row, ipd.is_set_item
		):
			result.extend(
				_garment_plan_row(grn, work_order, deliverables, row, output, quantity, valuation_cache)
				for row in allocated_rows
			)
	return result


def _remaining_by_row(calculated):
	return {_row_key(row): max(flt(row.delivered_quantity) - flt(row.received_qty), 0) for row in calculated}


def _allocate_best_effort(rows, requested, remaining_by_row, is_set_item):
	"""Fill each colour's delivered remaining, then spread any excess by planned quantity.

	Packing consumes colourless Loose Piece stock, so the colour split only links
	inputs to Work Order rows and never limits the receipt.
	"""
	allocate = _allocate_set_rows if is_set_item else _allocate_rows
	allocations = allocate(rows, requested, remaining_by_row)
	excess = flt(flt(requested) - sum(quantity for _rows, quantity in allocations), 6)
	if excess <= QTY_TOLERANCE:
		return allocations
	groups = (
		[group for group in _set_groups(rows) if len(group) > 1] if is_set_item else [[row] for row in rows]
	)
	return allocations + _spread_by_planned(excess, groups)


def _spread_by_planned(excess, groups):
	"""Split by planned quantity (evenly when none is planned) with cumulative rounding."""
	if not groups:
		frappe.throw(
			_("Packing needs {0} more pieces, but no complete garment set is on the Work Order.").format(
				excess
			)
		)
	weights = [flt(group[0].get("quantity")) for group in groups]
	if sum(weights) <= QTY_TOLERANCE:
		weights = [1] * len(groups)
	total = sum(weights)
	digits = 0 if excess.is_integer() else 6
	result = []
	cumulative = previous = 0
	for group, weight in zip(groups, weights, strict=True):
		cumulative += weight
		upto = flt(excess * cumulative / total, digits)
		if upto - previous > QTY_TOLERANCE:
			result.append((group, upto - previous))
		previous = upto
	return result


def _set_groups(rows):
	groups = {}
	for row in rows:
		key = tuple(sorted(json_object(row.set_combination).items()))
		groups.setdefault(key, []).append(row)
	return sorted(groups.values(), key=lambda values: min(flt(row.idx) for row in values))


def _allocate_set_rows(rows, requested, remaining_by_row=None):
	remaining_by_row = remaining_by_row or _remaining_by_row(rows)
	remaining = flt(requested)
	allocations = []
	for group_rows in _set_groups(rows):
		if len(group_rows) < 2:
			continue
		available = min(flt(remaining_by_row.get(_row_key(row))) for row in group_rows)
		quantity = min(remaining, available)
		if quantity > 0:
			allocations.append((group_rows, quantity))
			for row in group_rows:
				key = _row_key(row)
				remaining_by_row[key] = flt(remaining_by_row.get(key)) - quantity
			remaining -= quantity
		if remaining <= 0.001:
			break
	return allocations


def _allocate_rows(rows, requested, remaining_by_row=None):
	remaining_by_row = remaining_by_row or _remaining_by_row(rows)
	remaining = flt(requested)
	allocations = []
	for row in sorted(rows, key=lambda value: flt(value.idx)):
		key = _row_key(row)
		available = flt(remaining_by_row.get(key))
		quantity = min(remaining, available)
		if quantity > 0:
			allocations.append(([row], quantity))
			remaining_by_row[key] = available - quantity
			remaining -= quantity
		if remaining <= 0.001:
			break
	return allocations


def _row_key(row):
	return row.get("name") or id(row)


def _find_deliverable(deliverables, calculated_row):
	combination = json_object(calculated_row.set_combination)
	candidates = [
		row
		for row in deliverables
		if row.item_variant == calculated_row.item_variant and json_object(row.set_combination) == combination
	]
	if len(candidates) != 1:
		frappe.throw(
			_("Cannot identify the packing Deliverable for {0}.").format(calculated_row.item_variant)
		)
	return candidates[0]
