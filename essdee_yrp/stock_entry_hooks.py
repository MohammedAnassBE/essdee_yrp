"""Thin Stock Entry event adapter for Essdee-owned workflows."""

import frappe
from frappe import _
from frappe.utils import flt


_COMPLETION_PURPOSES = {"DC Completion", "GRN Completion"}


def _normalize_completion_row_indexes(doc):
	"""Keep every generated completion row visible in the base YRP Vue grid.

	Delivery Challan and Goods Received Note rows may carry string row indexes
	(``matrix-0001`` and similar), while Stock Entry Detail stores an Int.  The
	copy therefore coerces every source index to ``0``.  Base YRP's grouped item
	editor treats equal row indexes as one logical item and renders only the
	first parent Item from that group.  Completion entries favour completeness:
	each physical child row receives its own stable integer index.
	"""
	if doc.get("purpose") not in _COMPLETION_PURPOSES:
		return False

	rows = list(doc.get("items") or [])
	keys = [row.get("row_index") for row in rows]
	if len(set(keys)) == len(keys) and all(key is not None for key in keys):
		return False

	for index, row in enumerate(rows):
		row.row_index = index
	return True


def onload(doc, method=None):
	"""Repair legacy/generated draft presentation without writing on read."""
	changed = _normalize_completion_row_indexes(doc)
	changed = preserve_dynamic_packing_completion_piece_uom(doc) or changed
	changed = preserve_dynamic_packing_dispatch_piece_uom(doc) or changed
	if not changed:
		return

	from yrp.stock.save_stock_items import group_items_for_ui

	doc.set_onload("item_details", group_items_for_ui(doc.get("items") or [], "Stock Entry"))


def before_validate(doc, method=None):
	_normalize_completion_row_indexes(doc)

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


def validate(doc, method=None):
	"""Reapply Essdee transaction semantics after base Stock Entry validation."""
	del method
	preserve_dynamic_packing_completion_piece_uom(doc)
	preserve_dynamic_packing_dispatch_piece_uom(doc)


def preserve_dynamic_packing_completion_piece_uom(doc):
	"""Keep a current dynamic Packing GRN completion in physical Pieces.

	Base Stock Entry correctly derives ordinary transaction UOM from the Item
	Variant master. Dynamic packing version 2 is the scoped exception: boxes live
	exclusively in the GRN batch ledger, while its item and completion quantities
	are physical pieces. The exact linked GRN Item remains authoritative for item,
	stock UOM, and rate ownership.
	"""
	if not (
		doc.get("purpose") == "GRN Completion"
		and doc.get("against") == "Goods Received Note"
		and doc.get("against_id")
	):
		return False

	from essdee_yrp.dynamic_packing import is_dynamic_packing_grn

	grn = frappe.get_doc("Goods Received Note", doc.against_id)
	if not is_dynamic_packing_grn(grn):
		return False
	if not (grn.get("includes_packing") and grn.get("from_finishing")):
		return False

	piece_uom = frappe.db.get_value("Lot", grn.get("lot"), "packing_uom")
	if not piece_uom:
		frappe.throw(_("Packing UOM is required on Lot {0}.").format(grn.get("lot")))
	source_items = {row.name: row for row in grn.get("items") or []}
	changed = False
	for row in doc.get("items") or []:
		source = source_items.get(row.get("against_id_detail"))
		if not source:
			frappe.throw(
				_("Row {0}: linked Goods Received Note Item is invalid for {1}.").format(
					row.idx, grn.name
				)
			)
		if row.get("item") != source.get("item_variant"):
			frappe.throw(
				_("Row {0}: item does not match linked Goods Received Note Item {1}.").format(
					row.idx, source.name
				)
			)
		stock_uom = source.get("stock_uom") or piece_uom
		if stock_uom != piece_uom:
			frappe.throw(
				_(
					"Dynamic packing completion requires Lot packing UOM {0} to match "
					"stock UOM {1} for {2}."
				).format(piece_uom, stock_uom, row.item)
			)
		new_values = {
			"uom": piece_uom,
			"stock_uom": piece_uom,
			"conversion_factor": 1,
			"stock_qty": flt(row.qty),
			"amount": flt(row.qty) * flt(row.rate),
		}
		for fieldname, value in new_values.items():
			if row.get(fieldname) != value:
				row.set(fieldname, value)
				changed = True
	doc.total_amount = sum(flt(row.amount) for row in doc.get("items") or [])
	return changed


