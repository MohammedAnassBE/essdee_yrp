# Copyright (c) 2023, Essdee and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document
from yrp.attribute_links import value as _attribute_value


class SDYRPLotwiseItemProfit(Document):
	def validate(self):
		from essdee_yrp.product_development.lotwise_costing import (
			calculate_all,
			validate_template_types,
		)

		validate_template_types(self)
		calculate_all(self)


@frappe.whitelist()
def get_lot_qty(lot: str, quantity_type: str | None = None, **kwargs) -> dict:
	"""Return the selected size-wise Lot quantity after enforcing read access."""

	# Preserve the F15 RPC argument name while keeping the Python builtin free.
	quantity_type = quantity_type or kwargs.get("type")
	allowed_fields = {"qty", "cut_qty", "final_qty"}
	if quantity_type not in allowed_fields:
		frappe.throw(_("Select a valid Lot quantity type."))

	lot_doc = frappe.get_doc("SD YRP Lot", lot)
	lot_doc.check_permission("read")
	return {
		_attribute_value(row.size): row.get(quantity_type)
		for row in lot_doc.planned_qty
		if _attribute_value(row.size)
	}


@frappe.whitelist()
def get_item_size_rates(item: str) -> list[dict]:
	"""Sellable sizes of an Item template with their SD YRP Sales Item Price rate."""
	from essdee_yrp.product_sales import get_sellable_variants

	frappe.get_doc('Item', item).check_permission("read")
	variants = get_sellable_variants(item)
	rates = dict(frappe.get_all(
		'SD YRP Sales Item Price',
		filters={"item_variant": ["in", [row.item for row in variants]]},
		fields=["item_variant", "rate"],
		as_list=True,
	)) if variants else {}
	return [{"size": row.size, "rate": rates.get(row.item) or 0} for row in variants]


LotwiseItemProfit = SDYRPLotwiseItemProfit
