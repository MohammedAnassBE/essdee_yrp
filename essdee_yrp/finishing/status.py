"""Finishing Plan dispatch totals, audit trail, and automatic status rules."""

import frappe
from frappe.utils import flt

from essdee_yrp.finishing.packing import get_finishing_packing_summary
from yrp.utils import get_variant_attr_details


AUTO_FP_STATUSES = (
	"",
	"Planned",
	"Partially Received",
	"Ready to Pack",
	"Partially Dispatched",
	"Dispatched",
	"Fully Dispatched",
)
FULLY_DISPATCHED_PCT = 97.0


def get_set_item_parts_count(finishing_doc):
	ipd_name = finishing_doc.production_detail or frappe.get_value(
		'SD YRP Lot', finishing_doc.lot, "production_detail"
	)
	if not ipd_name:
		return 1

	ipd_doc = frappe.get_cached_doc('YRP Item Production Detail', ipd_name)
	if not ipd_doc.is_set_item:
		return 1

	parts = {
		row.set_item_attribute_value
		for row in ipd_doc.get("set_item_combination_details") or []
		if row.set_item_attribute_value
	}
	if parts:
		return len(parts)

	if ipd_doc.set_item_attribute:
		for row in finishing_doc.get("finishing_plan_details") or []:
			part = get_variant_attr_details(row.item_variant).get(ipd_doc.set_item_attribute)
			if part:
				parts.add(part)
	return len(parts) or 1


def get_finishing_plan_total_cutting(finishing_doc):
	total_cutting = sum(
		flt(row.cutting_qty)
		for row in finishing_doc.get("finishing_plan_details") or []
	)
	if total_cutting or not finishing_doc.work_order:
		return total_cutting

	return flt(
		frappe.db.sql(
			"""
				SELECT SUM(quantity)
				FROM `tabYRP Work Order Calculated Item`
				WHERE parent = %s
			""",
			finishing_doc.work_order,
		)[0][0]
	)


def get_finishing_dispatch_totals(finishing_doc):
	if isinstance(finishing_doc, str):
		finishing_doc = frappe.get_doc('SD YRP Finishing Plan', finishing_doc)

	total_cutting = get_finishing_plan_total_cutting(finishing_doc)
	packing_summary = get_finishing_packing_summary(finishing_doc)
	if packing_summary.dynamic_ratio_packing:
		total_dispatched_pieces = flt(packing_summary.total_dispatched)
	else:
		pieces_per_box = flt(finishing_doc.pieces_per_box)
		set_item_parts_count = get_set_item_parts_count(finishing_doc)
		total_dispatched_pieces = sum(
			flt(row.dispatched) * pieces_per_box * set_item_parts_count
			for row in finishing_doc.get("finishing_plan_grn_details") or []
		)

	return frappe._dict(
		{
			"total_cutting": total_cutting,
			"total_dispatched_pieces": total_dispatched_pieces,
			"dispatch_percentage": (
				(total_dispatched_pieces / total_cutting) * 100 if total_cutting else 0
			),
		}
	)


def record_finishing_dispatch_log(
	finishing_doc,
	stock_entry,
	dispatch_boxes,
	source_doctype=None,
	source_name=None,
	dispatch_pieces=None,
):
	if not frappe.get_meta('SD YRP Finishing Plan').has_field("finishing_plan_dispatch_logs"):
		return
	if flt(dispatch_boxes) <= 0:
		return

	source_doctype = source_doctype or stock_entry.against
	source_name = source_name or stock_entry.against_id
	if dispatch_pieces is None:
		dispatch_pieces = (
			flt(dispatch_boxes)
			* flt(finishing_doc.pieces_per_box)
			* get_set_item_parts_count(finishing_doc)
		)
	else:
		dispatch_pieces = flt(dispatch_pieces)

	totals = get_finishing_dispatch_totals(finishing_doc)
	previous_dispatched = max(flt(totals.total_dispatched_pieces) - dispatch_pieces, 0)
	previous_percentage = (
		(previous_dispatched / flt(totals.total_cutting)) * 100
		if totals.total_cutting
		else 0
	)
	log_data = {
		"stock_entry": stock_entry.name,
		"source_doctype": source_doctype,
		"source_name": source_name,
		"posting_date": stock_entry.posting_date,
		"posting_time": stock_entry.posting_time,
		"dispatch_boxes": dispatch_boxes,
		"dispatch_pieces": dispatch_pieces,
		"total_dispatched_pieces_after": totals.total_dispatched_pieces,
		"cutting_qty": totals.total_cutting,
		"dispatch_percentage_before": previous_percentage,
		"dispatch_percentage_after": totals.dispatch_percentage,
		"cancelled": 0,
	}

	for row in finishing_doc.get("finishing_plan_dispatch_logs") or []:
		if (
			row.stock_entry == stock_entry.name
			and row.source_doctype == source_doctype
			and row.source_name == source_name
		):
			row.update(log_data)
			return
	finishing_doc.append("finishing_plan_dispatch_logs", log_data)


