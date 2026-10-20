"""SD YRP Stock Item Balance Difference."""

import frappe
from frappe import _
from yrp.yrp_stock.report.yrp_stock_balance.yrp_stock_balance import get_item_warehouse_map


def execute(filters=None):
	return get_columns(), get_data(frappe._dict(filters or {}))


def merge_balances(bins, ledger, remove_zero=False):
	balances = {}
	for rows, quantity_field in ((bins, "item_bal"), (ledger, "stock_bal")):
		for row in rows:
			key = tuple(row.get(field) for field in ("item", "warehouse", "lot", "received_type"))
			if key not in balances:
				balances[key] = {
					field: row.get(field)
					for field in ("item", "parent_item", "warehouse", "lot", "received_type")
				}
				balances[key].update(item_bal=0.0, stock_bal=0.0)
			balances[key][quantity_field] += float(row["quantity"])
	result = []
	for row in balances.values():
		row["diff_between"] = row["stock_bal"] - row["item_bal"]
		if not remove_zero or row["diff_between"] != 0:
			result.append(row)
	return result


def get_data(filters):
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are required"))
	conditions = []
	for field, column in {
		"item": "iv.name",
		"parent_item": "COALESCE(NULLIF(iv.variant_of, ''), iv.name)",
		"warehouse": "b.warehouse",
		"lot": "b.lot",
		"received_type": "b.received_type",
	}.items():
		if filters.get(field):
			conditions.append(f"AND {column} = %({field})s")
	# Bin is current stock; dates constrain only the ledger side, as in MRP.
	bin_rows = frappe.db.sql(
		f"""
		SELECT b.item_code AS item, COALESCE(NULLIF(iv.variant_of, ''), iv.name) AS parent_item, b.warehouse,
			b.lot, b.received_type, b.actual_qty AS quantity
		FROM `tabYRP Bin` b JOIN `tabItem` iv ON iv.name = b.item_code
		JOIN `tabSupplier` s ON s.name = b.warehouse
		WHERE 1 = 1 {" ".join(conditions)}
		""",
		filters,
		as_dict=True,
	)
	ledger_conditions = " ".join(conditions).replace("b.", "sle.")
	sle = frappe.db.sql(
		f"""
		SELECT sle.item, COALESCE(NULLIF(iv.variant_of, ''), iv.name) AS parent_item, sle.warehouse, sle.lot,
			sle.received_type, sle.posting_date, sle.qty, sle.valuation_rate,
			sle.voucher_type, sle.voucher_no, sle.qty_after_transaction,
			sle.stock_value_difference, sle.stock_value
		FROM `tabYRP Stock Ledger Entry` sle JOIN `tabItem` iv ON iv.name = sle.item
		JOIN `tabItem` template ON template.name = COALESCE(NULLIF(iv.variant_of, ''), iv.name)
		JOIN `tabSupplier` s ON s.name = sle.warehouse
		WHERE sle.docstatus < 2 AND sle.is_cancelled = 0 AND sle.posting_date <= %(to_date)s
		{ledger_conditions}
		ORDER BY TIMESTAMP(sle.posting_date, sle.posting_time), sle.creation, sle.qty
		""",
		filters,
		as_dict=True,
	)
	quantities = get_item_warehouse_map(filters, sle, ["lot", "received_type"])
	ledger_rows = {}
	for row in sle:
		key = (row.item, row.warehouse, row.lot, row.received_type)
		if key not in ledger_rows:
			normalized_key = (row.item, row.warehouse, row.lot or "", row.received_type or "")
			ledger_rows[key] = {
				"item": row.item,
				"parent_item": row.parent_item,
				"warehouse": row.warehouse,
				"lot": row.lot,
				"received_type": row.received_type,
				# MRP retains zero-transaction groups through the supplier name.
				"quantity": quantities.get(normalized_key, {}).get("bal_qty", 0.0),
			}
	return merge_balances(bin_rows, ledger_rows.values(), remove_zero=filters.get("remove_zero_diff") == 1)


def get_columns():

	columns = [
		{
			"label": _("Item"),
			"fieldname": "item",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{
			"label": _("Item Name"),
			"fieldname": "parent_item",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{
			"label": _("Lot"),
			"fieldname": "lot",
			"fieldtype": "Link",
			"options": "SD YRP Lot",
			"width": 100,
		},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 100,
		},
		{
			"fieldname": "received_type",
			"label": "Received Type",
			"fieldtype": "Link",
			"options": "YRP Received Type",
			"width": "80",
		},
	]

	columns.extend(
		[
			{
				"label": _("Stock Difference"),
				"fieldname": "diff_between",
				"fieldtype": "Float",
				"width": 100,
				"convertible": "qty",
			},
			{
				"label": _("Stock Qty"),
				"fieldname": "stock_bal",
				"fieldtype": "Float",
				"width": 100,
				"convertible": "qty",
			},
			{
				"label": _("Item Balance"),
				"fieldname": "item_bal",
				"fieldtype": "Float",
				"width": 100,
				"convertible": "qty",
			},
		]
	)

	return columns
