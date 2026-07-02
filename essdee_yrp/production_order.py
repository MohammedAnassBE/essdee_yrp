import frappe

from yrp.yrp.doctype.item.item import get_attribute_details


@frappe.whitelist()
def get_lot_ordered_details(production_order):
	"""Lot-wise ordered quantities for the Production Order form view.

	Replicates F15 production_api's PO "Lotwise Ordered Detail" section:
	groups `production_ordered_details` rows by Lot, then by the variant's
	primary attribute value (size). On base yrp the child rows carry a
	generic dynamic reference (`reference_doctype`/`reference_name`) — only
	rows referencing a Lot are shown here.
	"""
	doc = frappe.get_doc("Production Order", production_order)
	doc.check_permission("read")

	rows = [
		row
		for row in doc.production_ordered_details or []
		if row.reference_doctype == "Lot" and row.reference_name and row.item_variant
	]

	primary_values = []
	lot_wise_detail = {}
	attr_cache = {}

	for row in rows:
		variant = frappe.get_cached_doc("Item Variant", row.item_variant)
		if variant.item not in attr_cache:
			attr_cache[variant.item] = get_attribute_details(variant.item)
		attr_details = attr_cache[variant.item]
		primary_attribute = attr_details.get("primary_attribute")

		for value in attr_details.get("primary_attribute_values") or []:
			if value not in primary_values:
				primary_values.append(value)

		for attr in variant.get("attributes") or []:
			if attr.attribute == primary_attribute:
				size = attr.attribute_value
				if not size:
					break
				lot_wise_detail.setdefault(row.reference_name, {})
				lot_wise_detail[row.reference_name].setdefault(size, {"qty": 0})
				lot_wise_detail[row.reference_name][size]["qty"] += row.quantity or 0
				break

	return {"primary_values": primary_values, "ordered": lot_wise_detail}
