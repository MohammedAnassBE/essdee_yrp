# Copyright (c) 2023, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe.query_builder import CustomFunction
from frappe.query_builder.functions import Coalesce, Sum

Timestamp = CustomFunction("TIMESTAMP", ["date", "time"])


def execute(filters=None):
	columns, data = [], []
	columns = get_columns()
	data = get_data(filters)
	stock_data = get_stock_data(filters)
	pending_po_data = get_po_qty(filters, 1)
	data = compute(data, stock_data, pending_po_data)
	return columns, data


def get_key(item, lot):
	return tuple([item, lot])


def compute(data, stock_data, pending_po_data):
	il_map = {}
	for d in data:
		group_by_key = get_key(d.item, d.lot)
		if group_by_key not in il_map:
			il_map[group_by_key] = frappe._dict(
				{
					"item": d.item,
					"parent_item": d.parent_item,
					"lot": d.lot,
					"required_qty": d.required_qty,
					"stock_qty": 0.0,
					"po_pending_qty": 0.0,
				}
			)
		else:
			il_map[group_by_key].required_qty += d.required_qty
	for stock in stock_data:
		group_by_key = get_key(stock.item, stock.lot)
		if group_by_key not in il_map:
			il_map[group_by_key] = frappe._dict(
				{
					"item": stock.item,
					"parent_item": stock.parent_item,
					"lot": stock.lot,
					"required_qty": 0.0,
					"stock_qty": stock.qty,
					"po_pending_qty": 0.0,
				}
			)
		else:
			il_map[group_by_key].stock_qty += stock.qty
	for po in pending_po_data:
		group_by_key = get_key(po.item, po.lot)
		if group_by_key not in il_map:
			il_map[group_by_key] = frappe._dict(
				{
					"item": po.item,
					"parent_item": po.parent_item,
					"lot": po.lot,
					"required_qty": 0.0,
					"stock_qty": 0.0,
					"po_pending_qty": po.qty,
				}
			)
		else:
			il_map[group_by_key].po_pending_qty += po.qty
	data = []
	for key in il_map:
		d = {}
		d.update(il_map[key])
		data.append(d)
	return data


def get_columns():
	return [
		{
			"fieldname": "lot",
			"label": "Lot",
			"fieldtype": "Link",
			"options": "SD YRP Lot",
			"width": 200,
		},
		{
			"fieldname": "parent_item",
			"label": "Parent Item",
			"fieldtype": "Link",
			"options": "Item",
			"width": 200,
		},
		{
			"fieldname": "item",
			"label": "Item",
			"fieldtype": "Link",
			"options": "Item",
			"width": 200,
		},
		{
			"fieldname": "required_qty",
			"label": "Required Qty",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"fieldname": "stock_qty",
			"label": "Stock Qty",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"fieldname": "po_pending_qty",
			"label": "PO Pending Qty",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"fieldname": "po_draft_qty",
			"label": "PO Draft Qty",
			"fieldtype": "Float",
			"width": 100,
		},
	]


def get_data(filters):
	bom = frappe.qb.DocType("SD YRP Lot BOM")
	item_variant = frappe.qb.DocType("Item")
	query = (
		frappe.qb.from_(bom)
		.from_(item_variant)
		.select(
			bom.parent.as_("lot"),
			bom.item_name.as_("item"),
			Coalesce(item_variant.variant_of, item_variant.name).as_("parent_item"),
			bom.required_qty,
		)
		.where(bom.item_name == item_variant.name)
	)

	if filters.get("lot"):
		query = query.where(bom.parent == filters.get("lot"))
	if filters.get("item"):
		query = query.where(bom.item_name == filters.get("item"))
	if filters.get("parent_item"):
		query = query.where(
			(item_variant.variant_of == filters.get("parent_item"))
			| ((item_variant.variant_of.isnull()) & (item_variant.name == filters.get("parent_item")))
		)

	return query.run(as_dict=True)


