"""Essdee business helpers over ERPNext's canonical Item Alternative master."""

import frappe


def get_alternative_items(item):
	if not item:
		return []
	forward = frappe.get_all(
		"Item Alternative", filters={"item_code": item}, pluck="alternative_item_code"
	)
	reverse = frappe.get_all(
		"Item Alternative",
		filters={"alternative_item_code": item, "two_way": 1},
		pluck="item_code",
	)
	return sorted({value for value in [*forward, *reverse] if value and value != item})
