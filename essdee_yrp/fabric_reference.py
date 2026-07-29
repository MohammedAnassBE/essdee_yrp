"""Route-allocation helpers for grouped fabric Work Order child rows."""

import json

import frappe
from frappe.utils import flt


def _qty(value):
	return round(flt(value), 3)


def get_reference_allocations(row, total_qty=None):
	"""Return {reference Item Variant: qty}, with legacy single-link fallback."""
	raw = row.get("fabric_reference_allocations")
	if isinstance(raw, str):
		try:
			raw = frappe.parse_json(raw)
		except (TypeError, ValueError):
			raw = None

	allocations = {}
	if isinstance(raw, dict):
		for reference, qty in raw.items():
			if reference and flt(qty):
				allocations[str(reference)] = (
					allocations.get(str(reference), 0) + flt(qty)
				)
	elif isinstance(raw, list):
		for allocation in raw:
			if not isinstance(allocation, dict):
				continue
			reference = allocation.get("reference_item_variant")
			qty = flt(allocation.get("qty"))
			if reference and qty:
				allocations[str(reference)] = allocations.get(str(reference), 0) + qty

	if allocations:
		return allocations

	reference = row.get("fabric_reference_variant")
	if reference:
		return {str(reference): flt(total_qty if total_qty is not None else row.get("qty"))}
	return {}


def normalise_reference_allocations(allocations, total_qty):
	"""Round allocations to 3dp while keeping their sum equal to the row qty."""
	total_qty = _qty(total_qty)
	rows = [
		(reference, _qty(qty))
		for reference, qty in (allocations or {}).items()
		if reference and flt(qty)
	]
	if not rows:
		return {}

	delta = _qty(total_qty - sum(qty for _reference, qty in rows))
	if delta:
		reference, qty = rows[-1]
		rows[-1] = (reference, _qty(qty + delta))
	return {reference: qty for reference, qty in rows if qty}


def serialise_reference_allocations(allocations, total_qty):
	normalised = normalise_reference_allocations(allocations, total_qty)
	if not normalised:
		return None
	return json.dumps(normalised, separators=(",", ":"), ensure_ascii=False)


def scale_reference_allocations(allocations, actual_qty):
	"""Split an actual receipt proportionally across its stored route plan."""
	actual_qty = _qty(actual_qty)
	weights = [
		(reference, flt(qty))
		for reference, qty in (allocations or {}).items()
		if reference and flt(qty) > 0
	]
	total_weight = sum(qty for _reference, qty in weights)
	if not weights or total_weight <= 0:
		return {}

	result = {}
	allocated = 0.0
	for index, (reference, weight) in enumerate(weights):
		if index == len(weights) - 1:
			qty = _qty(actual_qty - allocated)
		else:
			qty = _qty(actual_qty * weight / total_weight)
			allocated += qty
		if qty:
			result[reference] = qty
	return result
