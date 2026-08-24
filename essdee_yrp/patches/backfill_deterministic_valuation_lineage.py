"""Backfill only historical valuation links that can be proven exactly.

Multi-output legacy GRNs and historical Work Order-close allocations are left
for explicit operator review; this patch never guesses how value was split.
"""

from collections import defaultdict

import frappe
from frappe.utils import flt


def execute():
	if not _contract_available():
		return
	_pair_lot_transfer_sles()
	_backfill_single_output_grns()
	readiness = get_valuation_lineage_readiness()
	if any(readiness.values()):
		frappe.log_error(
			title="Essdee valuation lineage needs review",
			message=frappe.as_json(readiness, indent=2),
		)


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
	for grn_name in frappe.get_all(
		"Goods Received Note",
		filters={
			"docstatus": 1,
			"against": "Work Order",
			"is_return": 0,
			"is_rework": 0,
		},
		pluck="name",
	):
		outputs = frappe.get_all(
			"Goods Received Note Item",
			filters={"parent": grn_name, "parentfield": "items"},
			fields=["name", "item_variant"],
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
				"qty": [">", 0],
				"is_cancelled": 0,
			},
			pluck="name",
		)
		if len(output_sles) != 1:
			continue

		links = []
		children = frappe.get_all(
			"YRP GRN Deliverable",
			filters={
				"parent": grn_name,
				"parenttype": "Goods Received Note",
				"parentfield": "grn_deliverables",
			},
			fields=["name", "stock_qty", "consumption_sle"],
			order_by="idx",
		)
		for child in children:
			consumption_sle = child.consumption_sle
			if not consumption_sle:
				matches = frappe.get_all(
					"Stock Ledger Entry",
					filters={
						"voucher_type": "Goods Received Note",
						"voucher_no": grn_name,
						"voucher_detail_no": child.name,
						"qty": ["<", 0],
						"is_cancelled": 0,
					},
					fields=[
						"name",
						"qty",
						"stock_value_difference",
						*dimension_fields,
					],
				)
				if len(matches) != 1:
					continue
				consumption = matches[0]
				consumption_sle = consumption.name
			else:
				consumption = frappe.db.get_value(
					"Stock Ledger Entry",
					consumption_sle,
					["qty", "stock_value_difference", *dimension_fields],
					as_dict=True,
				)
			if not consumption or flt(consumption.qty) >= 0:
				continue
			stock_dimensions = {
				fieldname: consumption.get(fieldname)
				for fieldname in dimension_fields
			}
			material_value = abs(flt(consumption.stock_value_difference))
			stock_qty = flt(child.stock_qty) or abs(flt(consumption.qty))
			frappe.db.set_value(
				"YRP GRN Deliverable",
				child.name,
				{
					"goods_received_note_item": output.name,
					"received_item_variant": output.item_variant,
					"valuation_rate": material_value / stock_qty if stock_qty else 0,
					"material_value": material_value,
					"consumption_sle": consumption_sle,
					"output_receipt_sle": output_sles[0],
					"stock_dimensions": frappe.as_json(stock_dimensions),
				},
				update_modified=False,
			)
			links.append(
				{
					"consumption_sle": consumption_sle,
					"output_receipt_sle": output_sles[0],
					"source_row": child.name,
					"input_quantity": stock_qty,
					"allocation_weight": stock_qty,
					"stock_dimensions": frappe.as_json(stock_dimensions),
				}
			)
		register_production_links("Goods Received Note", grn_name, links)


@frappe.whitelist()
def get_valuation_lineage_readiness():
	"""Return unresolved historical rows without altering them."""
	if not _contract_available():
		return {"contract_missing": 1}
	return {
		"unmapped_grn_deliverables": _count_submitted_grn_rows_missing(
			"goods_received_note_item"
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
	}


def _count_submitted_grn_rows_missing(fieldname):
	if fieldname not in {
		"goods_received_note_item",
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
