"""Closed Work Order receipt route owned by the Essdee sewing workflow."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.utils import cint, cstr, flt, getdate, nowtime, today

from yrp.stock.dimensions import apply_dimension_defaults
from yrp.stock.save_stock_items import group_items_for_ui, ungroup_items_from_ui
from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import (
	_apply_dimension_values_to_rows,
	_get_production_group_dimensions,
)
from yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note import (
	_pending_receivable_rows,
)


def is_closed_sewing_grn(doc) -> bool:
	return bool(
		doc.get("from_closed_wo_sewing_details")
		and doc.against == 'YRP Work Order'
		and doc.against_id
	)


def validate_closed_sewing_grn(doc) -> None:
	"""Validate the narrow exception before base GRN lifecycle code continues."""

	work_order = _get_closed_sewing_work_order(doc.against_id)
	if doc.get("delivery_challan"):
		frappe.throw(_("Closed Sewing Work Order GRN cannot use a Delivery Challan."))
	if doc.get("is_return"):
		frappe.throw(_("Closed Sewing Work Order GRN cannot be a return."))
	if doc.supplier and doc.supplier != work_order.supplier:
		frappe.throw(_("GRN Supplier must match the closed Work Order unit."))


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_closed_sewing_work_orders(
	doctype,
	txt,
	searchfield,
	start,
	page_len,
	filters,
):
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	supplier = cstr(filters.get("supplier")).strip()
	if not supplier:
		return []
	if not frappe.has_permission('YRP Work Order', "read"):
		return []

	return frappe.db.sql(
		f"""
		SELECT DISTINCT
			wo.name,
			wo.lot,
			wo.item,
			wo.process_name
		FROM `tabYRP Work Order` wo
		INNER JOIN `tabSD YRP Sewing Plan` sp ON sp.work_order = wo.name
		WHERE wo.docstatus = 1
			AND wo.open_status = 'Close'
			AND wo.supplier = %(supplier)s
			AND (
				wo.name LIKE %(txt)s
				OR wo.lot LIKE %(txt)s
				OR wo.item LIKE %(txt)s
				OR wo.process_name LIKE %(txt)s
			)
			{get_match_cond('YRP Work Order')}
		ORDER BY wo.modified DESC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"supplier": supplier,
			"txt": f"%{cstr(txt).strip()}%",
			"start": int(start or 0),
			"page_len": int(page_len or 20),
		},
		as_list=True,
	)


@frappe.whitelist()
def get_closed_work_order_grn_details(work_order: str, supplier: str) -> dict:
	doc = _get_closed_sewing_work_order(work_order, supplier)
	rows = _closed_work_order_receivable_rows(doc)
	return {
		"work_order": doc.name,
		"item": doc.item,
		"lot": doc.lot,
		"process": doc.process_name,
		"supplier": doc.supplier,
		"supplier_address": doc.supplier_address,
		"delivery_location": doc.delivery_location,
		"delivery_address": doc.delivery_address,
		"has_pending_items": bool(rows),
		"items": rows,
		"item_details": group_items_for_ui(rows, 'YRP Goods Received Note'),
	}


@frappe.whitelist()
def create_closed_work_order_grn(
	work_order: str,
	supplier: str,
	values,
	item_details,
) -> dict:
	frappe.has_permission('YRP Goods Received Note', "create", throw=True)
	frappe.has_permission('YRP Goods Received Note', "submit", throw=True)

	# Hold the source row lock through insert+submit, preventing two requests from
	# consuming the same pending quantity.
	doc = _get_closed_sewing_work_order(work_order, supplier, for_update=True)
	values = _json_object(values)
	rows = ungroup_items_from_ui(item_details, 'YRP Goods Received Note')
	rows = _normalize_selected_rows(doc, rows)

	posting_date = getdate(values.get("posting_date") or today())
	delivery_date = getdate(values.get("delivery_date") or posting_date)
	if delivery_date > posting_date:
		frappe.throw(_("Delivery Date cannot be after Posting Date."))

	supplier_document_no = cstr(values.get("supplier_document_no")).strip()
	vehicle_no = cstr(values.get("vehicle_no")).strip()
	if not supplier_document_no:
		frappe.throw(_("Supplier Document Number is required."))
	if not vehicle_no:
		frappe.throw(_("Vehicle Number is required."))

	grn = frappe.new_doc('YRP Goods Received Note')
	grn.update(
		{
			"naming_series": "GRN-",
			"against": 'YRP Work Order',
			"against_id": doc.name,
			"supplier": doc.supplier,
			"supplier_address": doc.supplier_address,
			"delivery_location": doc.delivery_location,
			"delivery_address": doc.delivery_address,
			"delivery_date": delivery_date,
			"posting_date": posting_date,
			"posting_time": values.get("posting_time") or nowtime(),
			"edit_posting_date_and_time": cint(
				values.get("edit_posting_date_and_time")
			),
			"supplier_document_no": supplier_document_no,
			"supplier_document_date": values.get("supplier_document_date")
			or delivery_date,
			"vehicle_no": vehicle_no,
			"dc_no": cstr(values.get("dc_no")).strip(),
			"comments": cstr(values.get("comments")).strip(),
			"lot": doc.lot,
			"process_name": doc.process_name,
			"is_internal_unit": doc.is_internal_unit,
			"is_rework": doc.is_rework,
			"includes_packing": doc.includes_packing,
			"from_closed_wo_sewing_details": 1,
			"items": rows,
		}
	)
	grn.insert()
	grn.submit()
	return {"name": grn.name, "docstatus": grn.docstatus}


