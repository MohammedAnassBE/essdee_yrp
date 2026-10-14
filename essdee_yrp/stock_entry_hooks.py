"""Thin Stock Entry event adapter for Essdee-owned workflows."""

import frappe
from frappe import _
from frappe.utils import flt
from yrp import attribute_links as attribute_db
from yrp.utils import update_if_string_instance


def onload(doc, method=None):
	"""Render physical children as logical rows with primary-attribute columns.

	The projection is deliberately built from copies.  Completion entries keep
	their exact saved children and source lineage, while Desk groups Size variants
	by parent Item, non-primary attributes, set combination, and Stock Dimensions.
	"""
	del method
	preserve_dynamic_packing_completion_piece_uom(doc)
	preserve_dynamic_packing_dispatch_piece_uom(doc)

	from yrp.stock.save_stock_items import group_items_for_ui

	from essdee_yrp.item_matrix import normalize_item_matrix_row_indexes

	doc.set_onload(
		"item_details",
		group_items_for_ui(
			normalize_item_matrix_row_indexes(doc.get("items") or []),
			"YRP Stock Entry",
		),
	)


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
		frappe.throw(_("Purpose {0} is not valid for a Cut Panel Movement").format(doc.purpose))


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
		and doc.get("against") == "YRP Goods Received Note"
		and doc.get("against_id")
	):
		return False

	from essdee_yrp.dynamic_packing import is_dynamic_packing_grn

	grn = frappe.get_doc("YRP Goods Received Note", doc.against_id)
	if not is_dynamic_packing_grn(grn) and not _is_mapped_size_wise_grn(grn):
		return False
	if not (grn.get("includes_packing") and grn.get("from_finishing")):
		return False

	piece_uom = attribute_db.get_value("SD YRP Lot", grn.get("lot"), "packing_uom")
	if not piece_uom:
		frappe.throw(_("Packing UOM is required on Lot {0}.").format(grn.get("lot")))
	source_items = {row.name: row for row in grn.get("items") or []}
	changed = False
	for row in doc.get("items") or []:
		source = source_items.get(row.get("against_id_detail"))
		if not source:
			frappe.throw(
				_("Row {0}: linked Goods Received Note Item is invalid for {1}.").format(row.idx, grn.name)
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
					"Dynamic packing completion requires Lot packing UOM {0} to match stock UOM {1} for {2}."
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


def _is_mapped_size_wise_grn(grn):
	if grn.get("against") != "YRP Work Order" or not grn.get("against_id"):
		return False
	production_detail = attribute_db.get_value("YRP Work Order", grn.against_id, "production_detail")
	if not production_detail:
		return False
	based_on_mapping, packing_mode = attribute_db.get_value(
		"YRP Item Production Detail",
		production_detail,
		["based_on_other_attribute_mapping", "packing_mode"],
	)
	return bool(based_on_mapping and packing_mode == "Size Wise Packing")


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
		and doc.get("against") in ("SD YRP Finishing Plan", "SD YRP Finishing Plan Dispatch")
		and doc.get("against_id")
	):
		return False

	batches = update_if_string_instance(doc.get("packing_batch_dispatch_json")) or []
	if not batches:
		return _preserve_mapped_size_wise_dispatch_piece_uom(doc)
	if not isinstance(batches, list):
		frappe.throw(_("Packing batch dispatch data must be a JSON list"))
	if any(not isinstance(batch, dict) for batch in batches):
		frappe.throw(_("Each packing batch dispatch row must be an object"))

	sources = _get_packing_dispatch_sources(doc, batches)
	dynamic_sources = [source for source in sources if source.version >= 2]
	if not dynamic_sources:
		return False
	expected_by_source = {}
	for source in dynamic_sources:
		key = (source.finishing_plan, source.lot)
		expected_by_source[key] = expected_by_source.get(key, 0) + source.quantity

	rows_to_restore = []
	actual_by_source = {}
	for row in doc.get("items") or []:
		plan, version = _get_dispatch_row_source(doc, row, sources)
		if flt(version) < 2:
			continue
		matching = [
			source
			for source in dynamic_sources
			if source.finishing_plan == plan and source.lot == row.get("lot")
		]
		if not matching:
			frappe.throw(_("Row {0}: dynamic packing source is invalid.").format(row.idx))
		key = (plan, row.get("lot"))
		actual_by_source[key] = actual_by_source.get(key, 0) + flt(row.qty)
		rows_to_restore.append((row, matching[0].piece_uom))

	for key, expected in expected_by_source.items():
		if abs(flt(actual_by_source.get(key)) - flt(expected)) > 1e-6:
			frappe.throw(
				_("Dynamic packing dispatch quantity for Lot {0} is {1}, expected {2}.").format(
					key[1], flt(actual_by_source.get(key)), flt(expected)
				)
			)

	return _restore_piece_uom(rows_to_restore)


