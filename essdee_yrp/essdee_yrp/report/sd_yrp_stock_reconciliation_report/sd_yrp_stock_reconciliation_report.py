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
		), history AS (
			SELECT h.item, h.warehouse, h.lot, h.posting_datetime,
				h.qty_after_transaction, h.stock_queue, h.valuation_rate,
				ROW_NUMBER() OVER (
					PARTITION BY h.item, h.warehouse, h.lot, h.posting_datetime ORDER BY h.name
				) AS time_rank
			FROM `tabYRP Stock Ledger Entry` h
			JOIN (
				SELECT item_variant, supplier, lot, MAX(posting_datetime) AS last_datetime
				FROM selected WHERE detail_rank = 1 GROUP BY item_variant, supplier, lot
			) keys_used ON keys_used.item_variant = h.item
				AND keys_used.supplier = h.warehouse AND keys_used.lot = h.lot
				AND h.posting_datetime <= keys_used.last_datetime
		), previous AS (
			SELECT item, warehouse, lot, posting_datetime,
				LAG(qty_after_transaction) OVER stock_history AS previous_quantity,
				LAG(stock_queue) OVER stock_history AS previous_queue,
				LAG(valuation_rate) OVER stock_history AS previous_rate
			FROM history WHERE time_rank = 1
			WINDOW stock_history AS (PARTITION BY item, warehouse, lot ORDER BY posting_datetime)
		)
		SELECT s.owner, s.creation, s.modified_by, s.modified, s.posting_date,
			s.stock_reconciliation, s.purpose, s.supplier, s.supplier_name, s.lot,
			s.item, s.item_variant, COALESCE(p.previous_quantity, 0) AS previous_quantity,
			s.updated_quantity, p.previous_queue, s.updated_queue, p.previous_rate,
			s.updated_rate, s.updated_quantity - COALESCE(p.previous_quantity, 0) AS difference, s.uom
		FROM selected s LEFT JOIN previous p ON p.item = s.item_variant
			AND p.warehouse = s.supplier AND p.lot = s.lot AND p.posting_datetime = s.posting_datetime
		WHERE s.detail_rank = 1
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
