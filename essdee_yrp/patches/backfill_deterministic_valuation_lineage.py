"""Backfill only historical valuation links that can be proved exactly.

Multi-output legacy GRNs and historical Work Order-close allocations are left
for explicit review. This patch never guesses how material value was split.
"""

from collections import defaultdict

import frappe
from frappe.utils import flt, get_datetime


READINESS_REVIEW_KEYS = {
	"contract_missing",
	"wholly_unmapped_grn_deliverables",
	"partially_mapped_grn_deliverables",
	"ambiguous_multi_output_unmapped_rows",
	"unmapped_grn_deliverables",
	"grn_deliverables_missing_work_order_deliverable",
	"grn_deliverables_missing_consumption_sle",
	"grn_deliverables_missing_output_sle",
	"unpaired_active_lot_transfer_sles",
	"invalid_goods_received_note_item_links",
	"invalid_consumption_sle_links",
	"invalid_output_receipt_sle_links",
}


def execute():
	if not _contract_available():
		return
	backfill_deterministic_valuation_lineage()


def backfill_deterministic_valuation_lineage():
	"""Run the idempotent post-load backfill and return its readiness report."""
	if not _contract_available():
		return {"contract_missing": 1}
	_pair_lot_transfer_sles()
	_backfill_single_output_grns()
	readiness = get_valuation_lineage_readiness()
	if _readiness_needs_review(readiness):
		frappe.log_error(
			title="Essdee valuation lineage needs review",
			message=frappe.as_json(readiness, indent=2),
		)
	return readiness


def _readiness_needs_review(readiness):
	return any(flt(readiness.get(key)) for key in READINESS_REVIEW_KEYS)


def _contract_available():
	return bool(
		frappe.db.exists("DocType", "Stock Valuation Production Link")
		and frappe.db.has_column("Stock Ledger Entry", "paired_stock_ledger_entry")
		and frappe.db.has_column("YRP GRN Deliverable", "goods_received_note_item")
	)


def _pair_lot_transfer_sles():
	rows = frappe.get_all(
		"Stock Ledger Entry",
		filters={
			"voucher_type": "Lot Transfer",
			"is_cancelled": 0,
			"paired_stock_ledger_entry": ["is", "not set"],
		},
		fields=["name", "voucher_no", "voucher_detail_no", "item", "warehouse", "qty"],
		order_by="voucher_no, voucher_detail_no, creation, name",
		limit_page_length=0,
	)
	groups = defaultdict(list)
	for row in rows:
		groups[(row.voucher_no, row.voucher_detail_no)].append(row)
	for group in groups.values():
		outgoing = [row for row in group if flt(row.qty) < 0]
		incoming = [row for row in group if flt(row.qty) > 0]
		if len(outgoing) != 1 or len(incoming) != 1:
			continue
		if (
			outgoing[0].item != incoming[0].item
			or outgoing[0].warehouse != incoming[0].warehouse
			or abs(abs(flt(outgoing[0].qty)) - flt(incoming[0].qty)) > 0.000001
		):
			continue
		frappe.db.set_value(
			"Stock Ledger Entry",
			outgoing[0].name,
			"paired_stock_ledger_entry",
			incoming[0].name,
			update_modified=False,
		)
		frappe.db.set_value(
			"Stock Ledger Entry",
			incoming[0].name,
			"paired_stock_ledger_entry",
			outgoing[0].name,
			update_modified=False,
		)


