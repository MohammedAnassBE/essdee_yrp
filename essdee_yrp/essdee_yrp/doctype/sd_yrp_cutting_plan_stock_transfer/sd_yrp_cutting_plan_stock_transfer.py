# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SDYRPCuttingPlanStockTransfer(Document):
	pass


def on_doctype_update():
	"""A stock transaction belongs to one Cutting Plan at most."""
	frappe.db.add_unique(
		"SD YRP Cutting Plan Stock Transfer",
		["against", "against_id"],
		constraint_name="uniq_cutting_plan_stock_transfer",
	)
