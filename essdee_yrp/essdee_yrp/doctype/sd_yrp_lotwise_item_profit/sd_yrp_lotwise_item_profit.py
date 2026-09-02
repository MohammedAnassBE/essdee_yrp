# Copyright (c) 2023, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SDYRPLotwiseItemProfit(Document):
	pass


@frappe.whitelist()
def get_lot_qty(lot: str, quantity_type: str | None = None, **kwargs) -> dict:
	"""Return the selected size-wise Lot quantity after enforcing read access."""

	# Preserve the F15 RPC argument name while keeping the Python builtin free.
	quantity_type = quantity_type or kwargs.get("type")
	allowed_fields = {"qty", "cut_qty", "final_qty"}
	if quantity_type not in allowed_fields:
		frappe.throw(_("Select a valid Lot quantity type."))

	lot_doc = frappe.get_doc('SD YRP Lot', lot)
	lot_doc.check_permission("read")
	return {
		row.size: row.get(quantity_type)
		for row in lot_doc.planned_qty
		if row.size
	}


LotwiseItemProfit = SDYRPLotwiseItemProfit
