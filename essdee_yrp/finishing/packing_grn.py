"""Calculate the garment stock consumed by a legacy packing GRN."""

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_grn import _stock_uom_values
from essdee_yrp.finishing.parsing import json_object
from yrp.stock.utils import get_stock_balance
from yrp.utils import get_variant_attr_details


def before_validate(grn, method=None):
	del method
	if not _is_legacy_packing_grn(grn):
		return
	work_order = frappe.get_cached_doc("Work Order", grn.against_id)
	ipd = frappe.get_cached_doc("Item Production Detail", work_order.production_detail)
	consumed = _allocate_consumed_garments(grn, work_order, ipd)
	grn.set("grn_deliverables", consumed)


def _is_legacy_packing_grn(grn):
	return bool(
		grn.get("against") == "Work Order"
		and grn.get("against_id")
		and grn.get("includes_packing")
		and not grn.get("is_return")
		and not grn.get("is_rework")
		and not grn.get("additional_grn")
		and not flt(grn.get("packing_calculation_version"))
	)


def _allocate_consumed_garments(grn, work_order, ipd):
	default_received_type = frappe.db.get_single_value(
		"YRP Stock Settings", "default_received_type"
	)
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
				combination = json_object(calculated_row.set_combination)
				dimensions = {
					"lot": source.get("lot") or work_order.get("lot"),
					"received_type": source.get("received_type")
					or default_received_type,
				}
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
						"quantity": quantity,
						"uom": source.uom,
						"work_order_deliverable": source.name,
						"lot": dimensions["lot"],
						"received_type": dimensions["received_type"],
						"valuation_rate": valuation_rate,
						"set_combination": combination,
						"stock_dimensions": dimensions,
						**_stock_uom_values(
							calculated_row.item_variant, source.uom, quantity
						),
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
