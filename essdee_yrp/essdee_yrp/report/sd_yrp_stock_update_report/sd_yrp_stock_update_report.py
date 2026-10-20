"""SD YRP Stock Update Report."""

import frappe
from frappe import _


def execute(filters=None):
	return get_columns(), get_data(frappe._dict(filters or {}))


def stock_after(update_type, available_stock, quantity):
	available_stock = available_stock or 0
	quantity = quantity or 0
	return available_stock + quantity if update_type == "Add" else available_stock - quantity


def get_data(filters):
	conditions = []
	# Location controls select Suppliers; warehouse IDs may differ from their supplier IDs.
	fields = {
		"warehouse": "COALESCE(NULLIF(w.supplier, ''), p.warehouse)",
		"lot": "d.lot",
		"item_variant": "d.item_variant",
		"item": "COALESCE(NULLIF(iv.variant_of, ''), iv.name)",
	}
	for field, column in fields.items():
		if filters.get(field):
			conditions.append(f"AND {column} = %({field})s")
	rows = frappe.db.sql(
		f"""
		SELECT p.name AS stock_update, p.update_type, p.warehouse,
			s.supplier_name AS warehouse_name, d.lot, COALESCE(NULLIF(iv.variant_of, ''), iv.name) AS item, d.item_variant,
			COALESCE(d.available_stock, 0) AS available_stock, COALESCE(d.update_diff_qty, 0) AS qty,
			d.uom, d.rate, p.comments
		FROM `tabYRP Stock Update` p
		JOIN `tabYRP Stock Update Detail` d ON d.parent = p.name
		LEFT JOIN `tabItem` iv ON iv.name = d.item_variant
		LEFT JOIN `tabWarehouse` w ON w.name = p.warehouse
		LEFT JOIN `tabSupplier` s ON s.name = COALESCE(NULLIF(w.supplier, ''), p.warehouse)
		WHERE p.docstatus = 1 AND p.posting_date BETWEEN %(from_date)s AND %(to_date)s
		{" ".join(conditions)}
		""",
		filters,
		as_dict=True,
	)
	for row in rows:
		row["stock_after"] = stock_after(row.update_type, row.available_stock, row.qty)
	return rows


def get_columns():
	return [
		{
			"fieldname": "stock_update",
			"fieldtype": "Link",
			"label": "Stock Update",
			"options": "YRP Stock Update",
			"width": 200,
		},
		{"fieldname": "update_type", "fieldtype": "Data", "label": "Update Type", "width": 130},
		{
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"label": "Warehouse",
			"options": "Warehouse",
			"width": 100,
		},
		{"fieldname": "warehouse_name", "fieldtype": "Data", "label": "Warehouse Name", "width": 200},
		{"fieldname": "lot", "fieldtype": "Link", "label": "Lot", "options": "SD YRP Lot", "width": 100},
		{"fieldname": "item", "fieldtype": "Link", "label": "Item", "options": "Item", "width": 250},
		{
			"fieldname": "item_variant",
			"fieldtype": "Link",
			"label": "Item Variant",
			"options": "Item",
			"width": 250,
		},
		{
			"fieldname": "available_stock",
			"fieldtype": "Float",
			"label": "Available Stock (Before)",
			"width": 150,
		},
		{"fieldname": "qty", "fieldtype": "Float", "label": "Quantity", "width": 100},
		{"fieldname": "stock_after", "fieldtype": "Float", "label": "Stock After", "width": 120},
		{"fieldname": "uom", "fieldtype": "Link", "label": "UOM", "options": "UOM", "width": 100},
		{"fieldname": "rate", "fieldtype": "Currency", "label": "Rate", "width": 100},
		{"fieldname": "comments", "fieldtype": "Data", "label": "Comments", "width": 200},
	]