def _preserve_mapped_size_wise_dispatch_piece_uom(doc):
	rows_to_restore = []
	config_by_plan = {}
	for row in doc.get("items") or []:
		plan = row.get("_packing_finishing_plan")
		if not plan and doc.against == "SD YRP Finishing Plan":
			plan = doc.against_id
		if not plan:
			continue
		if plan not in config_by_plan:
			production_detail, lot = attribute_db.get_value(
				"SD YRP Finishing Plan", plan, ["production_detail", "lot"]
			)
			based_on_mapping, packing_mode = attribute_db.get_value(
				"YRP Item Production Detail",
				production_detail,
				["based_on_other_attribute_mapping", "packing_mode"],
			)
			config_by_plan[plan] = (
				attribute_db.get_value("SD YRP Lot", lot, "packing_uom")
				if based_on_mapping and packing_mode == "Size Wise Packing"
				else None
			)
		if config_by_plan[plan]:
			rows_to_restore.append((row, config_by_plan[plan]))
	return _restore_piece_uom(rows_to_restore)


def _restore_piece_uom(rows):
	changed = False
	for row, piece_uom in rows:
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


def _get_packing_dispatch_sources(doc, batches):
	sources = []
	for batch in batches:
		finishing_plan = batch.get("finishing_plan")
		if not finishing_plan and doc.against == "SD YRP Finishing Plan":
			finishing_plan = doc.against_id
		if not finishing_plan:
			frappe.throw(_("Dynamic packing dispatch is missing its Finishing Plan"))
		lot = frappe.db.get_value("SD YRP Finishing Plan", finishing_plan, "lot")
		if not lot:
			frappe.throw(_("Finishing Plan {0} has no Lot").format(finishing_plan))
		piece_uom = attribute_db.get_value("SD YRP Lot", lot, "packing_uom")
		if not piece_uom:
			frappe.throw(_("Packing UOM is required on Lot {0}.").format(lot))
		stock_uom = batch.get("stock_uom") or piece_uom
		version = flt(batch.get("packing_calculation_version"))
		if version >= 2 and stock_uom != piece_uom:
			frappe.throw(
				_(
					"Dynamic packing dispatch requires Lot packing UOM {0} to match "
					"batch stock UOM {1} for {2}."
				).format(piece_uom, stock_uom, lot)
			)
		stock_quantities = update_if_string_instance(batch.get("stock_quantities")) or {}
		if not isinstance(stock_quantities, dict):
			frappe.throw(_("Packing batch stock quantities must be an object"))
		sources.append(
			frappe._dict(
				finishing_plan=finishing_plan,
				lot=lot,
				piece_uom=piece_uom,
				stock_uom=stock_uom,
				version=version,
				quantities=tuple(flt(quantity) for quantity in stock_quantities.values()),
				quantity=sum(flt(quantity) for quantity in stock_quantities.values()),
			)
		)
	return sources


def _get_dispatch_row_source(doc, row, sources):
	plan = row.get("_packing_finishing_plan")
	version = row.get("_packing_calculation_version")
	if not plan and doc.against == "SD YRP Finishing Plan":
		plan = doc.against_id
	matching = [
		source for source in sources if source.finishing_plan == plan and source.lot == row.get("lot")
	]
	if version is None and matching:
		versions = {
			source.version
			for source in matching
			if any(abs(flt(row.qty) - quantity) <= 1e-6 for quantity in source.quantities)
		}
		if len(versions) != 1:
			versions = {source.version for source in matching if source.stock_uom == row.get("uom")}
		if len(versions) == 1:
			version = versions.pop()
		elif len({source.version for source in matching}) == 1:
			version = matching[0].version
	if version is not None or plan:
		return plan, version

	matching = [source for source in sources if source.lot == row.get("lot")]
	plans = {source.finishing_plan for source in matching}
	versions = {source.version for source in matching}
	if len(plans) == 1 and len(versions) == 1:
		return plans.pop(), versions.pop()
	return plan, version


def before_submit(doc, method=None):
	if doc.against not in ("SD YRP Finishing Plan", "SD YRP Finishing Plan Dispatch"):
		return
	if doc.against == "SD YRP Finishing Plan Dispatch" and doc.purpose != "Material Issue":
		frappe.throw(_("Finishing Plan Dispatch requires a Material Issue Stock Entry"))
	if not frappe.db.exists(doc.against, doc.against_id):
		frappe.throw(_("{0} {1} does not exist").format(doc.against, doc.against_id))

	add_goods_value = frappe.db.get_single_value("YRP Stock Settings", "add_finishing_plan_goods_value")
	if doc.purpose == "Material Issue" and not add_goods_value:
		doc.total_amount = doc.additional_amount or 0


def on_submit(doc, method=None):
	from essdee_yrp.cutting.movement import apply_transaction
	from essdee_yrp.finishing.stock import apply_stock_entry

	apply_transaction(doc, cancelled=False)
	apply_stock_entry(doc, cancelled=False)
	sync_dc_completion_cutting_plan(doc)


def on_cancel(doc, method=None):
	from essdee_yrp.cutting.movement import apply_transaction
	from essdee_yrp.finishing.stock import apply_stock_entry

	apply_transaction(doc, cancelled=True)
	apply_stock_entry(doc, cancelled=True)
	sync_dc_completion_cutting_plan(doc)


def sync_dc_completion_cutting_plan(doc):
	if not (
		doc.get("purpose") == "DC Completion"
		and doc.get("against") == "YRP Delivery Challan"
		and doc.get("against_id")
	):
		return
	delivery_challan = frappe.get_doc("YRP Delivery Challan", doc.against_id)
	from essdee_yrp.delivery_challan_hooks import sync_cutting_plan_received_cloth

	sync_cutting_plan_received_cloth(delivery_challan)
