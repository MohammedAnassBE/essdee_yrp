"""Essdee boundary adjustments for the base YRP rework Work Order popup."""

import frappe
from frappe.utils import cint, flt
from yrp.yrp.doctype.yrp_work_order.yrp_work_order import (
	get_rework_source_rows as get_base_rework_source_rows,
)


QTY_TOLERANCE = 0.0001


@frappe.whitelist()
def get_rework_source_rows(work_order):
	"""Return base rework sources after Essdee direct-clear consumption.

	Essdee checks both source read access and target Work Order create access
	before the base method calculates stock-bearing rows. The base method remains
	authoritative for eligible stock dimensions, inspection outflow, and prior
	rework Work Order reservations.
	Essdee's Rework Details page can also convert stock directly, so its exact
	GRN child consumption must be removed before presenting the popup quantity.
	"""
	doc = frappe.get_doc('YRP Work Order', work_order)
	doc.check_permission("read")
	frappe.has_permission('YRP Work Order', "create", throw=True)
	return _subtract_direct_clearing(get_base_rework_source_rows(work_order))


def _subtract_direct_clearing(rows, direct_rows=None):
	direct_source_names = sorted(
		{
			row.get("source_grn_item")
			for row in rows
			if row.get("source_type") == 'YRP Goods Received Note Item'
			and row.get("source_grn_item")
		}
	)
	if not direct_source_names:
		return rows

	if direct_rows is None:
		direct_rows = frappe.get_all(
			'SD YRP GRN Rework Item Detail',
			filters={"source_grn_item": ["in", direct_source_names]},
			fields=["source_grn_item", "quantity", "reworked", "completed"],
			limit_page_length=0,
		)

	cleared_by_source = {}
	for direct_row in direct_rows:
		source_grn_item = direct_row.get("source_grn_item")
		if not source_grn_item:
			continue
		cleared_qty = (
			flt(direct_row.get("quantity"))
			if cint(direct_row.get("completed"))
			else flt(direct_row.get("reworked"))
		)
		cleared_by_source[source_grn_item] = (
			flt(cleared_by_source.get(source_grn_item)) + cleared_qty
		)

	available_rows = []
	for row in rows:
		if row.get("source_type") != 'YRP Goods Received Note Item':
			available_rows.append(row)
			continue
		available_qty = max(
			flt(row.get("available_qty"))
			- flt(cleared_by_source.get(row.get("source_grn_item"))),
			0,
		)
		if available_qty <= QTY_TOLERANCE:
			continue
		row["available_qty"] = available_qty
		available_rows.append(row)
	return available_rows