def cancel_finishing_dispatch_log(finishing_doc, stock_entry_name):
	if not frappe.get_meta('SD YRP Finishing Plan').has_field("finishing_plan_dispatch_logs"):
		return
	for row in finishing_doc.get("finishing_plan_dispatch_logs") or []:
		if row.stock_entry == stock_entry_name:
			row.cancelled = 1


def compute_received_status(finishing_doc):
	if isinstance(finishing_doc, str):
		finishing_doc = frappe.get_doc('SD YRP Finishing Plan', finishing_doc)

	total_cutting = get_finishing_plan_total_cutting(finishing_doc)
	if not total_cutting:
		return None

	rows = finishing_doc.get("finishing_plan_details") or []
	total_received = sum(flt(row.delivered_quantity) for row in rows)
	total_dc_qty = sum(flt(row.dc_qty) for row in rows)
	total_dispatched = get_finishing_dispatch_totals(
		finishing_doc
	).total_dispatched_pieces
	settings = frappe.get_cached_doc('SD YRP MRP Settings')

	if total_dispatched > 0:
		dispatch_percentage = (total_dispatched / total_cutting) * 100
		dispatch_threshold = flt(
			getattr(settings, "partially_dispatched_percentage", None)
		) or 90
		if dispatch_percentage < dispatch_threshold:
			return "Partially Dispatched"
		if dispatch_percentage > FULLY_DISPATCHED_PCT:
			unaccountable = get_unaccountable_quantity(finishing_doc, total_dispatched)
			if abs(unaccountable) < 1e-6:
				return "Fully Dispatched"
		return "Dispatched"

	total_received = max(total_received, total_dc_qty)
	if not total_received:
		return None
	received_percentage = (total_received / total_cutting) * 100
	received_threshold = flt(
		getattr(settings, "partial_received_percentage", None)
	) or 50
	return (
		"Ready to Pack"
		if received_percentage >= received_threshold
		else "Partially Received"
	)


def apply_auto_fp_status(finishing_doc):
	new_status = compute_received_status(finishing_doc)
	if new_status and (finishing_doc.fp_status or "") in AUTO_FP_STATUSES:
		finishing_doc.fp_status = new_status


def get_unaccountable_quantity(finishing_doc, dispatched_pieces=None):
	"""Compute the aggregate OCR balance without coupling Stock Entry to its UI.

	This is the sum-equivalent of the F15 part/colour/size OCR matrix.  The UI can
	build the detailed matrix separately; automatic status needs only this total.
	"""
	rows = finishing_doc.get("finishing_plan_details") or []
	inward = sum(
		flt(row.delivered_quantity)
		+ flt(row.lot_transferred)
		+ flt(row.ironing_excess)
		for row in rows
	)
	transferred = sum(flt(row.transferred_qty) for row in rows)
	rejected = sum(flt(row.rejected_qty) for row in rows)
	loose_piece = sum(flt(row.return_qty) for row in rows)
	loose_piece_set = sum(flt(row.pack_return_qty) for row in rows)

	for row in finishing_doc.get("finishing_plan_reworked_details") or []:
		rejected += flt(row.rejected_qty)
		# Rework still outstanding is part of the OCR pending quantity.
		transferred += max(
			flt(row.quantity) - flt(row.reworked_quantity) - flt(row.rejected_qty),
			0,
		)

	for row in finishing_doc.get("finishing_old_lot_given_items") or []:
		loose_piece -= flt(row.loose_piece_given)
		loose_piece_set -= flt(row.loose_piece_set_given)
	for row in finishing_doc.get("finishing_old_lot_received_items") or []:
		loose_piece += flt(row.loose_piece_taken)
		loose_piece_set += flt(row.loose_piece_set_taken)

	if dispatched_pieces is None:
		dispatched_pieces = get_finishing_dispatch_totals(
			finishing_doc
		).total_dispatched_pieces
	return (
		inward
		- flt(dispatched_pieces)
		- rejected
		- loose_piece
		- loose_piece_set
		- transferred
	)
