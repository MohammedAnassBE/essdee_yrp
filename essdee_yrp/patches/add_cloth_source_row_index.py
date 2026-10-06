import frappe


def execute():
	frappe.db.add_index(
		"YRP Work Order Deliverables",
		["source_grn_item", "parent"],
		"cloth_source_grn_item",
	)
