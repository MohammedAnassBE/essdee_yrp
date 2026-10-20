import frappe


@frappe.whitelist()
def get_item_filter_values(items):
	"""Expand Item filters using readable variants, including disabled ones."""
	frappe.has_permission("Item", "read", throw=True)
	items = list(dict.fromkeys(frappe.parse_json(items) if isinstance(items, str) else items))
	values = {item: [item] for item in items}
	if not items:
		return values
	for variant in frappe.get_list(
		"Item",
		filters={"variant_of": ["in", items]},
		fields=["name", "variant_of"],
		limit_page_length=0,
	):
		values[variant.variant_of].append(variant.name)
	return values
