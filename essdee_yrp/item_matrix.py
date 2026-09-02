"""Essdee item-matrix display normalization.

Stock and production documents keep one child row per exact Item Variant.
Their Vue editors use ``row_index`` separately to show every value of the
parent Item's primary attribute (normally Size) across one logical row.
"""

import json

import frappe

from yrp.stock.dimensions import get_dimension_fieldnames


def normalize_item_matrix_row_indexes(rows):
	"""Return rows grouped by logical item, excluding the primary attribute.

	The function changes only copied display indexes. It does not mutate saved
	child rows, quantities, references, or Stock Dimensions.
	"""
	dimension_fields = get_dimension_fieldnames()
	logical_indexes = {}
	normalized = []
	for position, source in enumerate(rows or []):
		row = frappe._dict(source if isinstance(source, dict) else source.as_dict())
		variant_name = row.get("item_variant") or row.get("item")
		if not variant_name:
			row.row_index = f"matrix-{position:04d}"
			normalized.append(row)
			continue

		variant = frappe.get_cached_doc("Item Variant", variant_name)
		parent_item = frappe.get_cached_doc("Item", variant.item)
		primary_attribute = parent_item.get("primary_attribute")
		attributes = tuple(
			sorted(
				(attribute.attribute, attribute.attribute_value)
				for attribute in (variant.get("attributes") or [])
				if attribute.attribute != primary_attribute
			)
		)
		dimensions = tuple(
			(fieldname, row.get(fieldname))
			for fieldname in dimension_fields
			if fieldname != "received_type"
		)
		key = (
			variant.item,
			attributes,
			_canonical_json(row.get("set_combination")),
			dimensions,
			# Stock Reconciliation stores the stock bucket warehouse on its
			# child row rather than as a configured Stock Dimension.  Keep it
			# as a grouping boundary even though the current Desk editor normally
			# fills every row from the header default.
			row.get("warehouse") or "",
			row.get("received_type") or "",
		)
		if key not in logical_indexes:
			logical_indexes[key] = len(logical_indexes)
		row.row_index = f"matrix-{logical_indexes[key]:04d}"
		normalized.append(row)
	return normalized


def _canonical_json(value):
	if not value:
		return "{}"
	if isinstance(value, str):
		value = frappe.parse_json(value)
	return json.dumps(value, sort_keys=True, separators=(",", ":"))
