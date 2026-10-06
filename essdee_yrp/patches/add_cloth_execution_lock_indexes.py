import frappe


def execute():
	frappe.db.add_index(
		"YRP Work Order",
		["lot", "process_name"],
		"cloth_execution_lot_process",
	)
	frappe.db.add_index(
		"YRP Goods Received Note",
		["against_id", "against", "docstatus"],
		"cloth_execution_against",
	)