def _get_closed_sewing_work_order(
	work_order: str,
	supplier: str | None = None,
	*,
	for_update: bool = False,
):
	work_order = cstr(work_order).strip()
	supplier = cstr(supplier).strip()
	if not work_order:
		frappe.throw(_("Work Order is required."))

	doc = frappe.get_doc('YRP Work Order', work_order, for_update=for_update)
	doc.check_permission("read")
	if doc.docstatus != 1 or doc.open_status != "Close":
		frappe.throw(
			_("Work Order {0} is not a submitted, closed Work Order.").format(
				frappe.bold(work_order)
			)
		)
	if supplier and doc.supplier != supplier:
		frappe.throw(
			_("Work Order {0} does not belong to unit {1}.").format(
				frappe.bold(work_order), frappe.bold(supplier)
			)
		)
	if not frappe.db.exists('SD YRP Sewing Plan', {"work_order": doc.name}):
		frappe.throw(
			_("Work Order {0} is not linked to Sewing Details.").format(
				frappe.bold(work_order)
			)
		)
	return doc


def _closed_work_order_receivable_rows(work_order) -> list[dict]:
	rows = _pending_receivable_rows(work_order)
	dimensions = _get_production_group_dimensions(work_order)
	_apply_dimension_values_to_rows(rows, dimensions)
	apply_dimension_defaults(rows)
	for row in rows:
		# Unlike the ordinary GRN form, this recovery route must require an
		# intentional entry. Opening the dialog must never pre-receive every
		# pending piece from a closed Work Order.
		row["quantity"] = 0
		if work_order.lot:
			row["lot"] = work_order.lot
	return rows


def _normalize_selected_rows(work_order, rows: list[dict]) -> list[dict]:
	"""Return server-authored GRN rows carrying only user-selected quantities.

	The browser is allowed to choose a quantity and one of the generated
	Received Type buckets. Item, Work Order reference, UOM, rate, combination,
	Lot, and every other Stock Dimension are rebuilt from the locked Work Order.
	"""

	if not rows:
		frappe.throw(_("Enter a received quantity for at least one item."))

	trusted_rows = _closed_work_order_receivable_rows(work_order)
	trusted = {
		(row.get("ref_docname"), cstr(row.get("received_type")).strip()): row
		for row in trusted_rows
	}
	selected = {}
	for row in rows:
		quantity = flt(row.get("quantity"))
		if quantity <= 0:
			frappe.throw(_("Received Quantity must be greater than zero."))
		key = (
			cstr(row.get("ref_docname")).strip(),
			cstr(row.get("received_type")).strip(),
		)
		template = trusted.get(key)
		if not template or row.get("ref_doctype") != 'YRP Work Order Receivables':
			frappe.throw(_("A selected item does not belong to this Work Order."))
		selected[key] = flt(selected.get(key)) + quantity

	normalized = []
	for key, quantity in selected.items():
		row = dict(trusted[key])
		row["quantity"] = quantity
		normalized.append(row)
	return normalized


def _json_object(value) -> dict:
	if isinstance(value, str):
		value = frappe.parse_json(value or "{}")
	if not isinstance(value, dict):
		frappe.throw(_("Invalid GRN values."))
	return value
