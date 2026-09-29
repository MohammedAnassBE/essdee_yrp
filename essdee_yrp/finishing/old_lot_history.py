"""Single-source read model for Finishing Plan old-lot transfer history."""

import frappe
from frappe.utils import flt


def active_old_lot_transfer_rows(rows):
	rows = list(rows or [])
	lot_transfers = {row.lot_transfer for row in rows if row.lot_transfer}
	if not lot_transfers:
		return rows
	cancelled = set(
		frappe.get_all(
			'SD YRP Lot Transfer',
			filters={"name": ("in", list(lot_transfers)), "docstatus": 2},
			pluck="name",
		)
	)
	return [
		row
		for row in rows
		if not row.lot_transfer or row.lot_transfer not in cancelled
	]


def get_old_lot_received_rows(doc):
	"""Derive destination receipts from source-side Given history.

	Legacy destination rows are retained only when no equivalent source-side row
	exists, allowing migrated old and new transfers to coexist without doubling
	the OCR quantity.
	"""
	legacy_rows = active_old_lot_transfer_rows(
		doc.get("finishing_old_lot_received_items")
	)
	if not doc.get("name"):
		return legacy_rows

	given_rows = active_old_lot_transfer_rows(
		frappe.get_all(
			'SD YRP Finishing Plan Old Lot Given',
			filters={"destination_fp": doc.name},
			fields=[
				"parent as source_fp",
				"item_variant",
				"colour",
				"part",
				"set_combination",
				"size",
				"loose_piece_given",
				"loose_piece_set_given",
				"lot_transfer",
			],
		)
	)
	if not given_rows:
		return legacy_rows

	source_fps = {row.source_fp for row in given_rows}
	source_lots = {
		row.name: row.lot
		for row in frappe.get_all(
			'SD YRP Finishing Plan',
			filters={"name": ("in", list(source_fps))},
			fields=["name", "lot"],
		)
	}
	received_rows = [
		frappe._dict(
			source_fp=row.source_fp,
			source_lot=source_lots.get(row.source_fp),
			item_variant=row.item_variant,
			colour=row.colour,
			part=row.part,
			set_combination=row.set_combination,
			size=row.size,
			loose_piece_taken=row.loose_piece_given,
			loose_piece_set_taken=row.loose_piece_set_given,
			lot_transfer=row.lot_transfer,
		)
		for row in given_rows
	]
	derived_keys = {
		(row.lot_transfer, row.source_fp, row.item_variant, row.size)
		for row in received_rows
	}
	received_rows.extend(
		row
		for row in legacy_rows
		if (row.lot_transfer, row.source_fp, row.item_variant, row.size)
		not in derived_keys
	)
	return received_rows


def get_old_lot_source_balance(source, item_variant):
	loose_piece = sum(
		flt(row.return_qty)
		for row in source.get("finishing_plan_details") or []
		if row.item_variant == item_variant
	)
	loose_piece_set = sum(
		flt(row.pack_return_qty)
		for row in source.get("finishing_plan_details") or []
		if row.item_variant == item_variant
	)
	for row in active_old_lot_transfer_rows(
		source.get("finishing_old_lot_given_items")
	):
		if row.item_variant != item_variant:
			continue
		loose_piece -= flt(row.loose_piece_given)
		loose_piece_set -= flt(row.loose_piece_set_given)
	return max(loose_piece, 0), max(loose_piece_set, 0)
