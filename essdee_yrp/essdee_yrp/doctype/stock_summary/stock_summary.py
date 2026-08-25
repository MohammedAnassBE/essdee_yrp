# Copyright (c) 2025, Essdee and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, flt, nowdate

from yrp.stock.dimensions import get_dimension_fieldnames
from yrp.yrp_stock.report.stock_balance.stock_balance import execute as stock_balance


ALLOWED_STOCK_ENTRY_PURPOSES = {
	"Material Consumed",
	"Material Issue",
	"Material Receipt",
	"Send to Warehouse",
}


class StockSummary(Document):
	pass


def _parse(value, default=None):
	if isinstance(value, str):
		value = frappe.parse_json(value)
	return value if value is not None else default


def _dimension_values(source: dict) -> dict:
	return {
		fieldname: source.get(fieldname) for fieldname in get_dimension_fieldnames()
	}


def _check_stock_read_permission():
	frappe.has_permission("Stock Ledger Entry", "read", throw=True)


@frappe.whitelist()
def get_stock_summary(
	lot=None,
	item=None,
	item_variant=None,
	warehouse=None,
	received_type=None,
	dimensions=None,
):
	_check_stock_read_permission()
	filters = frappe._dict(
		remove_zero_balance_item=1,
		from_date=add_months(nowdate(), -1),
		to_date=nowdate(),
	)
	if item:
		filters.parent_item = item
	if item_variant:
		filters.item = item_variant
	if warehouse:
		filters.warehouse = warehouse

	dimension_filters = _parse(dimensions, {}) or {}
	if "received_type" in get_dimension_fieldnames() and received_type:
		dimension_filters["received_type"] = received_type
	lots = _parse(lot, []) or []
	lot_names = [row.get("lot") if isinstance(row, dict) else row for row in lots]
	lot_names = [name for name in lot_names if name]
	for fieldname in get_dimension_fieldnames():
		if fieldname != "lot" and dimension_filters.get(fieldname):
			filters[fieldname] = dimension_filters[fieldname]

	if "lot" not in get_dimension_fieldnames() or not lot_names:
		return stock_balance(filters)[1]

	result = []
	for lot_name in lot_names:
		filters.lot = lot_name
		result.extend(stock_balance(filters)[1])
	return result


def _new_stock_entry(purpose: str, locations: dict, rows: list[dict]):
	if purpose not in ALLOWED_STOCK_ENTRY_PURPOSES:
		frappe.throw(_("Unsupported Stock Entry purpose {0}.").format(purpose))
	frappe.has_permission("Stock Entry", "create", throw=True)
	doc = frappe.new_doc("Stock Entry")
	doc.purpose = purpose
	doc.from_warehouse = locations.get("from_warehouse")
	doc.to_warehouse = locations.get("to_warehouse")
	if purpose == "Material Receipt" and not doc.to_warehouse:
		frappe.throw(_("To Warehouse is required."))
	if purpose != "Material Receipt" and not doc.from_warehouse:
		frappe.throw(_("From Warehouse is required."))
	if purpose == "Send to Warehouse" and not doc.to_warehouse:
		frappe.throw(_("To Warehouse is required."))

	detail_meta = frappe.get_meta("Stock Entry Detail")
	for source in rows:
		qty = flt(source.get("qty") or source.get("bal_qty"))
		if qty <= 0:
			frappe.throw(_("Quantity must be greater than zero."))
		values = {
			"item": source.get("item_variant") or source.get("item"),
			"qty": qty,
			"uom": source.get("uom") or source.get("stock_uom"),
			"rate": source.get("val_rate") or source.get("rate") or 0,
		}
		for fieldname, value in _dimension_values(source).items():
			if detail_meta.get_field(fieldname):
				values[fieldname] = value
		doc.append("items", values)
	doc.insert()
	return doc


@frappe.whitelist()
def create_stock_entry(stock_values):
	values = _parse(stock_values, {}) or {}
	doc = _new_stock_entry(
		values.get("purpose"),
		{
			"from_warehouse": values.get("from_warehouse"),
			"to_warehouse": values.get("to_warehouse"),
		},
		[values],
	)
	if values.get("posting_date") or values.get("posting_time"):
		doc.edit_posting_date_and_time = 1
		doc.posting_date = values.get("posting_date") or doc.posting_date
		doc.posting_time = values.get("posting_time") or doc.posting_time
		doc.save()
	return doc.name


