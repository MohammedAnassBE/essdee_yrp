# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

"""Essdee Cutting Plan adapter for actual fabric substitutions."""

from copy import deepcopy

import frappe
from frappe.utils import flt

from essdee_yrp.fabric_substitution import substitution_index


@frappe.whitelist()
def get_cloth1(cutting_plan):
	"""Compatibility route to the single migrated Generate implementation."""
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
		get_cloth1 as generate_cloth,
	)

	return generate_cloth(cutting_plan)


def expand_cutting_rows(rows, index):
	"""Pure row expansion used by Generate and unit tests.

	Required weight is a garment demand and must not change when one planned
	variant becomes several physical variants. It is distributed in the same
	proportion as terminal-process receipts, with the final row absorbing the
	3-decimal rounding remainder.
	"""
	expanded = []
	changed = 0
	for source in rows:
		row = source.as_dict() if hasattr(source, "as_dict") else dict(source)
		mapping = index.get(row.get("cloth_item_variant"))
		actual = [
			item for item in (mapping or {}).get("actual") or []
			if item.get("item_variant") and flt(item.get("received_qty")) > 0
		]
		if not actual:
			expanded.append(_clean_child_row(row))
			continue

		allocations = _split_required_weight(
			flt(row.get("required_weight")),
			[flt(item.get("received_qty")) for item in actual],
		)
		for item, required_weight in zip(actual, allocations):
			replacement = _clean_child_row(deepcopy(row))
			replacement.update({
				"cloth_item_variant": item["item_variant"],
				"dia": item.get("dia"),
				"colour": item.get("colour"),
				"required_weight": required_weight,
				# Generate is a requirement refresh. The existing base method also
				# resets received weight; Fetch Received Cloth remains authoritative.
				"weight": 0,
				"used_weight": 0,
				"balance_weight": 0,
			})
			expanded.append(replacement)
		changed += 1
	return expanded, changed


def _split_required_weight(required_weight, weights):
	required_weight = round(flt(required_weight), 3)
	total = sum(max(flt(weight), 0) for weight in weights)
	if not weights:
		return []
	if total <= 0:
		return [required_weight] + [0] * (len(weights) - 1)

	result = []
	allocated = 0.0
	for index, weight in enumerate(weights):
		if index == len(weights) - 1:
			quantity = round(required_weight - allocated, 3)
		else:
			quantity = round(required_weight * max(flt(weight), 0) / total, 3)
			allocated += quantity
		result.append(quantity)
	return result


def _clean_child_row(row):
	return {
		key: value
		for key, value in row.items()
		if key not in {
			"doctype", "name", "owner", "creation", "modified", "modified_by",
			"docstatus", "idx", "parent", "parentfield", "parenttype",
		}
	}
