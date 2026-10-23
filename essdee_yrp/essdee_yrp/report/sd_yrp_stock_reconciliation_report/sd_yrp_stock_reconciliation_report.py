"""SD YRP Stock Reconciliation Report."""

import frappe
from frappe import _


def execute(filters=None):
	return get_columns(), get_data(frappe._dict(filters or {}))


def get_data(filters):
	conditions = []
	# The Supplier filter selects the location linked to the transaction's Warehouse.
	for field, column in {
		"supplier": "COALESCE(NULLIF(w.supplier, ''), p.default_warehouse)",
		"lot": "d.lot",
		"item_variant": "d.item",
		"item": "COALESCE(NULLIF(iv.variant_of, ''), iv.name)",
	}.items():
		if filters.get(field):
			conditions.append(f"AND {column} = %({field})s")
	return frappe.db.sql(
		f"""
		WITH selected AS (
			SELECT p.owner, p.creation, p.modified_by, p.modified, p.posting_date,
				p.name AS stock_reconciliation, p.purpose, s.supplier_name,
				COALESCE(NULLIF(iv.variant_of, ''), iv.name) AS item, l.item AS item_variant, l.warehouse AS supplier,
				l.lot, l.qty_after_transaction AS updated_quantity,
				l.stock_queue AS updated_queue, l.valuation_rate AS updated_rate, l.uom,
				l.posting_datetime, d.name AS detail_name,
				ROW_NUMBER() OVER (PARTITION BY d.name ORDER BY l.name) AS detail_rank
			FROM `tabYRP Stock Reconciliation` p
			JOIN `tabYRP Stock Reconciliation Item` d ON d.parent = p.name
			JOIN `tabYRP Stock Ledger Entry` l ON l.voucher_type = 'YRP Stock Reconciliation'
				AND l.voucher_no = p.name AND l.voucher_detail_no = d.name
			LEFT JOIN `tabItem` iv ON iv.name = l.item
			LEFT JOIN `tabWarehouse` w ON w.name = p.default_warehouse
			LEFT JOIN `tabSupplier` s ON s.name = COALESCE(NULLIF(w.supplier, ''), p.default_warehouse)
			WHERE p.docstatus = 1 AND p.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{" ".join(conditions)}
		), ranked AS (
			SELECT selected.*, (
				SELECT h.name FROM `tabYRP Stock Ledger Entry` h
				WHERE h.item = selected.item_variant AND h.warehouse = selected.supplier
					AND h.lot = selected.lot AND h.posting_datetime < selected.posting_datetime
				ORDER BY h.posting_datetime DESC, h.name
				LIMIT 1
			) AS previous_entry
			FROM selected WHERE detail_rank = 1
		)
		SELECT s.owner, s.creation, s.modified_by, s.modified, s.posting_date,
			s.stock_reconciliation, s.purpose, s.supplier, s.supplier_name, s.lot,
			s.item, s.item_variant, COALESCE(p.qty_after_transaction, 0) AS previous_quantity,
			s.updated_quantity, p.stock_queue AS previous_queue, s.updated_queue,
			p.valuation_rate AS previous_rate, s.updated_rate,
			s.updated_quantity - COALESCE(p.qty_after_transaction, 0) AS difference, s.uom
		FROM ranked s LEFT JOIN `tabYRP Stock Ledger Entry` p ON p.name = s.previous_entry
		""",
		filters,
		as_dict=True,
	)


def get_columns():
	return [
		{"fieldname": "owner", "fieldtype": "Link", "options": "User", "label": "Owner"},
		{"fieldname": "creation", "fieldtype": "Datetime", "label": "Creation"},
		{"fieldname": "modified_by", "fieldtype": "Link", "options": "User", "label": "Modified By"},
		{"fieldname": "modified", "fieldtype": "Datetime", "label": "Modified"},
		{
			"fieldname": "stock_reconciliation",
			"fieldtype": "Link",
			"label": "Stock Reconciliation",
			"options": "YRP Stock Reconciliation",
			"width": 200,
		},
		{"fieldname": "purpose", "fieldtype": "Data", "label": "Purpose", "width": 130},
		{"fieldname": "posting_date", "fieldtype": "Date", "label": "Posting Date"},
		{
			"fieldname": "supplier",
			"fieldtype": "Link",
			"label": "Supplier",
			"options": "Supplier",
			"width": 100,
		},
		{"fieldname": "supplier_name", "fieldtype": "Data", "label": "Supplier Name", "width": 200},
		{"fieldname": "lot", "fieldtype": "Link", "label": "Lot", "options": "SD YRP Lot", "width": 100},
		{"fieldname": "item", "fieldtype": "Link", "label": "Item", "options": "Item", "width": 250},
		{
			"fieldname": "item_variant",
			"fieldtype": "Link",
			"label": "Item Variant",
			"options": "Item",
			"width": 250,
		},
		{"fieldname": "previous_quantity", "fieldtype": "Float", "label": "Previous Quantity", "width": 100},
		{"fieldname": "updated_quantity", "fieldtype": "Float", "label": "Updated Quantity", "width": 100},
		{"fieldname": "previous_queue", "fieldtype": "Data", "label": "Previous Queue"},
		{"fieldname": "updated_queue", "fieldtype": "Data", "label": "Updated Queue"},
		{"fieldname": "previous_rate", "fieldtype": "Currency", "label": "Previous Rate"},
		{"fieldname": "updated_rate", "fieldtype": "Currency", "label": "Updated Rate"},
		{"fieldname": "difference", "fieldtype": "Float", "label": "Difference", "width": 100},
		{"fieldname": "uom", "fieldtype": "Link", "label": "UOM", "options": "UOM", "width": 100},
	]
