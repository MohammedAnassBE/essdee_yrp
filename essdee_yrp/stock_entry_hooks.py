"""Thin Stock Entry event adapter for Essdee-owned workflows."""

import frappe
from frappe import _


def before_validate(doc, method=None):
	from essdee_yrp.cutting.movement import (
		set_completion_cut_panel_movement,
		validate_transaction_link,
	)

	set_completion_cut_panel_movement(doc)
	validate_transaction_link(doc)
	if doc.get("cut_panel_movement") and doc.purpose not in (
		"Send to Warehouse",
		"Receive at Warehouse",
		"DC Completion",
		"GRN Completion",
	):
		frappe.throw(
			_("Purpose {0} is not valid for a Cut Panel Movement").format(doc.purpose)
		)


def before_submit(doc, method=None):
	if doc.against not in ("Finishing Plan", "Finishing Plan Dispatch"):
		return
	if doc.against == "Finishing Plan Dispatch" and doc.purpose != "Material Issue":
		frappe.throw(_("Finishing Plan Dispatch requires a Material Issue Stock Entry"))
	if not frappe.db.exists(doc.against, doc.against_id):
		frappe.throw(_("{0} {1} does not exist").format(doc.against, doc.against_id))

	add_goods_value = frappe.db.get_single_value(
		"YRP Stock Settings", "add_finishing_plan_goods_value"
	)
	if doc.purpose == "Material Issue" and not add_goods_value:
		doc.total_amount = doc.additional_amount or 0


def on_submit(doc, method=None):
	from essdee_yrp.cutting.movement import apply_transaction
	from essdee_yrp.finishing.stock import apply_stock_entry

	apply_transaction(doc, cancelled=False)
	apply_stock_entry(doc, cancelled=False)


def on_cancel(doc, method=None):
	from essdee_yrp.cutting.movement import apply_transaction
	from essdee_yrp.finishing.stock import apply_stock_entry

	apply_transaction(doc, cancelled=True)
	apply_stock_entry(doc, cancelled=True)