def _backfill_single_output_grns():
	from yrp.stock.dimensions import get_dimension_fieldnames
	from yrp.yrp_stock.doctype.stock_valuation_adjustment.stock_valuation_adjustment import (
		register_production_links,
	)

	dimension_fields = get_dimension_fieldnames()
	for grn in frappe.get_all(
		"Goods Received Note",
		filters={
			"docstatus": 1,
			"against": "Work Order",
			"is_return": 0,
			"is_rework": 0,
		},
		fields=["name", "against_id"],
		limit_page_length=0,
	):
		grn_name = grn.name
		outputs = frappe.get_all(
			"Goods Received Note Item",
			filters={"parent": grn_name, "parentfield": "items"},
			fields=["name", "item_variant"],
			limit_page_length=0,
		)
		if len(outputs) != 1:
			continue
		output = outputs[0]
		output_sles = frappe.get_all(
			"Stock Ledger Entry",
			filters={
				"voucher_type": "Goods Received Note",
				"voucher_no": grn_name,
				"voucher_detail_no": output.name,
				"item": output.item_variant,
				"qty": [">", 0],
				"is_cancelled": 0,
			},
			fields=["name", "posting_datetime", "creation"],
			limit_page_length=0,
		)
		if len(output_sles) != 1:
			continue
		output_sle = output_sles[0]

		links = []
		children = frappe.get_all(
			"YRP GRN Deliverable",
			filters={
				"parent": grn_name,
				"parenttype": "Goods Received Note",
				"parentfield": "grn_deliverables",
			},
			fields=[
				"name",
				"item_variant",
				"uom",
				"stock_qty",
				"consumption_sle",
				"lot",
				"received_type",
				"set_combination",
				"stock_dimensions",
			],
			order_by="idx",
			limit_page_length=0,
		)
		for child in children:
			work_order_deliverable = _resolve_exact_work_order_deliverable(
				grn.against_id, child, dimension_fields
			)
			if not work_order_deliverable:
				# A mapped cancellation must reverse the exact Work Order bookkeeping
				# row as well as the stock. Do not activate a partial historical route.
				continue
			consumption = _get_owned_consumption_sle(
				grn_name, child, dimension_fields
			)
			if not consumption:
				continue
			consumption_sle = consumption.name
			if not _has_base_compatible_production_posting_order(
				output_sle, consumption
			):
				continue
			stock_dimensions = {
				fieldname: consumption.get(fieldname) for fieldname in dimension_fields
			}
			material_value = abs(flt(consumption.stock_value_difference))
			stock_qty = flt(child.stock_qty) or abs(flt(consumption.qty))
			frappe.db.set_value(
				"YRP GRN Deliverable",
				child.name,
				{
					"goods_received_note_item": output.name,
					"received_item_variant": output.item_variant,
					"work_order_deliverable": work_order_deliverable,
					"valuation_rate": material_value / stock_qty if stock_qty else 0,
					"material_value": material_value,
					"consumption_sle": consumption_sle,
					"output_receipt_sle": output_sle.name,
					"stock_dimensions": frappe.as_json(stock_dimensions),
				},
				update_modified=False,
			)
			links.append(
				{
					"consumption_sle": consumption_sle,
					"output_receipt_sle": output_sle.name,
					"source_row": child.name,
					"input_quantity": stock_qty,
					"allocation_weight": stock_qty,
					"stock_dimensions": frappe.as_json(stock_dimensions),
				}
			)
		register_production_links("Goods Received Note", grn_name, links)


def _has_base_compatible_production_posting_order(output_sle, consumption_sle):
	"""Keep historical activation within base YRP's causal ordering contract."""
	if (
		not output_sle.posting_datetime
		or not output_sle.creation
		or not consumption_sle.posting_datetime
		or not consumption_sle.creation
	):
		return False
	return (
		get_datetime(output_sle.posting_datetime),
		get_datetime(output_sle.creation),
	) >= (
		get_datetime(consumption_sle.posting_datetime),
		get_datetime(consumption_sle.creation),
	)


def _get_owned_consumption_sle(grn_name, child, dimension_fields):
	"""Return one active outgoing SLE owned by this exact legacy input row."""
	filters = {
		"voucher_type": "Goods Received Note",
		"voucher_no": grn_name,
		"voucher_detail_no": child.name,
		"item": child.item_variant,
		"qty": ["<", 0],
		"is_cancelled": 0,
	}
	if child.consumption_sle:
		filters["name"] = child.consumption_sle
	rows = frappe.get_all(
		"Stock Ledger Entry",
		filters=filters,
		fields=[
			"name",
			"qty",
			"stock_value_difference",
			"posting_datetime",
			"creation",
			*dimension_fields,
		],
		limit_page_length=0,
	)
	return rows[0] if len(rows) == 1 else None