def get_stock_data(filters):
	"""Balance rows at each item/warehouse/lot's latest active posting time."""
	parents = get_parent_items(filters)
	warehouses = dict(frappe.get_all("Warehouse", fields=["name", "warehouse_name"], as_list=True))
	item_filtered = bool(filters.get("item") or filters.get("parent_item"))
	if item_filtered and not parents:
		return []
	entries = get_stock_entries(filters, list(parents) if item_filtered else None)
	return [
		frappe._dict(
			item=item,
			parent_item=parents[item],
			warehouse=warehouse,
			warehouse_name=warehouses[warehouse],
			lot=lot,
			qty=qty,
		)
		for (item, warehouse, lot), qty in get_latest_balances(entries)
		if item in parents and warehouse in warehouses
	]


def get_parent_items(filters):
	item = frappe.qb.DocType("Item")
	query = frappe.qb.from_(item).select(item.name, Coalesce(item.variant_of, item.name))
	if filters.get("item"):
		query = query.where(item.name == filters.get("item"))
	if filters.get("parent_item"):
		query = query.where(
			(item.variant_of == filters.get("parent_item"))
			| ((item.variant_of.isnull()) & (item.name == filters.get("parent_item")))
		)
	return dict(query.run())


def get_stock_entries(filters, items=None):
	"""Stream ledger rows; a GROUP BY over item, warehouse and lot is far slower on the full ledger."""
	sle = frappe.qb.DocType("YRP Stock Ledger Entry")
	query = (
		frappe.qb.from_(sle)
		.select(
			sle.item,
			sle.warehouse,
			sle.lot,
			Timestamp(sle.posting_date, sle.posting_time),
			sle.qty_after_transaction,
			(sle.docstatus < 2) & (sle.is_cancelled == 0),
		)
		.where(sle.item.isnotnull() & sle.warehouse.isnotnull() & sle.lot.isnotnull())
	)
	if filters.get("lot"):
		query = query.where(sle.lot == filters.get("lot"))
	if items is not None:
		query = query.where(sle.item.isin(items))
	with frappe.db.unbuffered_cursor():
		yield from query.run(as_list=True, as_iterator=True)


def get_latest_balances(entries):
	"""Yield every row posted at its bucket's latest active time, cancelled rows included."""
	buckets = {}
	for item, warehouse, lot, posted_at, qty, is_active in entries:
		bucket = buckets.setdefault((item, warehouse, lot), [None, {}])
		if is_active and (bucket[0] is None or posted_at > bucket[0]):
			bucket[0] = posted_at
			bucket[1] = {at: rows for at, rows in bucket[1].items() if at >= posted_at}
		if bucket[0] is None or posted_at >= bucket[0]:
			bucket[1].setdefault(posted_at, []).append(qty)
	for key, (latest_at, candidates) in buckets.items():
		for qty in candidates.get(latest_at, []) if latest_at is not None else []:
			yield key, qty


def get_po_qty(filters, docstatus):
	po = frappe.qb.DocType("Purchase Order")
	po_item = frappe.qb.DocType("Purchase Order Item")
	item_variant = frappe.qb.DocType("Item")

	query = (
		frappe.qb.from_(po)
		.from_(po_item)
		.from_(item_variant)
		.where(
			(po.name == po_item.parent)
			& (po.docstatus == docstatus)
			& (po.is_yrp_managed == 1)
			& (po.open_status == "Open")
			& (po_item.item_code == item_variant.name)
		)
		.groupby(po_item.item_code)
		.groupby(po_item.lot)
		.groupby(item_variant.variant_of)
		.groupby(item_variant.name)
		.select(
			po_item.item_code.as_("item"),
			po_item.lot,
			Coalesce(item_variant.variant_of, item_variant.name).as_("parent_item"),
			Sum(po_item.pending_quantity).as_("qty"),
		)
	)

	if filters.get("lot"):
		query = query.where(po_item.lot == filters.get("lot"))
	if filters.get("item"):
		query = query.where(po_item.item_code == filters.get("item"))
	if filters.get("parent_item"):
		query = query.where(
			(item_variant.variant_of == filters.get("parent_item"))
			| ((item_variant.variant_of.isnull()) & (item_variant.name == filters.get("parent_item")))
		)

	d = query.run(as_dict=True)
	return d