@frappe.whitelist()
def create_bulk_stock_entry(locations, selected_items, purpose, submit=False):
	locations = _parse(locations, {}) or {}
	rows = _parse(selected_items, []) or []
	_validate_selected_warehouses(rows, locations, purpose)
	doc = _new_stock_entry(purpose, locations, rows)
	if cint(submit):
		doc.submit()
	return doc.name


def _validate_selected_warehouses(rows, locations, purpose):
	warehouses = {row.get("warehouse") for row in rows if row.get("warehouse")}
	if len(warehouses) > 1:
		frappe.throw(_("Select stock from one Warehouse at a time."))
	expected = (
		locations.get("to_warehouse")
		if purpose == "Material Receipt"
		else locations.get("from_warehouse")
	)
	if warehouses and expected not in warehouses:
		frappe.throw(_("The selected stock does not belong to the chosen Warehouse."))


@frappe.whitelist()
def reduce_stock(selected_items, warehouse):
	rows = _parse(selected_items, []) or []
	_validate_selected_warehouses(rows, {"from_warehouse": warehouse}, "Material Issue")
	frappe.has_permission("Stock Update", "create", throw=True)
	doc = frappe.new_doc("Stock Update")
	doc.warehouse = warehouse
	doc.update_type = "Reduce"
	detail_meta = frappe.get_meta("Stock Update Detail")
	for source in rows:
		values = {
			"item_variant": source.get("item"),
			"uom": source.get("stock_uom"),
			"update_diff_qty": flt(source.get("bal_qty")),
			"available_stock": flt(source.get("bal_qty")),
			"rate": source.get("val_rate") or 0,
		}
		for fieldname, value in _dimension_values(source).items():
			if detail_meta.get_field(fieldname):
				values[fieldname] = value
		doc.append("stock_update_details", values)
	doc.insert()
	return doc.name


@frappe.whitelist()
def stock_reconcile(selected_items, warehouse):
	rows = _parse(selected_items, []) or []
	_validate_selected_warehouses(rows, {"from_warehouse": warehouse}, "Material Issue")
	frappe.has_permission("Stock Reconciliation", "create", throw=True)
	doc = frappe.new_doc("Stock Reconciliation")
	doc.purpose = "Stock Reconciliation"
	doc.default_warehouse = warehouse
	detail_meta = frappe.get_meta("Stock Reconciliation Item")
	for source in rows:
		values = {
			"item": source.get("item"),
			"qty": 0,
			"make_qty_zero": 1,
			"warehouse": warehouse,
			"uom": source.get("stock_uom"),
			"rate": source.get("val_rate") or 0,
		}
		for fieldname, value in _dimension_values(source).items():
			if detail_meta.get_field(fieldname):
				values[fieldname] = value
		doc.append("items", values)
	doc.insert()
	return doc.name


@frappe.whitelist()
def lot_transfer_items(selected_items, transfer_lot):
	rows = _parse(selected_items, []) or []
	warehouses = {row.get("warehouse") for row in rows if row.get("warehouse")}
	if len(warehouses) != 1:
		frappe.throw(_("Select stock from one Warehouse at a time."))
	if not frappe.db.exists("Lot", transfer_lot):
		frappe.throw(_("Target Lot {0} does not exist.").format(transfer_lot))
	frappe.has_permission("Lot Transfer", "create", throw=True)
	doc = frappe.new_doc("Lot Transfer")
	detail_meta = frappe.get_meta("Lot Transfer Item")
	for source in rows:
		if source.get("lot") == transfer_lot:
			frappe.throw(_("Source and target Lot must be different."))
		values = {
			"item": source.get("item"),
			"from_lot": source.get("lot"),
			"to_lot": transfer_lot,
			"warehouse": source.get("warehouse"),
			"uom": source.get("stock_uom"),
			"qty": flt(source.get("bal_qty")),
			"rate": source.get("val_rate") or 0,
		}
		for fieldname, value in _dimension_values(source).items():
			if fieldname != "lot" and detail_meta.get_field(fieldname):
				values[fieldname] = value
		doc.append("items", values)
	doc.insert()
	return doc.name
