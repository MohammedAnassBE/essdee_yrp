from copy import deepcopy

from frappe.utils import flt


def expand_cutting_rows(rows, index):
	"""Split cloth demand across actual receipts without changing its total."""
	expanded = []
	changed = 0
	for source in rows:
		row = source.as_dict() if hasattr(source, "as_dict") else dict(source)
		row = _clean_child_row(row)
		planned = row.get("cloth_item_variant")
		mapping = index.get(planned) or {}
		actual = [
			item for item in mapping.get("actual") or []
			if item.get("item_variant") and flt(item.get("received_qty")) > 0
		]
		if row.get("accessory") or not actual or (len(actual) == 1 and actual[0]["item_variant"] == planned):
			expanded.append(row)
			continue
		allocations = split_required_weight(
			row.get("required_weight"), [item["received_qty"] for item in actual]
		)
		for item, required_weight in zip(actual, allocations, strict=True):
			replacement = deepcopy(row)
			replacement.update({
				"cloth_item_variant": item["item_variant"],
				"dia": item.get("dia"),
				"required_weight": required_weight,
				"weight": 0,
				"used_weight": 0,
				"balance_weight": 0,
			})
			expanded.append(replacement)
		changed += 1
	return _merge_rows(expanded), changed


def _merge_rows(rows):
	"""Combine matching demand, retaining first position and resetting receipts."""
	merged = {}
	required_weights = {}
	for row in rows:
		key = tuple(row.get(field) for field in ("cloth_item_variant", "cloth_type", "colour", "dia"))
		if key in merged:
			required_weights[key] = (
				required_weights.get(key, flt(merged[key].get("required_weight")))
				+ flt(row.get("required_weight"))
			)
		else:
			merged[key] = row
	for key, required_weight in required_weights.items():
		merged[key].update(required_weight=round(required_weight, 3), weight=0, used_weight=0, balance_weight=0)
	return list(merged.values())


def split_required_weight(required_weight, weights):
	"""Allocate demand to three decimals, assigning the remainder last."""
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