def preserve_dynamic_packing_dispatch_piece_uom(doc):
	"""Keep current dynamic batch dispatch quantities in physical Pieces.

	A dynamic packing batch stores boxes only in ``GRN Packing Batch``. Its Stock
	Entry rows are the batch's normalized physical stock quantities. Base Stock
	Entry validation may reapply the packed Item Variant's master transaction UOM,
	so this narrow post-validation adapter restores the Lot packing/stock UOM for
	Material Issues created by either approved Finishing dispatch route.
	"""
	if not (
		doc.get("purpose") == "Material Issue"
		and doc.get("against") in ("Finishing Plan", "Finishing Plan Dispatch")
		and doc.get("against_id")
		and doc.get("packing_batch_dispatch_json")
	):
		return False

	from yrp.utils import update_if_string_instance

	batches = update_if_string_instance(doc.packing_batch_dispatch_json) or []
	if not isinstance(batches, list):
		frappe.throw(_("Packing batch dispatch data must be a JSON list"))
	if not batches or any(
		flt(batch.get("packing_calculation_version")) < 2
		for batch in batches
		if isinstance(batch, dict)
	):
		return False
	if any(not isinstance(batch, dict) for batch in batches):
		frappe.throw(_("Each packing batch dispatch row must be an object"))

	expected_by_lot = {}
	uom_by_lot = {}
	for batch in batches:
		finishing_plan = batch.get("finishing_plan")
		if not finishing_plan and doc.against == "Finishing Plan":
			finishing_plan = doc.against_id
		if not finishing_plan:
			frappe.throw(_("Dynamic packing dispatch is missing its Finishing Plan"))
		lot = frappe.db.get_value("Finishing Plan", finishing_plan, "lot")
		if not lot:
			frappe.throw(_("Finishing Plan {0} has no Lot").format(finishing_plan))
		piece_uom = frappe.db.get_value("Lot", lot, "packing_uom")
		if not piece_uom:
			frappe.throw(_("Packing UOM is required on Lot {0}.").format(lot))
		stock_uom = batch.get("stock_uom") or piece_uom
		if stock_uom != piece_uom:
			frappe.throw(
				_(
					"Dynamic packing dispatch requires Lot packing UOM {0} to match "
					"batch stock UOM {1} for {2}."
				).format(piece_uom, stock_uom, lot)
			)
		if lot in uom_by_lot and uom_by_lot[lot] != piece_uom:
			frappe.throw(_("Dynamic packing dispatch has conflicting UOMs for Lot {0}").format(lot))
		uom_by_lot[lot] = piece_uom
		stock_quantities = update_if_string_instance(batch.get("stock_quantities")) or {}
		if not isinstance(stock_quantities, dict):
			frappe.throw(_("Packing batch stock quantities must be an object"))
		expected_by_lot[lot] = expected_by_lot.get(lot, 0) + sum(
			flt(quantity) for quantity in stock_quantities.values()
		)

	actual_by_lot = {}
	for row in doc.get("items") or []:
		if row.get("lot") not in uom_by_lot:
			frappe.throw(
				_("Row {0}: Lot {1} is not owned by this packing batch dispatch.").format(
					row.idx, row.get("lot") or ""
				)
			)
		actual_by_lot[row.lot] = actual_by_lot.get(row.lot, 0) + flt(row.qty)
	for lot, expected in expected_by_lot.items():
		if abs(flt(actual_by_lot.get(lot)) - flt(expected)) > 1e-6:
			frappe.throw(
				_(
					"Dynamic packing dispatch quantity for Lot {0} is {1}, expected {2}."
				).format(lot, flt(actual_by_lot.get(lot)), flt(expected))
			)

	changed = False
	for row in doc.get("items") or []:
		piece_uom = uom_by_lot[row.lot]
		new_values = {
			"uom": piece_uom,
			"stock_uom": piece_uom,
			"conversion_factor": 1,
			"stock_qty": flt(row.qty),
			"amount": flt(row.qty) * flt(row.rate),
		}
		for fieldname, value in new_values.items():
			if row.get(fieldname) != value:
				row.set(fieldname, value)
				changed = True
	return changed


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
