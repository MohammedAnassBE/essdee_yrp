"""Calculate every Work Order input consumed by a packing GRN."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.dynamic_packing import is_dynamic_packing_grn
from essdee_yrp.fabric_grn import (
	_allocate_to_work_order_deliverables,
	populate_grn_deliverables,
)
from essdee_yrp.finishing.parsing import json_object
from essdee_yrp.garment_bom import calculate_essdee_accessory_bom
from yrp.stock.utils import get_stock_balance
from yrp.utils import get_variant_attr_details


QTY_TOLERANCE = 0.000001


def before_validate(grn, method=None):
	del method
	if not _is_packing_grn(grn):
		return
	work_order = frappe.get_cached_doc('YRP Work Order', grn.against_id)
	ipd = frappe.get_cached_doc('YRP Item Production Detail', work_order.production_detail)
	populate_grn_deliverables(
		grn, _calculate_packing_inputs(grn, work_order, ipd)
	)


def calculate_packing_consumption_plan(grn):
	"""Rebuild the complete packing input plan under the Work Order lock."""
	if not _is_packing_grn(grn):
		return []
	work_order = frappe.get_doc('YRP Work Order', grn.against_id)
	ipd = frappe.get_cached_doc('YRP Item Production Detail', work_order.production_detail)
	return _calculate_packing_inputs(grn, work_order, ipd)


def _calculate_packing_inputs(grn, work_order, ipd):
	garments = (
		_allocate_dynamic_consumed_garments(grn, work_order, ipd)
		if is_dynamic_packing_grn(grn)
		else _allocate_consumed_garments(grn, work_order, ipd)
	)
	accessories = _allocate_consumed_accessories(
		grn, work_order, ipd, garments
	)
	return [*garments, *accessories]


def _is_packing_grn(grn):
	return bool(
		grn.get("against") == 'YRP Work Order'
		and grn.get("against_id")
		and grn.get("includes_packing")
		and not grn.get("is_return")
		and not grn.get("is_rework")
		and not grn.get("additional_grn")
	)


def _is_legacy_packing_grn(grn):
	return bool(_is_packing_grn(grn) and not flt(grn.get("packing_calculation_version")))


def _allocate_dynamic_consumed_garments(grn, work_order, ipd):
	"""Allocate each batch colour/size to every available garment part.

	Dynamic packing stores physical boxes and ratios separately while the GRN
	output rows store their resulting piece quantities.  The batch is therefore
	the immutable colour identity; output rows alone are intentionally not used
	to guess which Work Order garment colour was packed.
	"""
	from yrp.stock.utils import get_conversion_factor
	from yrp.yrp.doctype.yrp_work_order.yrp_work_order import _stock_dimension_values

	calculated = list(work_order.get("work_order_calculated_items") or [])
	deliverables = list(work_order.get("deliverables") or [])
	attributes = {
		_row_key(row): get_variant_attr_details(row.item_variant)
		for row in calculated
	}
	remaining_by_row = {
		_row_key(row): max(flt(row.delivered_quantity) - flt(row.received_qty), 0)
		for row in calculated
	}
	outputs_by_size = _positive_outputs_by_size(grn, ipd)
	output_remaining = {
		row.name: flt(row.get("stock_qty") or row.get("quantity"))
		for rows in outputs_by_size.values()
		for row in rows
	}
	source_remaining = {}
	valuation_cache = {}
	result = []

	batches = list(grn.get("packing_batches") or [])
	if not batches:
		frappe.throw(_("A dynamic packing GRN requires at least one packing batch."))
	for batch in batches:
		colour = batch.get("colour")
		ratio = json_object(batch.get("ratio_json") or batch.get("ratio"))
		boxes = flt(batch.get("box_quantity"))
		for size, per_box in ratio.items():
			requested = boxes * flt(per_box)
			if requested <= 0:
				continue
			for output, output_quantity in _take_output_chunks(
				outputs_by_size, output_remaining, size, requested
			):
				candidates = [
					row
					for row in calculated
					if attributes[_row_key(row)].get(ipd.primary_item_attribute) == size
					and attributes[_row_key(row)].get(ipd.packing_attribute) == colour
					and flt(remaining_by_row.get(_row_key(row))) > QTY_TOLERANCE
				]
				if not candidates:
					frappe.throw(
						_(
							"Packing needs {0} delivered pieces for {1} / {2}, but none are available."
						).format(output_quantity, colour, size)
					)

				groups = [candidates]
				if ipd.is_set_item:
					by_part = defaultdict(list)
					for row in candidates:
						row_attributes = attributes[_row_key(row)]
						part = row_attributes.get(ipd.set_item_attribute) or json_object(
							row.set_combination
						).get("major_part")
						by_part[part or ""].append(row)
					groups = list(by_part.values())

				for group in groups:
					allocations = _allocate_rows(
						group, output_quantity, remaining_by_row
					)
					allocated = sum(quantity for _rows, quantity in allocations)
					if allocated + QTY_TOLERANCE < output_quantity:
						frappe.throw(
							_(
								"Packing needs {0} delivered pieces for {1} / {2}, but only {3} are available."
							).format(output_quantity, colour, size, allocated)
						)
					for rows, quantity in allocations:
						for calculated_row in rows:
							source = _find_deliverable(deliverables, calculated_row)
							conversion = get_conversion_factor(source.item_variant, source.uom)
							factor = flt(conversion.get("conversion_factor")) or 1
							if source.name not in source_remaining:
								source_remaining[source.name] = max(
									(
										flt(source.qty)
										- flt(source.pending_quantity)
										- flt(source.stock_update)
									)
									* factor,
									0,
								)
							if source_remaining[source.name] + QTY_TOLERANCE < quantity:
								frappe.throw(
									_(
										"Work Order input {0} has only {1} delivered, unconsumed stock available; packing needs {2}."
									).format(
										source.item_variant,
										source_remaining[source.name],
										quantity,
									)
								)
							source_remaining[source.name] -= quantity
							dimensions = _stock_dimension_values(work_order, source)
							valuation_key = (
								calculated_row.item_variant,
								tuple(sorted(dimensions.items())),
							)
							if valuation_key not in valuation_cache:
								_balance, valuation_cache[valuation_key] = get_stock_balance(
									calculated_row.item_variant,
									grn.from_warehouse,
									posting_date=grn.posting_date,
									posting_time=grn.posting_time,
									with_valuation_rate=True,
									**dimensions,
								)
							result.append(
								{
									"item_variant": calculated_row.item_variant,
									"goods_received_note_item": output.name,
									"received_item_variant": output.item_variant,
									"quantity": quantity / factor,
									"stock_qty": quantity,
									"uom": source.uom,
									"stock_uom": conversion.get("stock_uom") or source.uom,
									"conversion_factor": factor,
									"work_order_deliverable": source.name,
									"valuation_rate": valuation_cache[valuation_key],
									"set_combination": json_object(calculated_row.set_combination),
									"dimensions": dimensions,
								}
							)

	leftover = sum(max(flt(quantity), 0) for quantity in output_remaining.values())
	if leftover > QTY_TOLERANCE:
		frappe.throw(
			_("Packing batch ratios do not account for {0} received pieces.").format(
				leftover
			)
		)
	return result


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
			_("Packing batches require {0} more received pieces for size {1}.").format(
				remaining, size
			)
		)
	return chunks


def _allocate_consumed_accessories(grn, work_order, ipd, garment_plan):
	"""Recalculate exact packing BOM rows and map them to delivered WO inputs."""
	if not garment_plan:
		return []
	lot = frappe.get_cached_doc('SD YRP Lot', grn.get("lot") or work_order.lot)
	process_names = {work_order.process_name}
	if frappe.db.get_value('YRP Process', work_order.process_name, "is_group"):
		process_names.update(
			frappe.get_all(
				'YRP Process Details',
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
	from yrp.stock.utils import get_conversion_factor
	from yrp.yrp.doctype.yrp_work_order.yrp_work_order import _stock_dimension_values

	deliverables = list(work_order.get("deliverables") or [])
	calculated = list(work_order.get("work_order_calculated_items") or [])
	remaining_by_row = {
		_row_key(row): max(flt(row.delivered_quantity) - flt(row.received_qty), 0)
		for row in calculated
	}
	result = []

	for output in grn.get("items") or []:
		output_stock_qty = flt(output.get("stock_qty"))
		if output_stock_qty <= 0:
			continue
		size = get_variant_attr_details(output.item_variant).get(
			ipd.primary_item_attribute
		)
		if not size:
			frappe.throw(
				_("Packed item {0} has no {1} attribute.").format(
					output.item_variant, ipd.primary_item_attribute
				)
			)
		candidates = [
			row
			for row in calculated
			if get_variant_attr_details(row.item_variant).get(ipd.primary_item_attribute)
			== size
			and flt(remaining_by_row.get(_row_key(row))) > 0
		]
		allocations = (
			_allocate_set_rows(candidates, output_stock_qty, remaining_by_row)
			if ipd.is_set_item
			else _allocate_rows(candidates, output_stock_qty, remaining_by_row)
		)
		allocated_output = sum(
			quantity for _rows, quantity in allocations
		)
		if allocated_output + 0.001 < output_stock_qty:
			frappe.throw(
				_(
					"Packing needs {0} delivered pieces for {1}, but only {2} are available."
				).format(output_stock_qty, size, allocated_output)
			)

		for rows, quantity in allocations:
			for calculated_row in rows:
				source = _find_deliverable(deliverables, calculated_row)
				conversion = get_conversion_factor(source.item_variant, source.uom)
				factor = flt(conversion.get("conversion_factor")) or 1
				combination = json_object(calculated_row.set_combination)
				dimensions = _stock_dimension_values(work_order, source)
				_balance, valuation_rate = get_stock_balance(
					calculated_row.item_variant,
					grn.from_warehouse,
					posting_date=grn.posting_date,
					posting_time=grn.posting_time,
					with_valuation_rate=True,
					**dimensions,
				)
				result.append(
					{
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
						"valuation_rate": valuation_rate,
						"set_combination": combination,
						"dimensions": dimensions,
					}
				)
	return result


def _allocate_set_rows(rows, requested, remaining_by_row=None):
	remaining_by_row = remaining_by_row or {
		_row_key(row): max(flt(row.delivered_quantity) - flt(row.received_qty), 0)
		for row in rows
	}
	groups = {}
	for row in rows:
		key = tuple(sorted(json_object(row.set_combination).items()))
		groups.setdefault(key, []).append(row)
	remaining = flt(requested)
	allocations = []
	for group_rows in sorted(
		groups.values(), key=lambda values: min(flt(row.idx) for row in values)
	):
		if len(group_rows) < 2:
			continue
		available = min(
			flt(remaining_by_row.get(_row_key(row)))
			for row in group_rows
		)
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
	remaining_by_row = remaining_by_row or {
		_row_key(row): max(flt(row.delivered_quantity) - flt(row.received_qty), 0)
		for row in rows
	}
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
		if row.item_variant == calculated_row.item_variant
		and json_object(row.set_combination) == combination
	]
	if len(candidates) != 1:
		frappe.throw(
			_("Cannot identify the packing Deliverable for {0}.").format(
				calculated_row.item_variant
			)
		)
	return candidates[0]
