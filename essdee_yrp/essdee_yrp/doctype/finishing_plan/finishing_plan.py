# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FinishingPlan(Document):
	pass


@frappe.whitelist()
def get_alternative_details(lot):
	from essdee_yrp.essdee_yrp.doctype.lot.lot import fetch_order_item_details

	frappe.get_doc("Lot", lot).check_permission("read")
	lot_dict = {}
	for alternative_lot in frappe.get_list(
		"Lot", filters={"transferred_lot": lot}, pluck="name"
	):
		lot_doc = frappe.get_doc("Lot", alternative_lot)
		lot_dict[alternative_lot] = {
			"item": lot_doc.item,
			"ipd": lot_doc.production_detail,
			"details": fetch_order_item_details(
				lot_doc.lot_order_details,
				lot_doc.production_detail,
			),
		}
	return lot_dict