def _resolve_exact_work_order_deliverable(work_order, child, dimension_fields):
	"""Return one immutable Work Order input row, never the first plausible row."""
	from yrp.yrp.doctype.delivery_challan.delivery_challan import _normal_json

	if not work_order or not child.item_variant:
		return None
	rows = frappe.get_all(
		"Work Order Deliverables",
		filters={"parent": work_order, "item_variant": child.item_variant},
		fields=[
			"name",
			"uom",
			"set_combination",
			*dimension_fields,
		],
		order_by="idx, name",
		limit_page_length=0,
	)
	if child.uom:
		rows = [row for row in rows if row.uom == child.uom]
	child_combination = _normal_json(child.set_combination)
	if child_combination not in (None, "", "{}", {}):
		rows = [
			row
			for row in rows
			if _normal_json(row.set_combination) == child_combination
		]
	raw_dimensions = child.stock_dimensions or {}
	if isinstance(raw_dimensions, str):
		try:
			raw_dimensions = frappe.parse_json(raw_dimensions)
		except (TypeError, ValueError):
			return None
	if not isinstance(raw_dimensions, dict):
		return None
	for fieldname in dimension_fields:
		value = child.get(fieldname) or raw_dimensions.get(fieldname)
		if value:
			rows = [row for row in rows if row.get(fieldname) == value]
	return rows[0].name if len(rows) == 1 else None


def get_valuation_lineage_readiness():
	"""Return unresolved historical rows without altering them."""
	if not _contract_available():
		return {"contract_missing": 1}
	total = _count_submitted_grn_rows()
	fully_mapped = _count_submitted_grn_rows_with_condition(
		"COALESCE(d.goods_received_note_item, '') != '' "
		"AND COALESCE(d.work_order_deliverable, '') != '' "
		"AND COALESCE(d.consumption_sle, '') != '' "
		"AND COALESCE(d.output_receipt_sle, '') != ''"
	)
	wholly_unmapped = _count_submitted_grn_rows_with_condition(
		"COALESCE(d.goods_received_note_item, '') = '' "
		"AND COALESCE(d.work_order_deliverable, '') = '' "
		"AND COALESCE(d.consumption_sle, '') = '' "
		"AND COALESCE(d.output_receipt_sle, '') = ''"
	)
	return {
		"submitted_regular_work_order_grn_deliverables": total,
		"fully_mapped_grn_deliverables": fully_mapped,
		"wholly_unmapped_grn_deliverables": wholly_unmapped,
		"partially_mapped_grn_deliverables": total - fully_mapped - wholly_unmapped,
		"ambiguous_multi_output_unmapped_rows": _count_ambiguous_multi_output_rows(),
		"unmapped_grn_deliverables": _count_submitted_grn_rows_missing(
			"goods_received_note_item"
		),
		"grn_deliverables_missing_work_order_deliverable": _count_submitted_grn_rows_missing(
			"work_order_deliverable"
		),
		"grn_deliverables_missing_consumption_sle": _count_submitted_grn_rows_missing(
			"consumption_sle"
		),
		"grn_deliverables_missing_output_sle": _count_submitted_grn_rows_missing(
			"output_receipt_sle"
		),
		"unpaired_active_lot_transfer_sles": frappe.db.count(
			"Stock Ledger Entry",
			filters={
				"voucher_type": "Lot Transfer",
				"is_cancelled": 0,
				"paired_stock_ledger_entry": ["is", "not set"],
			},
		),
		"invalid_goods_received_note_item_links": _count_invalid_grn_item_links(),
		"invalid_consumption_sle_links": _count_invalid_sle_links(
			"consumption_sle", "<"
		),
		"invalid_output_receipt_sle_links": _count_invalid_sle_links(
			"output_receipt_sle", ">"
		),
	}


def _count_submitted_grn_rows_missing(fieldname):
	if fieldname not in {
		"goods_received_note_item",
		"work_order_deliverable",
		"consumption_sle",
		"output_receipt_sle",
	}:
		raise ValueError(fieldname)
	return frappe.db.sql(
		f"""
		SELECT COUNT(*)
		FROM `tabYRP GRN Deliverable` d
		INNER JOIN `tabGoods Received Note` g ON g.name = d.parent
		WHERE d.parenttype = 'Goods Received Note'
		  AND d.parentfield = 'grn_deliverables'
		  AND g.docstatus = 1
		  AND g.against = 'Work Order'
		  AND COALESCE(g.is_return, 0) = 0
		  AND COALESCE(g.is_rework, 0) = 0
		  AND COALESCE(d.`{fieldname}`, '') = ''
		"""
	)[0][0]


