"""SD YRP Stock Entry Report."""

import frappe
from frappe import _


def execute(filters=None):
	return get_columns(), get_data(frappe._dict(filters or {}))


def get_data(filters):
	conditions = []
	# Location controls select Suppliers; warehouse IDs may differ from their supplier IDs.
	fields = {
		"from_warehouse": "COALESCE(NULLIF(fwh.supplier, ''), p.from_warehouse)",
		"to_warehouse": "COALESCE(NULLIF(twh.supplier, ''), p.to_warehouse)",
		"lot": "d.lot",
		"item_variant": "d.item",
		"item": "COALESCE(NULLIF(iv.variant_of, ''), iv.name)",
	}
	for field, column in fields.items():
		if filters.get(field):
			conditions.append(f"AND {column} = %({field})s")
	return frappe.db.sql(
		f"""
		SELECT p.name AS stock_entry, p.purpose, p.from_warehouse,
			fw.supplier_name AS from_warehouse_name, p.to_warehouse,
			tw.supplier_name AS to_warehouse_name, d.lot, COALESCE(NULLIF(iv.variant_of, ''), iv.name) AS item,
			d.item AS item_variant, d.qty, d.uom, d.stock_uom_rate AS valuation_rate, d.remarks
		FROM `tabYRP Stock Entry` p
		JOIN `tabYRP Stock Entry Detail` d ON d.parent = p.name
		LEFT JOIN `tabItem` iv ON iv.name = d.item
		LEFT JOIN `tabWarehouse` fwh ON fwh.name = p.from_warehouse
		LEFT JOIN `tabWarehouse` twh ON twh.name = p.to_warehouse
		LEFT JOIN `tabSupplier` fw ON fw.name = COALESCE(NULLIF(fwh.supplier, ''), p.from_warehouse)
		LEFT JOIN `tabSupplier` tw ON tw.name = COALESCE(NULLIF(twh.supplier, ''), p.to_warehouse)
		WHERE p.docstatus = 1 AND p.posting_date BETWEEN %(from_date)s AND %(to_date)s
		{" ".join(conditions)}
		""",
		filters,
		as_dict=True,
	)


def get_columns():
	return [
		{
			"fieldname": "stock_entry",
			"fieldtype": "Link",
			"label": "Stock Entry",
			"options": "YRP Stock Entry",
			"width": 200,
		},
		{"fieldname": "purpose", "fieldtype": "Data", "label": "Purpose", "width": 130},
		{
			"fieldname": "from_warehouse",
			"fieldtype": "Link",
			"label": "From Warehouse",
			"options": "Warehouse",
			"width": 100,
		},
		{
			"fieldname": "from_warehouse_name",
			"fieldtype": "Data",
			"label": "From Warehouse Name",
			"width": 200,
		},
		{
			"fieldname": "to_warehouse",
			"fieldtype": "Link",
			"label": "To Location",
			"options": "Warehouse",
			"width": 100,
		},
		{"fieldname": "to_warehouse_name", "fieldtype": "Data", "label": "To Location Name", "width": 200},
		{"fieldname": "lot", "fieldtype": "Link", "label": "Lot", "options": "SD YRP Lot", "width": 100},
		{"fieldname": "item", "fieldtype": "Link", "label": "Item", "options": "Item", "width": 250},
		{
			"fieldname": "item_variant",
			"fieldtype": "Link",
			"label": "Item Variant",
			"options": "Item",
			"width": 250,
		},
		{"fieldname": "qty", "fieldtype": "Float", "label": "Quantity", "width": 100},
		{"fieldname": "uom", "fieldtype": "Link", "label": "UOM", "options": "UOM", "width": 100},
		{"fieldname": "valuation_rate", "fieldtype": "Currency", "label": "Valuation Rate", "width": 100},
		{"fieldname": "remarks", "fieldtype": "Data", "label": "Remarks", "width": 200},
	]
