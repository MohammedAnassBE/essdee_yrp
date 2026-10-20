import frappe
from frappe import _
from yrp import attribute_links as attribute_db
from yrp.attribute_links import value as _attribute_value
from yrp.utils import get_variant_attr_details
from yrp.yrp.doctype.yrp_item.yrp_item import (
	build_variant_attributes,
	get_or_create_variant,
	get_parent_item,
)

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_bundle_movement_ledger.sd_yrp_cut_bundle_movement_ledger import (
	check_dependent_stage_variant,
)


def get_loose_piece_stock_variant(doc, item_variant):
	"""Hold a packing voucher's stitched pieces at the packing unit as Loose Piece.

	Frappe 15 converts the IPD stitching-out variant to the IPD Settings Loose
	Piece stage (dependent attribute value) whenever packing stock reaches the
	packing unit: DC, DC Completion, finishing return and packing GRN issue.
	"""
	if not doc.get("includes_packing") or not item_variant:
		return item_variant
	production_detail = get_production_detail(doc)
	if not production_detail:
		return item_variant
	dependent_attribute, stitching_out_stage = attribute_db.get_value(
		"YRP Item Production Detail",
		production_detail,
		["dependent_attribute", "stiching_out_stage"],
	)
	stitching_out_stage = _attribute_value(stitching_out_stage)
	if not stitching_out_stage or not check_dependent_stage_variant(
		item_variant, dependent_attribute, stitching_out_stage
	):
		return item_variant
	loose_piece_stage = _attribute_value(
		frappe.db.get_single_value("SD YRP IPD Settings", "default_loose_piece_stage")
	)
	if not loose_piece_stage:
		frappe.throw(_("Set Default Loose Piece Stage in SD YRP IPD Settings."))
	loose_piece_variant = get_or_create_variant(
		get_parent_item(item_variant),
		build_variant_attributes(
			get_variant_attr_details(item_variant), loose_piece_stage, production_detail
		),
	)
	if doc.docstatus == 2 and not _voucher_posted(doc, loose_piece_variant):
		# Reverse a voucher posted before Loose Piece holding with its original variant.
		return item_variant
	return loose_piece_variant


def _voucher_posted(doc, item_variant):
	return bool(
		frappe.db.exists(
			"YRP Stock Ledger Entry",
			{"voucher_type": doc.doctype, "voucher_no": doc.name, "item": item_variant},
		)
	)


def get_production_detail(doc):
	if doc.get("production_detail"):
		return doc.production_detail
	if doc.doctype == "YRP Stock Entry" and doc.get("against") == "YRP Delivery Challan":
		return frappe.db.get_value("YRP Delivery Challan", doc.against_id, "production_detail")
	if doc.get("lot"):
		return attribute_db.get_value("SD YRP Lot", doc.lot, "production_detail")
	return None