def _count_submitted_grn_rows():
	return _count_submitted_grn_rows_with_condition("1=1")


def _count_submitted_grn_rows_with_condition(condition):
	return frappe.db.sql(
		f"""
		SELECT COUNT(*)
		FROM `tabYRP GRN Deliverable` d
		INNER JOIN `tabGoods Received Note` g ON g.name = d.parent
		WHERE d.parenttype = 'Goods Received Note'
		  AND d.parentfield = 'grn_deliverables'
		  AND g.docstatus = 1
		  AND g.against = 'Work Order'
		  AND COALESCE(g.is_return, 0) = 0
		  AND COALESCE(g.is_rework, 0) = 0
		  AND ({condition})
		"""
	)[0][0]


def _count_ambiguous_multi_output_rows():
	return frappe.db.sql(
		"""
		SELECT COUNT(*)
		FROM `tabYRP GRN Deliverable` d
		INNER JOIN `tabGoods Received Note` g ON g.name = d.parent
		INNER JOIN (
			SELECT parent, COUNT(*) AS output_count
			FROM `tabGoods Received Note Item`
			WHERE parenttype = 'Goods Received Note' AND parentfield = 'items'
			GROUP BY parent
		) outputs ON outputs.parent = g.name AND outputs.output_count > 1
		WHERE d.parenttype = 'Goods Received Note'
		  AND d.parentfield = 'grn_deliverables'
		  AND g.docstatus = 1
		  AND g.against = 'Work Order'
		  AND COALESCE(g.is_return, 0) = 0
		  AND COALESCE(g.is_rework, 0) = 0
		  AND COALESCE(d.goods_received_note_item, '') = ''
		"""
	)[0][0]


def _count_invalid_grn_item_links():
	return frappe.db.sql(
		"""
		SELECT COUNT(*)
		FROM `tabYRP GRN Deliverable` d
		INNER JOIN `tabGoods Received Note` g ON g.name = d.parent
		LEFT JOIN `tabGoods Received Note Item` i
		  ON i.name = d.goods_received_note_item
		 AND i.parent = g.name
		 AND i.parenttype = 'Goods Received Note'
		 AND i.parentfield = 'items'
		WHERE d.parenttype = 'Goods Received Note'
		  AND d.parentfield = 'grn_deliverables'
		  AND g.docstatus = 1
		  AND g.against = 'Work Order'
		  AND COALESCE(g.is_return, 0) = 0
		  AND COALESCE(g.is_rework, 0) = 0
		  AND COALESCE(d.goods_received_note_item, '') != ''
		  AND i.name IS NULL
		"""
	)[0][0]


def _count_invalid_sle_links(fieldname, quantity_operator):
	if fieldname not in {"consumption_sle", "output_receipt_sle"}:
		raise ValueError(fieldname)
	if quantity_operator not in {"<", ">"}:
		raise ValueError(quantity_operator)
	return frappe.db.sql(
		f"""
		SELECT COUNT(*)
		FROM `tabYRP GRN Deliverable` d
		INNER JOIN `tabGoods Received Note` g ON g.name = d.parent
		LEFT JOIN `tabStock Ledger Entry` s
		  ON s.name = d.`{fieldname}`
		 AND s.voucher_type = 'Goods Received Note'
		 AND s.voucher_no = g.name
		 AND s.qty {quantity_operator} 0
		 AND s.is_cancelled = 0
		WHERE d.parenttype = 'Goods Received Note'
		  AND d.parentfield = 'grn_deliverables'
		  AND g.docstatus = 1
		  AND g.against = 'Work Order'
		  AND COALESCE(g.is_return, 0) = 0
		  AND COALESCE(g.is_rework, 0) = 0
		  AND COALESCE(d.`{fieldname}`, '') != ''
		  AND s.name IS NULL
		"""
	)[0][0]
