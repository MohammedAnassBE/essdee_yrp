# Copyright (c) 2024, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	columns, data = get_columns(filters), get_data(filters)
	return columns, data


def get_columns(filters):
	return [
		{
			"label": _("Item"),
			"fieldname": "item",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{
			"label": _("Item Variant"),
			"fieldname": "item_variant",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 120,
		},
		{
			"label": _("Warehouse Name"),
			"fieldname": "warehouse_name",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Lot"),
			"fieldname": "lot",
			"fieldtype": "Link",
			"options": "SD YRP Lot",
			"width": 150,
		},
		{
			"fieldname": "received_type",
			"fieldtype": "Link",
			"label": _("Received Type"),
			"options": "YRP Received Type",
			"width": 80,
		},
		{
			"label": _("Actual Qty"),
			"fieldname": "actual_qty",
			"fieldtype": "Float",
			"width": 140,
		},
		{
			"label": _("Reserved Qty"),
			"fieldname": "reserved_qty",
			"fieldtype": "Float",
			"width": 140,
		},
		{
			"label": _("Balance Qty"),
			"fieldname": "bal_qty",
			"fieldtype": "Float",
			"width": 140,
		},
		{
			"label": _("UOM"),
			"fieldname": "stock_uom",
			"fieldtype": "Data",
			"width": 140,
		},
	]


def get_data(filters):
	filters = frappe._dict(filters or {})
	conditions = []
	values = {}
	for field, column in {
		"warehouse": "b.warehouse",
		"lot": "b.lot",
		"item_variant": "b.item_code",
		"item": "COALESCE(NULLIF(i.variant_of, ''), i.name)",
		"received_type": "b.received_type",
	}.items():
		if filters.get(field):
			conditions.append(f"{column} = %({field})s")
			values[field] = filters[field]
	if filters.get("remove_zero_balance_item"):
		conditions.append("b.actual_qty != 0")
	where = " AND " + " AND ".join(conditions) if conditions else ""
	return frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(i.variant_of, ''), i.name) AS item, b.item_code AS item_variant,
			b.warehouse, s.supplier_name AS warehouse_name, b.lot, b.received_type,
			b.actual_qty, b.stock_uom, b.reserved_qty,
			(b.actual_qty - b.reserved_qty) AS bal_qty
		FROM `tabYRP Bin` b
		JOIN `tabItem` i ON i.name = b.item_code
		JOIN `tabSupplier` s ON s.name = b.warehouse
		WHERE 1=1 {where}
		""",
		values,
		as_dict=True,
	)
